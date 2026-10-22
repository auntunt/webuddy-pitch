"""Exact-content human knowledge publication with durable file-side receipts.

The caller records the human decision in its database outbox first. These
projections never pretend the database and the knowledge files share a transaction.
All publication and recovery occurs under the existing KB lock; GETs only read.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from .. import kb
from . import learning as L, signoff
from .errors import ApiError
from .store import now


def _paths(p, origin_id):
    root = Path(p["root"]).resolve()
    try:
        page = kb.page_path(root, origin_id)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ApiError(400, "事实页面标识无效") from exc
    regpath = kb.kdir(root) / ".pages.json"
    for path in (page, regpath, root / ".tmh" / "cache", root / ".tmh" / "cache" / "kb.lock"):
        for part in (path, *path.parents):
            if part == root:
                break
            if part.is_symlink():
                raise ApiError(409, "知识发布路径不能经过符号链接")
        if not path.is_relative_to(root):
            raise ApiError(409, "知识发布路径超出项目")
    return root, page, regpath


def _read(p, origin_id):
    root, page, regpath = _paths(p, origin_id)
    try:
        with page.open(encoding="utf-8", newline="") as stream:
            text = stream.read()
        reg = json.loads(regpath.read_text(encoding="utf-8"))
        if not isinstance(reg, dict) or not isinstance(reg.get(origin_id), dict):
            raise ValueError("页面没有登记")
        if kb.parse_page(text)["meta"].get("id") != origin_id:
            raise ValueError("页面登记标识不匹配")
    except (OSError, UnicodeError, ValueError) as exc:
        raise ApiError(409, "知识页面或登记不可读：" + str(exc)) from exc
    return root, page, text, reg


def _token(p, origin_id, text, record):
    return L.digest({"root": str(Path(p["root"]).resolve()), "project_id": p["id"],
                     "origin_id": origin_id, "content": text, "registry": record})


def revision_token(P, p, origin_id):
    """Read-only optimistic snapshot, with no lock file creation or recovery."""
    p = L.project(P, p)
    _, _, text, reg = _read(p, origin_id)
    _, _, check, current = _read(p, origin_id)
    token = _token(p, origin_id, text, reg[origin_id])
    if token != _token(p, origin_id, check, current[origin_id]):
        raise ApiError(409, "知识页面正在变化，请刷新")
    return token


def _sources_current(P, p, source):
    if L.binding(P, p) != source.get("binding"):
        raise ApiError(409, "项目工作区、提交或引用授权已变化")
    for evidence in source.get("evidence", []):
        if L.digest(L.safe_read(p["root"], evidence["path"])) != evidence["sha256"]:
            raise ApiError(409, "事实证据文件已变化：" + evidence["path"])


def active_revision(P, p, origin_id):
    p = L.project(P, p)
    try:
        _, _, text, reg = _read(p, origin_id)
    except ApiError:
        return None
    record = reg[origin_id]
    state = record.get("learning") or {}
    if not isinstance(state, dict):
        return None
    if state.get("pending") or not state.get("active_revision") or kb.confirmation_status(record, text) != kb.STATUS_OK:
        return None
    receipts = state.get("receipts")
    receipt = receipts.get(state.get("decision_id")) if isinstance(receipts, dict) else None
    if not isinstance(receipt, dict) or receipt.get("stage") != "applied" or receipt.get("revision_id") != state["active_revision"]:
        return None
    # An old source does not erase the human's pointer: it must remain visible
    # for revocation. Consumers check source currency separately before use.
    return state["active_revision"]


def _status(text, value):
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
    if not match:
        raise ApiError(409, "知识页面缺少可验证的登记字段")
    head = match.group(1)
    if re.search(r"^status:", head, re.M):
        head = re.sub(r"^status:[^\n]*", "status: " + value, head, flags=re.M)
    else:
        head += "\nstatus: " + value
    return "---\n" + head + "\n---\n" + text[match.end():]


def _checked_revision(P, p, r, actor, decision_id, expected_token, reason):
    if not signoff.human(actor):
        raise ApiError(403, "事实采用和撤销只允许人工操作者")
    if not isinstance(decision_id, str) or not decision_id or not isinstance(expected_token, str) or not expected_token:
        raise ApiError(400, "事实发布需要决定标识和预期页面版本")
    if not isinstance(reason, str) or not reason.strip():
        raise ApiError(400, "需要人工决定原因")
    actual = L.revision(P, p, r.get("id"))
    if actual["kind"] != "fact" or actual != r:
        raise ApiError(409, "事实修订不属于当前项目或内容不一致")
    return actual


def _identity(action, r, actor, expected_token, reason):
    return L.digest({"action": action, "revision_id": r["id"], "fingerprint": r["fingerprint"],
                     "actor": actor, "expected_token": expected_token, "reason": reason})


def _check_receipt(receipt, action, r, actor, decision_id, expected_token, reason):
    """Validate a durable success against its immutable revision before replay."""
    values = {"identity": _identity(action, r, actor, expected_token, reason), "action": action,
              "revision_id": r["id"], "decision_id": decision_id, "actor": actor,
              "expected_token": expected_token, "reason": reason, "source": r["source"]}
    if any(receipt.get(key) != value for key, value in values.items()):
        raise ApiError(409, "同一人工决定不能更换正文、原因或预期版本")
    for key in ("before", "draft", "final"):
        text = receipt.get(key + "_content")
        if not isinstance(text, str) or L.digest(text) != receipt.get(key + "_sha256"):
            raise ApiError(409, "事实发布回执内容摘要不一致")
    candidate = r["content"] if action == "adopt" else receipt["before_content"]
    if (receipt["draft_content"] != _status(candidate, kb.STATUS_DRAFT) or
            receipt["final_content"] != _status(candidate, kb.STATUS_OK if action == "adopt" else kb.STATUS_DRAFT)):
        raise ApiError(409, "事实发布回执不属于原固定修订")
    expected = {"status": "applied", "action": action, "revision_id": r["id"],
                "decision_id": decision_id, "content_sha256": receipt["final_sha256"], "actor": actor}
    if receipt.get("result") != expected:
        raise ApiError(409, "事实发布成功回执不完整")


def _prepare(P, p, r, actor, decision_id, expected_token, reason, action, text, reg):
    pid = r["origin_id"]
    record = reg[pid]
    original = copy.deepcopy(record)
    state = record.get("learning", {})
    if not isinstance(state, dict):
        raise ApiError(409, "知识发布回执不可读，请修复原记录后重试")
    receipts = state.get("receipts", {})
    if not isinstance(receipts, dict):
        raise ApiError(409, "知识发布回执不可读，请修复原记录后重试")
    identity = _identity(action, r, actor, expected_token, reason)
    receipt = receipts.get(decision_id)
    if decision_id in receipts:
        if not isinstance(receipt, dict):
            raise ApiError(409, "知识发布回执不可读，请修复原记录后重试")
        if receipt.get("stage") not in ("prepared", "applied"):
            raise ApiError(409, "此发布已放弃或回执无效，不能重放；请重新固定修订并作出新决定")
        _check_receipt(receipt, action, r, actor, decision_id, expected_token, reason)
        if receipt["stage"] == "applied":
            # Historical success is independent of later content or source
            # edits. Replay only completes outbox auditing; it never republishes.
            return receipt
        if kb._learning_state_digest(record) != receipt.get("prepared_state"):
            raise ApiError(409, "此决定之后页面登记已有变化，不能重放旧发布")
        hashes = {receipt["before_sha256"], receipt["draft_sha256"], receipt["final_sha256"]}
        if L.digest(text) not in hashes:
            raise ApiError(409, "此决定之后正文已有变化，不能重放旧发布")
        if action == "adopt":
            _sources_current(P, p, r["source"])
        return receipt
    if state.get("pending"):
        raise ApiError(409, "已有未完成的事实发布，请先恢复原决定")
    # The CAS includes the full preexisting page record, before adding new fields.
    if _token(p, pid, text, original) != expected_token:
        raise ApiError(409, "知识正文或人工登记已变化，请刷新后重新决定")
    if action == "adopt":
        if not L.revision_current(P, p, r):
            raise ApiError(409, "事实来源已过期，请重新固定修订")
        candidate = r["content"]
        # Proposal validation is also checked here, not trusted from the UI.
        def protected(value):
            head = re.match(r"\A---\s*\n.*?\n---\s*\n", value, re.S)
            return head.group() if head else "", kb.FACTS_RX.findall(value)
        if protected(candidate) != protected(text):
            raise ApiError(409, "修订不能改变登记字段或程序生成事实")
        errors, _ = kb.validate_content(Path(p["root"]), pid, candidate)
        if errors:
            raise ApiError(409, "事实正文校验未通过：" + "；".join(errors))
    else:
        if state.get("active_revision") != r["id"]:
            raise ApiError(409, "当前采用版本已变化，不能撤销旧版本")
        candidate = text
    draft = _status(candidate, kb.STATUS_DRAFT)
    final = _status(candidate, kb.STATUS_OK) if action == "adopt" else draft
    before_record = copy.deepcopy(original)
    # Prior receipt bodies remain in the outer append-only ledger, referenced here.
    if isinstance(before_record.get("learning"), dict):
        old = before_record["learning"].pop("receipts", {})
        before_record["learning"]["receipt_ids"] = list(old)
    receipt = {"stage": "prepared", "identity": identity, "action": action, "revision_id": r["id"],
               "decision_id": decision_id, "actor": actor, "expected_token": expected_token,
               "reason": reason, "source": copy.deepcopy(r["source"]), "before_content": text,
               "before_registry": before_record, "before_sha256": L.digest(text),
               "draft_content": draft, "draft_sha256": L.digest(draft),
               "final_content": final, "final_sha256": L.digest(final),
               "result": {"status": "applied", "action": action, "revision_id": r["id"],
                          "decision_id": decision_id, "content_sha256": L.digest(final), "actor": actor}}
    record["status"] = kb.STATUS_DRAFT
    for key in ("confirmed_by", "confirmed_at", "confirm_note", "stale"):
        record.pop(key, None)
    state["pending"] = decision_id
    receipts[decision_id] = receipt
    state["receipts"] = receipts
    record["learning"] = state
    receipt["prepared_state"] = kb._learning_state_digest(record)
    kb.save_registry(Path(p["root"]), reg, _atomic=True)
    return receipt


def _project(P, p, r, actor, decision_id, expected_token, reason, action):
    # The database outbox uses DB -> KB ordering. Keep that order for direct
    # callers too; source checks below only read Store and never open a transaction.
    with P.store.lock:
        return _project_locked(P, p, r, actor, decision_id, expected_token, reason, action)


def _project_locked(P, p, r, actor, decision_id, expected_token, reason, action):
    p = L.project(P, p)
    r = _checked_revision(P, p, r, actor, decision_id, expected_token, reason)
    root, _, regpath = _paths(p, r["origin_id"])
    cache = root / ".tmh" / "cache"
    cache.mkdir(exist_ok=True)
    with kb._Lock(cache / "kb.lock"):
        # An already durable receipt can complete the database audit even when
        # somebody has since removed or invalidated the page. Never touch it.
        try:
            saved = json.loads(regpath.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            saved = {}
        record = saved.get(r["origin_id"]) if isinstance(saved, dict) else None
        state = record.get("learning") if isinstance(record, dict) else None
        receipts = state.get("receipts") if isinstance(state, dict) else None
        applied = receipts.get(decision_id) if isinstance(receipts, dict) else None
        if isinstance(applied, dict) and applied.get("stage") == "applied":
            _check_receipt(applied, action, r, actor, decision_id, expected_token, reason)
            return dict(applied["result"])
        root, page, text, reg = _read(p, r["origin_id"])
        receipt = _prepare(P, p, r, actor, decision_id, expected_token, reason, action, text, reg)
        if receipt["stage"] == "applied":
            return dict(receipt["result"])
        if action == "adopt":
            _sources_current(P, p, r["source"])
        if L.digest(text) == receipt["before_sha256"]:
            kb._atomic_text(page, receipt["draft_content"])
        if L.digest(page.read_text(encoding="utf-8")) not in (receipt["draft_sha256"], receipt["final_sha256"]):
            raise ApiError(409, "事实发布期间正文发生变化")
        if action == "adopt":
            kb.confirm(root, r["origin_id"], actor, reason, _locked=True,
                       _learning={"decision_id": decision_id,
                                  "recheck": lambda: _sources_current(P, p, r["source"])})
        else:
            record = reg[r["origin_id"]]
            state = record["learning"]
            state.update(pending="", active_revision="", confirmed_sha256="", decision_id=decision_id)
            receipt["stage"] = "applied"
            receipt["applied_state"] = kb._learning_state_digest(record)
            kb.save_registry(root, reg, _atomic=True)
        return dict(receipt["result"])


def project_revision(P, p, r, actor, decision_id, expected_token, reason):
    return _project(P, p, r, actor, decision_id, expected_token, reason, "adopt")


def revoke_revision(P, p, r, actor, decision_id, expected_token, reason):
    return _project(P, p, r, actor, decision_id, expected_token, reason, "revoke")


def abandon(P, p, r, actor, decision_id, expected_token, reason):
    """Release one unfinished publication; never replace or confirm its page.

    A changed source is precisely why a human may need to abandon a projection,
    so this operation uses the current full page/registry CAS, not old evidence.
    The caller must still verify the individual operator's session.
    """
    with P.store.lock:
        p = L.project(P, p)
        r = _checked_revision(P, p, r, actor, decision_id, expected_token, reason)
        root, _, _ = _paths(p, r["origin_id"])
        cache = root / ".tmh" / "cache"
        cache.mkdir(exist_ok=True)
        with kb._Lock(cache / "kb.lock"):
            root, _, text, reg = _read(p, r["origin_id"])
            record = reg[r["origin_id"]]
            state = record.get("learning")
            receipts = state.get("receipts") if isinstance(state, dict) else None
            receipt = receipts.get(decision_id) if isinstance(receipts, dict) else None
            if not isinstance(receipt, dict) or receipt.get("revision_id") != r["id"]:
                raise ApiError(409, "没有与此修订匹配的未完成发布")
            if receipt.get("stage") == "applied":
                raise ApiError(409, "此决定已成功保存，不能放弃；请改走撤销")
            identity = _identity("abandon", r, actor, expected_token, reason)
            if receipt.get("stage") == "abandoned":
                saved = receipt.get("abandonment") or {}
                if (saved.get("identity") != identity or state.get("pending") or
                        saved.get("state") != kb._learning_state_digest(record) or
                        saved.get("content_sha256") != L.digest(text)):
                    raise ApiError(409, "放弃决定之后正文或登记已变化，不能重放旧决定")
                return dict(saved["result"])
            if receipt.get("stage") != "prepared" or state.get("pending") != decision_id:
                raise ApiError(409, "当前待完成发布已变化，不能放弃旧决定")
            if _token(p, r["origin_id"], text, record) != expected_token:
                raise ApiError(409, "知识正文或人工登记已变化，请刷新后重新决定是否放弃")
            before = copy.deepcopy(record)
            prior = before["learning"].pop("receipts", {})
            before["learning"]["receipt_ids"] = list(prior)
            result = {"status": "abandoned", "action": "abandon", "revision_id": r["id"],
                      "decision_id": decision_id, "actor": actor, "content_sha256": L.digest(text),
                      "message": "已放弃未完成发布，当前正文保留并待人工确认；放弃不代表确认"}
            saved = {"identity": identity, "actor": actor, "at": now(), "reason": reason,
                     "expected_token": expected_token, "content": text, "content_sha256": L.digest(text),
                     "before_registry": before, "result": result}
            receipt.update(stage="abandoned", abandonment=saved)
            record["status"] = kb.STATUS_DRAFT
            for key in ("confirmed_by", "confirmed_at", "confirm_note", "stale"):
                record.pop(key, None)
            state.update(pending="", active_revision="", confirmed_sha256="", decision_id="")
            saved["state"] = kb._learning_state_digest(record)
            kb.save_registry(root, reg, _atomic=True)
            return dict(result)
