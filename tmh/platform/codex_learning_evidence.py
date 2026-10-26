"""Read-only Codex file-binding checks, deliberately outside adoption routes.

No database, process, recovery or authorization entry point is called here.
Even a valid bundle is NOT authenticated execution or an adoptable experiment.
"""
import os
from pathlib import Path, PurePosixPath
import re
import stat

from scripts.rsi import codex_protocol as C


def _identity(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_nlink,
            st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _private(st, directory=False):
    C.require((stat.S_ISDIR(st.st_mode) if directory else stat.S_ISREG(st.st_mode)) and
              st.st_uid == os.getuid() and not st.st_mode & 0o077, "owner-only ordinary file/directory required")
    if not directory:
        C.require(st.st_nlink == 1, "hard links are not evidence originals")


def _checked_private(fd, directory=False):
    checked = os.fstat(fd)
    _private(checked, directory)
    C.require(_identity(os.fstat(fd)) == _identity(checked), "object changed during private check")
    return checked


def _node(st):
    return st.st_dev, st.st_ino


def _links(parts, chain):
    # System ancestors need stable directory entries, not private permissions.
    for index, part in enumerate(parts):
        entry = os.stat(part, dir_fd=chain[index], follow_symlinks=False)
        C.require(stat.S_ISDIR(entry.st_mode) and _node(entry) == _node(os.fstat(chain[index + 1])),
                  "absolute directory chain was replaced")


def _absolute_chain(root):
    parts = root.parts[1:]
    chain = [os.open(root.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)]
    try:
        for part in parts:
            chain.append(os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=chain[-1]))
        _links(parts, chain)
        return chain
    except BaseException:
        for fd in reversed(chain):
            os.close(fd)
        raise


class _Files:
    def __init__(self, root):
        C.require(os.name == "posix" and hasattr(os, "O_NOFOLLOW"), "POSIX no-follow reads required")
        self.root = Path(root)
        C.require(self.root.is_absolute() and self.root == self.root.resolve(), "canonical absolute bundle path required")
        self.chain = _absolute_chain(self.root)
        self.fd = self.chain[-1]
        try:
            checked = _checked_private(self.fd, True)
            self.identity = _identity(checked)
            self.ancestry = [_node(os.fstat(fd)) for fd in self.chain]
        except BaseException:
            self.close()
            raise
        self.seen = {}
        self.directories = {}

    def close(self):
        for fd in reversed(self.chain):
            os.close(fd)

    def read(self, name):
        C.text(name)
        parts = name.split("/")
        C.require(not PurePosixPath(name).is_absolute() and
                  all(p not in ("", ".", "..") for p in parts) and "\\" not in name,
                  "relative ordinary evidence path required")
        chain = [os.dup(self.fd)]
        checked_directories = []
        try:
            checked = _checked_private(chain[0], True)
            C.require(_identity(checked) == self.identity, "bundle identity changed")
            checked_directories.append(_identity(checked))
            for index, part in enumerate(parts[:-1]):
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=chain[-1])
                chain.append(child)
                checked = _checked_private(child, True)
                prefix = "/".join(parts[:index + 1])
                identity = _identity(checked)
                C.require(self.directories.setdefault(prefix, identity) == identity,
                          "evidence directory was replaced or changed")
                checked_directories.append(identity)
            child = os.open(parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=chain[-1])
            try:
                before = _checked_private(child)
                chunks = []
                size = 0
                while True:
                    chunk = os.read(child, 65536)
                    if not chunk:
                        break
                    size += len(chunk)
                    C.require(size <= before.st_size, "evidence grew while reading")
                    chunks.append(chunk)
                raw = b"".join(chunks)
                after = os.fstat(child)
                C.require(_identity(before) == _identity(after) and len(raw) == before.st_size,
                          "evidence changed while reading")
                previous = self.seen.setdefault(name, _identity(before))
                C.require(previous == _identity(before), "evidence path was replaced")
                _links(parts[:-1], chain)
                for directory, identity in zip(chain, checked_directories):
                    C.require(_identity(_checked_private(directory, True)) == identity,
                              "evidence directory changed during read")
                entry = os.stat(parts[-1], dir_fd=chain[-1], follow_symlinks=False)
                C.require(_identity(entry) == _identity(before), "evidence file entry was replaced")
                return raw
            finally:
                os.close(child)
        finally:
            for fd in reversed(chain):
                os.close(fd)

    def artifact(self, reference, expected):
        C.fields(reference, ("path", "bytes", "sha256"))
        C.require(reference["path"] == expected, "unexpected artifact path")
        C.integer(reference["bytes"])
        C.sha(reference["sha256"])
        raw = self.read(expected)
        C.require(len(raw) == reference["bytes"] and C.digest(raw) == reference["sha256"], "artifact binding mismatch")
        return raw

    def unchanged(self):
        for name in list(self.seen):
            self.read(name)
        chain = _absolute_chain(self.root)
        try:
            C.require([_node(os.fstat(fd)) for fd in chain] == self.ancestry,
                      "absolute directory chain identity changed")
            C.require(_identity(_checked_private(chain[-1], True)) == self.identity,
                      "bundle directory was replaced or changed")
            _links(self.root.parts[1:], self.chain)
        finally:
            for fd in reversed(chain):
                os.close(fd)


def _events(raw):
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise C.InvalidEvidence("output is not UTF-8 JSONL") from exc
    C.require(lines and all(line.strip() for line in lines), "complete nonblank JSONL required")
    started = active = completed = False
    answer, usage = "", {}
    for line in lines:
        event = C.strict(line)
        C.require(isinstance(event, dict) and not completed, "invalid or trailing CLI event")
        kind = event.get("type")
        if kind == "thread.started":
            C.require(not started and not active, "duplicate thread")
            C.text(event.get("thread_id"))
            started = True
        elif kind == "turn.started":
            C.require(started and not active, "missing thread or duplicate turn")
            active = True
        elif kind in ("item.started", "item.updated", "item.completed"):
            C.require(active, "item outside turn")
            item = event.get("item")
            C.require(isinstance(item, dict), "item object required")
            if kind == "item.completed" and item.get("type") == "agent_message":
                C.text(item.get("text"))
                answer = item["text"]
        elif kind == "turn.completed":
            C.require(active and bool(answer), "missing turn or final answer")
            usage = event.get("usage")
            C.require(isinstance(usage, dict) and
                      not set(usage) - {"input_tokens", "cached_input_tokens", "output_tokens"}, "unsupported usage fields")
            for value in usage.values():
                C.integer(value)
            if "cached_input_tokens" in usage:
                C.require("input_tokens" in usage and usage["cached_input_tokens"] <= usage["input_tokens"], "cache is an input subset")
            completed = True
        else:
            raise C.InvalidEvidence("failed, error or unsupported CLI event")
    C.require(completed, "missing completed CLI turn")
    return answer, usage


def _attempt(files, item, limit):
    C.fields(item, ("request_id", "phase", "state", "owner", "original_folder", "files"))
    rid = item["request_id"]
    C.require(isinstance(rid, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", rid) is not None, "safe request ID required")
    C.require(item["phase"] in ("A", "B", "C", "D") and item["state"] == "settled", "unsettled or unknown attempt")
    owner = item["owner"]
    C.fields(owner, ("token", "run_id", "data_dir"))
    for value in owner.values():
        C.text(value)
    C.require(Path(owner["data_dir"]).is_absolute(), "absolute original data directory required")
    C.text(item["original_folder"])
    C.require(Path(item["original_folder"]).is_absolute(), "absolute original supervisor folder required")
    C.fields(item["files"], ("input", "planned", "result", "output"))
    names = {"input": "input.bin", "planned": "supervisor.json", "result": "supervisor-result.json", "output": "output.bin"}
    raw = {k: files.artifact(item["files"][k], "attempts/" + rid + "/" + n) for k, n in names.items()}
    C.require(bool(raw["input"]), "complete input required")
    planned, result = C.strict(raw["planned"]), C.strict(raw["result"])
    C.fields(planned, ("schema", "owner", "nonce", "folder", "phase", "supervisor_pid", "pid", "pgid"))
    C.fields(result, ("schema", "owner", "nonce", "folder", "phase", "supervisor_pid", "pid", "pgid",
                      "returncode", "process_returncode", "reason", "elapsed_seconds", "ended_at", "cleanup", "output"))
    for key in ("schema", "owner", "nonce", "folder", "supervisor_pid", "pid", "pgid"):
        C.require(type(planned[key]) is type(result[key]) and planned[key] == result[key],
                  "contradictory supervisor identity")
    C.require(type(result["schema"]) is int and result["schema"] == 1 and result["owner"] == owner and
              result["folder"] == item["original_folder"], "supervisor does not own this attempt")
    C.text(result["nonce"])
    C.integer(result["supervisor_pid"], 1)
    C.integer(result["pid"], 1)
    C.integer(result["pgid"], 1)
    C.require(result["pid"] == result["pgid"] and planned.get("phase") == "running" and
              result.get("phase") == "finished", "missing actual supervised process")
    for key in ("returncode", "process_returncode"):
        C.require(type(result.get(key)) is int and result[key] == 0, "process did not exit successfully")
    C.require(result.get("reason") == "exited" and "error" not in result, "stopped or errored process")
    C.seconds(result.get("elapsed_seconds"))
    C.require(result["elapsed_seconds"] <= limit, "observation exceeds declared total duration")
    C.seconds(result.get("ended_at"))
    cleanup = result.get("cleanup")
    C.fields(cleanup, ("trigger", "term_sent", "kill_sent", "signals", "errors", "remaining_group",
                       "output_complete", "reaped", "complete"))
    for key, expected in (("complete", True), ("reaped", True), ("output_complete", True),
                          ("remaining_group", False), ("term_sent", False), ("kill_sent", False)):
        C.require(cleanup.get(key) is expected, "cleanup is incomplete or contradictory")
    C.require(cleanup.get("trigger") is None and cleanup.get("errors") == [] and cleanup.get("signals") == [], "cleanup errors or stops")
    C.fields(result["output"], ("file", "bytes", "sha256"))
    C.integer(result["output"]["bytes"])
    C.sha(result["output"]["sha256"])
    C.require(result["output"] == {"file": "output.bin", "bytes": len(raw["output"]),
                                     "sha256": C.digest(raw["output"])}, "supervisor output mismatch")
    answer, usage = _events(raw["output"])
    return {"request_id": rid, "final_answer_sha256": C.digest(answer.encode()), "client_usage": usage,
            "elapsed_seconds": result["elapsed_seconds"], "nonce": result["nonce"]}


def verify(bundle_dir, expected_manifest_sha256):
    """Validate a retained observation snapshot, never return adoption authority.

    The external digest must come from the caller's independent commitment.
    There is no producer authenticity, admission, unseen-data or deadline proof
    in this first protocol increment; all remain explicitly unverified.
    """
    C.sha(expected_manifest_sha256)
    files = None
    try:
        files = _Files(bundle_dir)
        raw = files.read("manifest.json")
        C.require(C.digest(raw) == expected_manifest_sha256, "manifest differs from external commitment")
        manifest = C.strict(raw)
        C.fields(manifest, ("schema", "contract", "origin", "attempts"))
        C.require(manifest["schema"] == C.SCHEMA and manifest["origin"] in ("synthetic-fixture", "official-cli-declared"), "unsupported observation schema/origin")
        contract = C.validate_contract(manifest["contract"])
        items = manifest["attempts"]
        C.require(isinstance(items, list) and 0 < len(items) <= contract["limits"]["max_outer_starts"], "missing or excessive outer attempts")
        rows = [_attempt(files, item, contract["limits"]["total_timeout_seconds"]) for item in items]
        C.require(len({r["request_id"] for r in rows}) == len(rows) and
                  len({r["nonce"] for r in rows}) == len(rows), "duplicate attempts or supervisor receipts")
        C.require(sum(r["elapsed_seconds"] for r in rows) <= contract["limits"]["total_timeout_seconds"], "declared cumulative duration exceeded")
        files.unchanged()
        return {"schema": C.SCHEMA, "file_bindings_verified": True, "origin_claim": manifest["origin"],
                "outer_attempt_records": len(rows), "actual_outer_exec_count": None,
                "requested_model_claim": contract["client"]["requested_model"],
                "observations": rows, "adoptable": False,
                "execution_admitted": False, "official_client_provenance_verified": False,
                "input_delivery_verified": False, "process_execution_verified": False,
                "isolation_verified": False, "holdout_unseen_verified": False, "deadline_verified": False,
                "actual_backend_model": None, "http_request_count": None, "internal_retry_count": None,
                "actual_cost": {"status": "unknown", "amount": None},
                "scope": "externally committed local file bindings only; not a qualified experiment or human decision"}
    except (OSError, TypeError, UnicodeError, KeyError, OverflowError) as exc:
        raise C.InvalidEvidence("unreadable or malformed evidence") from exc
    finally:
        if files is not None:
            files.close()
