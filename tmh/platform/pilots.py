"""Personal, versioned team trials. Recording is never business acceptance.

Lock order is Registry authorization -> Store -> SQLite transaction. No model,
Git command, URL fetch, worker, task transition or human decision is launched.
"""
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import uuid

from . import tenant_policy as TP, tool_read, signoff, project_library, metrics
from .errors import ApiError

DUTIES = {"requirements": "需求", "development": "研发", "testing": "测试", "delivery": "交付", "operations": "运维"}
ACTIVITIES = ("analysis", "implementation", "testing", "handoff", "rework", "operations", "other")
PROTOCOL = "team-pilot-recording-v1"
CALENDAR = timezone(timedelta(hours=8))
DDL = (
    "CREATE TABLE project_pilots(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id INTEGER NOT NULL,creator TEXT NOT NULL,created TEXT NOT NULL,current_revision INTEGER NOT NULL,version INTEGER NOT NULL)",
    "CREATE TABLE project_pilot_revisions(pilot_id TEXT NOT NULL,revision INTEGER NOT NULL,protocol TEXT NOT NULL,sources TEXT NOT NULL,protocol_hash TEXT NOT NULL,state TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(pilot_id,revision))",
    "CREATE TABLE project_pilot_events(id INTEGER PRIMARY KEY,pilot_id TEXT NOT NULL,revision INTEGER NOT NULL,kind TEXT NOT NULL,actor TEXT NOT NULL,request_id TEXT NOT NULL UNIQUE,fingerprint TEXT NOT NULL,payload TEXT NOT NULL,created TEXT NOT NULL)",
)


def encoded(v):
    try:
        text = json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        text.encode("utf-8")
        return text
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ApiError(400, "记录必须可以完整编码为有限 JSON") from exc


def digest(v):
    return hashlib.sha256(encoded(v).encode("utf-8")).hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat()


def today():
    # Calendar fields use the product's declared China time, not host TZ.
    return datetime.now(timezone.utc).astimezone(CALENDAR).date()


@contextmanager
def transaction(st):
    with st.lock:
        if st.db.in_transaction:
            raise ApiError(409, "不能在已有事务中登记试点")
        st.db.execute("BEGIN IMMEDIATE")
        try:
            yield st.db
            st.db.commit()
        except BaseException:
            st.db.rollback()
            raise


def schema(st):
    with transaction(st) as db:
        names = {r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        tables = {"project_pilots", "project_pilot_revisions", "project_pilot_events"}
        if names & tables and not tables <= names:
            raise ApiError(409, "试点记录结构不完整")
        if not names & tables:
            for sql in DDL:
                db.execute(sql)
        expected = {
            "project_pilots": set("id tenant_id project_id creator created current_revision version".split()),
            "project_pilot_revisions": set("pilot_id revision protocol sources protocol_hash state created".split()),
            "project_pilot_events": set("id pilot_id revision kind actor request_id fingerprint payload created".split()),
        }
        for table, columns in expected.items():
            info = list(db.execute("PRAGMA table_info(" + table + ")"))
            if not columns <= {x["name"] for x in info}:
                raise ApiError(409, "试点记录字段不完整")
            primary = {x["name"]: x["pk"] for x in info if x["pk"]}
            if primary != ({"pilot_id": 1, "revision": 2} if table == "project_pilot_revisions" else {"id": 1}):
                raise ApiError(409, "试点记录主键损坏")
        unique_request = False
        for idx in db.execute("PRAGMA index_list(project_pilot_events)"):
            if idx["unique"] and not idx["partial"]:
                name = idx["name"].replace('"', '""')
                unique_request |= [x["name"] for x in db.execute('PRAGMA index_info("' + name + '")')] == ["request_id"]
        if not unique_request:
            raise ApiError(409, "试点原请求唯一约束损坏")


def project(P, key):
    p = P.store.project(key)
    if not p:
        raise ApiError(404, "没有这个项目")
    return p


def _text(v, field):
    if not isinstance(v, str):
        raise ApiError(400, field + "必须为完整文本")
    try:
        v.encode("utf-8")
    except UnicodeError as exc:
        raise ApiError(400, field + "必须为有效 UTF-8 文本") from exc
    return v


def _fields(v, allowed):
    if not isinstance(v, dict) or set(v) - set(allowed):
        raise ApiError(400, "记录包含未知字段")


def _day(v):
    if not isinstance(v, str):
        raise ApiError(400, "日期必须为文本")
    try:
        if v and date.fromisoformat(v).isoformat() != v:
            raise ValueError()
    except ValueError as exc:
        raise ApiError(400, "日期应为 YYYY-MM-DD 或留空") from exc
    return v


def _decimal(v, positive=False):
    if v is None or v == "":
        return
    if not isinstance(v, str) or not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", v):
        raise ApiError(400, "数值应为非负十进制文本；未知请留空")
    try:
        if not Decimal(v).is_finite() or positive and Decimal(v) <= 0:
            raise InvalidOperation()
    except InvalidOperation as exc:
        raise ApiError(400, "数值不正确") from exc


def protocol(v):
    fields = ("title", "goal", "application_reference", "baseline_reference", "comparison", "inclusion_rule", "participants", "periods", "tasks", "targets", "followup_on", "exit_rule", "missing_rule", "model_budget_cny")
    _fields(v, fields)
    result = {k: _text(v.get(k, ""), k) for k in fields if k not in ("participants", "periods", "tasks", "targets", "model_budget_cny")}
    if result["comparison"] not in ("", "before_after", "parallel"):
        raise ApiError(400, "请选择前后对照或并行对照")
    _day(result["followup_on"])
    result["model_budget_cny"] = v.get("model_budget_cny")
    _decimal(result["model_budget_cny"], positive=True)
    for name in ("participants", "periods", "tasks"):
        if not isinstance(v.get(name, []), list):
            raise ApiError(400, name + "必须是列表")
        result[name] = json.loads(encoded(v.get(name, [])))
    seen = set()
    for row in result["participants"]:
        _fields(row, ("user", "duties"))
        user, duties = row.get("user"), row.get("duties")
        if not isinstance(user, str) or not user or user in seen or not isinstance(duties, list) or any(not isinstance(d, str) or d not in DUTIES for d in duties) or len(set(duties)) != len(duties):
            raise ApiError(400, "参与者应为不重复个人，职责必须有效")
        seen.add(user)
    seen = set()
    for row in result["periods"]:
        _fields(row, ("id", "name", "kind", "start_on", "end_on"))
        if not isinstance(row.get("id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", row["id"]) or row["id"] in seen or row.get("kind") not in ("baseline", "control", "trial"):
            raise ApiError(400, "阶段编号或类型不正确")
        seen.add(row["id"])
        _text(row.get("name", ""), "阶段名称")
        a, b = _day(row.get("start_on", "")), _day(row.get("end_on", ""))
        if a and b and a > b:
            raise ApiError(400, "阶段结束不能早于开始")
    seen = set()
    for row in result["tasks"]:
        _fields(row, ("ticket", "period", "complexity"))
        _text(row.get("ticket"), "工单")
        _text(row.get("period"), "所属阶段")
        row["complexity"] = _text(row.get("complexity", ""), "复杂度")
        if row["ticket"] in seen:
            raise ApiError(400, "同一工单只能纳入一次；不能重复计算分母")
        seen.add(row["ticket"])
    result["targets"] = v.get("targets", {})
    _fields(result["targets"], ("quality", "improvement", "cost_shift"))
    for row in result["targets"].values():
        _fields(row, ("metric", "direction", "value", "unit"))
        for k in ("metric", "direction", "unit"):
            _text(row.get(k, ""), k)
        if row.get("direction", "") not in ("", "at_most", "at_least"):
            raise ApiError(400, "目标方向不正确")
        _decimal(row.get("value", ""))
    return json.loads(encoded(result))


def _sources(P, p, spec):
    from .agent_api import _requirement
    result = {"project": p, "references": project_library.reference_state(P.store, p), "tickets": []}
    for item in spec["tasks"]:
        t = P.store.ticket(item["ticket"])
        if not t or t["project_id"] != p["id"]:
            raise ApiError(400, "固定全集只能选择本项目现有工单")
        original, records = tool_read.saved_lines(signoff.epath(P.data_dir, t["key"]))
        if original["jsonl_status"] != "complete":
            raise ApiError(409, "原工单合同无法完整读取；不能固定空合同")
        result["tickets"].append({"ticket": t, "events": P.store.events(t["id"]), "contract_original": original,
                                  "contracts": records, "requirement_hash": _requirement(t, P.store, contract_records=records)})
    return result


def _source_identity(s):
    return {"project": {k: s["project"].get(k) for k in ("id", "key", "root")}, "references": s["references"],
            "tickets": [(x["ticket"]["id"], x["ticket"]["key"], x["requirement_hash"]) for x in s["tickets"]]}


def _authority(P, p, user):
    who = TP.experiment_identity(P, user, p, "contributor")
    reg = P.tenant_context.registry
    relevant = []
    for row in reg.q("SELECT id,action,payload FROM access_audit WHERE tenant_id=? ORDER BY id", (who["tenant_id"],)):
        payload = json.loads(row["payload"])
        if row["action"] in ("tenant_disable", "tenant_enable") or (payload.get("user") == user and
            (row["action"] in ("member_set", "member_remove") or row["action"] in ("project_grant", "project_revoke") and str(payload.get("project_id")) == str(p["id"]))):
            relevant.append(row["id"])
    return digest({"epoch": who["account_epoch"], "events": relevant})


def _row(P, p, pid, rev=None):
    head = P.store.one("SELECT * FROM project_pilots WHERE id=? AND project_id=? AND tenant_id=?", (pid, p["id"], P.tenant_context.tenant_id))
    if not head:
        raise ApiError(404, "没有这个团队试点")
    revision = P.store.one("SELECT * FROM project_pilot_revisions WHERE pilot_id=? AND revision=?", (pid, rev or head["current_revision"]))
    if not revision:
        raise ApiError(404, "没有这个协议修订")
    r = dict(revision, protocol=json.loads(revision["protocol"]), sources=json.loads(revision["sources"]))
    if r["protocol_hash"] != digest({"schema": PROTOCOL, "protocol": r["protocol"], "sources": r["sources"]}):
        raise ApiError(409, "原协议或来源记录损坏，不能借旧摘要继续确认")
    return head, r


def _events(P, pid, revision=None):
    sql = "SELECT * FROM project_pilot_events WHERE pilot_id=?" + (" AND revision=?" if revision else "") + " ORDER BY id"
    return [dict(r, payload=json.loads(r["payload"])) for r in P.store.q(sql, (pid, revision) if revision else (pid,))]


def _checks(P, p, r):
    spec, missing = r["protocol"], []
    labels = {"title": "试点名称", "goal": "改善目标与质量约束", "application_reference": "项目版本依据", "baseline_reference": "对照来源与可比性说明", "comparison": "对照方式", "inclusion_rule": "任务纳入规则", "exit_rule": "退出规则", "missing_rule": "缺失处理规则", "followup_on": "后续观察终点"}
    for field in ("title", "goal", "application_reference", "baseline_reference", "comparison", "inclusion_rule", "exit_rule", "missing_rule", "followup_on"):
        if not spec[field].strip():
            missing.append("尚未填写" + labels[field])
    if not spec["model_budget_cny"]:
        missing.append("模型试点预算尚未明确（不会授权模型调用）")
    members = TP.eligible_members(P, p)
    participants = spec["participants"]
    if len(participants) < 2:
        missing.append("至少需要两位不同的真实个人参与者")
    if len({tuple(sorted(x["duties"])) for x in participants}) < 2:
        missing.append("至少需要不同职责的参与者")
    duties = set()
    for row in participants:
        duties.update(row["duties"])
        if not row["duties"] or row["user"] not in members:
            missing.append("参与者或职责当前不可用：" + row["user"])
    if duties != set(DUTIES):
        missing.append("需求、研发、测试、交付、运维职责尚未覆盖")
    periods = spec["periods"]
    complete = [x for x in periods if x.get("start_on") and x.get("end_on")]
    trials = sorted((x for x in complete if x["kind"] == "trial"), key=lambda x: x["start_on"])
    if len(complete) != len(periods) or len(trials) < 2 or not any(x["kind"] in ("baseline", "control") for x in complete):
        missing.append("需要完整对照阶段及至少两个试验周期")
    if any(a["end_on"] >= b["start_on"] for a, b in zip(trials, trials[1:])):
        missing.append("试验周期必须在日历上分离")
    controls = [x for x in complete if x["kind"] in ("baseline", "control")]
    if trials and controls:
        if spec["comparison"] == "before_after" and any(x["end_on"] >= trials[0]["start_on"] for x in controls):
            missing.append("前后对照的基线必须早于试验周期")
        if spec["comparison"] == "parallel" and not all(any(c["start_on"] <= t["start_on"] and c["end_on"] >= t["end_on"] for c in controls) for t in trials):
            missing.append("并行对照需要覆盖每个试验周期")
    if trials and spec["followup_on"] and spec["followup_on"] < trials[-1]["end_on"]:
        missing.append("后续观察终点早于试验结束")
    if not spec["tasks"]:
        missing.append("尚未登记固定任务全集")
    for row in spec["tasks"]:
        # Older successfully saved drafts may omit this optional text. Read
        # without rewriting the original protocol or its bound digest.
        if row["period"] not in {x["id"] for x in periods} or not row.get("complexity", "").strip():
            missing.append("工单阶段或复杂度未明确：" + row["ticket"])
    for key in ("quality", "improvement", "cost_shift"):
        target = spec["targets"].get(key, {})
        if any(target.get(k, "") in ("", None) for k in ("metric", "direction", "value", "unit")):
            missing.append("数值目标未明确：" + {"quality": "质量约束", "improvement": "改善目标", "cost_shift": "全角色负担上界"}[key])
    try:
        fresh = digest(_source_identity(_sources(P, p, spec))) == digest(_source_identity(r["sources"]))
    except (ApiError, OSError, ValueError):
        fresh = False
    if not fresh:
        missing.append("任务或引用依据已变化，请另存修订并重新确认")
    if any(not ref.get("available") for ref in r["sources"]["references"]):
        missing.append("固定引用中存在不可用授权，不能冻结为有效依据")
    return missing, fresh


def _confirmations(P, p, r, events):
    latest = {e["actor"]: e for e in events if e["kind"] == "confirm"}
    result = []
    for part in r["protocol"]["participants"]:
        e = latest.get(part["user"])
        try:
            effective = bool(e and e["payload"]["authority"] == _authority(P, p, part["user"]))
        except ApiError:
            effective = False
        result.append({"user": part["user"], "duties": part["duties"], "confirmed": effective,
                       "recorded_at": e["created"] if e else None, "stale": bool(e and not effective)})
    return result


def _receipt(head, r, event, replayed=False):
    return {"id": head["id"], "revision": r["revision"], "version": head["version"], "protocol_hash": r["protocol_hash"],
            "receipt": {"event_id": event["id"], "request_id": event["request_id"], "replayed": replayed,
                        "notice": "只证明该动作已登记；当前确认及来源请重新读取"}}


def listing(P, key, actor):
    p = project(P, key)
    with TP.experiment_guard(P, actor, p), P.store.lock:
        manager = _manager(P, p, actor)
        rows = P.store.q("SELECT h.id,h.version,r.revision,r.state,r.protocol FROM project_pilots h JOIN project_pilot_revisions r ON h.id=r.pilot_id AND h.current_revision=r.revision WHERE h.project_id=? AND h.tenant_id=? ORDER BY h.created DESC,h.id", (p["id"], P.tenant_context.tenant_id))
        return {"project": p["key"], "actor": actor, "can_manage": manager, "members": TP.eligible_members(P, p), "duties": DUTIES,
                "tickets": P.store.q("SELECT num,title,status FROM tickets WHERE project_id=? ORDER BY num", (p["id"],)),
                "items": [dict(x, protocol=json.loads(x["protocol"])) for x in rows], "schema": PROTOCOL}


def _manager(P, p, actor):
    try:
        TP.experiment_identity(P, actor, p, "manager")
        return True
    except ApiError:
        return False


def read(P, key, pid, actor, revision=None):
    p = project(P, key)
    with TP.experiment_guard(P, actor, p), P.store.lock:
        # A consistent SQLite read snapshot, without a business mutation.
        P.store.db.execute("SAVEPOINT pilot_read")
        try:
            head, r = _row(P, p, pid, revision)
            events = _events(P, pid, r["revision"])
            missing, fresh = _checks(P, p, r)
            confirms = _confirmations(P, p, r, events)
            return {"id": pid, "project": key, "actor": actor, "version": head["version"], "revision": r["revision"],
                    "current_revision": head["current_revision"], "protocol_hash": r["protocol_hash"], "state": r["state"], "protocol": r["protocol"],
                    "sources": r["sources"], "source_current": fresh, "missing": missing, "confirmations": confirms,
                    "can_manage": _manager(P, p, actor), "events": [{**e, "payload": {k: v for k, v in e["payload"].items() if k != "authority"}} for e in events],
                    "revisions": P.store.q("SELECT revision,protocol_hash,state,created FROM project_pilot_revisions WHERE pilot_id=? ORDER BY revision", (pid,)),
                    "report": _report(P, p, r, events, actor)}
        finally:
            P.store.db.execute("RELEASE pilot_read")


def _labor_events(events):
    work = [e for e in events if e["kind"] == "labor"]
    superseded = {e["payload"]["supersedes"] for e in work if e["payload"].get("supersedes")}
    return [e for e in work if e["id"] not in superseded]


def _moment(v):
    try:
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            raise ValueError()
        return dt
    except (TypeError, ValueError) as exc:
        raise ApiError(400, "开始时间需要明确时区") from exc


def _labor(P, r, events, actor, body):
    item = body.get("labor")
    _fields(item, ("ticket", "duty", "activity", "started_at", "minutes", "note", "evidence_refs", "zero_reason", "outside_reason", "supersedes"))
    value = dict(item)
    for k in ("ticket", "duty", "activity", "started_at", "note", "zero_reason", "outside_reason"):
        value[k] = _text(item.get(k, ""), k)
    part = next((x for x in r["protocol"]["participants"] if x["user"] == actor), None)
    task = next((x for x in r["protocol"]["tasks"] if x["ticket"] == value["ticket"]), None)
    if not part or value["duty"] not in part["duties"] or not task or value["activity"] not in ACTIVITIES:
        raise ApiError(403, "只能登记本人约定职责与固定全集中的任务")
    minutes = item.get("minutes")
    if type(minutes) is not int or minutes < 0 or minutes > 1440 or not value["note"].strip() or minutes == 0 and not value["zero_reason"].strip():
        raise ApiError(400, "请填写实际分钟（0–1440）及完整说明；0 需明确原因")
    refs = item.get("evidence_refs", [])
    if not isinstance(refs, list) or any(not isinstance(x, str) or not x.strip() for x in refs):
        raise ApiError(400, "证据引用必须为完整文本列表")
    value["evidence_refs"] = refs
    start = _moment(value["started_at"])
    end = start + timedelta(minutes=minutes)
    if end > _moment(stamp()):
        raise ApiError(400, "不能提前登记尚未发生的劳动")
    period = next(x for x in r["protocol"]["periods"] if x["id"] == task["period"])
    local_end_day = (end - timedelta(microseconds=1) if minutes else end).astimezone(CALENDAR).date().isoformat()
    value["outside_period"] = not (period["start_on"] <= start.astimezone(CALENDAR).date().isoformat() <= local_end_day <= period["end_on"])
    value["protocol_hash"] = r["protocol_hash"]
    value["declared_period"] = task["period"]
    value["allocation"] = "unallocated_outside_period" if value["outside_period"] else "assigned_period"
    if value["outside_period"] and not value["outside_reason"].strip():
        raise ApiError(400, "超出登记阶段的劳动需说明，不能伪装同期记录")
    value["retrospective"] = start.astimezone(CALENDAR).date().isoformat() < _moment(stamp()).astimezone(CALENDAR).date().isoformat() or r["state"] == "ended"
    oldid = item.get("supersedes")
    if oldid is not None and (type(oldid) is not int or oldid < 1):
        raise ApiError(400, "更正应引用原记录编号")
    own = _labor_events(events)
    if oldid and not any(e["id"] == oldid and e["actor"] == actor for e in own):
        raise ApiError(409, "只能追加更正本人当前有效记录")
    all_events = [dict(e, payload=json.loads(e["payload"])) for e in P.store.q("SELECT e.* FROM project_pilot_events e JOIN project_pilots p ON p.id=e.pilot_id WHERE e.kind='labor' AND e.actor=? AND p.tenant_id=?", (actor, P.tenant_context.tenant_id))]
    for e in _labor_events(all_events):
        if e["id"] == oldid:
            continue
        v = e["payload"]
        a = _moment(v["started_at"])
        b = a + timedelta(minutes=v["minutes"])
        if minutes and v["minutes"] and start < b and a < end:
            raise ApiError(409, "本人劳动时间与已有有效记录重叠；请更正而非重复累计")
    return value


def act(P, key, body, actor, pid=None):
    _fields(body, ("action", "request_id", "expected_actor", "version", "revision", "protocol_hash", "protocol", "labor", "ticket", "reason"))
    action = body.get("action")
    if action not in ("create", "revise", "confirm", "freeze", "start", "end", "labor", "exit"):
        raise ApiError(400, "未知试点操作")
    if (action == "create") != (pid is None):
        raise ApiError(400, "创建与既有试点入口不匹配")
    rid = body.get("request_id")
    if not isinstance(rid, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", rid):
        raise ApiError(400, "需要稳定请求编号")
    if body.get("expected_actor") != actor:
        raise ApiError(409, "当前个人身份与读页面时不同，请重新读取")
    p = project(P, key)
    level = "manager" if action in ("create", "revise", "freeze", "start", "end", "exit") else "contributor"
    fingerprint = digest({"project": p["id"], "pilot": pid, "actor": actor, "body": body})
    # Request IDs are global within this tenant, including creators and projects.
    # Reauthorization precedes lookup; collisions never disclose other receipts.
    with TP.experiment_guard(P, actor, p, level), transaction(P.store) as db:
        old = P.store.one("SELECT * FROM project_pilot_events WHERE request_id=?", (rid,))
        if old:
            if old["actor"] != actor or old["fingerprint"] != fingerprint:
                raise ApiError(409, "请求编号已用于不同动作或正文")
            head, r = _row(P, p, old["pilot_id"], old["revision"])
            return _receipt(head, r, old, True)
        if action == "create":
            if type(body.get("version")) is not int or type(body.get("revision")) is not int or body.get("version") != 0 or body.get("revision") != 0 or body.get("protocol_hash") != "":
                raise ApiError(409, "新试点应从空版本开始")
            pid = uuid.uuid4().hex
            db.execute("INSERT INTO project_pilots VALUES(?,?,?,?,?,?,?)", (pid, P.tenant_context.tenant_id, p["id"], actor, stamp(), 0, 0))
            head = P.store.one("SELECT * FROM project_pilots WHERE id=?", (pid,))
        else:
            if type(body.get("version")) is not int or type(body.get("revision")) is not int or body["revision"] < 1:
                raise ApiError(409, "需要阅读时的确切协议版本")
            # A later draft must not strand the previous active trial's effort
            # or explicit end. Those events still bind its immutable revision.
            target = body["revision"] if action in ("labor", "end", "exit") else None
            head, r = _row(P, p, pid, target)
            if (body["version"], body["revision"], body.get("protocol_hash")) != (head["version"], r["revision"], r["protocol_hash"]):
                raise ApiError(409, "试点或协议已变化，请保留草稿并重新读取")
        payload = {}
        if action in ("create", "revise"):
            spec = protocol(body.get("protocol", {}))
            sources = _sources(P, p, spec)
            rev = head["current_revision"] + 1
            ph = digest({"schema": PROTOCOL, "protocol": spec, "sources": sources})
            db.execute("INSERT INTO project_pilot_revisions VALUES(?,?,?,?,?,?,?)", (pid, rev, encoded(spec), encoded(sources), ph, "draft", stamp()))
            db.execute("UPDATE project_pilots SET current_revision=? WHERE id=?", (rev, pid))
            payload = {"protocol_hash": ph}
        else:
            rev, state = r["revision"], r["state"]
            events = _events(P, pid, rev)
            if action == "confirm":
                if state != "draft" or actor not in {x["user"] for x in r["protocol"]["participants"]}:
                    raise ApiError(403, "只能由协议参与者本人确认当前草稿")
                if not _checks(P, p, r)[1]:
                    raise ApiError(409, "原依据已变化，不能确认旧协议")
                payload = {"authority": _authority(P, p, actor), "protocol_hash": r["protocol_hash"]}
            elif action == "freeze":
                missing, fresh = _checks(P, p, r)
                trials = [x["start_on"] for x in r["protocol"]["periods"] if x["kind"] == "trial" and x.get("start_on")]
                if state != "draft" or missing or not all(x["confirmed"] for x in _confirmations(P, p, r, events)) or not trials or min(trials) <= today().isoformat():
                    raise ApiError(409, "冻结需要完整协议、当前本人确认，且早于首个试验日：" + "；".join(missing))
                db.execute("UPDATE project_pilot_revisions SET state='frozen' WHERE pilot_id=? AND revision=?", (pid, rev))
            elif action in ("start", "end"):
                expected, new = ("frozen", "active") if action == "start" else ("active", "ended")
                if state != expected:
                    raise ApiError(409, "当前协议状态不允许此操作")
                if action == "start" and (not _checks(P, p, r)[1] or not all(x["confirmed"] for x in _confirmations(P, p, r, events))):
                    raise ApiError(409, "来源或参与者确认已失效，需要另存修订")
                db.execute("UPDATE project_pilot_revisions SET state=? WHERE pilot_id=? AND revision=?", (new, pid, rev))
            elif action == "labor":
                if state not in ("active", "ended"):
                    raise ApiError(409, "只能在明确开始记录后登记投入")
                payload = _labor(P, r, events, actor, body)
            elif action == "exit":
                if state not in ("active", "ended") or body.get("ticket") not in {x["ticket"] for x in r["protocol"]["tasks"]} or not isinstance(body.get("reason"), str) or not body["reason"].strip():
                    raise ApiError(400, "任务退出需绑定固定任务并保留完整原因")
                payload = {"ticket": body["ticket"], "reason": body["reason"]}
        eventid = db.execute("INSERT INTO project_pilot_events(pilot_id,revision,kind,actor,request_id,fingerprint,payload,created) VALUES(?,?,?,?,?,?,?,?)", (pid, rev, action, actor, rid, fingerprint, encoded(payload), stamp())).lastrowid
        db.execute("UPDATE project_pilots SET version=version+1 WHERE id=?", (pid,))
        head, r = _row(P, p, pid, rev)
        return _receipt(head, r, P.store.one("SELECT * FROM project_pilot_events WHERE id=?", (eventid,)))


def _waiting(events, observed):
    """Union recorded waiting intervals; no handoff evidence means unknown."""
    by = {}
    for e in events:
        by.setdefault(e["handoff_id"], []).append(e)
    spans, open_wait = [], False
    try:
        for history in by.values():
            if history[0]["status"] != "waiting":
                raise ValueError("missing initial handoff source")
            start = None
            previous = None
            for e in history:
                dt = datetime.fromtimestamp(metrics._t(metrics.ts_norm(e["ts"])), timezone.utc)
                if previous and dt < previous:
                    raise ValueError("out of order handoff clock")
                previous = dt
                # Blocking work already received is not waiting for receipt.
                waiting = e["status"] == "waiting" or e["status"] == "blocked" and start is not None
                if waiting and start is None:
                    start = dt
                elif not waiting and start is not None:
                    if dt < start:
                        raise ValueError()
                    spans.append((start, dt))
                    start = None
            if start:
                if observed < start:
                    raise ValueError()
                spans.append((start, observed))
                open_wait = True
        merged = []
        for a, b in sorted(spans):
            if merged and a <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
            else:
                merged.append((a, b))
        return {"seconds": sum((b-a).total_seconds() for a, b in merged) if events else None, "status": "observed_open" if open_wait else "recorded" if events else "unknown"}
    except (ValueError, TypeError, OverflowError):
        return {"seconds": None, "status": "unknown_invalid_timestamps"}


def _report(P, p, r, events, actor):
    labor = _labor_events(events)
    report = {"schema": PROTOCOL, "observed_at": stamp(), "protocol_hash": r["protocol_hash"], "revision": r["revision"],
              "scope": "本人申报与已存来源；不证明因果收益或技术验收", "tasks": [], "labor": labor,
              "actual_model_cost": {"status": "unknown", "amount": None, "currency": "CNY"}, "improvement_percent": None,
              "hold_days": metrics.HOLD_DAYS, "periods": r["protocol"]["periods"], "participants": r["protocol"]["participants"]}
    report["event_range"] = {"first": events[0]["id"] if events else None, "last": events[-1]["id"] if events else None, "count": len(events)}
    report["completeness"] = {"status": "unknown", "reason": "没有逐人完整填报声明或NA核对；存在记录不等于全部投入完整",
                              "expected_scope": "固定任务×该任务阶段×所有登记参与者的职责；阶段外未分配不填补阶段内缺失",
                              "na_rule": "本批不以经理代录、未填或0分钟自动推定不适用"}
    # Only public decision metadata, never private evaluator/report payloads.
    report["project_learning_decisions"] = P.store.q("SELECT id,kind,origin_id,revision_id,action,actor,status,created FROM learning_decisions WHERE project_id=? ORDER BY created,id", (p["id"],))
    observed = _moment(report["observed_at"])
    for item in r["protocol"]["tasks"]:
        frozen = next(x for x in r["sources"]["tickets"] if x["ticket"]["key"] == item["ticket"])
        t = P.store.ticket(frozen["ticket"]["id"])
        available = bool(t and t["project_id"] == p["id"] and t["key"] == item["ticket"])
        evs = P.store.events(t["id"]) if available else []
        # Reuse the existing protected experiment projection; a corrupt managed
        # run attached to a ticket must fail closed, never leak private assets.
        runs = [tool_read.run_get(P, row["id"], 0, [p["id"]], actor) for row in P.store.q("SELECT id FROM runs WHERE ticket_id=? AND project_id=? ORDER BY id", (t["id"], p["id"]))] if available else []
        handoffs = tool_read.rows(P.store, "ticket_handoff_events", "WHERE ticket_id=? ORDER BY id", (t["id"],)) if available else []
        accepted = [e for e in evs if e["kind"] == "accept"]
        # Match metrics.compute: reacceptance cannot erase a return during the
        # fourteen days after the first recorded acceptance.
        accepted_at = accepted[0]["ts"] if accepted else None
        hours = metrics._hours(metrics.ts_norm(accepted_at), metrics.ts_norm(report["observed_at"])) if accepted_at else None
        maturity = "unknown" if not available else "not_accepted" if not accepted_at else "unknown" if hours is None else "pending" if hours < metrics.HOLD_DAYS * 24 else "matured"
        coverage = []
        for part in r["protocol"]["participants"]:
            for duty in part["duties"]:
                records = [e for e in labor if e["actor"] == part["user"] and e["payload"]["ticket"] == item["ticket"] and e["payload"]["duty"] == duty]
                inside = [e for e in records if not e["payload"]["outside_period"]]
                outside = [e for e in records if e["payload"]["outside_period"]]
                coverage.append({"user": part["user"], "duty": duty, "minutes": sum(e["payload"]["minutes"] for e in records) if records else None,
                                 "in_period_minutes": sum(e["payload"]["minutes"] for e in inside) if inside else None,
                                 "outside_period_minutes": sum(e["payload"]["minutes"] for e in outside) if outside else None,
                                 "record_ids": [e["id"] for e in records]})
        report["tasks"].append({**item, "current_available": available, "current_ticket": t if available else None, "frozen_source": frozen,
                                "events": evs, "runs": runs, "handoff_events": handoffs,
                                "handoff_materials": tool_read.rows(P.store, "ticket_handoffs", "WHERE ticket_id=? ORDER BY id", (t["id"],)) if available else [],
                                "candidates": [tool_read.candidate(P, c["id"], [p["id"]]) for c in tool_read.rows(P.store, "code_candidates", "WHERE ticket_id=? ORDER BY id", (t["id"],))] if available else [],
                                "waiting": _waiting(handoffs, observed),
                                "coverage": coverage, "exits": [e for e in events if e["kind"] == "exit" and e["payload"]["ticket"] == item["ticket"]],
                                "acceptance": {"status": maturity, "recorded_at": accepted_at, "latest_recorded_at": accepted[-1]["ts"] if accepted else None, "recorded_only": True,
                                               "reopened": metrics._reopened(evs, accepted_at) if accepted_at else None}})
    report["task_count"] = len(report["tasks"])
    report["missing_labor_cells"] = sum(x["in_period_minutes"] is None for t in report["tasks"] for x in t["coverage"])
    report["recorded_minutes"] = sum(e["payload"]["minutes"] for e in labor)
    report["outside_period_minutes"] = sum(e["payload"]["minutes"] for e in labor if e["payload"]["outside_period"])
    report["retrospective_minutes"] = sum(e["payload"]["minutes"] for e in labor if e["payload"]["retrospective"])
    report["notice"] = "只累计已申报劳动；缺失不按0，等待不计劳动，退出及失败不缩分母。预算是声明，不授权模型或证明实付。"
    report["source_read_interval"] = {"started_at": report["observed_at"], "finished_at": stamp(),
                                     "scope": "数据库一致读快照；文件为此读取区间内的完整历史原件，不声明跨文件原子快照"}
    report["snapshot_sha256"] = digest(report)
    return report


def markdown(view):
    # Full JSON in a Markdown fence preserves every original field and history.
    # A dynamic fence prevents embedded user backticks escaping the data block.
    raw = json.dumps(view, ensure_ascii=False, indent=2, allow_nan=False)
    fence = "`" * max(3, max((len(x) for x in re.findall(r"`+", raw)), default=0) + 1)
    r = view["report"]
    summary = ("# 团队试点完整阶段记录\n\n报告截点：%s\n\n固定任务 %s 项；已申报 %s 分钟；阶段外 %s 分钟。"
               "填报完整性、实费和收益仍待核证。\n\n缺失、失败、退出与未成熟均保留；不据此证明组织收益。\n\n" %
               (r["observed_at"], r["task_count"], r["recorded_minutes"], r["outside_period_minutes"]))
    return summary + fence + "json\n" + raw + "\n" + fence + "\n"
