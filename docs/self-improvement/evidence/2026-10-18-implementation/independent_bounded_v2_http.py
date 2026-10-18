"""Independent bounded-body strict-decoding v2 acceptance for the generated title-edit implementation.

Extends the preserved first-version suite with a 1000-character recovery case,
64 KiB boundary checks, and header-only rejection of larger declared requests.

Only disposable databases and ephemeral loopback servers are mutated. The app source is
loaded without bytecode writes; its hash is checked again after all cases. No platform,
preview, or project database is used. This does not claim browser visual verification.
"""
import argparse
import hashlib
import http.client
import json
import sqlite3
import sys
import tempfile
import threading
import traceback
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode

sys.dont_write_bytecode = True


class Document(HTMLParser):
    def __init__(self, markup):
        super().__init__(convert_charrefs=True)
        self.forms, self.fields, self.links, self.tags, self.labels = [], [], [], [], []
        self.current_form = self.area = None
        self.feed(markup)
        for field in self.fields:
            if field["tag"] == "textarea" and field["value"].startswith("\n"):
                field["value"] = field["value"][1:]

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.tags.append((tag, attributes))
        if tag == "form":
            self.current_form = {"action": attributes.get("action"), "fields": [], "method": attributes.get("method", "get")}
            self.forms.append(self.current_form)
        elif tag in ("input", "textarea"):
            field = {**attributes, "tag": tag, "value": attributes.get("value", "")}
            self.fields.append(field)
            if self.current_form is not None:
                self.current_form["fields"].append(field)
            if tag == "textarea":
                self.area = field
        elif tag == "a":
            self.links.append(attributes.get("href"))
        elif tag == "label":
            self.labels.append(attributes.get("for"))

    def handle_endtag(self, tag):
        if tag == "form":
            self.current_form = None
        elif tag == "textarea":
            self.area = None

    def handle_data(self, data):
        if self.area is not None:
            self.area["value"] += data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-path", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    app_path = Path(args.app_path).resolve()
    source = app_path.read_bytes()
    report = {"app_path": str(app_path), "started_utc": datetime.now(timezone.utc).isoformat(),
              "source_sha256_before": hashlib.sha256(source).hexdigest(), "checks": [], "requests": [],
              "data_scope": "TemporaryDirectory only; existing project/platform data untouched",
              "verification": "Independent HTTP and SQLite; no browser/layout claim"}

    def check(label, condition, detail=None):
        report["checks"].append({"check": label, "passed": bool(condition), "detail": detail})
        if not condition:
            raise AssertionError(label + ": " + repr(detail))

    namespace = {"__name__": "independently_checked_app", "__file__": str(app_path)}
    exec(compile(source, str(app_path), "exec"), namespace)
    server = thread = None

    def stop():
        nonlocal server, thread
        if server is not None:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            server = thread = None

    try:
        with tempfile.TemporaryDirectory(prefix="webuddy-independent-edit-") as directory:
            for index, prefix in enumerate(("", "/demo", "/pv/BOOTV2/independent")):
                database = Path(directory) / ("case-%d.sqlite3" % index)
                label = prefix or "<root>"

                def start():
                    nonlocal server, thread
                    server = namespace["make_server"](("127.0.0.1", 0), database, prefix, "独立验收")
                    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
                    thread.start()

                def call(method, path, fields=None):
                    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=8)
                    try:
                        connection.request(method, path, urlencode(fields) if fields is not None else None,
                                           {"Content-Type": "application/x-www-form-urlencoded"})
                        response = connection.getresponse()
                        status, headers, body = response.status, dict(response.getheaders()), response.read().decode("utf-8")
                        report["requests"].append({"prefix": prefix, "method": method, "path": path, "status": status,
                                                   "location": headers.get("Location"), "response_bytes": len(body.encode("utf-8"))})
                        return status, headers, body
                    finally:
                        connection.close()

                def raw_call(path, payload=None, declared=None):
                    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=2)
                    try:
                        connection.putrequest("POST", path)
                        connection.putheader("Content-Type", "application/x-www-form-urlencoded")
                        connection.putheader("Content-Length", str(declared if declared is not None else len(payload)))
                        connection.endheaders(payload)
                        response = connection.getresponse()
                        status, headers, body = response.status, dict(response.getheaders()), response.read().decode("utf-8")
                        report["requests"].append({"prefix": prefix, "method": "POST", "path": path, "status": status,
                                                   "declared_bytes": declared if declared is not None else len(payload),
                                                   "sent_body_bytes": len(payload) if payload else 0,
                                                   "connection": headers.get("Connection"), "response_bytes": len(body.encode("utf-8"))})
                        check(label + " exact response Content-Length", int(headers["Content-Length"]) == len(body.encode("utf-8")))
                        return status, headers, body
                    finally:
                        connection.close()

                def rows():
                    connection = sqlite3.connect(database)
                    try:
                        return connection.execute("SELECT id,title,done FROM items ORDER BY id").fetchall()
                    finally:
                        connection.close()

                def token():
                    status, _, body = call("GET", prefix + "/")
                    check(label + " home is reachable", status == 200, status)
                    return next(field["value"] for field in Document(body).fields if field.get("name") == "csrf")

                def safe(markup, location):
                    doc = Document(markup)
                    check(label + " safe markup " + location,
                          all(tag not in ("script", "iframe", "object") and
                              not any(name.lower().startswith("on") for name in attributes)
                              for tag, attributes in doc.tags))
                    return doc

                def editable_form(markup, action, expected, location):
                    doc = safe(markup, location)
                    forms = [form for form in doc.forms if form["action"] == action]
                    check(label + " correct form target " + location, len(forms) == 1, [f["action"] for f in doc.forms])
                    form = forms[0]
                    fields = {field["name"]: field["value"] for field in form["fields"] if "name" in field}
                    title = next(field for field in form["fields"] if field.get("name") == "title")
                    check(label + " intact input " + location, fields.get("title") == expected,
                          {"expected": expected, "actual": fields.get("title")})
                    check(label + " accessible form " + location,
                          form["method"].lower() == "post" and title.get("id") in doc.labels and prefix + "/" in doc.links)
                    return form["action"], fields

                start()
                csrf = token()
                for title in ("待编辑", "不能改变的另一项"):
                    status, headers, _ = call("POST", prefix + "/items", {"csrf": csrf, "title": title})
                    check(label + " create baseline", status == 303 and headers.get("Location") == prefix + "/", status)
                call("POST", prefix + "/items/1", {"csrf": csrf, "done": "1"})
                check(label + " baseline records", rows() == [(1, "待编辑", 1), (2, "不能改变的另一项", 0)], rows())
                edit_path = prefix + "/items/1/edit"
                home = Document(call("GET", prefix + "/")[2])
                check(label + " edit entry for each row", all(prefix + "/items/%d/edit" % i in home.links for i in (1, 2)))
                status, _, body = call("GET", edit_path)
                check(label + " edit page", status == 200, status)
                action, fields = editable_form(body, edit_path, "待编辑", "edit page")
                payload = " \n审计 \"<script>alert(1)</script>\" & '原文'\r末尾 "
                fields["title"] = payload
                status, headers, _ = call("POST", action, fields)
                check(label + " edit redirects within prefix", status == 303 and headers.get("Location") == prefix + "/", headers.get("Location"))
                expected = [(1, payload, 1), (2, "不能改变的另一项", 0)]
                check(label + " edit changes only target title", rows() == expected, rows())
                safe(call("GET", prefix + "/")[2], "home after hostile text")
                editable_form(call("GET", edit_path)[2], edit_path, payload, "hostile text round trip")
                stop()
                start()
                check(label + " same database survives instance restart", rows() == expected, rows())
                csrf = token()
                editable_form(call("GET", edit_path)[2], edit_path, payload, "after restart")

                for bad in ("", " \t\n", "字" * 201):
                    status, _, body = call("POST", edit_path, {"csrf": csrf, "title": bad})
                    check(label + " invalid input gets 400", status == 400, {"length": len(bad), "status": status})
                    editable_form(body, edit_path, bad, "invalid length " + str(len(bad)))
                    check(label + " invalid input leaves database unchanged", rows() == expected, rows())
                long_title = "字" * 1000
                encoded = urlencode([("title", long_title), ("csrf", csrf)]).encode("ascii")
                check(label + " 1000 CJK chars exceed save cap but fit recovery cap", 8192 < len(encoded) < 65536, len(encoded))
                status, _, body = raw_call(edit_path, encoded)
                check(label + " 1000 CJK chars receive recoverable 413", status == 413, status)
                correction_action, correction_fields = editable_form(body, edit_path, long_title, "1000-character recovery")
                check(label + " long invalid title cannot write", rows() == expected)
                correction_fields["title"] = "修正长输入后仍只更新原事项"
                status, _, _ = call("POST", correction_action, correction_fields)
                check(label + " long-input correction updates original ID/state", status == 303 and rows() == [(1, correction_fields["title"], 1), expected[1]], rows())
                call("POST", edit_path, {"csrf": csrf, "title": payload})
                check(label + " restore independent baseline after correction", rows() == expected)
                for size in (65535, 65536):
                    for recovery_csrf, expected_status in ((csrf, 413), ("非法令牌", 403)):
                        submitted = [("title", long_title), ("csrf", recovery_csrf), ("padding", "")]
                        base_size = len(urlencode(submitted).encode("ascii"))
                        submitted[-1] = ("padding", "x" * (size - base_size))
                        encoded = urlencode(submitted).encode("ascii")
                        check(label + " exact recovery boundary input", len(encoded) == size, len(encoded))
                        status, _, body = raw_call(edit_path, encoded)
                        check(label + " recovery boundary rejects save with CSRF priority", status == expected_status, {"bytes": size, "status": status})
                        editable_form(body, edit_path, long_title, "recovery boundary " + str(size))
                        check(label + " recovery boundary cannot modify records", rows() == expected)
                for declared in (65537, 2**40):
                    status, headers, body = raw_call(edit_path, declared=declared)
                    check(label + " header-only oversized request rejected immediately", status == 413 and headers.get("Connection") == "close", {"declared": declared, "status": status})
                    doc = safe(body, "hard rejection")
                    check(label + " hard rejection says body not received", "正文未接收" in body and "编辑未保存" in body and edit_path in doc.links)
                    check(label + " hard rejection never fabricates recovered input", not any(field.get("name") == "title" for field in doc.fields))
                    check(label + " header-only rejection cannot write", rows() == expected)

                for encoded_title in (b"%FF", b"%E4%B8"):
                    for padding in (0, 9000):
                        encoded = b"title=" + encoded_title + b"&csrf=" + csrf.encode("ascii") + b"&padding=" + b"x" * padding
                        status, _, body = raw_call(edit_path, encoded)
                        check(label + " invalid percent-encoded UTF-8 rejected", status == 400 and "表单格式错误" in body,
                              {"title": encoded_title.decode("ascii"), "bytes": len(encoded), "status": status})
                        check(label + " decoding error never replaces original text", rows() == expected)
                for invalid_token in (None, "wrong", "非ASCII令牌"):
                    fields = {"title": payload}
                    if invalid_token is not None:
                        fields["csrf"] = invalid_token
                    status, _, body = call("POST", edit_path, fields)
                    check(label + " CSRF rejection", status == 403, status)
                    editable_form(body, edit_path, payload, "csrf error")
                    check(label + " CSRF cannot write", rows() == expected)
                for target in ("999", "0", "-1", "1.5", str(2**63), "9" * 100):
                    path = prefix + "/items/" + target + "/edit"
                    check(label + " invalid/missing target GET", call("GET", path)[0] == 404, target)
                    status, _, body = call("POST", path, {"csrf": csrf, "title": payload})
                    check(label + " invalid/missing target POST", status == 404, target)
                    safe(body, "missing target " + target)
                    check(label + " missing target cannot write", rows() == expected)

                retry_title = '数据库恢复后只更新原 id "<script>unsafe</script>"'
                backup = database.with_suffix(".backup")
                database.rename(backup)
                database.mkdir()
                try:
                    status, _, body = call("GET", prefix + "/health")
                    check(label + " health reports real outage", status == 503 and json.loads(body)["status"] == "unavailable")
                    status, _, body = call("POST", edit_path, {"csrf": csrf, "title": retry_title})
                    check(label + " edit storage failure gets 503", status == 503, status)
                    retry_action, retry_fields = editable_form(body, edit_path, retry_title, "503 recovery")
                    status, _, long_error_body = call("POST", edit_path, {"csrf": csrf, "title": long_title})
                    check(label + " long-input storage failure retains 503 semantics", status == 503, status)
                    editable_form(long_error_body, edit_path, long_title, "long-input 503 recovery")
                    status, _, create_body = call("POST", prefix + "/items", {"csrf": csrf, "title": "恢复新增"})
                    check(label + " create outage still gets 503", status == 503, status)
                    create_form = next(form for form in Document(create_body).forms if form["action"] == prefix + "/items")
                    create_fields = {field["name"]: field["value"] for field in create_form["fields"] if "name" in field}
                finally:
                    database.rmdir()
                    backup.rename(database)
                status, headers, _ = call("POST", retry_action, retry_fields)
                expected = [(1, retry_title, 1), (2, "不能改变的另一项", 0)]
                check(label + " real 503 form retries original target",
                      status == 303 and headers.get("Location") == prefix + "/" and rows() == expected, rows())
                call("POST", create_form["action"], create_fields)
                check(label + " original create retry still creates one new row", rows() == expected + [(3, "恢复新增", 0)], rows())
                status, _, body = call("GET", prefix + "/health")
                check(label + " health recovers", status == 200 and json.loads(body)["status"] == "ok")
                call("POST", prefix + "/items/1", {"csrf": csrf, "done": "0"})
                check(label + " reopen still preserves edited title", rows()[0] == (1, retry_title, 0), rows()[0])
                stop()
        report["passed"] = True
    except Exception:
        report["passed"] = False
        report["error"] = traceback.format_exc()
    finally:
        stop()
        report["source_sha256_after"] = hashlib.sha256(app_path.read_bytes()).hexdigest()
        report["source_unchanged"] = report["source_sha256_before"] == report["source_sha256_after"]
        report["passed"] = report.get("passed", False) and report["source_unchanged"]
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        report["checks_passed"] = sum(item["passed"] for item in report["checks"])
        report["checks_total"] = len(report["checks"])
        report["http_requests"] = len(report["requests"])
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({key: report[key] for key in ("passed", "checks_passed", "checks_total", "http_requests", "source_unchanged", "source_sha256_after")}, ensure_ascii=False))
        if report.get("error"):
            print(report["error"])
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
