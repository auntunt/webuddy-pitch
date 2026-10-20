# -*- coding: utf-8 -*-
"""HTTP 入站适配器。

两套路由:
  /api/*      0.1 版接口,路径、参数、响应形状、错误码与 0.1 版一致,页面依赖它们
  /api/v1/*   子系统标准接口:统一错误体、健康检查、清单、201 创建语义
两套都调同一个 WeighbillService,业务不在这一层。
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from .bootstrap import build_service
from .manifest import build_manifest
from .ports import RecordQuery
from .blob_keys import is_image_key
from .domain import canon_doc_type
from .export_xlsx import ExportImageError
from .service import UNCONDITIONAL, Queued, RecordNotFound, ServiceError, TooManyRequests, WeighbillService

STATIC = Path(__file__).resolve().parent / "static"
# 页面每次回源校验(ETag 未变仍是 304):升级后现场手机不会一直停在旧页面
NO_CACHE = {"Cache-Control": "no-cache"}


def _q(date_from="", date_to="", q="", status="", limit=500, doc_type="", stage="", ticket_from="",
       ticket_to="", voided="", flagged=False, origin_id="") -> RecordQuery:
    return RecordQuery(date_from=date_from, date_to=date_to, q=q, status=status, limit=max(1, int(limit)),
                       doc_type=doc_type, stage=stage, ticket_from=ticket_from, ticket_to=ticket_to,
                       voided=voided if voided in ("", "only", "all") else "", flagged=bool(flagged), origin_id=origin_id)


class _RateLimit:
    """滑动窗口计数,进程内。超了返回 False。"""
    def __init__(self):
        import threading
        self._hits, self._lock = {}, threading.Lock()

    def allow(self, key: str, limit: int, window: float = 3600.0) -> bool:
        import time
        now = time.monotonic()
        with self._lock:
            q = [t for t in self._hits.get(key, []) if now - t < window]
            ok = len(q) < limit
            if ok:
                q.append(now)
            self._hits[key] = q
            return ok


class _MaskTokens:
    """访问日志里把现场链接令牌换成 ***:日志进 journald,能读日志的人不该拿到能上传的链接。"""
    import re as _re
    _pat = _re.compile(r"(/c/|/api/v1/capture/)[^/\s?\"]+")

    def filter(self, record) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(self._pat.sub(r"\1***", a) if isinstance(a, str) else a for a in record.args)
        return True


def link_source(token: str) -> str:
    """现场链接在记录上的身份:令牌的单向摘要。改链接名字不影响,两条链接同名也分得开,数据库里查不出令牌。"""
    import hashlib
    return "link:" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def _xlsx(data: bytes, name: str) -> Response:
    from urllib.parse import quote
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


def _csv(svc: WeighbillService, query: RecordQuery) -> Response:
    return Response(svc.export_csv(query), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=weighbill_ledger.csv"})


def create_app(service: Optional[WeighbillService] = None) -> FastAPI:
    svc = service or build_service()
    base_path = svc.settings.validated_base_path
    from urllib.parse import urlsplit
    preview_origins = svc.settings.local_preview_origins
    if not isinstance(preview_origins, list):
        raise ValueError("local_preview_origins 必须是精确 Origin 列表")
    for origin in preview_origins:
        u = urlsplit(origin) if isinstance(origin, str) else None
        if (not u or u.scheme not in ("http", "https") or not u.hostname or u.username
                or "*" in origin or u.password or u.path or u.query or u.fragment or origin != f"{u.scheme}://{u.netloc}"):
            raise ValueError("local_preview_origins 只接受完整的 http/https Origin，不接受通配符或路径")
    if preview_origins and (not base_path or svc.settings.gateway_secret):
        raise ValueError("local_preview_origins 仅供无网关密钥、带 base_path 的本机隔离预览使用")

    def page(name):
        return HTMLResponse((STATIC / name).read_text("utf-8").replace("__WB_BASE_PATH__", base_path), headers=NO_CACHE)

    background = set()             # 正在跑的处理任务:留引用,免得被回收;超时返回后它们接着跑完

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(_app):
        """后台:每 10 秒把暂存区里该处理的处理掉(含重启前没处理完的),每小时清一次过期的。"""
        async def loop():
            import logging, time
            last_purge = 0.0
            while True:
                try:
                    await svc.drain_spool()
                    if time.monotonic() - last_purge > 3600:
                        svc.spool.purge(); last_purge = time.monotonic()
                except Exception:
                    logging.getLogger(__name__).exception("暂存区后台处理异常")
                await asyncio.sleep(10)
        worker = asyncio.ensure_future(loop())
        try:
            yield
        finally:
            worker.cancel()

    app = FastAPI(title="称重单采集与台账子系统", version=__version__, lifespan=lifespan)
    app.state.service = svc
    limiter = _RateLimit()
    import logging
    logging.getLogger("uvicorn.access").addFilter(_MaskTokens())

    # ------------------------------------------------------------ 先收下,再处理(暂存区)

    async def spooled(raw: bytes, upload_id: str, uploader: str, doc_type: str, customer: str, source=None, origin_id=None):
        """照片落盘 → 当场处理,最多等 spool_sync_wait 秒。返回 ("done", [(记录, 重复理由)]) 或 ("queued", meta)。"""
        import uuid
        upload_id = (upload_id or "").strip() or uuid.uuid4().hex
        meta, _ = svc.accept_upload(raw, upload_id, uploader, doc_type, customer, source, origin_id)
        task = asyncio.ensure_future(svc.process_upload(upload_id))
        background.add(task); task.add_done_callback(background.discard)
        done, _ = await asyncio.wait({task}, timeout=max(1, svc.settings.spool_sync_wait))
        if not done:
            return "queued", svc.spool.get(upload_id)
        exc = task.exception()
        if isinstance(exc, Queued):
            return "queued", svc.spool.get(upload_id)
        if exc is not None:
            raise exc
        return "done", task.result()

    def queued_body(meta: dict) -> dict:
        return {"records": [], "upload_id": meta["upload_id"], "status": "queued",
                "message": "照片已经安全收下。服务器这会儿没处理完(或后台服务暂时连不上),会自动接着处理,不用重拍。"}

    def upload_allowed(key: str):
        if not limiter.allow(key, max(1, int(svc.settings.upload_limit_per_hour))):
            raise TooManyRequests(f"这一小时上传次数太多(上限 {svc.settings.upload_limit_per_hour} 次),稍后再试")

    # Preserve direct static page URLs while rendering their explicit path placeholders too.
    @app.get("/static/report.html", include_in_schema=False)
    def static_report():
        return page("report.html")

    @app.get("/static/capture.html", include_in_schema=False)
    def static_capture():
        return page("capture.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    def image_response(request: Request, key: str) -> Response:
        """图片都经这里给:只放行单据图片的键(0.1 版把整个数据目录挂出去,库文件能被直接下载);
        本地盘、对象存储一个样;预览图没有就现做。图片键的内容不会变,浏览器缓存一年,再看只回 304。"""
        import hashlib
        try:
            data = svc.image(key)
        except (ServiceError, ValueError):
            return Response(status_code=404)
        etag = '"' + hashlib.sha1(data).hexdigest()[:20] + '"'
        headers = {"ETag": etag, "Cache-Control": "private, max-age=31536000, immutable"}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        return Response(data, media_type=__import__("mimetypes").guess_type(key)[0] or "application/octet-stream", headers=headers)

    @app.get("/files/{key:path}", include_in_schema=False)
    def files(key: str, request: Request):
        return image_response(request, key)

    @app.middleware("http")
    async def _no_cross_site_writes(request: Request, call_next):
        # 浏览器跨站发来的写请求一律拒:登录是 Basic 认证,浏览器会自动带上,别的网页就能借审核员的身份上传、改单。
        # multipart 上传不触发预检,光靠 CORS 挡不住(安全审计)。
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            site = request.headers.get("sec-fetch-site", "")
            origin = request.headers.get("origin", "")
            host = request.headers.get("host", "")
            # A trusted Origin exception is effective only on an actual loopback connection and Host.
            import ipaddress
            def loopback(value):
                try:
                    return ipaddress.ip_address(value).is_loopback
                except ValueError:
                    return value == "localhost"
            preview = (origin in preview_origins and request.client is not None
                       and loopback(request.client.host) and loopback(urlsplit("//" + host).hostname or ""))
            if site == "cross-site" or (origin and (origin == "null" or urlsplit(origin).netloc != host) and not preview):
                return JSONResponse({"error": {"code": "CrossSite", "message": "不接受从别的网站发来的修改请求"}},
                                    status_code=403)
        return await call_next(request)

    @app.middleware("http")
    async def _revalidate_static(request: Request, call_next):
        # 页面资源每次回源校验:不依赖手工改版本号,升级后不会有人停在旧样式上
        resp = await call_next(request)
        if request.url.path.startswith(base_path + "/static/"):
            resp.headers["Cache-Control"] = "no-cache"
        return resp

    # ============================================================ 页面
    @app.get("/", include_in_schema=False)
    def page_capture():
        return page("capture.html")

    @app.get("/sw.js", include_in_schema=False)
    def service_worker():
        # 放在根路径才能管 / 和 /c/<令牌> 两个采集入口;每次回源校验,升级立即生效
        return Response((STATIC / "sw.js").read_text("utf-8").replace("__WB_BASE_PATH__", base_path), media_type="application/javascript",
                        headers={**NO_CACHE, "Service-Worker-Allowed": base_path + "/"})

    @app.get("/report", include_in_schema=False)
    def page_report():
        return page("report.html")

    # ============================================================ 0.1 版接口(兼容)
    @app.post("/api/upload", tags=["legacy"])
    async def api_upload(request: Request, photo: UploadFile = File(...)):
        try:
            svc.ensure_ingest_available()
            upload_allowed("user:" + actor_of(request))
        except ServiceError as e:
            raise HTTPException(e.http_status, str(e))
        raw = await photo.read()
        if len(raw) > svc.settings.max_upload_bytes:
            raise HTTPException(413, "图片超过30MB")
        try:
            recs = await svc.ingest(raw, actor_of(request), submit=True)
        except Exception as e:
            raise HTTPException(500, f"处理失败:{e}")
        return {"records": [svc.record_view(r) for r in recs]}

    @app.get("/api/records", tags=["legacy"])
    def api_records(date_from: str = "", date_to: str = "", q: str = "", status: str = "", limit: int = 500):
        return {"records": [svc.record_view(r) for r in svc.query(_q(date_from, date_to, q, status, limit))]}

    @app.get("/api/records/{rid}", tags=["legacy"])
    def api_record(rid: str):
        try:
            return svc.record_view(svc.get(rid))
        except ServiceError as e:
            raise HTTPException(e.http_status, str(e))

    @app.patch("/api/records/{rid}", tags=["legacy"])
    def api_update(rid: str, request: Request, body: dict = Body(...)):
        try:
            actor = actor_of(request)
            rec = svc.review(rid, body.get("fields") or {}, actor, privileged=svc.can_review(actor),
                             expected_version=body.get("expected_version", UNCONDITIONAL))
        except ServiceError as e:
            raise HTTPException(e.http_status, str(e))
        return svc.record_view(rec)

    @app.get("/api/export.csv", tags=["legacy"])
    def api_export(date_from: str = "", date_to: str = "", q: str = "", status: str = "", origin_id: str = ""):
        return _csv(svc, _q(date_from, date_to, q, status, origin_id=origin_id))

    @app.get("/api/config", tags=["legacy"])
    def api_config():
        s = svc.settings
        return {"seg_model": s.seg_model, "rec_model": s.rec_model,
                "base_url": s.base_url, "key_set": bool(s.api_key)}

    # ============================================================ v1 标准接口
    def err(e: ServiceError) -> JSONResponse:
        return JSONResponse({"error": {"code": type(e).__name__, "message": str(e)}},
                            status_code=e.http_status)

    @app.get("/api/v1/manifest", tags=["v1"])
    def v1_manifest():
        return build_manifest(svc.settings)

    @app.get("/api/v1/health", tags=["v1"])
    def v1_health():
        h = svc.health()
        return JSONResponse(h, status_code=200 if h["status"] != "down" else 503)

    def actor_of(request: Request) -> str:
        secret = svc.settings.gateway_secret
        if secret:
            import hmac
            if not hmac.compare_digest(request.headers.get("x-gateway-secret", ""), secret):
                return svc.settings.anonymous_name        # 没走网关登录的请求:操作人头不可信
        who = svc.identity.resolve(request.headers)
        if who == svc.settings.anonymous_name and svc.settings.local_user and not secret:
            return svc.settings.local_user
        return who

    @app.get("/api/v1/schema", tags=["v1"])
    def v1_schema():
        """页面按单据类型取列(与客户台账同序同名),前端不再写死一份。"""
        from .domain import DOC_COLUMNS, DOC_TYPES, FIELDS, col_label
        n = svc.settings.naming
        return {"origins": svc.settings.origin_catalog, "fields": FIELDS, "supplier_name": n.supplier, "site_name": n.site, "customers": n.customers,
                "doc_types": {k: {"label": n.labels[k], "title": n.titles[k],
                                  "columns": [{"key": c, "label": col_label(k, c)} for c in DOC_COLUMNS[k]]}
                              for k, v in DOC_TYPES.items()}}

    @app.get("/api/v1/me", tags=["v1"])
    def v1_me(request: Request):
        a = actor_of(request)
        return {"user": a, "reviewer": svc.can_review(a)}

    @app.post("/api/v1/records", tags=["v1"], status_code=201)
    async def v1_ingest(request: Request, photo: UploadFile = File(...), doc_type: str = Form("site_in"),
                        customer: str = Form(""), upload_id: str = Form(""), origin_id: str = Form("")):
        try:
            svc.ensure_ingest_available()
            upload_allowed("user:" + actor_of(request))
            kind, res = await spooled(await photo.read(), upload_id, actor_of(request), doc_type, customer, origin_id=origin_id or None)
        except ServiceError as e:
            return err(e)
        if kind == "queued":
            return JSONResponse(queued_body(res), status_code=202)
        return JSONResponse({"records": [{**svc.record_view(r), "duplicate": why} for r, why in res],
                             "upload_id": res and res[0][0].batch_id}, status_code=201)

    @app.get("/api/v1/uploads/{upload_id}", tags=["v1"])
    def v1_upload_status(upload_id: str, request: Request):
        m = svc.spool.get(upload_id)
        if m is None or (m.get("uploader") != actor_of(request) and not svc.can_review(actor_of(request))):
            return err(RecordNotFound("没有这次上传"))
        m = svc.upload_status(upload_id)
        return {"upload_id": upload_id, "status": m["status"], "last_error": m.get("last_error"),
                "records": [{**svc.record_view(r), "duplicate": why} for r, why in svc.upload_result(m)]}

    # 静态段先于 /{rid} 声明,否则会被路径参数吞掉
    @app.get("/api/v1/records/export.csv", tags=["v1"])
    def v1_export(date_from: str = "", date_to: str = "", q: str = "", status: str = "", origin_id: str = ""):
        return _csv(svc, _q(date_from, date_to, q, status, origin_id=origin_id))

    @app.post("/api/v1/records/approve", tags=["v1"])
    def v1_approve(request: Request, body: dict = Body(...)):
        a = actor_of(request)
        try:
            return svc.approve(body.get("ids") or [], a, privileged=svc.can_review(a),
                               versions=body.get("versions", UNCONDITIONAL))
        except ServiceError as e:
            return err(e)

    @app.get("/api/v1/records", tags=["v1"])
    def v1_records(date_from: str = "", date_to: str = "", q: str = "", status: str = "", limit: int = 500,
                   doc_type: str = "", stage: str = "", ticket_from: str = "", ticket_to: str = "",
                   voided: str = "", flagged: bool = False, origin_id: str = ""):
        recs = [svc.record_view(r) for r in svc.query(_q(date_from, date_to, q, status, limit, doc_type, stage,
                                                          ticket_from, ticket_to, voided, flagged, origin_id))]
        return {"records": recs, "count": len(recs)}

    @app.get("/api/v1/records/{rid}", tags=["v1"])
    def v1_record(rid: str):
        try:
            return svc.record_view(svc.get(rid))
        except ServiceError as e:
            return err(e)

    @app.patch("/api/v1/records/{rid}", tags=["v1"])
    def v1_review(rid: str, request: Request, body: dict = Body(...)):
        a = actor_of(request)
        try:
            return svc.record_view(svc.review(rid, body.get("fields") or {}, a, privileged=svc.can_review(a),
                                              customer=body.get("customer"), doc_type=body.get("doc_type"), origin_id=body.get("origin_id"),
                                              expected_version=body.get("expected_version", UNCONDITIONAL)))
        except ServiceError as e:
            return err(e)

    @app.post("/api/v1/records/{rid}/submit", tags=["v1"])
    def v1_submit(rid: str, request: Request, body: dict = Body(default={})):
        a = actor_of(request)
        try:
            return svc.record_view(svc.submit(rid, body.get("fields") or {}, a, privileged=svc.can_review(a),
                                              customer=body.get("customer"), doc_type=body.get("doc_type"), origin_id=body.get("origin_id"),
                                              expected_version=body.get("expected_version", UNCONDITIONAL)))
        except ServiceError as e:
            return err(e)

    @app.post("/api/v1/records/{rid}/void", tags=["v1"])
    def v1_void(rid: str, request: Request, body: dict = Body(default={})):
        a = actor_of(request)
        try:
            own = svc.get(rid).uploader == a              # 登录的现场人员可以丢弃自己还没提交的
            return svc.record_view(svc.void(rid, a, body.get("reason") or "", privileged=svc.can_review(a), own=own))
        except ServiceError as e:
            return err(e)

    @app.post("/api/v1/records/{rid}/restore", tags=["v1"])
    def v1_restore(rid: str, request: Request):
        a = actor_of(request)
        try:
            return svc.record_view(svc.restore(rid, a, privileged=svc.can_review(a)))
        except ServiceError as e:
            return err(e)

    @app.post("/api/v1/records/{rid}/flag", tags=["v1"])
    def v1_flag(rid: str, request: Request, body: dict = Body(default={})):
        a = actor_of(request)
        try:
            return svc.record_view(svc.flag(rid, a, body.get("note"), privileged=svc.can_review(a)))
        except ServiceError as e:
            return err(e)

    @app.get("/api/v1/records/{rid}/history", tags=["v1"])
    def v1_history(rid: str):
        try:
            return {"history": svc.history(rid)}
        except ServiceError as e:
            return err(e)

    @app.get("/api/v1/reconciliation", tags=["v1"])
    def v1_reconciliation(date_from: str = "", date_to: str = "", origin_id: str = ""):
        return svc.reconciliation_view(svc.reconciliation(date_from, date_to, origin_id))

    @app.get("/api/v1/settings/thresholds", tags=["v1"])
    def v1_thresholds():
        return svc.thresholds()

    @app.put("/api/v1/settings/thresholds", tags=["v1"])
    def v1_set_thresholds(request: Request, body: dict = Body(...)):
        actor = actor_of(request)
        try:
            return svc.set_thresholds(body, actor, svc.can_review(actor))
        except ServiceError as e:
            return err(e)

    @app.get("/api/v1/stats", tags=["v1"])
    def v1_stats(date_from: str = "", date_to: str = "", origin_id: str = ""):
        return svc.stats(date_from, date_to, origin_id)

    @app.get("/api/v1/export.xlsx", tags=["v1"])
    def v1_export_xlsx(kind: str, date_from: str = "", date_to: str = "", q: str = "", status: str = "",
                       stage: str = "", ticket_from: str = "", ticket_to: str = "", origin_id: str = ""):
        try:
            if kind == "reconciliation":
                return _xlsx(svc.export_reconciliation_xlsx(ticket_from, ticket_to, origin_id),
                             f"磅差对比_{ticket_from or '全部'}_{ticket_to or ''}.xlsx")
            kind = canon_doc_type(kind)
            data = svc.export_records_xlsx(kind, _q(date_from, date_to, q, status, 2000, kind, stage,
                                                    ticket_from, ticket_to, origin_id=origin_id))
            return _xlsx(data, f"{svc.settings.naming.labels.get(kind, kind)}_{ticket_from or date_from or '全部'}.xlsx")
        except ServiceError as e:
            return err(e)
        except ExportImageError as e:
            return JSONResponse({"error": {"code": "ExportImageUnavailable", "message": str(e)}}, status_code=503)

    # ============================================================ 现场上传链接(不登录)
    # 监磅员拿 /c/<令牌> 直接拍。令牌在配置 capture_links 里;页面、图片、上传、提交都只认令牌,
    # 网关要把 /c/、/api/v1/capture/、/static/ 三个前缀放在登录之外。
    def link_of(token: str) -> dict:
        link = (svc.settings.capture_links or {}).get(token)
        if not link:
            raise RecordNotFound("链接无效或已停用")
        return link if isinstance(link, dict) else {"label": str(link)}

    def capture_view(token: str, r) -> dict:
        v = svc.record_view(r)
        from .blob_keys import variant_key
        from urllib.parse import quote
        keys = dict(orig_path=r.orig_key, crop_path=r.crop_key, sig_path=r.sig_key,
                    thumb_path=variant_key(r.crop_key or r.orig_key, "t"),
                    preview_path=variant_key(r.crop_key or r.orig_key, "m"))
        for k, key in keys.items():
            if key:
                v[k] = svc.settings.app_path(f"/api/v1/capture/{quote(token, safe='')}/files/{key}")
        return v

    def duplicate_brief(r, why: str) -> dict:
        """重复的磅单:已有那条可能是别人传的,现场链接只给看个摘要(谁、什么时候、车号、净重、到哪一步),不给图、不给改。"""
        f = r.fields or {}
        return {"id": r.id, "ref_no": r.ref_no, "duplicate": why, "doc_type": r.doc_type, "stage": r.stage,
                "stage_label": svc.record_view(r)["stage_label"], "uploader": r.uploader, "created_at": r.created_at,
                "status": r.status, "fields": {k: f.get(k) for k in ("车号", "净重", "序号")}, "warnings": [],
                "seq_in_batch": r.seq_in_batch}

    def is_own(token: str, r, link: dict) -> bool:
        if r.source:
            return r.source == link_source(token)
        return (r.uploader or "").endswith(f"({link['label']})")     # 0.5.0 以前的老记录没有来源,按链接名认

    def own(token: str, rid: str, link: dict):
        r = svc.get(rid)
        if not is_own(token, r, link):
            raise RecordNotFound("记录不存在")      # 只能动这条链接自己传的单据
        return r

    @app.get("/c/{token}", include_in_schema=False)
    def page_capture_link(token: str):
        try:
            link_of(token)
        except ServiceError:
            return Response("链接无效或已停用,请联系管理员。", status_code=404, media_type="text/plain; charset=utf-8")
        return page("capture.html")

    @app.get("/api/v1/capture/{token}", tags=["capture"])
    def cap_info(token: str):
        try:
            link = link_of(token)
        except ServiceError as e:
            return err(e)
        n = svc.settings.naming
        return {"label": link["label"], "doc_type": canon_doc_type(link.get("doc_type")) if link.get("doc_type") else None,
                "doc_labels": n.labels, "customers": n.customers, "origins": svc.settings.origin_catalog,
                "origin_id": link.get("origin_id"), "capabilities": svc.health()["capabilities"]}

    @app.post("/api/v1/capture/{token}/records", tags=["capture"], status_code=201)
    async def cap_ingest(token: str, photo: UploadFile = File(...), name: str = Form(""),
                         doc_type: str = Form("site_in"), customer: str = Form(""), upload_id: str = Form(""), origin_id: str = Form("")):
        try:
            link = link_of(token)
            upload_allowed(link_source(token))
            who = (name.strip() or "监磅员")[:20]
            kind, recs = await spooled(await photo.read(), upload_id, f"{who}({link['label']})",
                                       canon_doc_type(link.get("doc_type") or doc_type), customer, source=link_source(token), origin_id=link.get("origin_id") or origin_id or None)
        except ServiceError as e:
            return err(e)
        if kind == "queued":
            return JSONResponse(queued_body(recs), status_code=202)

        def view(r, why):
            if not why:
                return capture_view(token, r)
            if is_own(token, r, link) and r.stage == "draft":
                return {**capture_view(token, r), "duplicate": why}     # 自己上次没提交的那张:给完整的、能改能提交的卡片
            return duplicate_brief(r, why)
        return JSONResponse({"records": [view(r, why) for r, why in recs]}, status_code=201)

    @app.get("/api/v1/capture/{token}/uploads/{upload_id}", tags=["capture"])
    def cap_upload_status(token: str, upload_id: str):
        try:
            link = link_of(token)
        except ServiceError as e:
            return err(e)
        m = svc.spool.get(upload_id)
        if m is None or m.get("source") != link_source(token):
            return err(RecordNotFound("没有这次上传"))
        m = svc.upload_status(upload_id)
        def view(r, why):
            if not why:
                return capture_view(token, r)
            if is_own(token, r, link) and r.stage == "draft":
                return {**capture_view(token, r), "duplicate": why}
            return duplicate_brief(r, why)
        return {"upload_id": upload_id, "status": m["status"], "last_error": m.get("last_error"),
                "records": [view(r, why) for r, why in svc.upload_result(m)]}

    @app.get("/api/v1/capture/{token}/records", tags=["capture"])
    def cap_list(token: str, hours: int = 36):
        """这条链接最近传的单据(含没提交的、没认出来的),手机上找回「上次没点提交」的那几张。"""
        try:
            link_of(token)
        except ServiceError as e:
            return err(e)
        since = (svc.clock() - __import__("datetime").timedelta(hours=max(1, min(hours, 24 * 7)))).isoformat(timespec="seconds")
        recs = svc.query(RecordQuery(source=link_source(token), limit=200))
        return {"records": [capture_view(token, r) for r in recs if r.created_at >= since]}

    @app.post("/api/v1/capture/{token}/records/{rid}/void", tags=["capture"])
    def cap_void(token: str, rid: str, body: dict = Body(default={})):
        try:
            link = link_of(token)
            r = own(token, rid, link)
            return capture_view(token, svc.void(r.id, r.uploader, body.get("reason") or "现场丢弃", privileged=False, own=True))
        except ServiceError as e:
            return err(e)

    @app.post("/api/v1/capture/{token}/records/{rid}/submit", tags=["capture"])
    def cap_submit(token: str, rid: str, body: dict = Body(default={})):
        try:
            link = link_of(token)
            r = own(token, rid, link)
            return capture_view(token, svc.submit(r.id, body.get("fields") or {}, r.uploader, privileged=False,
                                                  customer=body.get("customer"),
                                                  doc_type=None if link.get("doc_type") else body.get("doc_type"),
                                                  origin_id=link.get("origin_id") or body.get("origin_id"),
                                                  expected_version=body.get("expected_version", UNCONDITIONAL)))
        except ServiceError as e:
            return err(e)

    @app.get("/api/v1/capture/{token}/files/{key:path}", include_in_schema=False)
    def cap_file(token: str, key: str, request: Request):
        try:
            link = link_of(token)
            if not is_image_key(key):
                raise RecordNotFound("文件不存在")
            # 只给看这条链接自己传的图:按文件名里的批次号找到记录,再核对来源
            batch = key.rsplit("/", 1)[-1].split("_", 1)[0]
            if not any(is_own(token, r, link) for r in svc.query(RecordQuery(batch_id=batch, voided="all", limit=50))):
                raise RecordNotFound("文件不存在")
        except (ServiceError, ValueError):
            return Response(status_code=404)
        return image_response(request, key)

    if base_path:
        root = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
        root.state.service = svc
        root.mount(base_path, app)
        return root
    return app
