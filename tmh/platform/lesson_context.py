"""Exact ordinary lesson blocks and stable authorization/content bindings.

Callers hold Store -> ledger while selecting, rendering and recording bindings.
Usage counters are frozen model input, not a reason to revoke a prior session.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat

from . import learn, learning as L, learning_decisions as D, lesson_input as I

SCHEMA = "lesson-block-v2"


def replace_template(prompt, old, new, metas, count=-1):
    """Expand platform placeholders without rewriting quoted lesson data."""
    parts = [(prompt, False)]
    for meta in metas:
        block = meta.get("block") if meta.get("mode") == "learning_lessons" else None
        text = block.get("text") if isinstance(block, dict) else None
        if not text:
            continue
        updated = []
        for part, protected in parts:
            if protected:
                updated.append((part, True))
                continue
            pieces = part.split(text)
            for index, piece in enumerate(pieces):
                if index:
                    updated.append((text, True))
                updated.append((piece, False))
        parts = updated
    result, remaining = [], count
    for part, protected in parts:
        if protected or remaining == 0:
            result.append(part)
        else:
            result.append(part.replace(old, new, remaining))
            if remaining > 0:
                remaining -= min(remaining, part.count(old))
    return "".join(result)


def _scope(card):
    return "public-legacy" if card.get("foreign") else "local"


def _stable_payload(payload):
    return {k: v for k, v in payload.items() if k != "usage_evidence"}


def _binding(data, project, card):
    if card.get("foreign"):
        return {"scope": "public-legacy", "id": card["id"],
                "public": learn.public_lesson_binding(data, project["key"], card)}
    return {"scope": "local", "id": card["id"],
            "token": learn.revision_token(data, card["id"])}


def freeze(store, project, cards):
    """Freeze exactly the already selected, usable and non-held-out cards."""
    data = store.path.parent
    payloads = [I.lesson_payload(card, scope=_scope(card)) for card in cards]
    value = dict(I.render_lessons(payloads), schema=SCHEMA,
                 selector_version=I.SELECTOR_VERSION, payloads=payloads,
                 bindings=[_binding(data, project, card) for card in cards])
    value["block_sha256"] = L.digest(value)
    # Detach everything, including nested files/stats, from caller-owned data.
    return json.loads(L.encoded(value))


def _lease_matches(data, identity):
    """A reentrant lease must still guard the currently named lock inode."""
    root = Path(data).resolve()
    try:
        current = (root / "lessons.lock").lstat()
        held = getattr(learn._LEDGER_LOCAL, "held", {}).get(str(root))
        if not held or not stat.S_ISREG(current.st_mode):
            return False
        opened = os.fstat(held["stream"].fileno())
        return (stat.S_ISREG(opened.st_mode) and (current.st_dev, current.st_ino) == identity
                and (opened.st_dev, opened.st_ino) == identity)
    except (OSError, ValueError):
        return False


def current(store, project, block):
    """Verify frozen bytes and present eligibility, without reranking/usage IO."""
    if (not isinstance(block, dict) or block.get("schema") != SCHEMA or
            block.get("renderer_version") != I.RENDERER_VERSION or
            block.get("selector_version") != I.SELECTOR_VERSION or
            block.get("block_sha256") != L.digest({k: v for k, v in block.items() if k != "block_sha256"})):
        return False
    payloads, bindings = block.get("payloads"), block.get("bindings")
    if not isinstance(payloads, list) or not isinstance(bindings, list) or len(payloads) != len(bindings):
        return False
    rendered = I.render_lessons(payloads)
    if any(block.get(key) != rendered[key] for key in ("renderer_version", "text", "payload_sha256", "rendered_sha256")):
        return False
    data = store.path.parent
    lock = data / "lessons.lock"
    try:
        before = lock.lstat()
    except OSError:
        return False
    if not stat.S_ISREG(before.st_mode):
        return False
    lease_identity = (before.st_dev, before.st_ino)
    with store.lock, learn.ledger_lock(data, create=False):
        if not _lease_matches(data, lease_identity):
            return False
        seen = set()
        for payload, binding in zip(payloads, bindings):
            if not isinstance(binding, dict):
                return False
            identity = (binding.get("scope"), binding.get("id"))
            if identity in seen or identity[0] not in ("local", "public-legacy"):
                return False
            seen.add(identity)
            card = (learn.shared_lesson(data, project["key"], identity[1]) if identity[0] == "public-legacy"
                    else learn.lesson(data, identity[1]))
            if not card or _binding(data, project, card) != binding:
                return False
            usable, _ = D.usable_lessons(store, project, [card])
            if not usable or _stable_payload(I.lesson_payload(card, scope=identity[0])) != _stable_payload(payload):
                return False
        return _lease_matches(data, lease_identity)


def has_history(data, project_key):
    """A retired local card or withdrawn take still existed in old CLI memory."""
    with learn.ledger_lock(data, create=False):
        if any(card.get("project") == project_key for card in learn._raw(data)):
            return True
        return any(row.get("kind") == "take" and row.get("project") == project_key
                   for _, row in learn._effective_log(learn._log(data)))
