"""autoflow.json is one file several pages write (the test machine, the comparison group): change only the keys
you mean to, under one lock, and replace the file whole so a crash never leaves half of it."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

_LOCK = threading.Lock()


def update_autoflow(data_dir: Path, changes: dict, drop: tuple = ()) -> dict:
    f = Path(data_dir) / "autoflow.json"
    with _LOCK:
        try:
            conf = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        except ValueError:
            raise ValueError("%s 不是有效的 JSON，先修好它再改设置" % f)
        if not isinstance(conf, dict):
            raise ValueError("%s 的内容要是一个 {…} 对象" % f)
        conf.update(changes)
        for k in drop:
            conf.pop(k, None)
        tmp = f.with_name(".autoflow.json.%d.tmp" % os.getpid())
        tmp.write_text(json.dumps(conf, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, f)
    return conf
