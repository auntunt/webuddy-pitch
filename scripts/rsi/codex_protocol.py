"""Strict, non-executing contract for Codex CLI observation files.

This version cannot register work, qualify an experiment or authorize adoption.
The caller must supply an independently retained manifest digest. File hashes
bind bytes; they do not establish official-client provenance or isolation.
"""
import hashlib
import json
import math
import re

SCHEMA = "codex-learning-observation-v1"
CONTRACT = "codex-learning-finite-v1"
STOPPED_ROOT = "b2a6c8da32006e9ac45a3a5ff50bc5ae07e382ddf02480a6858dfe278aea5ed9"


class InvalidEvidence(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InvalidEvidence(message)


def fields(value, names):
    require(isinstance(value, dict) and set(value) == set(names), "unexpected or missing fields")


def text(value):
    require(isinstance(value, str) and bool(value.strip()), "nonempty text required")


def sha(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None, "sha256 required")


def integer(value, minimum=0):
    require(type(value) is int and value >= minimum, "integer required")


def seconds(value):
    require(type(value) in (int, float) and math.isfinite(value) and value > 0, "positive finite seconds required")


def strict(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON field")
            result[key] = value
        return result
    def finite(number):
        value = float(number)
        require(math.isfinite(value), "nonfinite JSON number")
        return value
    try:
        return json.loads(raw, object_pairs_hook=unique,
                          parse_float=finite,
                          parse_constant=lambda _: require(False, "nonfinite JSON number"))
    except (UnicodeError, ValueError, TypeError) as exc:
        raise InvalidEvidence("invalid strict JSON") from exc


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def validate_contract(value):
    fields(value, ("schema", "root_id", "tenant", "project_id", "application_commit",
                   "baseline_sha256", "candidate_sha256", "client", "limits", "accounting"))
    require(value["schema"] == CONTRACT, "unsupported Codex contract")
    sha(value["root_id"])
    require(value["root_id"] != STOPPED_ROOT, "stopped root cannot be reused")
    text(value["tenant"])
    integer(value["project_id"], 1)
    require(isinstance(value["application_commit"], str) and
            re.fullmatch(r"[0-9a-f]{40}", value["application_commit"]) is not None, "fixed application commit required")
    for key in ("baseline_sha256", "candidate_sha256"):
        sha(value[key])
    require(value["baseline_sha256"] != value["candidate_sha256"], "distinct rule versions required")
    client = value["client"]
    fields(client, ("engine", "requested_model", "profile_sha256", "executable_sha256"))
    require(client["engine"] == "codex", "official Codex protocol required")
    text(client["requested_model"])
    sha(client["profile_sha256"])
    sha(client["executable_sha256"])
    fields(value["limits"], ("max_outer_starts", "total_timeout_seconds"))
    integer(value["limits"]["max_outer_starts"], 1)
    seconds(value["limits"]["total_timeout_seconds"])
    fields(value["accounting"], ("unit", "total_tokens_cap", "total_cost_cap"))
    require(value["accounting"] == {"unit": "cli_outer_start", "total_tokens_cap": None,
                                    "total_cost_cap": None}, "finite outer starts; token and cost caps waived")
    return value
