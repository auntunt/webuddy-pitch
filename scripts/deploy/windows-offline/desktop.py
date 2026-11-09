"""Desktop entry point for the standard installer; owns only its managed server."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
STATE = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Webuddy'


def configuration():
    # Embedded Python's ._pth deliberately omits the script directory.
    import importlib.util
    spec = importlib.util.spec_from_file_location('bundle_launcher', ROOT / 'launcher.py')
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    path = launcher.config_path(ROOT, os.environ)
    return launcher.configuration(ROOT, str(path) if path.exists() else '')


def stop():
    STATE.mkdir(parents=True, exist_ok=True)
    receipt = STATE / 'desktop.json'
    if not receipt.exists():
        return
    from tmh.platform.windows_process import is_running
    info = json.loads(receipt.read_text(encoding='utf-8'))
    if not is_running(info['pid']):
        return
    _, _, data, _, _ = configuration()
    for path in data.rglob('platform.db') if data.exists() else []:
        with sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='runs'").fetchone():
                if db.execute("SELECT count(*) FROM runs WHERE status IN ('running','queued')").fetchone()[0]:
                    raise RuntimeError('还有任务正在执行。请先在工作台停止或等待完成，再退出或升级。')
    (STATE / 'desktop.stop').touch()
    for _ in range(100):
        if not is_running(info['pid']):
            return
        time.sleep(.2)
    raise RuntimeError('程序尚未退出。请稍后重试，保留现有运行。')


def serve():
    from tmh.platform.process_control import run_process
    from tmh.platform.windows_process import receipt_lock
    STATE.mkdir(parents=True, exist_ok=True)
    with receipt_lock(STATE / 'desktop-owner'):
        marker = STATE / 'desktop.stop'
        marker.unlink(missing_ok=True)
        receipt = STATE / 'desktop.json'
        receipt.write_text(json.dumps({'pid': os.getpid(), 'root': str(ROOT)}), encoding='utf-8')
        cancel = threading.Event()
        def watch():
            while not cancel.wait(.2):
                if marker.exists():
                    cancel.set()
        threading.Thread(target=watch, daemon=True).start()
        try:
            result = run_process([str(ROOT / 'runtime/python/python.exe'), '-B', str(ROOT / 'launcher.py'), 'start'],
                                 cwd=str(ROOT), cancel_event=cancel, timeout=None,
                                 on_output=lambda text: print(text, end='', flush=True))
            return result.returncode
        finally:
            cancel.set()
            receipt.unlink(missing_ok=True)
            marker.unlink(missing_ok=True)


def start():
    from tmh.platform.windows_process import is_running, receipt_lock
    STATE.mkdir(parents=True, exist_ok=True)
    with receipt_lock(STATE / 'desktop-start'):
        _, _, _, _, port = configuration()
        receipt = STATE / 'desktop.json'
        owned = json.loads(receipt.read_text(encoding='utf-8')) if receipt.exists() else None
        if not owned or not is_running(owned['pid']):
            with socket.socket() as sock:
                if sock.connect_ex(('127.0.0.1', port)) == 0:
                    raise RuntimeError('端口 %s 已被占用。请先退出原程序，或在配置中选择其他端口。' % port)
            log = (STATE / 'desktop.log').open('ab')
            try:
                proc = subprocess.Popen([str(ROOT / 'runtime/python/pythonw.exe'), '-B', str(ROOT / 'desktop.py'), 'serve'],
                                        cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                        creationflags=subprocess.CREATE_NO_WINDOW)
            finally:
                log.close()
        else:
            proc = None
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(120):
            if proc and proc.poll() is not None:
                raise RuntimeError('启动失败。请查看 %s' % (STATE / 'desktop.log'))
            try:
                with opener.open('http://127.0.0.1:%s/login' % port, timeout=1) as response:
                    if response.status == 200:
                        _, env, _, _, _ = configuration()
                        url = 'http://127.0.0.1:%s/next/' % port
                        if env.get('TMH_TOKEN'):
                            url += '?' + urllib.parse.urlencode({'token': env['TMH_TOKEN']})
                        webbrowser.open(url)
                        return
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(.5)
        raise RuntimeError('启动仍未就绪。请查看 %s' % (STATE / 'desktop.log'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('start', 'serve', 'stop', 'cursor-login', 'initialize'))
    parser.add_argument('--lan', action='store_true')
    args = parser.parse_args()
    if args.action == 'initialize':
        STATE.mkdir(parents=True, exist_ok=True)
        path = Path(os.environ.get('WEBUDDY_CONFIG') or STATE / 'config.json')
        if not path.exists():
            path.write_text(json.dumps({'host': '0.0.0.0' if args.lan else '127.0.0.1', 'port': 8790}), encoding='utf-8')
        elif args.lan:
            value = json.loads(path.read_text(encoding='utf-8-sig'))
            value['host'] = '0.0.0.0'
            path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    elif args.action == 'cursor-login':
        from tmh.platform.executor_setup import _cursor_candidates
        found = _cursor_candidates()
        if not found:
            raise RuntimeError('尚未安装 Cursor CLI。请重新运行安装程序，勾选安装 Cursor CLI。')
        subprocess.Popen([found[0], 'login'], creationflags=subprocess.CREATE_NEW_CONSOLE)
    elif args.action == 'serve':
        return serve()
    elif args.action == 'stop':
        stop()
    else:
        start()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        ctypes.windll.user32.MessageBoxW(None, str(exc), 'Webuddy', 0x10)
        raise SystemExit(1)
