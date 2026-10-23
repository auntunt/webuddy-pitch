"""Personal, revocable and project-scoped credentials for external tools.

The browser grants these credentials explicitly. A tool name is only a label:
identity is the authenticated owner, and no credential grants execution or human
approval. Secrets are returned once and never persisted in audit or receipts.
All callers protecting business work must retain authorization_guard through
that work and revalidate the signed connection inside the worker.
"""
import hashlib
import hmac
import json
import re
import secrets
import time

from .errors import ApiError
from .store import now

READ_OPERATIONS = (
    "status", "projects_list", "tickets_list", "ticket_get", "messages_list",
    "request_get", "run_get", "candidates_list", "candidate_get", "library_get",
    "library_search", "library_read", "preview_get",
)
CONTENT_OPERATIONS = ("ticket_create", "message_send")
DDL = (
    "CREATE TABLE IF NOT EXISTS tool_connections(id TEXT PRIMARY KEY,user TEXT NOT NULL,tenant TEXT NOT NULL,label TEXT NOT NULL,project_ids TEXT NOT NULL,scope TEXT NOT NULL,secret_hash TEXT NOT NULL,account_epoch TEXT NOT NULL,authority_hash TEXT NOT NULL,created TEXT NOT NULL,expires_at INTEGER NOT NULL,revoked_at TEXT NOT NULL DEFAULT '',revoke_reason TEXT NOT NULL DEFAULT '')",
    "CREATE TABLE IF NOT EXISTS tool_access_requests(user TEXT NOT NULL,tenant TEXT NOT NULL,request_id TEXT NOT NULL,fingerprint TEXT NOT NULL,action TEXT NOT NULL,connection_id TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(user,tenant,request_id))",
)


def schema(db):
    """Called by Registry within its atomic schema migration transaction."""
    for statement in DDL:
        db.execute(statement)


def allowed_operations(scope):
    if scope == "read":
        return READ_OPERATIONS
    if scope == "content":
        return READ_OPERATIONS + CONTENT_OPERATIONS
    return ()


def _error(code, message, reason="tool_access_denied"):
    error = ApiError(code, message)
    error.reason = reason
    return error


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value):
    return hashlib.sha256(_encoded(value).encode("utf-8")).hexdigest()


def context_token(record):
    """Bind a gateway request to this connection's immutable authority ceiling.

    This is a context digest, not authentication. The worker must first call
    validate_connection, which independently enforces current permission,
    revocation and expiry. Unrelated access_meta revisions are intentionally
    absent so other members' administrative changes cannot reject valid work.
    """
    bound = {key: record[key] for key in ("id", "user", "tenant", "scope", "expires_at")}
    bound["project_ids"] = sorted(record["project_ids"])
    return _digest(bound)


def _invalid():
    return _error(401, "工具连接已失效或无权访问；请在个人账号中检查连接授权", "tool_credential_invalid")


def _base_authorize(reg, user, tenant):
    from .tenancy import authorize
    return authorize(reg, user, tenant, "read")


def _authorize_projects(reg, user, tenant, projects, scope):
    from .tenancy import authorize
    _base_authorize(reg, user, tenant)
    for project in projects:
        authorize(reg, user, tenant, "read" if scope == "read" else "write", project)


def _authority(db, user, tenant, projects, scope):
    """Only the connection's effective authority, never global revision.

    This also detects out-of-band account epochs or permission loss. Normal
    mutations additionally revoke affected records atomically so a later grant
    cannot resurrect a credential after an intervening loss of authority.
    """
    account = db.execute("SELECT active,epoch FROM accounts WHERE name=?", (user,)).fetchone()
    target = db.execute("SELECT status FROM tenants WHERE id=?", (tenant,)).fetchone()
    membership = db.execute("SELECT role FROM memberships WHERE tenant_id=? AND user=?", (tenant, user)).fetchone()
    if not account or not account["active"] or not target or target["status"] != "active" or not membership:
        return None
    role = membership["role"]
    if role not in ("admin", "member", "viewer") or scope not in ("read", "content") or scope == "content" and role == "viewer":
        return None
    grants = []
    for project in projects:
        grant = db.execute("SELECT role FROM project_grants WHERE tenant_id=? AND project_id=? AND user=?", (tenant, str(project), user)).fetchone()
        effective = "admin" if role == "admin" else grant["role"] if grant else None
        if effective not in ("admin", "manager", "contributor", "viewer") or scope == "content" and effective == "viewer":
            return None
        grants.append((project, effective))
    return account["epoch"], _digest({"role": role, "projects": grants})


def _status(db, row):
    if row["revoked_at"]:
        return "revoked"
    if row["expires_at"] <= time.time():
        return "expired"
    current = _authority(db, row["user"], row["tenant"], json.loads(row["project_ids"]), row["scope"])
    if current is None or not hmac.compare_digest(current[0], row["account_epoch"]) or not hmac.compare_digest(current[1], row["authority_hash"]):
        return "invalidated"
    return "active"


def _public(db, row):
    status = _status(db, row)
    return {"id": row["id"], "user": row["user"], "tenant": row["tenant"],
            "label": row["label"], "project_ids": json.loads(row["project_ids"]),
            "scope": row["scope"], "created": row["created"], "expires_at": row["expires_at"],
            "status": status, "active": status == "active", "revoked_at": row["revoked_at"],
            "revoke_reason": row["revoke_reason"]}


def _body(body, action):
    if not isinstance(body, dict):
        raise _error(400, "工具连接请求必须是对象", "invalid_tool_request")
    fields = {"label", "project_ids", "scope", "expires_days"} if action == "create" else {"connection_id"}
    if set(body) - fields - {"action", "request_id"} or body.get("action", action) != action:
        raise _error(400, "工具连接请求包含未知字段或操作", "invalid_tool_request")
    request_id = body.get("request_id")
    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", request_id):
        raise _error(400, "需要稳定请求编号", "invalid_tool_request")
    if action == "create":
        label, projects, scope, days = (body.get(k) for k in ("label", "project_ids", "scope", "expires_days"))
        if not isinstance(label, str) or not label.strip() or len(label) > 120 or any(ord(c) < 32 for c in label):
            raise _error(400, "请填写工具名称（最多120字）", "invalid_tool_request")
        if not isinstance(projects, list) or not projects or any(type(p) is not int or p <= 0 or p > 9223372036854775807 for p in projects) or len(set(projects)) != len(projects):
            raise _error(400, "请选择不重复的有效项目编号", "invalid_tool_request")
        if scope not in ("read", "content"):
            raise _error(400, "工具连接只允许读取或限定内容操作", "invalid_tool_request")
        if type(days) is not int or not 1 <= days <= 30:
            raise _error(400, "连接期限应为1至30天", "invalid_tool_request")
    else:
        if not isinstance(body.get("connection_id"), str) or not re.fullmatch(r"[a-f0-9]{32}", body["connection_id"]):
            raise _error(400, "工具连接编号不正确", "invalid_tool_request")
    # Exact body fingerprint includes action. Unknown result retries must preserve
    # the request, not silently reinterpret a changed scope or expiry.
    return request_id, _digest({"action": action, "body": body})


def _old(db, user, tenant, request_id, fingerprint, action):
    old = db.execute("SELECT * FROM tool_access_requests WHERE user=? AND tenant=? AND request_id=?", (user, tenant, request_id)).fetchone()
    if old and (old["action"] != action or not hmac.compare_digest(old["fingerprint"], fingerprint)):
        raise _error(409, "请求编号已用于不同内容", "request_conflict")
    return old


def _audit(db, user, tenant, action, record, request_id):
    revision = db.execute("SELECT revision FROM access_meta WHERE id=1").fetchone()[0]
    payload = {"connection_id": record["id"], "scope": record["scope"], "project_ids": record["project_ids"], "request_id": request_id}
    db.execute("INSERT INTO access_audit(actor,action,tenant_id,payload,revision,created) VALUES(?,?,?,?,?,?)",
               (user, "tool_connection_" + action, tenant, _encoded(payload), revision, now()))


def _receipt(db, user, tenant, request_id, fingerprint, action, connection_id):
    db.execute("INSERT INTO tool_access_requests VALUES(?,?,?,?,?,?,?)", (user, tenant, request_id, fingerprint, action, connection_id, now()))


def create(reg, user, tenant, body):
    request_id, fingerprint = _body(body, "create")
    with reg.authorization_guard(), reg.transaction() as db:
        _authorize_projects(reg, user, tenant, body["project_ids"], body["scope"])
        old = _old(db, user, tenant, request_id, fingerprint, "create")
        if old:
            row = db.execute("SELECT * FROM tool_connections WHERE id=? AND user=? AND tenant=?", (old["connection_id"], user, tenant)).fetchone()
            if not row:
                raise _error(409, "原连接记录不可用，请检查个人连接列表", "connection_unavailable")
            return {"connection": _public(db, row), "connection_id": row["id"], "replayed": True, "credential_unavailable": True}
        projects = sorted(body["project_ids"])
        authority = _authority(db, user, tenant, projects, body["scope"])
        if not authority:
            raise _error(403, "当前项目授权不足")
        connection_id, secret = secrets.token_hex(16), secrets.token_urlsafe(32)
        token = "wbt_" + connection_id + "." + secret
        db.execute("INSERT INTO tool_connections(id,user,tenant,label,project_ids,scope,secret_hash,account_epoch,authority_hash,created,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (connection_id, user, tenant, body["label"].strip(), _encoded(projects), body["scope"], hashlib.sha256(token.encode("ascii")).hexdigest(), authority[0], authority[1], now(), int(time.time()) + body["expires_days"] * 86400))
        row = db.execute("SELECT * FROM tool_connections WHERE id=?", (connection_id,)).fetchone()
        record = _public(db, row)
        _audit(db, user, tenant, "create", record, request_id)
        _receipt(db, user, tenant, request_id, fingerprint, "create", connection_id)
        return {"connection": record, "token": token, "connection_id": connection_id, "replayed": False}


def listing(reg, user, tenant):
    with reg.authorization_guard(), reg.lock:
        _base_authorize(reg, user, tenant)
        rows = reg.db.execute("SELECT * FROM tool_connections WHERE user=? AND tenant=? ORDER BY created DESC,id DESC", (user, tenant)).fetchall()
        return {"connections": [_public(reg.db, row) for row in rows], "user": user, "tenant": tenant}


def revoke(reg, user, tenant, body):
    request_id, fingerprint = _body(body, "revoke")
    with reg.authorization_guard(), reg.transaction() as db:
        # Current membership is necessary; project loss must not prevent someone
        # from listing/revoking their own now-invalid credential.
        _base_authorize(reg, user, tenant)
        old = _old(db, user, tenant, request_id, fingerprint, "revoke")
        row = db.execute("SELECT * FROM tool_connections WHERE id=? AND user=? AND tenant=?", (body["connection_id"], user, tenant)).fetchone()
        if not row:
            raise _error(404, "没有这个个人工具连接", "connection_not_found")
        if old:
            return {"connection": _public(db, row), "connection_id": row["id"], "replayed": True}
        changed = not row["revoked_at"]
        if changed:
            db.execute("UPDATE tool_connections SET revoked_at=?,revoke_reason='owner_revoked' WHERE id=?", (now(), row["id"]))
            row = db.execute("SELECT * FROM tool_connections WHERE id=?", (row["id"],)).fetchone()
        record = _public(db, row)
        _audit(db, user, tenant, "revoke", record, request_id)
        _receipt(db, user, tenant, request_id, fingerprint, "revoke", row["id"])
        return {"connection": record, "connection_id": row["id"], "replayed": False, "changed": changed}


def authenticate(reg, tenant, bearer):
    if not isinstance(bearer, str) or not re.fullmatch(r"wbt_[a-f0-9]{32}\.[A-Za-z0-9_-]{43}", bearer):
        raise _invalid()
    connection_id = bearer[4:36]
    with reg.authorization_guard(), reg.lock:
        row = reg.db.execute("SELECT * FROM tool_connections WHERE id=? AND tenant=?", (connection_id, tenant)).fetchone()
        if not row or not hmac.compare_digest(row["secret_hash"], hashlib.sha256(bearer.encode("ascii")).hexdigest()):
            raise _invalid()
        record = _public(reg.db, row)
        if not record["active"]:
            raise _invalid()
        return record


def validate_connection(reg, tenant, connection_id, user):
    """Recheck the trusted gateway-signed identity at business execution time."""
    if not isinstance(connection_id, str) or not re.fullmatch(r"[a-f0-9]{32}", connection_id):
        raise _invalid()
    with reg.authorization_guard(), reg.lock:
        row = reg.db.execute("SELECT * FROM tool_connections WHERE id=? AND tenant=? AND user=?", (connection_id, tenant, user)).fetchone()
        if not row:
            raise _invalid()
        record = _public(reg.db, row)
        if not record["active"]:
            raise _invalid()
        return record


def invalidate_for_change(db, action, tenant, target_user, project_id=None):
    """Called inside the same transaction as the control-plane change.

    Inspect only affected members/projects and revoke only an actual authority
    change. Reapplying an identical grant or editing another member cannot make
    unrelated connections stale, while revoked credentials never revive.
    """
    if action in ("password_reset", "account_disable", "account_enable", "account_set", "account_remove"):
        where, values = "user=?", (target_user,)
    elif action in ("member_set", "member_remove", "project_grant", "project_revoke"):
        where, values = "tenant=? AND user=?", (tenant, target_user)
    elif action in ("tenant_disable", "tenant_enable"):
        where, values = "tenant=?", (tenant,)
    else:
        return
    rows = db.execute("SELECT * FROM tool_connections WHERE revoked_at='' AND " + where, values).fetchall()
    for row in rows:
        if action in ("project_grant", "project_revoke") and str(project_id) not in {str(p) for p in json.loads(row["project_ids"])}:
            continue
        current = _authority(db, row["user"], row["tenant"], json.loads(row["project_ids"]), row["scope"])
        if current is None or current != (row["account_epoch"], row["authority_hash"]):
            db.execute("UPDATE tool_connections SET revoked_at=?,revoke_reason=? WHERE id=?", (now(), "authorization_changed:" + action, row["id"]))
