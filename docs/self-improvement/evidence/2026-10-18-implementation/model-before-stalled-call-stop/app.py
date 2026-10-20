"""Local web starter: persistent items, accessible forms and a health endpoint."""
import hmac
import html
import json
import re
import secrets
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


MAX_FORM_BYTES = 8192
# Oversized edits may only recover input, never save; keep the total read bounded.
MAX_EDIT_RECOVERY_BYTES = 64 * 1024


def make_server(address, database, prefix="", title="我的应用"):
    database = str(database)
    prefix = "/" + prefix.strip("/") if prefix.strip("/") else ""
    token = secrets.token_urlsafe(32)
    edit_script = '''<script id="edit-script">
(() => {
    const form = document.getElementById('edit-form');
    if (!form || !window.fetch) return;
    const title = form.elements.namedItem('title');
    const csrf = form.elements.namedItem('csrf');
    const save = form.querySelector('button[type="submit"]');
    const message = document.getElementById('edit-error');
    let saving = false;
    form.noValidate = true;
    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (saving) return;
        let count = 0;
        for (const character of title.value) {
            if (++count > 200) break;
        }
        if (!title.value.trim() || count > 200) {
            message.textContent = '事项应为 1 到 200 字，不能全为空白；输入已保留，请修改后重试。';
            title.focus();
            return;
        }
        const body = new URLSearchParams(new FormData(form)).toString();
        // URLSearchParams produces ASCII, so its length is the encoded byte count.
        if (body.length > 8192) {
            message.textContent = '表单内容过大，尚未提交；输入已保留，请修改后重试。';
            return;
        }
        saving = true;
        save.disabled = true;
        title.readOnly = true;
        message.textContent = '正在保存…';
        try {
            const response = await fetch(form.action, {
                method: 'POST', body,
                headers: {'Accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded'},
                credentials: 'same-origin'
            });
            const result = await response.json();
            if (response.ok && typeof result.redirect === 'string') {
                message.textContent = '已保存，正在返回…';
                window.location.assign(result.redirect);
                return;
            }
            if (typeof result.csrf === 'string') csrf.value = result.csrf;
            message.textContent = result.error || '暂时无法保存；输入已保留，请重试。';
        } catch (error) {
            message.textContent = '无法确认保存结果；输入已保留，请重试。';
        }
        saving = false;
        save.disabled = false;
        title.readOnly = false;
    });
    document.getElementById('edit-result-region').hidden = true;
})();
</script>'''
    style = ('body{font:16px system-ui;color:#20242b;background:#f5f6f8;margin:0}main{max-width:720px;margin:64px auto;padding:24px}'
             'h1{font-size:36px;letter-spacing:-1px}p{color:#596270;line-height:1.7}form{display:flex;flex-wrap:wrap;gap:12px;align-items:center}'
             'input,textarea{font:inherit;padding:12px;border:1px solid #b8c0cc;border-radius:6px;flex:1;min-width:0;box-sizing:border-box}'
             'textarea{width:100%;max-width:100%;resize:vertical}.edit-form{display:block}.edit-form label,.edit-form textarea{display:block;margin-bottom:12px}'
             'iframe{display:block;width:100%;height:360px;box-sizing:border-box;border:1px solid #b8c0cc;border-radius:6px}'
             '.edit-result main{margin:0;padding:12px}.edit-result h1{font-size:20px;letter-spacing:normal}'
             'button{font:inherit;background:#20242b;color:white;border:0;border-radius:6px;padding:12px;cursor:pointer}'
             'button:focus-visible,input:focus-visible,textarea:focus-visible,a:focus-visible{outline:3px solid #386bd6;outline-offset:3px}'
             'ul{padding:0;list-style:none}li{padding:16px 0;border-bottom:1px solid #d9dee5}li span{flex:1;min-width:0;overflow-wrap:anywhere}'
             'small{color:#697383}@media(max-width:600px){main{margin:16px auto}h1{font-size:28px}}')
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY, title TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0)")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, body, kind="text/html; charset=utf-8"):
            body = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if self.close_connection:
                self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

        def page(self, status, heading, content):
            return self.send(status, '<!doctype html><html lang="zh-CN"' + (' class="edit-result"' if self.inline_edit_result() else '') + '><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                             '<title>' + html.escape(heading) + '</title><style>' + style + '</style><main><h1>' + html.escape(heading) + '</h1>' + content + '</main></html>')

        def inline_edit_result(self):
            url = urlsplit(self.path)
            return self.command == 'POST' and url.query == 'result=1' and self.edit_id(url.path) is not None

        def edit_result(self, status, message):
            back = '<a target="_parent" href="' + html.escape(prefix + '/', quote=True) + '">' + ('返回应用' if status == 200 else '取消编辑并返回应用') + '</a>'
            return self.page(status, '保存结果', '<p role="' + ('status' if status == 200 else 'alert') + '">' + html.escape(message) + '</p>' + back)

        def edit_id(self, path):
            match = re.fullmatch(re.escape(prefix) + r'/items/([0-9]{1,19})/edit', path)
            if match and 0 < int(match[1]) <= 2**63 - 1:
                return int(match[1])

        def edit_page(self, item_id, raw_title, status=200, error=""):
            if self.command == 'POST' and self.headers.get('Accept') == 'application/json':
                return self.send(status, json.dumps({'error': error, 'csrf': token}, ensure_ascii=False), 'application/json; charset=utf-8')
            inline = self.inline_edit_result()
            # The extra leading newline is consumed by HTML; preserve the user's first newline.
            value = html.escape(raw_title, quote=True).replace('\r', '&#13;')
            # Only the outer form edits input; native posts replace the result frame.
            field = '<label for="edit-title">事项标题</label><textarea id="edit-title" name="title" rows="2" required aria-describedby="edit-error"' + (' readonly' if inline or status == 404 else '') + '>\n' + value + '</textarea>'
            message = '<p id="edit-error" role="alert" aria-live="polite">' + html.escape(error) + '</p>'
            if inline and status != 404:
                message += '<p>修改标题请使用上方原编辑框；下方仅可重试本次提交的内容。</p>'
            back = '<a' + (' target="_parent"' if inline else '') + ' href="' + html.escape(prefix + '/', quote=True) + '">' + ('取消编辑并返回应用' if inline else '返回应用' if error else '取消') + '</a>'
            if status == 404:
                content = message + '<div class="edit-form">' + field + back + '</div>'
            else:
                action = html.escape(prefix + '/items/%d/edit?result=1' % item_id, quote=True)
                content = message + '<form id="edit-form" class="edit-form" method="post" target="' + ('_self' if inline else 'edit-result') + '" action="' + action + '"><input type="hidden" name="csrf" value="' + token + '">' + field + '<button type="submit">' + ('重试保存' if error else '保存') + '</button> ' + back + '</form>'
                if not inline:
                    content += '<section id="edit-result-region" role="region" aria-label="保存结果"><p>保存结果显示在下方；编辑框中的内容会保留，可修改后再次保存。</p><iframe id="edit-result" name="edit-result" title="保存结果" srcdoc="&lt;p&gt;尚未提交，保存后会在这里显示结果。&lt;/p&gt;"></iframe></section>' + edit_script
            return self.page(status, '编辑事项', content)

        def unavailable(self):
            if urlsplit(self.path).path == prefix + "/health":
                return self.send(503, '{"status":"unavailable"}', "application/json")
            retry = ""
            if self.pending_save is not None:
                operation, item_id, raw_title = self.pending_save
                if operation == 'edit':
                    return self.edit_page(item_id, raw_title, 503, '数据暂时不可用，请稍后重试；此次编辑尚未保存。')
                retry = '<form method="post" action="' + html.escape(prefix + '/items', quote=True) + '"><input type="hidden" name="csrf" value="' + token + '"><label for="retry-title">未保存的内容</label><input id="retry-title" name="title" maxlength="200" value="' + html.escape(raw_title, quote=True) + '"><button>重试保存</button></form>'
            return self.page(503, '数据暂时不可用', '<p>请稍后重试，当前操作未完成。</p>' + retry + '<p><a href="' + html.escape(prefix + '/', quote=True) + '">返回应用</a></p>')

        def do_GET(self):
            self.pending_save = None
            try:
                return self.get()
            except sqlite3.Error:
                return self.unavailable()

        def get(self):
            path = urlsplit(self.path).path
            if path == prefix + "/health":
                with sqlite3.connect(database) as db:
                    db.execute("SELECT id FROM items LIMIT 1").fetchall()
                return self.send(200, '{"status":"ok"}', "application/json")
            item_id = self.edit_id(path)
            if item_id is not None:
                with sqlite3.connect(database) as db:
                    row = db.execute('SELECT title FROM items WHERE id=?', (item_id,)).fetchone()
                if row is None:
                    return self.edit_page(item_id, '', 404, '事项不存在')
                return self.edit_page(item_id, row[0])
            if path != prefix + "/":
                return self.send(404, "页面不存在")
            with sqlite3.connect(database) as db:
                rows = db.execute("SELECT id,title,done FROM items ORDER BY id DESC").fetchall()
            esc = html.escape
            items = "".join('<li><form method="post" action="%s/items/%d"><input type="hidden" name="csrf" value="%s"><span>%s</span><button name="done" value="%d">%s</button><a href="%s/items/%d/edit">编辑</a></form></li>' %
                            (esc(prefix, quote=True), i, token, esc(text), 0 if done else 1, "重新打开" if done else "完成", esc(prefix, quote=True), i) for i, text, done in rows)
            self.send(200, '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                      '<title>' + esc(title) + '</title><style>' + style + '</style><main>'
                      '<small>WEB 应用起点</small><h1>' + esc(title) + '</h1><p>应用已经可以运行。先添加一项内容，刷新后仍会保留。具体业务能力将在交付流程中实现和验证。</p>'
                      '<form method="post" action="' + prefix + '/items"><input type="hidden" name="csrf" value="' + token + '"><label for="title">新事项</label><input id="title" name="title" required maxlength="200" placeholder="写下一件要做的事"><button>添加</button></form>'
                      '<ul>' + (items or '<li>还没有内容，添加第一项开始。</li>') + '</ul><p><small>仅用于本地开发；正式发布前需要按实际业务配置身份验证、数据保护和部署环境。</small></p></main></html>')

        def do_POST(self):
            self.pending_save = None
            try:
                return self.post()
            except sqlite3.Error:
                return self.unavailable()

        def post(self):
            path = urlsplit(self.path).path
            item_id = self.edit_id(path)
            try:
                n = int(self.headers.get("Content-Length", "0"))
                read_limit = MAX_EDIT_RECOVERY_BYTES if item_id is not None else MAX_FORM_BYTES
                if not 0 < n <= read_limit:
                    self.close_connection = True
                    if n > read_limit and item_id is not None:
                        error = '表单内容超过 64 KiB 的错误恢复上限，未修改事项。服务端未读取正文，请返回原编辑页面修改后重试。'
                        if self.headers.get('Accept') == 'application/json':
                            return self.edit_page(item_id, '', 413, error)
                        if self.inline_edit_result():
                            return self.edit_result(413, '提交内容过大，未保存。完整输入仍在上方编辑框，请修改为 1 到 200 字后再次保存。')
                        back = html.escape(prefix + '/items/%d/edit' % item_id, quote=True)
                        return self.page(413, '表单内容过大', '<p>' + error + '</p><a href="' + back + '">返回编辑页</a> <a href="' + html.escape(prefix + '/', quote=True) + '">返回应用</a>')
                    return self.send(413, "表单内容过大或为空")
                values = parse_qs(self.rfile.read(n).decode("utf-8"), keep_blank_values=True)
            except (ValueError, UnicodeError):
                return self.send(400, "表单格式错误")
            raw_title = values.get("title", [""])[0]
            if not hmac.compare_digest(values.get("csrf", [""])[0].encode("utf-8"), token.encode("ascii")):
                if item_id is not None:
                    return self.edit_page(item_id, raw_title, 403, '页面已过期，请确认内容后重试')
                return self.send(403, "页面已过期，请刷新后重试")
            if item_id is not None:
                self.pending_save = ('edit', item_id, raw_title)
            elif path.startswith(prefix + '/items/') and path.endswith('/edit'):
                return self.send(404, '事项不存在')
            elif path == prefix + '/items':
                self.pending_save = ('create', None, raw_title)
            with sqlite3.connect(database) as db:
                if item_id is not None:
                    if db.execute('SELECT id FROM items WHERE id=?', (item_id,)).fetchone() is None:
                        return self.edit_page(item_id, raw_title, 404, '事项不存在')
                    if not raw_title.strip() or len(raw_title) > 200:
                        return self.edit_page(item_id, raw_title, 400, '事项应为 1 到 200 字，不能全为空白')
                    if n > MAX_FORM_BYTES:
                        return self.edit_page(item_id, raw_title, 413, '表单内容超过 8192 字节，未修改事项；输入已保留，请重试。')
                    cur = db.execute('UPDATE items SET title=? WHERE id=?', (raw_title, item_id))
                    if not cur.rowcount:
                        return self.edit_page(item_id, raw_title, 404, '事项不存在')
                elif path == prefix + "/items":
                    text = values.get("title", [""])[0].strip()
                    if not text or len(text) > 200:
                        return self.send(400, "事项应为 1 到 200 字")
                    db.execute("INSERT INTO items(title) VALUES(?)", (text,))
                elif path.startswith(prefix + "/items/") and path.rsplit("/", 1)[1].isdigit():
                    done = values.get("done", [""])[0]
                    if done not in ("0", "1"):
                        return self.send(400, "状态不正确")
                    cur = db.execute("UPDATE items SET done=? WHERE id=?", (int(done), int(path.rsplit("/", 1)[1])))
                    if not cur.rowcount:
                        return self.send(404, "事项不存在")
                else:
                    return self.send(404, "页面不存在")
            if item_id is not None and self.headers.get('Accept') == 'application/json':
                return self.send(200, json.dumps({'redirect': prefix + '/'}), 'application/json; charset=utf-8')
            if item_id is not None and self.inline_edit_result():
                return self.edit_result(200, '已保存本次提交的标题。继续编辑可再次保存，或返回应用查看。')
            self.send_response(303)
            self.send_header("Location", prefix + "/")
            self.send_header("Content-Length", "0")
            self.end_headers()

    return ThreadingHTTPServer(address, Handler)


if __name__ == "__main__":
    project = json.loads(Path("project.json").read_text(encoding="utf-8"))
    server = make_server(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8000),
                         sys.argv[3] if len(sys.argv) > 3 else "app.db",
                         sys.argv[2] if len(sys.argv) > 2 else "", project["name"])
    print("Ready on http://127.0.0.1:%d" % server.server_address[1], flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
