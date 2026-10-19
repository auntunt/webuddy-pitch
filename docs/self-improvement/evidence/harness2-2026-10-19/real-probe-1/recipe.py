"""BOOTV2 item workflow probe. Run in a supervised process, never import app code.

This is a trusted-workspace integration test, not an OS security sandbox. The
application gets its own process, fresh database and immutable Git snapshot.
All observations and application output are retained without clipping.
"""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
import http.client
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
from urllib.parse import urlencode, urlsplit


RECIPE = "bootv2-items-search-v1"
CHECKS = {
    "A1": "中文、Unicode 大小写及特殊字符按字面搜索",
    "A2": "全部/未完成/已完成与关键词组合筛选、空结果及清除",
    "A3": "固定路径、刷新、编辑取消及保存保持筛选条件",
    "A4": "原编号/状态、200字换行、失败重试和重启后持久保存",
}


def require(condition, message):
    """Business checks must run even under PYTHONOPTIMIZE / python -O."""
    if not condition:
        raise AssertionError(message)


class Page(HTMLParser):
    def __init__(self, body):
        super().__init__(convert_charrefs=True)
        self.ids, self.forms, self.links, self.textareas = [], [], [], []
        self.csrf, self.current_textarea = "", None
        self.feed(body)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self.forms.append(a)
            m = re.search(r"/items/(\d+)$", urlsplit(a.get("action", "")).path)
            if m:
                self.ids.append(int(m[1]))
        if tag == "input" and a.get("name") == "csrf":
            self.csrf = a.get("value", "")
        if tag == "a":
            self.links.append(a.get("href", ""))
        if tag == "textarea":
            self.current_textarea = ""

    def handle_data(self, text):
        if self.current_textarea is not None:
            self.current_textarea += text

    def handle_endtag(self, tag):
        if tag == "textarea" and self.current_textarea is not None:
            # HTML removes the first newline immediately after a textarea tag.
            self.textareas.append(self.current_textarea.removeprefix("\n"))
            self.current_textarea = None


class Probe:
    def __init__(self, root, output):
        self.root, self.output = Path(root), Path(output)
        self.database = self.output / "items.db"
        self.prefix = "/probe/" + RECIPE
        self.process = None
        self.stream = None
        self.observations = []
        self.results = []
        self.output.mkdir(parents=True, exist_ok=True)

    def start(self):
        log = self.output / ("application-%d.log" % time.time_ns())
        self.stream = log.open("xb")
        self.process = subprocess.Popen(
            [sys.executable, "-u", str(self.root / "app.py"), "0", self.prefix, str(self.database)],
            cwd=self.root, stdout=self.stream, stderr=subprocess.STDOUT)
        # Let the OS write every byte directly to the retained log. A pipe
        # reader in this process would lose buffered tails if both processes
        # were killed on timeout. Readiness is a separate observation only.
        deadline = time.monotonic() + 10
        with log.open("rb") as observation:
            pending = b""
            while time.monotonic() < deadline:
                pending += observation.read()
                m = re.search(rb"Ready on http://127\.0\.0\.1:(\d+)\s", pending)
                if m:
                    self.port = int(m[1])
                    status, _, body = self.request("GET", "/health")
                    require(status == 200 and json.loads(body)["status"] == "ok", "health check did not pass")
                    return
                if self.process.poll() is not None:
                    raise RuntimeError("application exited before readiness")
                # Keep enough overlap to recognize a split readiness line;
                # the entire original output remains in the binary log.
                pending = pending[-128:]
                time.sleep(.02)
        raise TimeoutError("application was not ready within 10 seconds")

    def stop(self):
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
            self.process = None
        if self.stream:
            self.stream.close()
            self.stream = None

    def request(self, method, path, values=None):
        body = urlencode(values).encode() if values is not None else None
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            connection.request(method, self.prefix + path, body,
                               {"Content-Type": "application/x-www-form-urlencoded"} if body else {})
            response = connection.getresponse()
            raw = response.read()
            headers = dict(response.getheaders())
            text = raw.decode("utf-8", "strict")
            row = {"method": method, "path": self.prefix + path, "form": values,
                   "status": response.status, "headers": headers, "body": text}
            self.observations.append(row)
            return response.status, headers, text
        finally:
            connection.close()

    def rows(self):
        with sqlite3.connect(self.database) as db:
            return db.execute("SELECT id,title,done FROM items ORDER BY id").fetchall()

    def listing(self, query="", expected=None):
        status, _, body = self.request("GET", "/" + query)
        require(status == 200, "listing HTTP status: %s" % status)
        page = Page(body)
        if expected is not None:
            require(sorted(page.ids) == sorted(expected), "expected item IDs %r, got %r" % (expected, page.ids))
        return page, body

    def seed(self):
        self.titles = ["中文 项目 Straße 100%", "中文 项目 STRASSE under_score", "other 'quoted' <b>text</b>"]
        page, _ = self.listing()
        require(page.csrf, "missing CSRF field")
        for title in self.titles:
            status, _, _ = self.request("POST", "/items", {"csrf": page.csrf, "title": title})
            require(status == 303, "create did not redirect")
        rows = self.rows()
        require(len(rows) == 3 and [r[1] for r in rows] == self.titles, "created values were not persisted")
        self.ids = [r[0] for r in rows]
        status, _, _ = self.request("POST", "/items/%d" % self.ids[1], {"csrf": page.csrf, "done": "1"})
        require(status == 303 and [r[2] for r in self.rows()] == [0, 1, 0], "state change not persisted")

    def a1(self):
        for word, ids in [("中文", self.ids[:2]), ("strasse", self.ids[:2]), ("%", self.ids[:1]),
                          ("_", self.ids[1:2]), ("'quoted'", self.ids[2:]), ("no-match", [])]:
            self.listing("?" + urlencode({"q": word}), ids)

    def a2(self):
        for query, ids in [("?status=all", self.ids), ("?status=pending", [self.ids[0], self.ids[2]]),
                           ("?status=completed", [self.ids[1]]),
                           ("?q=strasse&status=completed", [self.ids[1]]), ("?q=absent&status=pending", [])]:
            page, body = self.listing(query, ids)
            require(self.prefix + "/" in page.links, "clear filter link is missing")
            if not ids:
                require('role="status"' in body, "empty result is not announced")
        self.listing("", self.ids)

    def a3(self):
        query = "?q=strasse&status=completed"
        page, _ = self.listing(query, [self.ids[1]])
        self.listing(query, [self.ids[1]])  # same URL after refresh
        path = "/items/%d/edit" % self.ids[1]
        edit = self.prefix + path + query
        require(edit in page.links, "edit link lost filter context")
        status, _, body = self.request("GET", path + query)
        editor = Page(body)
        require(status == 200 and self.prefix + "/" + query in editor.links, "cancel lost context")
        invalid = " "
        status, _, body = self.request("POST", path + query, {"csrf": editor.csrf, "title": invalid})
        retry = Page(body)
        require(status == 400 and retry.textareas == [invalid], "invalid edit was not retained")
        require(any(f.get("action") == edit for f in retry.forms), "retry lost filters")
        before = self.rows()
        status, headers, _ = self.request("POST", path + query, {"csrf": retry.csrf, "title": before[1][1]})
        require(status == 303 and headers.get("Location") == self.prefix + "/" + query, "save lost filters")
        require(self.rows() == before, "save changed item identity/state unexpectedly")

    def a4(self):
        item = self.ids[1]
        path = "/items/%d/edit" % item
        _, _, body = self.request("GET", path)
        csrf = Page(body).csrf
        title = "汉" * 99 + "\r\n" + "字" * 100
        before = self.rows()
        status, _, _ = self.request("POST", path, {"csrf": csrf, "title": title})
        require(status == 303, "200 logical characters containing CRLF were rejected")
        require(self.rows()[1] == (item, title, before[1][2]), "edit lost content/identity/state")
        pending = "完整保留 <script> & '重试'\n第二行"
        saved = self.database.with_suffix(".saved")
        self.database.rename(saved)
        self.database.mkdir()
        try:
            status, _, body = self.request("POST", path, {"csrf": csrf, "title": pending})
            error_page = Page(body)
            require(status == 503 and error_page.textareas == [pending], "failure did not preserve the entire edit")
            require("<script>" not in body, "pending edit was not escaped")
        finally:
            self.database.rmdir()
            saved.rename(self.database)
        status, _, _ = self.request("POST", path, {"csrf": error_page.csrf, "title": pending})
        require(status == 303 and self.rows()[1] == (item, pending, before[1][2]), "retry changed identity/state")
        expected = self.rows()
        require(expected[0] == before[0] and expected[2] == before[2], "unrelated rows changed")
        status, _, _ = self.request("POST", path, {"csrf": "invalid", "title": "must not save"})
        require(status == 403 and self.rows() == expected, "invalid CSRF saved data")
        self.stop()
        self.start()
        require(self.rows() == expected, "restart lost stored data")
        self.listing("", self.ids)

    def run(self):
        setup_error = ""
        try:
            self.start()
            self.seed()
            for key, check in zip(CHECKS, (self.a1, self.a2, self.a3, self.a4)):
                begin = len(self.observations)
                try:
                    check()
                    result, error = "pass", ""
                except AssertionError as exc:
                    result, error = "fail", str(exc)
                except Exception as exc:
                    result, error = "unknown", "%s: %s" % (type(exc).__name__, exc)
                self.results.append({"id": key, "status": result, "error": error,
                                     "observation_start": begin, "observation_end": len(self.observations)})
        except Exception as exc:
            setup_error = "%s: %s" % (type(exc).__name__, exc)
        finally:
            try:
                self.stop()
            except Exception as exc:
                setup_error += " cleanup: " + str(exc)
            done = {r["id"] for r in self.results}
            self.results += [{"id": key, "status": "unknown", "error": setup_error or "not executed"}
                             for key in CHECKS if key not in done]
            report = {"schema": 1, "recipe": RECIPE, "results": self.results, "setup_error": setup_error,
                      "observations": self.observations, "database": str(self.database)}
            (self.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps({"recipe": RECIPE, "results": self.results, "setup_error": setup_error}, ensure_ascii=False))
        # 0 proves the probe protocol completed, not that application behavior passed.
        return 0 if not setup_error else 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    return Probe(args.root, args.output).run()


if __name__ == "__main__":
    raise SystemExit(main())
