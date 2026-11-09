"""`serve`: start the HTTP server for one data directory."""
from __future__ import annotations

import errno
import os
import re
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from ..app import Platform
from .handler import make_handler
from .preview import make_preview_handler


def serve(data_dir: Path, host: str = "127.0.0.1", port: int = 8790, user: str = "", project: Path | None = None,
          key: str = "", open_browser: bool = False, brand: str = "", preview_port: int = 0) -> int:
    tenant_mode = (Path(data_dir).expanduser() / "control" / "access.db").is_file()
    from .. import login
    if tenant_mode and login.registration_enabled():
        # LAN accounts share the registry, but do not opt into tenant workers.
        from ..tenancy import Registry
        reg = Registry(data_dir)
        try:
            tenants = reg.q("SELECT id,path,status,runtime FROM tenants")
            if len(tenants) != 1 or dict(tenants[0]) != {
                "id": "default", "path": str(Path(data_dir).expanduser().resolve()),
                "status": "active", "runtime": "legacy",
            }:
                raise ValueError("局域网注册模式仅用于独立实例，不能接管已有多租户或隔离配置")
        finally:
            reg.close()
        tenant_mode = False
    if tenant_mode:
        from ..tenant_gateway import serve as serve_tenants
        if project or preview_port:
            print("多租户模式请从管理入口登记项目；预览需独立隔离环境")
        return serve_tenants(data_dir, host, port)
    P = Platform(data_dir, user, brand)
    token = os.environ.get("TMH_TOKEN", "")
    if host not in ("127.0.0.1", "localhost", "::1") and not token:
        print("对外开放（--host %s）必须先设置环境变量 TMH_TOKEN 作为访问令牌" % host)
        return 2
    if project:
        project = Path(project).resolve()
        known = [p for p in P.store.projects() if Path(p["root"]) == project]
        if not known:
            k = key or re.sub(r"[^A-Za-z0-9]", "", project.name)[:6].upper() or "PRJ"
            if not k[0].isalpha():
                k = "P" + k[:5]
            name = project.name
            try:
                from ... import config as cfgmod
                name = cfgmod.load(project).get("project", {}).get("name") or name
            except Exception:  # noqa: BLE001
                pass
            P.store.add_project(k, name, str(project))
            print("已添加项目 %s（%s）" % (k, project))
    try:
        httpd = ThreadingHTTPServer((host, port), make_handler(P, token))
    except OSError as e:
        if e.errno not in (errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", -1)):
            raise
        print("端口 %d 已被占用：平台可能已经在另一个窗口运行。关掉那个窗口再启动，或用 --port 换一个端口。" % port)
        return 1
    httpd.daemon_threads = True
    preview_port = preview_port or int(os.environ.get("TMH_PREVIEW_PORT") or 0)
    if preview_port:  # previews on an address of their own: another origin, so the browser keeps them apart
        try:
            pv = ThreadingHTTPServer((host, preview_port), make_preview_handler(P))
        except OSError as e:
            print("预览端口 %d 用不了（%s），预览改为在平台地址下隔离运行" % (preview_port, e))
        else:
            pv.daemon_threads = True
            P.preview_port = preview_port
            threading.Thread(target=pv.serve_forever, daemon=True).start()
            print("预览版本地址：%s" % (os.environ.get("TMH_PREVIEW_BASE") or "端口 %d" % preview_port))
    from .. import reform
    reform.reconcile(P)
    from .. import handwork
    handwork.heartbeat(P)  # 我来写: wb/* branches pushed by people are picked up every minute
    from .. import intake
    intake.watch(P)  # a reading left behind by a restart is settled by the rules, a client's answer with it
    url = "http://%s:%d/" % ("127.0.0.1" if host in ("0.0.0.0", "::") else host, port)
    print("%s 已启动：%s%s" % (P.brand, url, "?token=<TMH_TOKEN>" if token else ""))
    print("数据目录：%s　按 Ctrl+C 停止" % P.data_dir)
    if open_browser:
        import webbrowser
        webbrowser.open(url + ("?token=" + token if token else ""))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()
    return 0
