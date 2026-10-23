"""Independent tenant control plane. Business stores and human signoffs stay separate.

The registry owns accounts and permissions transactionally after an explicit
bootstrap. Merely constructing it never constructs a Platform or starts a worker.
"""
from contextlib import closing, contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading

from . import filelock, signoff
from .errors import ApiError
from .store import now

TENANT_ROLES = ("admin", "member", "viewer")
PROJECT_ROLES = ("manager", "contributor", "viewer")
ACTIONS = ("tenant_create", "tenant_rename", "tenant_disable", "tenant_enable", "member_set", "member_remove",
           "project_grant", "project_revoke", "account_create", "password_reset", "account_disable", "account_enable")
DDL = (
    "CREATE TABLE IF NOT EXISTS access_meta(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL)",
    "CREATE TABLE IF NOT EXISTS accounts(name TEXT PRIMARY KEY,pw TEXT NOT NULL,active INTEGER NOT NULL,epoch TEXT NOT NULL,updated TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS platform_owners(name TEXT PRIMARY KEY)",
    "CREATE TABLE IF NOT EXISTS tenants(id TEXT PRIMARY KEY,name TEXT NOT NULL,path TEXT NOT NULL UNIQUE,status TEXT NOT NULL,runtime TEXT NOT NULL,created TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS memberships(tenant_id TEXT NOT NULL,user TEXT NOT NULL,role TEXT NOT NULL,PRIMARY KEY(tenant_id,user))",
    "CREATE TABLE IF NOT EXISTS project_grants(tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,user TEXT NOT NULL,role TEXT NOT NULL,PRIMARY KEY(tenant_id,project_id,user))",
    "CREATE TABLE IF NOT EXISTS access_audit(id INTEGER PRIMARY KEY AUTOINCREMENT,actor TEXT NOT NULL,action TEXT NOT NULL,tenant_id TEXT NOT NULL,payload TEXT NOT NULL,revision INTEGER NOT NULL,created TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS access_requests(actor TEXT NOT NULL,request_id TEXT NOT NULL,fingerprint TEXT NOT NULL,result TEXT NOT NULL,context_tenant TEXT NOT NULL DEFAULT '',context_digest TEXT NOT NULL DEFAULT '',PRIMARY KEY(actor,request_id))",
)
_LOCKS = {}
_LOCKS_LOCK = threading.Lock()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def request_fingerprint(body):
    # A fast hash of a password-bearing payload is an offline password oracle,
    # even though the password itself never appears in the receipt or audit.
    if body.get("action") in ("account_create", "password_reset"):
        from .login import hash_password
        return hash_password(encoded(body))
    return digest(body)


def fingerprint_matches(body, fingerprint):
    if body.get("action") in ("account_create", "password_reset"):
        from .login import _check
        # Old experimental fast password fingerprints cannot safely be replayed.
        # Existing effects are retained; this rejects without executing anything.
        return fingerprint.startswith("pbkdf2_sha256$") and _check(encoded(body), fingerprint)
    return hmac.compare_digest(digest(body), fingerprint)


def _error(code, message, reason="access_denied"):
    err = ApiError(code, message)
    err.reason = reason
    return err


def _username(name):
    if not isinstance(name, str) or not name or len(name) > 40 or any(c in name for c in " .:$/\\") or not signoff.human(name):
        raise _error(400, "个人账号名格式不正确", "invalid_account")
    return name


def _path(data):
    return Path(data).expanduser().resolve() / "control" / "access.db"


def account_users(data):
    """Used by login without constructing a registry or triggering migration."""
    path = _path(data)
    if not path.exists():
        return None
    with closing(sqlite3.connect(str(path))) as db:
        return {name: {"pw": pw, "updated": updated, "session_epoch": epoch}
                for name, pw, updated, epoch in db.execute("SELECT name,pw,updated,epoch FROM accounts WHERE active=1")}


def has_accounts(data):
    path = _path(data)
    if not path.exists():
        return None
    with closing(sqlite3.connect(str(path))) as db:
        return bool(db.execute("SELECT 1 FROM accounts LIMIT 1").fetchone())


class Registry:
    def __init__(self, data_dir, *, bootstrap_owner=None):
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.path = _path(self.data_dir)
        if self.path.parent.is_symlink() or self.path.is_symlink():
            raise ValueError("控制面路径不能是符号链接")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        # Initial publication is atomic: failed schema/import/bootstrap cannot
        # leave a file that switches a legacy server into half-configured mode.
        with self.authorization_guard():
            temporary = None if self.path.exists() else self.path.with_name("access." + secrets.token_hex(12) + ".tmp")
            opening = temporary or self.path
            self.db = sqlite3.connect(str(opening), timeout=15, check_same_thread=False)
            os.chmod(opening, 0o600)
            self.db.row_factory = sqlite3.Row
            try:
                with self.transaction() as db:
                    for statement in DDL:
                        db.execute(statement)
                    columns = {r[1] for r in db.execute("PRAGMA table_info(access_requests)")}
                    for column in ("context_tenant", "context_digest"):
                        if column not in columns:
                            db.execute("ALTER TABLE access_requests ADD COLUMN %s TEXT NOT NULL DEFAULT ''" % column)
                    if not db.execute("SELECT 1 FROM access_meta").fetchone():
                        db.execute("INSERT INTO access_meta VALUES(1,0)")
                        db.execute("INSERT INTO tenants VALUES('default',?,?, 'active','legacy',?)", ("默认组织", str(self.data_dir), now()))
                        source = self.data_dir / "users.json"
                        users = json.loads(source.read_text(encoding="utf-8")) if source.exists() else {}
                        if not isinstance(users, dict):
                            raise ValueError("旧账号目录格式不正确")
                        for name, account in users.items():
                            _username(name)
                            db.execute("INSERT INTO accounts VALUES(?,?,?,?,?)", (name, account["pw"], not account.get("disabled", False), secrets.token_hex(16), account.get("updated") or now()))
                            db.execute("INSERT INTO memberships VALUES('default',?,'member')", (name,))
                    if bootstrap_owner is not None:
                        self._bootstrap(db, bootstrap_owner)
                if temporary:
                    self.db.close()
                    os.replace(temporary, self.path)
                    self.db = sqlite3.connect(str(self.path), timeout=15, check_same_thread=False)
                    self.db.row_factory = sqlite3.Row
            except BaseException:
                self.db.close()
                if temporary:
                    temporary.unlink(missing_ok=True)
                raise

    def close(self):
        self.db.close()

    @contextmanager
    def authorization_guard(self):
        """Serialize revocations with complete protected business requests.

        Reentrant in one thread, shared across Registry instances and processes.
        Callers must acquire this before any registry or business write lock.
        """
        key = str(self.path)
        with _LOCKS_LOCK:
            lock, local = _LOCKS.setdefault(key, (threading.RLock(), threading.local()))
        with lock:
            depth = getattr(local, "depth", 0)
            if depth:
                local.depth += 1
                try:
                    yield
                finally:
                    local.depth -= 1
                return
            with (self.path.parent / "authorization.lock").open("a+b") as stream:
                filelock.try_lock(stream, blocking=True)
                local.depth = 1
                try:
                    yield
                finally:
                    local.depth = 0
                    filelock.unlock(stream)

    @contextmanager
    def transaction(self):
        with self.lock:
            if self.db.in_transaction:
                raise RuntimeError("access transaction cannot nest")
            try:
                self.db.execute("BEGIN IMMEDIATE")
                yield self.db
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise

    def q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.q(sql, args)
        return rows[0] if rows else None

    def _bootstrap(self, db, name):
        _username(name)
        account = db.execute("SELECT active FROM accounts WHERE name=?", (name,)).fetchone()
        if not account or not account["active"]:
            raise _error(400, "显式引导所有者必须是已有有效个人账号")
        owners = db.execute("SELECT name FROM platform_owners").fetchall()
        if owners:
            if name not in {r["name"] for r in owners}:
                raise _error(409, "平台所有者已经配置，不能通过重复引导替换")
            return
        db.execute("INSERT INTO platform_owners VALUES(?)", (name,))
        db.execute("INSERT INTO memberships VALUES('default',?,'admin') ON CONFLICT(tenant_id,user) DO UPDATE SET role='admin'", (name,))
        db.execute("UPDATE access_meta SET revision=revision+1")
        revision = db.execute("SELECT revision FROM access_meta").fetchone()[0]
        db.execute("INSERT INTO access_audit(actor,action,tenant_id,payload,revision,created) VALUES(?,?,?,?,?,?)", (name, "bootstrap_owner", "default", encoded({"user": name}), revision, now()))

    def directory(self, tenant):
        return {r["name"]: {"name": r["name"], "role": r["role"]} for r in self.q(
            "SELECT a.name,m.role FROM accounts a JOIN memberships m ON a.name=m.user WHERE m.tenant_id=? AND a.active=1", (tenant,))}

    def context(self, user, tenant="default"):
        return context(self, user, tenant)

    def read(self, user, tenant="default"):
        return read(self, user, tenant)

    def dispatch(self, user, body, *, request_context=None):
        return dispatch(self, user, body, request_context=request_context)


def context(reg, user, tenant="default"):
    with reg.lock:
        reg.db.execute("SAVEPOINT access_context")
        try:
            account = reg.one("SELECT name,active,epoch FROM accounts WHERE name=?", (user,))
            if not account or not account["active"]:
                raise _error(403, "账号已停用或不存在", "identity_revoked")
            target = reg.one("SELECT * FROM tenants WHERE id=?", (tenant,))
            if not target:
                raise _error(404, "没有这个租户", "tenant_not_found")
            owner = bool(reg.one("SELECT 1 FROM platform_owners WHERE name=?", (user,)))
            membership = reg.one("SELECT role FROM memberships WHERE tenant_id=? AND user=?", (tenant, user))
            role = membership["role"] if membership else None
            if not role and not owner:
                raise _error(403, "你已不属于这个租户", "membership_revoked")
            grants = reg.q("SELECT project_id,role FROM project_grants WHERE tenant_id=? AND user=? ORDER BY project_id", (tenant, user))
            revision = reg.one("SELECT revision FROM access_meta WHERE id=1")["revision"]
            capabilities = {"tenant_create": owner, "tenant_manage": owner or role == "admin", "member_manage": owner or role == "admin",
                            "project_manage": role == "admin", "account_manage": owner,
                            "read": bool(role), "write": role in ("admin", "member"),
                            "execution": bool(owner and role in ("admin", "member") and tenant == "default" and target["status"] == "active")}
            value = {"user": user, "tenant": target, "role": role, "platform_owner": owner, "project_grants": grants,
                     "authz_revision": revision, "revision": revision, "capabilities": capabilities,
                     "can_manage": owner or role == "admin"}
            value["context_token"] = digest({"user": user, "epoch": account["epoch"], "tenant": tenant, "revision": revision, "role": role, "grants": grants})
            return value
        finally:
            reg.db.execute("RELEASE access_context")


def authorize(reg, user, tenant, permission, project_id=None):
    c = context(reg, user, tenant)
    management = permission in ("tenant_create", "tenant_manage", "member_manage", "account_manage")
    if c["tenant"]["status"] != "active" and not management:
        raise _error(403, "租户已停用", "tenant_disabled")
    project_manager = permission == "project_manage" and project_id is not None and c["role"] == "member" and any(g["project_id"] == str(project_id) and g["role"] == "manager" for g in c["project_grants"])
    if permission in c["capabilities"] and not c["capabilities"][permission] and not project_manager:
        raise _error(403, "当前角色无此权限")
    if permission not in (*c["capabilities"], "acceptance"):
        raise _error(403, "未登记的权限默认拒绝")
    if permission == "acceptance" and not c["capabilities"]["write"]:
        raise _error(403, "只读成员不能执行人工确认")
    if project_id is not None and not management:
        grant = next((g["role"] for g in c["project_grants"] if g["project_id"] == str(project_id)), None)
        if c["role"] != "admin" and (grant is None or permission != "read" and grant not in ("manager", "contributor")):
            raise _error(403, "没有这个项目的访问或操作权限", "project_denied")
        if permission == "project_manage" and c["role"] != "admin" and grant != "manager":
            raise _error(403, "项目配置需要管理权限")
    return c


def _permissions(c):
    value = {k: c["capabilities"][k] for k in ("tenant_create", "tenant_manage", "member_manage", "project_manage", "account_manage")}
    # Registry administration is separate from permission to read/change a
    # tenant's projects. Owners may grant access without inheriting that access.
    value["project_manage"] = c["platform_owner"] or c["role"] == "admin"
    return value


def read(reg, user, tenant="default"):
    with reg.authorization_guard():
        c = context(reg, user, tenant)
        allowed = c["can_manage"]
        if not allowed:
            raise _error(403, "成员与权限管理仅供管理员")
        tenants = reg.q("SELECT * FROM tenants ORDER BY created,id") if c["platform_owner"] else reg.q("SELECT t.* FROM tenants t JOIN memberships m ON t.id=m.tenant_id WHERE m.user=? ORDER BY t.created,t.id", (user,))
        for t in tenants:
            member = reg.one("SELECT role FROM memberships WHERE tenant_id=? AND user=?", (t["id"], user))
            t["role"] = member["role"] if member else None
            t.pop("path", None)
        members = reg.q("SELECT m.user id,m.user name,m.role,a.active FROM memberships m JOIN accounts a ON a.name=m.user WHERE m.tenant_id=? ORDER BY m.user", (tenant,))
        for m in members:
            m["active"] = bool(m["active"])
            m["actions"] = {"member_set": allowed, "member_remove": allowed and m["id"] != user}
        accounts = reg.q("SELECT name id,name,active FROM accounts ORDER BY name") if c["platform_owner"] else []
        for a in accounts:
            a["active"] = bool(a["active"])
            a["actions"] = {"password_reset": True, "account_disable": a["active"] and a["id"] != user, "account_enable": not a["active"]}
        current = {k: v for k, v in c["tenant"].items() if k != "path"}
        audits = reg.q("SELECT * FROM access_audit" + ("" if c["platform_owner"] else " WHERE tenant_id=?") + " ORDER BY id DESC", () if c["platform_owner"] else (tenant,))
        for a in audits:
            a["payload"] = json.loads(a["payload"])
        return {"viewer": user, "revision": c["revision"], "current_tenant": current, "tenants": tenants, "members": members,
                "project_grants": reg.q("SELECT project_id,user,role FROM project_grants WHERE tenant_id=? ORDER BY project_id,user", (tenant,)),
                "accounts": accounts, "permissions": _permissions(c), "roles": {"tenant": list(TENANT_ROLES), "project": list(PROJECT_ROLES)}, "audit": audits}


def _active(reg, name):
    _username(name)
    if not reg.one("SELECT 1 FROM accounts WHERE name=? AND active=1", (name,)):
        raise _error(400, "请选择当前有效个人账号")


def _last_admin(reg, tenant, user):
    member = reg.one("SELECT role FROM memberships WHERE tenant_id=? AND user=?", (tenant, user))
    if member and member["role"] == "admin":
        others = reg.one("SELECT COUNT(*) n FROM memberships m JOIN accounts a ON a.name=m.user WHERE m.tenant_id=? AND m.role='admin' AND a.active=1 AND m.user<>?", (tenant, user))["n"]
        if not others:
            raise _error(409, "不能移除或停用租户最后一位有效管理员", "last_admin")


def bound_receipt(reg, user, body, tenant, token):
    """Only an exact HTTP retry may read its receipt with the original token.

    Caller still checks the live session and calls dispatch to recheck current
    management permission. This exception cannot execute a fresh mutation.
    """
    if not isinstance(body, dict) or not isinstance(body.get("request_id"), str) or not token:
        return False
    old = reg.one("SELECT * FROM access_requests WHERE actor=? AND request_id=?", (user, body["request_id"]))
    return bool(old and old["context_tenant"] == tenant and old["context_digest"] == digest(token) and fingerprint_matches(body, old["fingerprint"]))


def dispatch(reg, user, body, *, request_context=None):
    if not isinstance(body, dict) or body.get("action") not in ACTIONS:
        raise _error(400, "未知管理操作", "invalid_action")
    action, tenant = body["action"], body.get("tenant", "default")
    if not isinstance(tenant, str):
        raise _error(400, "租户标识格式不正确")
    fields = {"tenant_create": {"name", "admin"}, "tenant_rename": {"name"}, "member_set": {"user", "role"}, "member_remove": {"user"},
              "project_grant": {"project_id", "user", "role"}, "project_revoke": {"project_id", "user"},
              "account_create": {"user", "password"}, "password_reset": {"user", "password"}, "account_disable": {"user"}, "account_enable": {"user"}}
    if set(body) - {"action", "tenant", "revision", "request_id"} - fields.get(action, set()):
        raise _error(400, "请求含未知字段，不能指定路径、运行器或操作者")
    rid = body.get("request_id")
    if not isinstance(rid, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", rid):
        raise _error(400, "需要稳定请求编号")
    if not isinstance(body.get("revision"), int) or isinstance(body["revision"], bool):
        raise _error(400, "需要当前管理修订号")
    permission = ("tenant_create" if action == "tenant_create" else "account_manage" if action.startswith("account_") or action == "password_reset"
                  else "member_manage" if action.startswith("member_") or action.startswith("project_") else "tenant_manage")
    authorize(reg, user, tenant, permission)
    password_hash = None
    if action in ("account_create", "password_reset"):
        from .login import hash_password
        if not isinstance(body.get("password"), str) or len(body["password"]) < 8:
            raise _error(400, "密码至少8位")
        password_hash = hash_password(body["password"])
    fingerprint = request_fingerprint(body)
    with reg.authorization_guard(), reg.transaction() as db:
        authorize(reg, user, tenant, permission)
        old = reg.one("SELECT * FROM access_requests WHERE actor=? AND request_id=?", (user, rid))
        if old:
            if not fingerprint_matches(body, old["fingerprint"]):
                raise _error(409, "请求编号已用于不同内容", "request_conflict")
            if request_context and old["context_tenant"] != request_context["tenant"]:
                raise _error(409, "原请求属于另一个页面租户", "request_conflict")
            return dict(json.loads(old["result"]), replayed=True)
        revision = reg.one("SELECT revision FROM access_meta")["revision"]
        if revision != body["revision"]:
            raise _error(409, "权限已变化，请刷新后再提交", "revision_conflict")
        target_user = body.get("user")
        if action == "tenant_create":
            name, admin = body.get("name"), body.get("admin", user)
            if not isinstance(name, str) or not name.strip() or len(name) > 120:
                raise _error(400, "请填写组织名称（最多120字）")
            _active(reg, admin)
            tenant = secrets.token_hex(12)
            if (reg.data_dir / "tenants").is_symlink():
                raise _error(409, "租户工作目录不能是符号链接")
            path = reg.data_dir / "tenants" / tenant / "data"
            db.execute("INSERT INTO tenants VALUES(?,?,?,'active','disabled',?)", (tenant, name.strip(), str(path), now()))
            db.execute("INSERT INTO memberships VALUES(?,?,'admin')", (tenant, admin))
        elif action == "tenant_rename":
            name = body.get("name")
            if not isinstance(name, str) or not name.strip() or len(name) > 120:
                raise _error(400, "请填写组织名称（最多120字）")
            db.execute("UPDATE tenants SET name=? WHERE id=?", (name.strip(), tenant))
        elif action in ("tenant_disable", "tenant_enable"):
            if tenant == "default" and action == "tenant_disable":
                raise _error(409, "默认组织保留控制面入口，不能在此停用", "self_lockout")
            db.execute("UPDATE tenants SET status=? WHERE id=?", ("disabled" if action == "tenant_disable" else "active", tenant))
        elif action in ("member_set", "member_remove"):
            _active(reg, target_user) if action == "member_set" else _username(target_user)
            role = body.get("role")
            if action == "member_set" and role not in TENANT_ROLES:
                raise _error(400, "未知成员角色")
            if target_user == user and (action == "member_remove" or role != "admin"):
                raise _error(409, "不能移除或降低自己的管理权限", "self_lockout")
            if action == "member_remove" or role != "admin":
                _last_admin(reg, tenant, target_user)
            if action == "member_set":
                db.execute("INSERT INTO memberships VALUES(?,?,?) ON CONFLICT(tenant_id,user) DO UPDATE SET role=excluded.role", (tenant, target_user, role))
            else:
                db.execute("DELETE FROM memberships WHERE tenant_id=? AND user=?", (tenant, target_user))
                db.execute("DELETE FROM project_grants WHERE tenant_id=? AND user=?", (tenant, target_user))
        elif action in ("project_grant", "project_revoke"):
            _active(reg, target_user)
            project = body.get("project_id")
            if not isinstance(project, (str, int)) or isinstance(project, bool) or not str(project) or len(str(project)) > 120:
                raise _error(400, "项目标识不正确")
            if not reg.one("SELECT 1 FROM memberships WHERE tenant_id=? AND user=?", (tenant, target_user)):
                raise _error(400, "先将账号加入本组织")
            if action == "project_grant":
                if body.get("role") not in PROJECT_ROLES:
                    raise _error(400, "未知项目角色")
                db.execute("INSERT INTO project_grants VALUES(?,?,?,?) ON CONFLICT(tenant_id,project_id,user) DO UPDATE SET role=excluded.role", (tenant, str(project), target_user, body["role"]))
            else:
                db.execute("DELETE FROM project_grants WHERE tenant_id=? AND project_id=? AND user=?", (tenant, str(project), target_user))
        else:
            _username(target_user)
            account = reg.one("SELECT * FROM accounts WHERE name=?", (target_user,))
            if action == "account_create":
                if account:
                    raise _error(409, "账号已存在")
                db.execute("INSERT INTO accounts VALUES(?,?,1,?,?)", (target_user, password_hash, secrets.token_hex(16), now()))
            else:
                if not account:
                    raise _error(404, "没有这个账号")
                if action == "account_disable":
                    if target_user == user or reg.one("SELECT 1 FROM platform_owners WHERE name=?", (target_user,)):
                        raise _error(409, "不能停用自己或平台所有者", "self_lockout")
                    for m in reg.q("SELECT tenant_id FROM memberships WHERE user=? AND role='admin'", (target_user,)):
                        _last_admin(reg, m["tenant_id"], target_user)
                db.execute("UPDATE accounts SET pw=?,active=?,epoch=?,updated=? WHERE name=?",
                           (password_hash if action == "password_reset" else account["pw"], 0 if action == "account_disable" else 1 if action == "account_enable" else account["active"], secrets.token_hex(16), now(), target_user))
        revision += 1
        db.execute("UPDATE access_meta SET revision=?", (revision,))
        payload = {k: v for k, v in body.items() if k != "password"}
        db.execute("INSERT INTO access_audit(actor,action,tenant_id,payload,revision,created) VALUES(?,?,?,?,?,?)", (user, action, tenant, encoded(payload), revision, now()))
        result = {"revision": revision, "operation": action, "tenant_id": tenant, "request_id": rid, "changed": True, "replayed": False}
        db.execute("INSERT INTO access_requests(actor,request_id,fingerprint,result,context_tenant,context_digest) VALUES(?,?,?,?,?,?)",
                   (user, rid, fingerprint, encoded(result), request_context["tenant"] if request_context else "", digest(request_context["token"]) if request_context else ""))
        return result


def local_set_user(data, name, password):
    """Existing owner-operated CLI remains local; it never grants owner/admin."""
    from .login import hash_password
    _username(name)
    password_hash = hash_password(password)
    reg = Registry(data)
    try:
        with reg.authorization_guard(), reg.transaction() as db:
            db.execute("INSERT INTO accounts VALUES(?,?,1,?,?) ON CONFLICT(name) DO UPDATE SET pw=excluded.pw,active=1,epoch=excluded.epoch,updated=excluded.updated",
                       (name, password_hash, secrets.token_hex(16), now()))
            db.execute("UPDATE access_meta SET revision=revision+1")
            rev = reg.one("SELECT revision FROM access_meta")["revision"]
            db.execute("INSERT INTO access_audit(actor,action,tenant_id,payload,revision,created) VALUES('local-cli','account_set','',?,?,?)", (encoded({"user": name}), rev, now()))
    finally:
        reg.close()


def local_del_user(data, name):
    reg = Registry(data)
    try:
        with reg.authorization_guard(), reg.transaction() as db:
            if not reg.one("SELECT 1 FROM accounts WHERE name=? AND active=1", (name,)):
                return False
            if reg.one("SELECT 1 FROM platform_owners WHERE name=?", (name,)):
                raise _error(409, "不能删除平台所有者")
            for m in reg.q("SELECT tenant_id FROM memberships WHERE user=? AND role='admin'", (name,)):
                _last_admin(reg, m["tenant_id"], name)
            db.execute("UPDATE accounts SET active=0,epoch=?,updated=? WHERE name=?", (secrets.token_hex(16), now(), name))
            db.execute("UPDATE access_meta SET revision=revision+1")
            rev = reg.one("SELECT revision FROM access_meta")["revision"]
            db.execute("INSERT INTO access_audit(actor,action,tenant_id,payload,revision,created) VALUES('local-cli','account_remove','',?,?,?)", (encoded({"user": name}), rev, now()))
            return True
    finally:
        reg.close()
