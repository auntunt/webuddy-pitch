"""Load the sample client tickets into a running platform.

    python3 examples/client-tickets/load.py --project OA [--base http://127.0.0.1:8790]

Each ticket is filed as the client who raised it, with the channel noted in the body.
The reading notes (what to ask first, scope, traps) stay in 甲方工单素材.md and are not posted.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote


def post(base, path, body, user):
    h = {"X-TMH": "1", "Content-Type": "application/json", "X-TMH-User": quote(user)}
    if os.environ.get("TMH_TOKEN"):
        h["X-TMH-Token"] = os.environ["TMH_TOKEN"]
    req = urllib.request.Request(base + path, method="POST", headers=h, data=json.dumps(body).encode())
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", required=True, help="项目代号，例如 OA")
    ap.add_argument("--base", default="http://127.0.0.1:8790")
    ap.add_argument("--file", default=str(Path(__file__).with_name("tickets.json")))
    a = ap.parse_args()
    tickets = json.loads(Path(a.file).read_text(encoding="utf-8"))
    for t in tickets:
        body = "%s\n\n——\n来源：%s · %s" % (t["body"], t["channel"], t["reporter"])
        try:
            r = post(a.base, "/api/tickets", {"project": a.project, "title": t["title"], "body": body, "type": t["type"],
                                              "priority": t["priority"], "labels": t["labels"] + ["素材:" + t["id"]]}, t["reporter"])
        except urllib.error.HTTPError as e:
            sys.exit("%s 导入失败：%s" % (t["id"], e.read().decode("utf-8", "replace")))
        except urllib.error.URLError as e:
            sys.exit("连不上平台 %s（%s），先启动平台再导入" % (a.base, e.reason))
        print("%s → %s %s" % (t["id"], r["key"], t["title"]))
    print("共导入 %d 张" % len(tickets))


if __name__ == "__main__":
    main()
