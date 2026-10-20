#!/usr/bin/env python3
"""Observe one fixed BOOTV2 candidate through real HTTP and an owned SQLite DB.

Trace hits prove execution reachability only. HTTP/database assertions are
recorded separately. Neither section is a customer signoff or production test.
"""
import argparse
import ast
import base64
import hashlib
import html
import http.client
import json
import re
import sqlite3
import subprocess
import tempfile
import threading
import types
from pathlib import Path
from urllib.parse import urlencode

COMMIT = "8be50de6b4b4200dc6d792c2a7f0b871f9288da4"
BASE = "6c7787b3de7d308120b9c2e298b3629b588a47c9"
SOURCE_SHA256 = "a5bc89078052bc070b96e46255408721e88ce92750c91eef01fa973d7739a009"


def run(repo, output):
    source = subprocess.check_output(["git", "-C", str(repo), "show", COMMIT + ":app.py"])
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError("fixed candidate source does not match the previously verified bytes")
    diff = subprocess.check_output(["git", "-C", str(repo), "diff", "--no-color", "-U0", BASE, COMMIT, "--", "app.py"])
    filename = "git-object:" + COMMIT + ":app.py"
    module = types.ModuleType("independent_fixed_bootv2")
    module.__file__ = filename
    exec(compile(source, filename, "exec"), module.__dict__)
    tree = ast.parse(source)
    assigned = [n for n in ast.walk(tree) if isinstance(n, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == "title_length" for t in n.targets)]
    guards = [n for n in ast.walk(tree) if isinstance(n, ast.If) and "title_length" in ast.unparse(n.test)]
    if len(assigned) != 1 or len(guards) != 1:
        raise ValueError("the independently verified change is no longer identifiable")
    changed_executable = {assigned[0].lineno, guards[0].lineno}
    report = {"source": {"commit": COMMIT, "baseline": BASE, "file": "app.py", "sha256": SOURCE_SHA256,
                          "diff_sha256": hashlib.sha256(diff).hexdigest()},
              "scope": "one fixed Python/http.server candidate; concrete observed HTTP requests only",
              "limitations": ["trace hits prove execution, not correct behavior", "business assertions are separate",
                              "no browser interaction, real model, customer signoff or production operation"],
              "changed_executable_lines": sorted(changed_executable), "cases": [], "pass": False}
    output.mkdir(parents=True, exist_ok=True)
    (output / "fixed-candidate-app.py").write_bytes(source)
    (output / "fixed-candidate.diff").write_bytes(diff)
    active = [None]
    original_trace = threading.gettrace()
    def trace(frame, event, arg):
        record = active[0]
        if record is not None and frame.f_code.co_filename == filename and event in ("call", "line", "return", "exception"):
            record["trace"].append({"event": event, "function": frame.f_code.co_qualname, "line": frame.f_lineno})
        return trace
    threading.settrace(trace)
    server = thread = None
    try:
        with tempfile.TemporaryDirectory(prefix="bootv2-independent-http-trace-") as temp:
            database = Path(temp) / "owned-test.db"
            for prefix in ("", "/pv/BOOTV2-1/__commit/" + COMMIT):
                if database.exists():
                    database.unlink()
                case = {"prefix": prefix, "requests": [], "business_assertions": [], "path_observations": []}
                report["cases"].append(case)
                def start():
                    nonlocal server, thread
                    server = module.make_server(("127.0.0.1", 0), database, prefix, "独立路径验证临时项目")
                    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
                    thread.start()
                def stop():
                    nonlocal server, thread
                    if server is not None:
                        server.shutdown()
                        server.server_close()
                        thread.join(5)
                        if thread.is_alive():
                            raise RuntimeError("owned temporary HTTP server did not stop")
                        server = thread = None
                def rows():
                    with sqlite3.connect(database) as db:
                        return [list(row) for row in db.execute("SELECT id,title,done FROM items ORDER BY id")]
                def check(name, actual, expected):
                    good = actual == expected
                    case["business_assertions"].append({"assertion": name, "actual": actual, "expected": expected, "pass": good})
                    if not good:
                        raise AssertionError(name + ": " + repr(actual) + " != " + repr(expected))
                def request(label, method, route, fields=None):
                    body = urlencode(fields).encode("ascii") if fields is not None else None
                    record = {"label": label, "method": method, "path": route, "request_body_base64":
                              base64.b64encode(body or b"").decode(), "trace": []}
                    case["requests"].append(record)
                    active[0] = record
                    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
                    try:
                        connection.request(method, route, body, {"Content-Type": "application/x-www-form-urlencoded"})
                        response = connection.getresponse()
                        payload = response.read()
                        record["response"] = {"status": response.status, "headers": response.getheaders(),
                            "body_base64": base64.b64encode(payload).decode(), "body_text": payload.decode("utf-8")}
                        return record
                    finally:
                        connection.close()
                        active[0] = None
                def csrf():
                    home = request("read CSRF from actual form", "GET", prefix + "/")
                    check("home is available", home["response"]["status"], 200)
                    return re.search(r'name="csrf" value="([^"]+)"', home["response"]["body_text"])[1]
                def saved_value(record):
                    match = re.search(r'<textarea\b[^>]*>(.*?)</textarea>', record["response"]["body_text"], re.S)
                    if not match:
                        raise AssertionError("recovery textarea missing")
                    raw = html.unescape(match[1])
                    return raw[1:] if raw.startswith("\n") else raw
                def path_observation(record, expected_changed):
                    calls = [e["function"] for e in record["trace"] if e["event"] == "call"]
                    lines = sorted({e["line"] for e in record["trace"] if e["event"] == "line"})
                    seen = changed_executable.intersection(lines)
                    observed = {"request": record["label"], "method": record["method"], "path": record["path"],
                                "called_functions": calls, "executed_lines": lines,
                                "changed_lines_hit": sorted(seen), "expected_changed_lines_reached": expected_changed,
                                "pass": (seen == changed_executable if expected_changed else not seen),
                                "meaning": "observed execution reachability only; see separate business assertions"}
                    for suffix in (".Handler.do_POST", ".Handler.post", ".Handler.edit_id"):
                        if not any(c.endswith(suffix) for c in calls):
                            observed["pass"] = False
                    case["path_observations"].append(observed)
                    if not observed["pass"]:
                        raise AssertionError("unexpected execution trace: " + record["label"])

                start()
                try:
                    token = csrf()
                    for title in ("旁边的事项不变", "原始待编辑事项"):
                        record = request("seed " + title, "POST", prefix + "/items", {"csrf": token, "title": title})
                        check("seed saved", record["response"]["status"], 303)
                    target = rows()[-1][0]
                    record = request("mark target done before edit", "POST", prefix + "/items/%d" % target,
                                     {"csrf": token, "done": "1"})
                    check("completion preserved baseline", record["response"]["status"], 303)
                    edit = prefix + "/items/%d/edit" % target
                    original = rows()
                    page = request("read actual edit form", "GET", edit)
                    check("edit page is available", page["response"]["status"], 200)
                    boundary = "事" * 100 + "\r\n" + "项" * 99
                    good = request("save native CRLF logical 200", "POST", edit, {"csrf": token, "title": boundary})
                    path_observation(good, True)
                    check("logical 200 saves", good["response"]["status"], 303)
                    expected = [[i, boundary if i == target else text, done] for i, text, done in original]
                    check("complete text/id/done/other row preserved", rows(), expected)
                    before = rows()
                    too_long = "事" * 100 + "\r\n" + "项" * 100
                    rejected = request("reject native CRLF logical 201", "POST", edit, {"csrf": token, "title": too_long})
                    path_observation(rejected, True)
                    check("logical 201 rejected", rejected["response"]["status"], 400)
                    check("rejection retains complete textarea", saved_value(rejected), too_long)
                    check("rejection does not change database", rows(), before)
                    other_route = request("different URL same POST dispatcher", "POST", prefix + "/unrelated",
                                          {"csrf": token, "title": "不能当编辑保存"})
                    path_observation(other_route, False)
                    check("different route remains 404", other_route["response"]["status"], 404)
                    check("same dispatcher does not prove edit behavior", rows(), before)
                    retry_title = "重" * 100 + "\r\n" + "试" * 99
                    backup = database.with_suffix(".owned-backup")
                    database.rename(backup)
                    database.mkdir()
                    try:
                        failed = request("database unavailable preserves edit", "POST", edit, {"csrf": token, "title": retry_title})
                    finally:
                        database.rmdir()
                        backup.rename(database)
                    path_observation(failed, False)
                    check("actual SQLite error returns 503", failed["response"]["status"], 503)
                    check("failure retains original complete input", saved_value(failed), retry_title)
                    check("recovery targets original item", 'action="' + edit + '"' in failed["response"]["body_text"], True)
                    check("failed write left data unchanged", rows(), before)
                    recovered = request("retry original item after storage recovery", "POST", edit, {"csrf": token, "title": retry_title})
                    path_observation(recovered, True)
                    check("retry saves", recovered["response"]["status"], 303)
                    expected = [[i, retry_title if i == target else text, done] for i, text, done in before]
                    check("retry edits exactly original item", rows(), expected)
                    stop()
                    start()
                    refreshed = request("read edit after service restart", "GET", edit)
                    check("restart retained complete saved text", saved_value(refreshed), retry_title)
                    check("restart retained all rows and completion", rows(), expected)
                finally:
                    stop()
            report["temporary_database_removed"] = True
        report["pass"] = all(x["pass"] for c in report["cases"] for x in c["business_assertions"] + c["path_observations"])
    except BaseException as error:
        report["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
            thread.join(5)
        threading.settrace(original_trace)
        report["servers_stopped"] = server is None
        (output / "independent-http-trace.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"pass": report["pass"], "cases": len(report["cases"]),
            "path_observations": sum(len(c["path_observations"]) for c in report["cases"]),
            "business_assertions": sum(len(c["business_assertions"]) for c in report["cases"]),
            "commit": COMMIT, "report": str(output / "independent-http-trace.json")}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.repo.resolve(), args.output.resolve())
