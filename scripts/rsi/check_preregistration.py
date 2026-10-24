#!/usr/bin/env python3
"""Read-only lint of RSI/pilot declarations. Never grants execution authority."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

SCHEMA = "rsi-preregistration-v1"
SCHEMA_V2 = "rsi-preregistration-v2"
ROLES = {"requirement", "development", "testing", "delivery", "operations"}


def _pairs(rows):
    result = {}
    for key, value in rows:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("non-finite JSON constant")


def loads(raw):
    return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)


class Check:
    def __init__(self):
        self.errors = []
        self.blockers = []

    def obj(self, value, fields, path):
        if not isinstance(value, dict):
            self.errors.append(path + ": object required")
            return {}
        if set(value) != set(fields):
            self.errors.append(path + ": exact declared fields required")
        return value

    def text(self, value, path, pattern=None):
        if value is None or value == "":
            self.blockers.append(path + ": not declared")
            return None
        if not isinstance(value, str) or not value.strip() or value != value.strip() or (pattern and not re.fullmatch(pattern, value)):
            self.errors.append(path + ": invalid text")
            return None
        return value

    def rows(self, value, path, minimum):
        if not isinstance(value, list):
            self.errors.append(path + ": list required")
            return []
        if len(value) < minimum:
            self.blockers.append(path + ": insufficient declarations")
        return value

    def positive(self, value, path):
        if value is None:
            self.blockers.append(path + ": not declared")
            return None
        if type(value) is not int or value <= 0:
            self.errors.append(path + ": positive integer required")
            return None
        return value

    def stamp(self, value, path):
        value = self.text(value, path)
        if value is None:
            return None
        try:
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if stamp.utcoffset() is None:
                raise ValueError("timezone required")
            return stamp
        except ValueError:
            self.errors.append(path + ": timezone-aware ISO timestamp required")
            return None


def check(value):
    """Check declarations only; evidence hashes are references, not verification."""
    c = Check()
    is_v2 = isinstance(value, dict) and value.get("schema") == SCHEMA_V2
    root_fields = ("schema", "application", "strategy", "evaluation", "model", "budget", "pilot", "protocol")
    root = c.obj(value, root_fields + (("trial_policy", "effect", "pilot_window") if is_v2 else ()), "root")
    if root.get("schema") not in (SCHEMA, SCHEMA_V2):
        c.errors.append("schema: unsupported")
    app = c.obj(root.get("application"), ("project_key", "commit"), "application")
    c.text(app.get("project_key"), "application.project_key")
    c.text(app.get("commit"), "application.commit", r"[0-9a-f]{40}")
    strategy = c.obj(root.get("strategy"), ("baseline_revision", "candidate_revision", "training_source_family"), "strategy")
    base = c.text(strategy.get("baseline_revision"), "strategy.baseline_revision")
    candidate = c.text(strategy.get("candidate_revision"), "strategy.candidate_revision")
    training = c.text(strategy.get("training_source_family"), "strategy.training_source_family")
    if base is not None and candidate == base:
        c.errors.append("strategy: baseline and candidate must differ")
    ev = c.obj(root.get("evaluation"), ("task_families", "holdout_cases", "followup_source_family", "custodian", "optimizer"), "evaluation")
    families = c.rows(ev.get("task_families"), "evaluation.task_families", 2)
    family_ids = [c.text(f, "evaluation.task_families[]") for f in families]
    known = [f for f in family_ids if f is not None]
    if len(set(known)) != len(known):
        c.errors.append("evaluation.task_families: duplicate family")
    followup = c.text(ev.get("followup_source_family"), "evaluation.followup_source_family")
    if (training is not None and training in known) or (followup is not None and (followup in known or followup == training)):
        c.errors.append("evaluation: training, holdout and followup families must be disjoint")
    custodian = c.text(ev.get("custodian"), "evaluation.custodian")
    optimizer = c.text(ev.get("optimizer"), "evaluation.optimizer")
    if custodian is not None and custodian == optimizer:
        c.errors.append("evaluation: optimizer cannot be holdout custodian")
    cases = c.rows(ev.get("holdout_cases"), "evaluation.holdout_cases", 3)
    ids, inputs, used = set(), set(), set()
    for row in cases:
        row = c.obj(row, ("id", "source_family", "input_sha256"), "evaluation.holdout_cases[]")
        cid = c.text(row.get("id"), "evaluation.holdout_cases[].id")
        family = c.text(row.get("source_family"), "evaluation.holdout_cases[].source_family")
        ih = c.text(row.get("input_sha256"), "evaluation.holdout_cases[].input_sha256", r"[0-9a-f]{64}")
        if cid is not None:
            if cid in ids:
                c.errors.append("evaluation.holdout_cases: duplicate id")
            ids.add(cid)
        if ih is not None:
            if ih in inputs:
                c.errors.append("evaluation.holdout_cases: duplicate input hash")
            inputs.add(ih)
        if family is not None:
            if family not in known:
                c.errors.append("evaluation.holdout_cases: undeclared family")
            used.add(family)
    if set(known) - used:
        c.blockers.append("evaluation.holdout_cases: declared family has no case")
    model_fields = ("profile_ref", "provider", "requested_model", "response_model", "identity_evidence_sha256", "metering_capability_evidence_sha256", "price_upper_bound_evidence_sha256", "provider_cap_evidence_sha256")
    model = c.obj(root.get("model"), model_fields, "model")
    for field in model_fields:
        c.text(model.get(field), "model." + field, r"[0-9a-f]{64}" if field.endswith("_sha256") else None)
    budget_fields = ("max_calls", "max_billed_tokens", "max_cost_micro_cny", "timeout_seconds")
    budget = c.obj(root.get("budget"), budget_fields, "budget")
    limits = {f: c.positive(budget.get(f), "budget." + f) for f in budget_fields}
    if limits["max_calls"] is not None and limits["max_calls"] < 2 * len(cases) + 2:
        c.errors.append("budget.max_calls: must cover both arms, one proposal and followup; judges/retries also require reservation")
    pilot_fields = ("participants", "cycles", "task_manifest_sha256", "baseline_manifest_sha256", "quality_targets")
    pilot = c.obj(root.get("pilot"), pilot_fields, "pilot")
    people = c.rows(pilot.get("participants"), "pilot.participants", 2)
    users, roles = set(), set()
    for row in people:
        row = c.obj(row, ("user_id", "roles", "consent_evidence_sha256"), "pilot.participants[]")
        user = c.text(row.get("user_id"), "pilot.participants[].user_id")
        if user is not None:
            if user in users:
                c.errors.append("pilot.participants: duplicate user")
            users.add(user)
        person_roles = c.rows(row.get("roles"), "pilot.participants[].roles", 1)
        for role in person_roles:
            if not isinstance(role, str) or role not in ROLES:
                c.errors.append("pilot.participants[].roles: unknown role")
            else:
                roles.add(role)
        c.text(row.get("consent_evidence_sha256"), "pilot.participants[].consent_evidence_sha256", r"[0-9a-f]{64}")
    if roles != ROLES:
        c.blockers.append("pilot.participants: all five delivery roles need responsible members")
    cycles = c.rows(pilot.get("cycles"), "pilot.cycles", 2)
    previous = None
    for row in cycles:
        row = c.obj(row, ("starts_at", "ends_at"), "pilot.cycles[]")
        start, end = (c.stamp(row.get(f), "pilot.cycles[]." + f) for f in ("starts_at", "ends_at"))
        if start is not None and end is not None:
            if start >= end or (previous is not None and start < previous):
                c.errors.append("pilot.cycles: positive ordered non-overlapping periods required")
            previous = end
    for field in ("task_manifest_sha256", "baseline_manifest_sha256"):
        c.text(pilot.get(field), "pilot." + field, r"[0-9a-f]{64}")
    c.text(pilot.get("quality_targets"), "pilot.quality_targets")
    protocol_fields = ("review_evidence_sha256", "scoring_protocol_sha256", "evaluation_protocol_sha256", "isolation_evidence_sha256", "prompt_parity_evidence_sha256")
    protocol = c.obj(root.get("protocol"), protocol_fields, "protocol")
    for field in protocol_fields:
        c.text(protocol.get(field), "protocol." + field, r"[0-9a-f]{64}")
    if is_v2:
        _v2(c, root, cases, pilot)
    return {"schema": SCHEMA_V2 if is_v2 else SCHEMA, "status": "invalid" if c.errors else "blocked" if c.blockers else "declared_complete",
            "errors": c.errors, "blockers": c.blockers, "execution_authorized": False, "evidence_verified": False,
            "score": None, "boundary": "Declarations only: hashes, identities, consent, isolation and accounting are not verified; no model call or production mutation is authorized."}



def _v2(c, root, cases, pilot):
    policy = c.obj(root.get("trial_policy"), ("selection_mode", "terminal_consumption", "root_budget_owner", "all_calls_in_root_budget", "all_started_denominator", "core_revoke_required", "fallback"), "trial_policy")
    required = {"selection_mode": "single_candidate_before_BC", "terminal_consumption": "once_per_root_family", "all_calls_in_root_budget": True, "all_started_denominator": True, "core_revoke_required": True, "fallback": "retain_baseline_without_adoption"}
    for key, expected in required.items():
        value = policy.get(key)
        if value is None:
            c.blockers.append("trial_policy." + key + ": not declared")
        elif type(value) is not type(expected) or value != expected:
            c.errors.append("trial_policy." + key + ": incompatible selection/denominator rule")
    c.text(policy.get("root_budget_owner"), "trial_policy.root_budget_owner")
    fields = ("mode", "primary_metric", "metric_unit", "gain_metric", "minimum_gain_micro_units", "quality_margin_micro_units", "max_cost_micro_cny", "max_latency_ms", "minimum_samples", "evaluator_evidence_sha256", "production_input_equivalence_sha256")
    effect = c.obj(root.get("effect"), fields, "effect")
    mode = c.text(effect.get("mode"), "effect.mode")
    gain = c.text(effect.get("gain_metric"), "effect.gain_metric")
    if mode is not None and mode not in {"quality_gain", "quality_noninferior_plus_cost_or_time_gain"}:
        c.errors.append("effect.mode: unsupported")
    if gain is not None and gain not in {"quality", "total_cost", "total_time"}:
        c.errors.append("effect.gain_metric: unsupported")
    if mode is not None and gain is not None and (mode == "quality_gain") != (gain == "quality"):
        c.errors.append("effect: selected gain must match predeclared mode")
    for key in ("primary_metric", "metric_unit"):
        c.text(effect.get(key), "effect." + key)
    for key in ("minimum_gain_micro_units", "max_cost_micro_cny", "max_latency_ms", "minimum_samples"):
        c.positive(effect.get(key), "effect." + key)
    margin = effect.get("quality_margin_micro_units")
    if margin is None:c.blockers.append("effect.quality_margin_micro_units: not declared")
    elif type(margin) is not int or margin < 0:c.errors.append("effect.quality_margin_micro_units: nonnegative integer required")
    minimum = effect.get("minimum_samples")
    if type(minimum) is int:
        if minimum < 3:c.errors.append("effect.minimum_samples: cannot weaken existing minimum")
        elif len(cases) < minimum:c.blockers.append("effect.minimum_samples: insufficient declared cases")
    for key in ("evaluator_evidence_sha256", "production_input_equivalence_sha256"):
        c.text(effect.get(key), "effect." + key, r"[0-9a-f]{64}")
    fields = ("calendar_start", "phase_end", "followup_end", "minimum_tasks", "minimum_cycles", "task_universe_sha256", "benefit_metric", "measurement_unit", "minimum_benefit_micro_units", "role_cost_shift_limit_micro_units", "baseline_comparability_sha256")
    window = c.obj(root.get("pilot_window"), fields, "pilot_window")
    stamps = [c.stamp(window.get(key), "pilot_window." + key) for key in ("calendar_start", "phase_end", "followup_end")]
    if all(stamp is not None for stamp in stamps) and not stamps[0] < stamps[1] < stamps[2]:
        c.errors.append("pilot_window: positive ordered calendar endpoints required")
    for key in ("minimum_tasks", "minimum_cycles", "minimum_benefit_micro_units"):
        c.positive(window.get(key), "pilot_window." + key)
    cycles = window.get("minimum_cycles")
    if type(cycles) is int:
        if cycles < 2:c.errors.append("pilot_window.minimum_cycles: at least two complete cycles")
        elif isinstance(pilot.get("cycles"), list) and len(pilot["cycles"]) < cycles:c.blockers.append("pilot_window.minimum_cycles: insufficient cycle declarations")
    shift = window.get("role_cost_shift_limit_micro_units")
    if shift is None:c.blockers.append("pilot_window.role_cost_shift_limit_micro_units: not declared")
    elif type(shift) is not int or shift < 0:c.errors.append("pilot_window.role_cost_shift_limit_micro_units: nonnegative integer required")
    for key in ("benefit_metric", "measurement_unit"):
        c.text(window.get(key), "pilot_window." + key)
    for key in ("task_universe_sha256", "baseline_comparability_sha256"):
        c.text(window.get(key), "pilot_window." + key, r"[0-9a-f]{64}")
    if window.get("task_universe_sha256") is not None and window.get("task_universe_sha256") != pilot.get("task_manifest_sha256"):
        c.errors.append("pilot_window: full task universe must match pilot task manifest")
    if stamps[0] is not None and stamps[1] is not None:
        for row in pilot.get("cycles", []) if isinstance(pilot.get("cycles"), list) else []:
            if not isinstance(row, dict):continue
            start, end = c.stamp(row.get("starts_at"), "pilot.cycles[].starts_at"), c.stamp(row.get("ends_at"), "pilot.cycles[].ends_at")
            if start is not None and end is not None and (start < stamps[0] or end > stamps[1]):
                c.errors.append("pilot_window: complete cycles must lie inside registered phase")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("protocol", type=Path)
    args = parser.parse_args(argv)
    raw = None
    try:
        raw = args.protocol.read_bytes()
        result = check(loads(raw))
    except (OSError, ValueError, UnicodeError, RecursionError):
        result = {"schema": SCHEMA, "status": "invalid", "errors": ["strict JSON document required"],
                  "blockers": [], "execution_authorized": False, "evidence_verified": False, "score": None}
    result["document_sha256"] = hashlib.sha256(raw).hexdigest() if raw is not None else None
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return {"invalid": 2, "blocked": 1, "declared_complete": 0}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
