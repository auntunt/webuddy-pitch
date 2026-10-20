# -*- coding: utf-8 -*-
"""业务编排。只依赖 ports 里的协议,不知道底下是 OpenRouter 还是 vLLM、SQLite 还是 MySQL。

处理流水线与 0.1 版 process_upload 的调用顺序一致:
  解码归一化 -> 存原图 -> 分割 -> 按框裁剪 -> 并行识别 -> 逐张: 存裁剪图、校验、
  签名(识别附带框 -> 墨迹吸附 -> 校验;不行则专项定位一次) -> 入账 -> 发事件
"""
from __future__ import annotations

import asyncio, datetime, io, json, logging, threading, uuid
from typing import Callable, Mapping, Optional

from PIL import Image

from . import SUBSYSTEM_ID, __version__
from .config import Settings
from .domain import (DOC_SUPPLIER_OUT, DOC_SITE_IN, DOC_TYPES, FIELDS, canon_doc_type, Record, STAGE_APPROVED, STAGE_DRAFT, normalize_fields,
                     STAGE_SUBMITTED, STAGES, STATUS_FAILED, STATUS_REVIEWED, auto_status, pick_fields,
                     validate_fields, weight_check)
from .reconcile import reconcile
from .blob_keys import variant_key
from .imaging import TooManyPixels, crop_percent, ink_snap, normalize, sig_valid
from .ports import (BlobStore, EVENT_RECORD_APPROVED, EVENT_RECORD_CREATED, EVENT_RECORD_REVIEWED,
                    EVENT_RECORD_SUBMITTED, EventSink,
                    IdentityResolver, RecordQuery, RecordStore, VisionModel, describe_or_empty)

log = logging.getLogger("weighbill")

# Omission is distinct from an explicitly supplied null (legacy compatibility).
UNCONDITIONAL = object()

def check_version(rec: Record, expected_version) -> None:
    if expected_version is UNCONDITIONAL:
        return
    if type(expected_version) is not int or expected_version < 0:
        raise InvalidInput("版本必须是非负整数")
    if rec.version != expected_version:
        raise Conflict("记录版本已变化，请保留草稿并核对最新数据后再保存或审核")


class ServiceError(Exception):
    """可预期的业务错误;入站适配器据此选择状态码。"""
    http_status = 500


class NotConfigured(ServiceError):
    http_status = 500           # 与 0.1 版一致:未配置密钥时上传返回 500


class PayloadTooLarge(ServiceError):
    http_status = 413


class InvalidImage(ServiceError):
    http_status = 422


class RecordNotFound(ServiceError):
    http_status = 404


class InvalidInput(ServiceError):
    http_status = 422


class Forbidden(ServiceError):
    http_status = 403


class Conflict(ServiceError):
    http_status = 409


class TooManyRequests(ServiceError):
    http_status = 429


class Queued(ServiceError):
    """照片已经安全收下,但这次没处理成(库/存储/识别暂时不可用),后台会自动重试。不是失败。"""
    http_status = 202


class _NoTicket(Exception):
    """模型正常答复了,但照片里没找到可用的单据——这类失败才可能是照片的问题。"""


# 失败记录 warnings[0] 的前缀,页面据此决定让人「重拍」还是「原样重传」
FAULT_SERVICE = "识别服务出错:"
FAULT_NO_TICKET = "分割失败:"


def _jpeg(im: Image.Image) -> bytes:
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=92); return buf.getvalue()


def _png(im: Image.Image) -> bytes:
    buf = io.BytesIO(); im.save(buf, "PNG"); return buf.getvalue()


def _date_from_times(fields: dict) -> None:
    """有的厂商单据不单印「日期」,日期写在出站/入站时间里(「2026-10-11 08:30:20」)。
    日期空着就取出站时间里的日期(没有再取入站):台账按这一天归档,进场单纠车号也按它找当天车队。"""
    import re
    if fields.get("日期"):
        return
    for k in ("出站时间", "入站时间"):
        m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", str(fields.get(k) or ""))
        if m:
            fields["日期"] = f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}"
            return


class WeighbillService:
    def __init__(self, vision: VisionModel, store: RecordStore, blobs: BlobStore,
                 events: EventSink, identity: IdentityResolver, settings: Settings,
                 clock: Callable[[], datetime.datetime] = datetime.datetime.now,
                 new_id: Callable[[], str] = lambda: uuid.uuid4().hex):
        self.vision, self.store, self.blobs = vision, store, blobs
        self.events, self.identity, self.settings = events, identity, settings
        self.clock, self.new_id = clock, new_id
        self._ev_lock = threading.Lock()
        # 改单据都是「读-改-写」;同步接口跑在线程池里,不串行化就会互相覆盖(审计复现:审核把别人刚改的净重盖回旧值)
        self._mut_lock = threading.RLock()
        from .spool import Spool
        self.spool = Spool(settings.spool_path, settings.spool_keep_days)
        self._upload_locks: dict = {}
        self._ev_published = 0
        self._ev_failed = 0
        self._ev_last_error: Optional[str] = None

    # ------------------------------------------------------------ 可用性
    def vision_configured(self) -> bool:
        return bool(describe_or_empty(self.vision).get("configured"))

    def ensure_ingest_available(self) -> None:
        if not self.vision_configured():
            raise NotConfigured("服务端未配置 LLM_API_KEY(config.json 或环境变量)")

    # ------------------------------------------------------------ 入账
    def resolve_origin(self, origin_id, doc_type, existing=False):
        catalog = {r["id"]: r for r in self.settings.origin_catalog}
        if origin_id is None:
            if doc_type == "site_out":
                return ""  # 出库去向是客户；不能把混合原料的成品自动归到某个来源
            active = [r["id"] for r in catalog.values() if r["enabled"]]
            if len(active) != 1:
                raise InvalidInput("请选择来源单位")
            return active[0]
        if origin_id == "" and doc_type == "site_out":
            return ""
        if origin_id not in catalog or (not existing and not catalog[origin_id]["enabled"]):
            raise InvalidInput("来源单位无效或已停用，请重新选择")
        return origin_id

    def origin_name(self, origin_id):
        return next((r["name"] for r in self.settings.origin_catalog if r["id"] == origin_id), origin_id or "未关联来源")

    async def ingest(self, raw: bytes, uploader: str, doc_type: str = DOC_SITE_IN,
                     customer: Optional[str] = None, submit: bool = False, origin_id=None) -> list[Record]:
        """返回这次照片对应的台账记录。重复的磅单返回已有那条(不新建)。"""
        return [r for r, _ in await self.ingest_detailed(raw, uploader, doc_type, customer, submit, origin_id=origin_id)]

    async def ingest_detailed(self, raw: bytes, uploader: str, doc_type: str = DOC_SITE_IN,
                              customer: Optional[str] = None, submit: bool = False,
                              source: Optional[str] = None, upload_id: Optional[str] = None,
                              received_at: Optional[str] = None, origin_id=None) -> list[tuple]:
        """同 ingest,但每条带上「重复理由」:None = 新登记;字符串 = 这张单早已登记过,返回的是已有记录。
        submit=False:进「待现场确认」,等监磅员核对后提交(新流程);
        submit=True:直接「未审核」可见(0.1 版接口沿用的行为)。"""
        doc_type = canon_doc_type(doc_type)
        if doc_type not in DOC_TYPES:
            raise InvalidInput(f"未知的单据类型 {doc_type!r};可选 {list(DOC_TYPES)}")
        origin_id = self.resolve_origin(origin_id, doc_type, existing=bool(upload_id))
        self.ensure_ingest_available()
        if len(raw) > self.settings.max_upload_bytes:
            raise PayloadTooLarge(f"图片超过{self.settings.max_upload_bytes // (1024 * 1024)}MB")
        try:
            # 解码、缩放、编码都是 CPU 活,放到线程里做,别卡住其他人的请求
            im = await asyncio.to_thread(normalize, raw, self.settings.max_side)
        except TooManyPixels as e:
            raise InvalidImage(f"{e},请用手机相机正常拍一张") from e
        except Exception as e:
            raise InvalidImage(f"无法解码图片: {type(e).__name__}: {e}") from e

        # 带 upload_id(手机端生成、经服务器暂存区)时,这次上传的批次号、登记时间、记录 ID 都由它决定:
        # 处理到一半断了再处理一遍,写出来的是同一批记录(已经写进去的认得出来),不会多登记。
        if upload_id:
            import hashlib
            identity = json.dumps([upload_id, source or uploader, hashlib.sha256(raw).hexdigest()], ensure_ascii=False)
            h = hashlib.sha256(identity.encode("utf-8")).hexdigest()
            batch = h[:12]                     # 纯十六进制:图片键的格式校验只放行这种(安全约定,别放宽)
            now_dt = datetime.datetime.fromisoformat(received_at) if received_at else self.clock()
            rid = lambda seq: hashlib.sha256(f"{h}|{seq}".encode()).hexdigest()[:32]
        else:
            batch = self.new_id()[:12]
            now_dt = self.clock()
            rid = lambda seq: self.new_id()
        now = now_dt.isoformat(timespec="seconds")
        day = now_dt.strftime("%Y%m%d")
        prefix = f"images/{day}/{batch}"
        with Image.open(io.BytesIO(raw)) as source_image:
            fmt = source_image.format
        ext = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif", "TIFF": "tiff",
               "BMP": "bmp", "HEIF": "heic", "AVIF": "avif"}.get(fmt, "bin")
        orig_key = self.blobs.put(f"{prefix}_orig.{ext}", raw,
                                  Image.MIME.get(fmt, "application/octet-stream"))

        vd = describe_or_empty(self.vision)
        seg_model, rec_model = vd.get("seg_model"), vd.get("rec_model")

        def base(seq: int, **kw) -> Record:
            return Record(id=rid(seq), created_at=now, uploader=uploader, batch_id=batch,
                          seq_in_batch=seq, orig_key=orig_key, crop_key=None, sig_key=None,
                          model=rec_model, seg_model=seg_model, doc_type=doc_type,
                          customer=(customer or None), stage=STAGE_SUBMITTED if submit else STAGE_DRAFT,
                          submitted_by=uploader if submit else None, submitted_at=now if submit else None,
                          source=source, origin_id=origin_id, **kw)

        # 1) 分割
        try:
            seg = await self.vision.segment(im)
            if isinstance(seg, dict):
                seg = [seg]
            if not isinstance(seg, list):
                raise ValueError(f"分割结果不是数组: {type(seg).__name__}")
            boxes = [b for b in seg if isinstance(b, dict)
                     and all(isinstance(b.get(k), (int, float)) for k in ("x", "y", "w", "h"))]
            if not boxes:
                raise _NoTicket("分割模型未返回有效框")
        except _NoTicket as e:
            rec = base(0, fields={}, warnings=[f"{FAULT_NO_TICKET}{e}"], status=STATUS_FAILED, error=str(e))
            rec = self._commit(rec)
            return [(rec, None)]
        except Exception as e:
            if upload_id:
                raise  # 已持久化的照片保持待处理，服务恢复后自动重试
            # 网络、鉴权、限流、模型输出不是合法 JSON……都与照片无关
            msg = f"{type(e).__name__}: {e}"
            rec = base(0, fields={}, warnings=[f"{FAULT_SERVICE}{msg}"], status=STATUS_FAILED, error=msg)
            rec = self._commit(rec)
            return [(rec, None)]

        crops = [c for c in (crop_percent(im, b, pad=2) for b in boxes) if c is not None]
        if not crops:
            # 0.1 版此处返回 0 条记录:照片已落盘,台账却查不到这次上传
            e = f"分割返回 {len(boxes)} 个框,但全部无法裁出有效区域"
            rec = base(0, fields={}, warnings=[f"{FAULT_NO_TICKET}{e}"], status=STATUS_FAILED, error=e)
            rec = self._commit(rec)
            return [(rec, None)]

        # 2) 识别(并行,调用次序 = 裁剪次序)
        results = await asyncio.gather(*[self.vision.recognize(c) for c in crops],
                                       return_exceptions=True)

        if upload_id:
            for result in results:
                if isinstance(result, BaseException):
                    raise result
                if not isinstance(result, dict):
                    raise ValueError("识别结果不是对象，等待重试")

        # 3) 逐单据落库
        records: list[Record] = []
        for i, (crop, res) in enumerate(zip(crops, results), start=1):
            if upload_id:
                done_before = self.store.get(rid(i))
                if done_before is not None:            # 上一次处理已经登记了这一张
                    records.append((done_before, None)); continue
            crop_key = self.blobs.put(f"{prefix}_r{i}.jpg", _jpeg(crop), "image/jpeg")
            if isinstance(res, BaseException) or not isinstance(res, dict):
                err = (f"{type(res).__name__}: {res}" if isinstance(res, BaseException)
                       else f"识别结果不是对象: {type(res).__name__}")
                rec = base(i, fields={}, warnings=[f"{FAULT_SERVICE}{err}"], status=STATUS_FAILED, error=err)
                rec.crop_key = crop_key
                rec = self._commit(rec); records.append((rec, None))
                continue

            fields = normalize_fields(pick_fields(res))
            _date_from_times(fields)
            snap_warn = self._snap_plate(fields, origin_id) if doc_type == DOC_SITE_IN else None
            warns = validate_fields(fields) + ([snap_warn] if snap_warn else [])
            if vd.get("adapter") == "cpu_ocr" and not fields.get("日期"):
                warns.append("磅单日期未识别，请对照原图补录；不能以上传日期代替业务日期")
            wok, wmsg = weight_check(fields)
            if not wok:
                fields, wok, wmsg = await self._reread_weights(crop, fields, wok, wmsg)

            sig_key = None
            sig_box = res.get("签名框")
            for attempt in range(2):
                if attempt == 1:
                    try:
                        sig_box = await self.vision.locate_signature(crop)
                    except Exception:
                        break
                snapped = ink_snap(crop, sig_box) or sig_box
                sig = crop_percent(crop, snapped, pad=2) if snapped else None
                if sig is not None and sig_valid(crop, sig) is not None:
                    sig_key = self.blobs.put(f"{prefix}_r{i}_sig.png", _png(sig), "image/png")
                    break
            if sig_key is None:
                warns.append("签名定位失败,需人工框选")

            # 查重 + 登记必须是一步:多台服务器同一秒识别到同一张单时,两边都查不到对方就会各登记一条。
            # 用跨服务器的锁(按单据类型)包住;识别、截签名这些慢活都在锁外,锁里只有一次查询和一次写入。
            # 同一张磅单拍了两次(或一张照片里被切出两次):不新建,告诉上传的人已经登记过了。
            # 但只有「已审核的」或「同一个人自己重拍」才挡;别人传的、还没审核的那条可能是认错了号、甚至是故意占号
            # (审计复现:现场链接把自己草稿的单号改成下一个号,真单子就再也登记不进来)——这种照样登记,标疑似重复交审核员。
            def register(i=i, fields=fields, warns=warns, wok=wok, wmsg=wmsg, crop_key=crop_key, sig_key=sig_key):
                with self.store.named_lock(f"dedupe:{doc_type}"):
                    dup = self._find_duplicate(doc_type, fields, [r for r, d in records if d is None],
                                               exclude_id=rid(i) if upload_id else "", origin_id=origin_id)
                    w = list(warns)
                    if dup is not None:
                        old, why, clash_only = dup
                        same_person = old.uploader == uploader or (source and old.source == source)
                        if not clash_only and (old.stage == STAGE_APPROVED or same_person or old.batch_id == batch):
                            return old, why
                        w.append(f"疑似与 {old.ref_no or old.id} 是同一张磅单({why}),请核对后作废其中一张")
                    rec = base(i, fields=fields, warnings=w, weight_ok=wok, weight_msg=wmsg,
                               status=auto_status(w, wok, fields), error=None)
                    rec.crop_key, rec.sig_key = crop_key, sig_key
                    return self._commit(rec), None
            records.append(await asyncio.to_thread(register))
        return records

    def _find_duplicate(self, doc_type: str, fields: dict, batch: list, exclude_id: str = "", origin_id: str = "legacy") -> Optional[tuple]:
        """在同类单据里找同一张磅单:这次照片里已经登记的 + 最近上传的同类单据 + 磅单日期前后一天的。
        「最近上传」不能省:重拍多半就在几分钟内,但两次可能把时间(日期从它来)读得不一样。
        识别失败的、作废的记录不算。返回 (记录, 理由, 是否只是「号撞了」):
        号相同但车号、净重都对不上,不是同一张,但两条记录同号一定有一条错了——也要报出来让人核对。"""
        from .domain import norm, same_ticket
        cands, seen = list(batch), {r.id for r in batch}
        qs = [RecordQuery(doc_type=doc_type, limit=1000, origin_id=origin_id)]          # 最近上传的 1000 条:重拍就在几分钟内
        day = str(fields.get("日期") or "")[:10]
        try:
            d = datetime.date.fromisoformat(day)
            qs.append(RecordQuery(doc_type=doc_type, origin_id=origin_id, ticket_from=(d - datetime.timedelta(days=1)).isoformat(),
                                  ticket_to=(d + datetime.timedelta(days=1)).isoformat(), limit=None))
        except ValueError:
            pass
        for q in qs:
            for r in self.store.query(q):
                if r.id not in seen:
                    seen.add(r.id); cands.append(r)
        sn, clash = norm(fields.get("序号")), None
        for r in cands:
            if r.origin_id != origin_id or r.status == STATUS_FAILED or r.doc_type != doc_type or r.id == exclude_id or getattr(r, "voided_at", None):
                continue
            why = same_ticket(fields, r.fields or {})
            if why:
                log.info("重复磅单:%s,已有记录 %s", why, r.id)
                return r, why, False
            if clash is None and len(sn) >= 6 and sn == norm((r.fields or {}).get("序号")):
                clash = r
        if clash is not None:
            return clash, "磅单号相同,但车号、净重都对不上", True
        return None

    def _snap_plate(self, fields: dict, origin_id="legacy") -> Optional[str]:
        """进场单的车一定也出现在厂商出厂单上(否则配不上磅差)。认出的车号不在当天及前一天的厂商车队里、
        而车队里恰好只有一辆差一个字,就按那辆改,并留一条提示让现场核对——不悄悄改。"""
        from .domain import norm_plate
        from .ocr_fields import _lev
        plate = norm_plate(fields.get("车号"))
        if not plate:
            return None
        day = str(fields.get("日期") or "")[:10] or self.clock().date().isoformat()
        try:
            d = datetime.date.fromisoformat(day)
        except ValueError:
            d = self.clock().date()
        fleet = {norm_plate((r.fields or {}).get("车号")) for r in self.store.query(RecordQuery(
            doc_type=DOC_SUPPLIER_OUT, origin_id=origin_id, ticket_from=(d - datetime.timedelta(days=1)).isoformat(),
            ticket_to=d.isoformat(), limit=None))} - {""}
        if not fleet or plate in fleet:
            return None
        near = [p for p in fleet if _lev(plate, p) <= 1]
        if len(near) != 1:
            return None
        old, fields["车号"] = fields.get("车号"), near[0]
        return f"车号「{old}」按{self.settings.naming.supplier}出厂单纠正为「{near[0]}」,请对照磅单核对"

    # ------------------------------------------------------------ 暂存区:先收下,再处理
    def accept_upload(self, raw: bytes, upload_id: str, uploader: str, doc_type: str, customer: Optional[str],
                      source: Optional[str], origin_id=None) -> tuple[dict, bool]:
        """照片落盘即算收下。同一个 upload_id 重复来(手机重试)不重复收。"""
        from .spool import valid_id
        doc_type = canon_doc_type(doc_type)
        if doc_type not in DOC_TYPES:
            raise InvalidInput(f"未知的单据类型 {doc_type!r};可选 {list(DOC_TYPES)}")
        if not valid_id(upload_id):
            raise InvalidInput("upload_id 要求 8~64 位字母数字")
        if len(raw) > self.settings.max_upload_bytes:
            raise PayloadTooLarge(f"图片超过{self.settings.max_upload_bytes // (1024 * 1024)}MB")
        if not raw:
            raise InvalidImage("没有收到照片内容")
        previous = self.spool.get(upload_id)
        if previous:
            previous_origin = previous.get("origin_id", "" if canon_doc_type(previous["doc_type"]) == "site_out" else "legacy")
            if origin_id is None:
                origin_id = previous_origin
        origin_id = self.resolve_origin(origin_id, doc_type, existing=bool(previous))
        meta, created = self.spool.put(upload_id, raw, {"uploader": uploader, "doc_type": doc_type,
                                               "customer": customer or None, "source": source, "origin_id": origin_id,
                                               "received_at": self.clock().isoformat(timespec="seconds")})
        if meta.get("source") != source or (not source and meta.get("uploader") != uploader):
            raise Conflict("上传编号已被其他来源使用，请重新选择照片上传")
        if meta.get("origin_id", "" if doc_type == "site_out" else "legacy") != origin_id or meta.get("doc_type") != doc_type:
            raise Conflict("这次上传已经属于另一个来源或类型，请重新选择照片上传")
        return meta, created


    def upload_status(self, upload_id: str):
        meta = self.spool.get(upload_id)
        if meta and meta.get("status") == "done":
            ids = meta.get("record_ids") or []
            if not ids or any(self.store.get(rid) is None for rid in ids):
                return self.spool.requeue(upload_id, "登记记录不完整，正在恢复；请保留手机待传照片")
        return meta

    def upload_result(self, meta: dict) -> list:
        """已处理完的上传:按记下的记录 ID 取回 (记录, 重复理由)。"""
        out = []
        for rid in meta.get("record_ids") or []:
            r = self.store.get(rid)
            if r is not None:
                out.append((r, (meta.get("duplicates") or {}).get(rid)))
        return out

    async def process_upload(self, upload_id: str) -> list:
        """处理暂存区里的一次上传。成功返回 [(记录, 重复理由)];照片本身有问题抛 InvalidImage 等(不再重试);
        其他失败(库、对象存储、识别服务连不上)记下、过一会儿重试,抛 Queued。"""
        from .spool import DONE, REJECTED
        lock = self._upload_locks.setdefault(upload_id, asyncio.Lock())
        async with lock:
            m = self.upload_status(upload_id)
            if m is None:
                raise RecordNotFound("没有这次上传")
            if m["status"] == DONE:
                return self.upload_result(m)
            if m["status"] == REJECTED:
                raise InvalidImage(m.get("last_error") or "这张照片处理不了")
            self.spool.update(upload_id, status="processing", started_at=self.clock().isoformat(timespec="seconds"))
            try:
                res = await self.ingest_detailed(self.spool.raw(upload_id), m["uploader"], m["doc_type"], m.get("customer"),
                                                 source=m.get("source"), upload_id=upload_id, received_at=m["received_at"], origin_id=m.get("origin_id", "" if canon_doc_type(m["doc_type"]) == "site_out" else "legacy"))
            except (InvalidImage, InvalidInput, PayloadTooLarge) as e:
                self.spool.fail(upload_id, str(e), permanent=True)
                raise
            except NotConfigured as e:
                self.spool.fail(upload_id, str(e))
                raise Queued(str(e)) from e
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                log.warning("上传 %s 处理失败,稍后重试:%s", upload_id, msg)
                self.spool.fail(upload_id, msg)
                raise Queued(msg) from e
            self.spool.finish(upload_id, [r.id for r, _ in res], {r.id: why for r, why in res if why})
            self._upload_locks.pop(upload_id, None)
            return res

    async def drain_spool(self) -> int:
        """后台:把该处理的都处理一遍。返回这轮处理成功的次数。"""
        n = 0
        for m in self.spool.due(self.clock().isoformat(timespec="seconds")):
            try:
                await self.process_upload(m["upload_id"])
                n += 1
            except (Queued, ServiceError):
                pass
            except Exception:
                log.exception("暂存区处理异常 %s", m.get("upload_id"))
        return n

    async def _reread_weights(self, crop, fields: dict, wok: int, wmsg: str):
        """首读重量对不上账时单独复读三行重量。复读结果自身满足「总重-皮重=净重」才采用,
        并把原读数写进 weight_msg 留痕;复读失败或仍对不上,原样保留首读结果。"""
        reread = getattr(self.vision, "reread_weights", None)
        if reread is None:
            return fields, wok, wmsg
        try:
            got = await reread(crop)
        except Exception:
            return fields, wok, wmsg
        if not isinstance(got, dict):
            return fields, wok, wmsg
        cand = dict(fields, **{k: got.get(k) for k in ("总重", "皮重", "净重")})
        ok, msg = weight_check(cand)
        if not ok:
            return fields, wok, wmsg
        before = "/".join(str(fields.get(k)) for k in ("总重", "皮重", "净重"))
        return cand, ok, f"{msg}(首读对不上账,复读更正:原 {before})"

    def _new_ref(self, doc_type: str, created_at: str) -> str:
        """登记编号 = 类型前缀-登记日期-当天该类型第几张,如 RK-20261014-0007。按登记日期(不是磅单日期):
        磅单日期可能被认错、被改,编号不能跟着变。"""
        prefix = self.settings.naming.ref_prefixes.get(doc_type, "WB")
        day = (created_at or self.clock().isoformat())[:10].replace("-", "")
        return f"{prefix}-{day}-{self.store.next_ref(f'{prefix}-{day}'):04d}"

    def ensure_ref_numbers(self) -> int:
        """老记录补发登记编号,按登记先后;已经有号的不动。启动时调一次,幂等。"""
        n = 0
        for r in self.store.without_ref():
            n += self.store.assign_ref(r.id, self._new_ref(r.doc_type, r.created_at))
        if n:
            log.info("给 %d 条老记录补发了登记编号", n)
        return n

    def _commit(self, rec: Record) -> Record:
        """登记一条。同一 ID 已经在库里(上一次处理到一半断了)就用库里那条,不重复登记、不重复发号。"""
        old = self.store.get(rec.id)
        if old is not None:
            return old
        if not rec.ref_no:
            rec.ref_no = self._new_ref(rec.doc_type, rec.created_at)
        self.store.insert(rec)
        self._emit(EVENT_RECORD_CREATED, rec)
        return rec

    # ------------------------------------------------------------ 查询与复核
    def get(self, record_id: str) -> Record:
        rec = self.store.get(record_id)
        if rec is None:
            raise RecordNotFound("记录不存在")
        return rec

    def query(self, q: RecordQuery) -> list[Record]:
        if q.doc_type and canon_doc_type(q.doc_type) != q.doc_type:
            import dataclasses
            q = dataclasses.replace(q, doc_type=canon_doc_type(q.doc_type))
        return self.store.query(q)

    def _names(self) -> dict:
        n = self.settings.naming
        return {"supplier_name": n.supplier, "site_name": n.site, "doc_labels": n.labels}

    # ------------------------------------------------------------ 磅差阈值(页面可改)
    THRESHOLD_KEYS = {"diff_alert_pct": (float, 0, 100), "diff_alert_kg": (float, 0, 100000),
                      "transit_alert_minutes": (int, 0, 24 * 60)}

    def _threshold_file(self):
        return self.settings.data_path / "thresholds.json"

    def thresholds(self) -> dict:
        """config.json 给默认值,审核员在页面上改过的存在库里(多台服务器看到同一份),优先生效。
        0.5 及以前存在数据目录的 thresholds.json:库里还没有时导入一次。"""
        out = {k: getattr(self.settings, k) for k in self.THRESHOLD_KEYS}
        saved = self.store.get_setting("thresholds")
        if saved is None:
            f = self._threshold_file()
            if f.exists():
                saved = json.loads(f.read_text("utf-8"))
                self.store.set_setting("thresholds", saved)
        if saved:
            out.update({k: v for k, v in saved.items() if k in self.THRESHOLD_KEYS})
        return out

    def set_thresholds(self, changes: Mapping, actor: str, privileged: bool) -> dict:
        if not privileged:
            raise Forbidden("只有审核员能改磅差阈值")
        cur = self.thresholds()
        for k, v in changes.items():
            if k not in self.THRESHOLD_KEYS:
                raise InvalidInput(f"不认识的阈值 {k!r};可改 {list(self.THRESHOLD_KEYS)}")
            typ, lo, hi = self.THRESHOLD_KEYS[k]
            try:
                v = typ(v)
            except (TypeError, ValueError):
                raise InvalidInput(f"{k} 要填数字")
            if not lo <= v <= hi:
                raise InvalidInput(f"{k} 要在 {lo}~{hi} 之间")
            cur[k] = v
        self.store.set_setting("thresholds", {**cur, "updated_by": actor,
                                              "updated_at": self.clock().isoformat(timespec="seconds")})
        log.info("磅差阈值改为 %s(%s)", cur, actor)
        return cur

    # ------------------------------------------------------------ 权限
    def can_review(self, actor: str) -> bool:
        """审核员名单为空 = 所有登录用户都是审核员(试用期默认)。现场链接的上传人、匿名(没过网关登录的)永远不是。"""
        if not actor or actor == self.settings.anonymous_name:
            return False
        return not self.settings.reviewers or actor in self.settings.reviewers

    # 现场审核员修改的时候,系统自己写的提示(按车队纠了车号、疑似重复)不能被「重新校验」冲掉——审核员要靠它们
    # 判断这张单哪里是机器改过的(审计复现:现场一提交,纠车号的提示就没了,批量审核的风险提示也跟着漏掉)。
    _SYSTEM_NOTE = ("按", "疑似与", "签名定位失败")

    def _system_notes(self, rec: Record, before: dict) -> list:
        keep = []
        for w in rec.warnings or []:
            if "纠正为" in w:
                if rec.fields.get("车号") == before.get("车号"):     # 人改过车号,这条就不成立了
                    keep.append(w)
            elif w.startswith("疑似与") or w.startswith("签名定位失败"):
                keep.append(w)
        return keep

    def _apply(self, rec: Record, changes: Mapping, customer=None, doc_type=None, origin_id=None) -> dict:
        """把改动落到记录上(不写库)。返回实际变了的东西 {字段: [原值, 新值]},没变的不算。"""
        diff = {}
        if doc_type is not None:
            doc_type = canon_doc_type(doc_type)
            if doc_type not in DOC_TYPES:
                raise InvalidInput(f"未知的单据类型 {doc_type!r}")
            if doc_type != rec.doc_type:
                diff["单据类型"] = [rec.doc_type, doc_type]
                rec.doc_type = doc_type
        if origin_id is not None:
            value = self.resolve_origin(origin_id, rec.doc_type, existing=origin_id == rec.origin_id)
            if value != rec.origin_id:
                diff["来源单位"] = [rec.origin_id, value]
                rec.origin_id = value
        if rec.doc_type != "site_out" and not rec.origin_id:
            raise InvalidInput("出厂和入库单必须选择来源单位")
        if customer is not None:
            c = customer.strip() or None
            if c != rec.customer:
                diff["客户"] = [rec.customer, c]
                rec.customer = c
        before = dict(rec.fields or {})
        new = dict(before)
        new.update({k: v for k, v in (changes or {}).items() if k in FIELDS})
        normalize_fields(new)
        norm_v = lambda v: None if v is None or str(v).strip() == "" else str(v).strip()
        for k in FIELDS:
            if norm_v(new.get(k)) != norm_v(before.get(k)):
                diff[k] = [before.get(k), new.get(k)]
        if any(k in FIELDS for k in diff):
            rec.fields = new
            notes = self._system_notes(rec, before)
            rec.warnings = validate_fields(rec.fields) + notes
            rec.weight_ok, rec.weight_msg = weight_check(rec.fields)
        return diff

    def _guard_duplicate(self, rec: Record) -> None:
        """改完以后不能变成另一张已登记单据的重复(否则同一车算两遍,磅差翻倍——审计复现过)。"""
        dup = self._find_duplicate(rec.doc_type, rec.fields or {}, [], exclude_id=rec.id, origin_id=rec.origin_id)
        if dup is not None and not dup[2]:
            old = dup[0]
            raise Conflict(f"改完和 {old.ref_no or old.id} 是同一张磅单({dup[1]})。"
                           f"如果确实是同一张,作废其中一张即可,不要两条都留着")

    def _write(self, rec: Record, dedupe: bool = False) -> None:
        """写回一条改过的记录。读出来以后被别人(另一个请求、另一台服务器)改过就不写,让人刷新后再来——不覆盖别人的修改。
        dedupe=True(改了字段、恢复作废):在跨服务器的查重锁里先查「改完是不是和别的单重复」再写,和登记走同一把锁。"""
        import contextlib
        from .ports import StaleRecord
        with (self.store.named_lock(f"dedupe:{rec.doc_type}") if dedupe else contextlib.nullcontext()):
            if dedupe:
                self._guard_duplicate(rec)
            try:
                self.store.update(rec)
            except StaleRecord:
                raise Conflict("这张单刚被别人改过,刷新后再操作(你这次的改动没有保存)")

    def _log(self, rec: Record, actor: str, action: str, detail: dict) -> None:
        self.store.append_history(rec.id, self.clock().isoformat(timespec="seconds"), actor, action, detail)

    def history(self, record_id: str) -> list:
        self.get(record_id)
        return self.store.history(record_id)

    def review(self, record_id: str, changes: Mapping, reviewer: str, privileged: bool = True,
               customer=None, doc_type=None, origin_id=None, expected_version=UNCONDITIONAL) -> Record:
        """改字段。已提交/已审核的单据只有审核员能改;改了已审核的单据要重新审核。"""
        with self._mut_lock:
            rec = self.get(record_id)
            check_version(rec, expected_version)
            if rec.stage != STAGE_DRAFT and not privileged:
                raise Forbidden("已提交的单据只有审核员能改")
            if rec.voided_at:
                raise Conflict("这张已作废,先恢复再改")
            diff = self._apply(rec, changes or {}, customer, doc_type, origin_id)
            # 0.1 版语义:不改字段地保存 = 「看过了,没问题」,同样记成已复核(但不让已审核的单据回退)
            rec.status = STATUS_REVIEWED
            rec.reviewed_by = reviewer
            rec.reviewed_at = self.clock().isoformat(timespec="seconds")
            reopened = bool(diff) and rec.stage == STAGE_APPROVED
            if reopened:
                rec.stage, rec.approved_by, rec.approved_at = STAGE_SUBMITTED, None, None
            self._write(rec, dedupe=bool(diff))
            self._log(rec, reviewer, "修改" if diff else "复核无改动",
                      {"changes": diff, **({"note": "改了已审核的单据,回到未审核"} if reopened else {})})
        self._emit(EVENT_RECORD_REVIEWED, rec)
        return rec

    def submit(self, record_id: str, changes: Mapping, actor: str, privileged: bool = False,
               customer=None, doc_type=None, origin_id=None, expected_version=UNCONDITIONAL) -> Record:
        """监磅员核对(可改)后提交:待现场确认 → 未审核,台账实时可见。"""
        with self._mut_lock:
            rec = self.get(record_id)
            check_version(rec, expected_version)
            if rec.voided_at:
                raise Conflict("这张已作废,不能提交")
            if rec.stage == STAGE_APPROVED:
                raise Conflict("已审核的单据不能再提交")
            if rec.stage == STAGE_SUBMITTED and (changes or customer is not None or doc_type is not None or origin_id is not None) and not privileged:
                raise Forbidden("已提交的单据只有审核员能改")
            diff = self._apply(rec, changes or {}, customer, doc_type, origin_id)
            if not str(rec.fields.get("净重") or "").strip():
                raise InvalidInput("净重为空,补录后再提交;如果照片里没有单据,请重拍")
            if diff:
                rec.reviewed_by, rec.reviewed_at = actor, self.clock().isoformat(timespec="seconds")
                rec.status = STATUS_REVIEWED          # 人改过(含识别失败后手填的)
            if rec.stage == STAGE_DRAFT:
                rec.stage = STAGE_SUBMITTED
                rec.submitted_by, rec.submitted_at = actor, self.clock().isoformat(timespec="seconds")
            self._write(rec, dedupe=bool(diff))
            self._log(rec, actor, "现场提交", {"changes": diff} if diff else {})
        self._emit(EVENT_RECORD_SUBMITTED, rec)
        return rec

    def approve(self, ids: list, actor: str, privileged: bool, versions=UNCONDITIONAL) -> dict:
        """审核员对照纸质磅单后批量确认。逐条报告结果,不会因为一条不行整批失败。
        现场还没确认的(待现场确认)也能审,但会记下「审核员代为确认」——页面上要先二次确认。"""
        if not privileged:
            raise Forbidden("只有审核员能审核")
        if versions is not UNCONDITIONAL and not isinstance(versions, dict):
            raise InvalidInput("versions 必须是按记录 ID 索引的版本对象")
        done, skipped, events = [], [], []
        with self._mut_lock:
            now = self.clock().isoformat(timespec="seconds")
            for rid in dict.fromkeys(ids or []):
                rec = self.store.get(rid)
                if rec is None:
                    skipped.append({"id": rid, "reason": "记录不存在"}); continue
                try:
                    check_version(rec, versions.get(rid) if versions is not UNCONDITIONAL else UNCONDITIONAL)
                except (InvalidInput, Conflict) as e:
                    skipped.append({"id": rid, "reason": str(e), "code": type(e).__name__}); continue
                if rec.voided_at:
                    skipped.append({"id": rid, "reason": "已作废"}); continue
                if rec.stage == STAGE_APPROVED:
                    skipped.append({"id": rid, "reason": "已经审核过"}); continue
                if not str(rec.fields.get("净重") or "").strip():
                    skipped.append({"id": rid, "reason": "净重为空,先补录"}); continue
                was_draft = rec.stage == STAGE_DRAFT
                if was_draft:
                    rec.submitted_by, rec.submitted_at = actor, now
                rec.stage, rec.approved_by, rec.approved_at = STAGE_APPROVED, actor, now
                try:
                    self._write(rec)
                except Conflict:
                    skipped.append({"id": rid, "reason": "刚被别人改过,刷新核对后再审", "code": "Conflict"}); continue
                self._log(rec, actor, "审核通过", {"note": "现场没确认,审核员代为确认"} if was_draft else {})
                events.append(rec); done.append(rid)
        for rec in events:
            self._emit(EVENT_RECORD_APPROVED, rec)
        return {"approved": done, "skipped": skipped}

    def void(self, record_id: str, actor: str, reason: str, privileged: bool, own: bool = False) -> Record:
        """作废(不删):审核员可以作废任何一张;现场的人只能丢弃自己还没提交的。作废的不进汇总、磅差、导出、查重,编号保留。"""
        reason = (reason or "").strip()
        if not reason:
            raise InvalidInput("写一句作废原因(比如:拍错了、重复了、试拍)")
        with self._mut_lock:
            rec = self.get(record_id)
            if rec.voided_at:
                return rec
            if not privileged and not (own and rec.stage == STAGE_DRAFT):
                raise Forbidden("已提交的单据只有审核员能作废")
            rec.voided_by, rec.voided_at, rec.void_reason = actor, self.clock().isoformat(timespec="seconds"), reason[:200]
            self._write(rec)
            self._log(rec, actor, "作废", {"reason": rec.void_reason})
            return self.get(record_id)

    def restore(self, record_id: str, actor: str, privileged: bool) -> Record:
        if not privileged:
            raise Forbidden("只有审核员能恢复作废的单据")
        with self._mut_lock:
            rec = self.get(record_id)
            if not rec.voided_at:
                return rec
            reason = rec.void_reason
            rec.voided_by = rec.voided_at = rec.void_reason = None
            self._write(rec, dedupe=True)
            self._log(rec, actor, "恢复", {"was": reason})
            return self.get(record_id)

    def flag(self, record_id: str, actor: str, note: Optional[str], privileged: bool) -> Record:
        """有疑问:审核员挂一句说明(note 为空 = 取消)。不改数字、不改审核状态。"""
        if not privileged:
            raise Forbidden("只有审核员能标记有疑问")
        with self._mut_lock:
            rec = self.get(record_id)
            note = (note or "").strip()[:200] or None
            if note == rec.flag_note:
                return rec
            old, rec.flag_note = rec.flag_note, note
            self._write(rec)
            self._log(rec, actor, "有疑问" if note else "取消疑问", {"note": note, "was": old})
            return self.get(record_id)

    # ------------------------------------------------------------ Excel
    def export_records_xlsx(self, doc_type: str, q: RecordQuery) -> bytes:
        from .export_xlsx import records_workbook
        doc_type = canon_doc_type(doc_type)
        if doc_type not in DOC_TYPES:
            raise InvalidInput(f"未知的单据类型 {doc_type!r}")
        recs = self.store.query(RecordQuery(q.date_from, q.date_to, q.q, q.status, None, doc_type, q.stage,
                                            q.ticket_from, q.ticket_to, origin_id=q.origin_id))
        return records_workbook(doc_type, recs, self.blobs.open, self.settings.naming, self.origin_name)

    def export_reconciliation_xlsx(self, date_from: str = "", date_to: str = "", origin_id="") -> bytes:
        from .export_xlsx import reconciliation_workbook
        return reconciliation_workbook(self.reconciliation(date_from, date_to, origin_id), self.blobs.open, self.settings.naming, self.origin_name)

    # ------------------------------------------------------------ 磅差
    def reconciliation(self, date_from: str = "", date_to: str = "", origin_id="") -> dict:
        """厂商出厂 ↔ 本场进场。按磅单日期取数。两边都多取前后两天、配完再按日期筛:
        只多取一边时,筛选区间会改变谁和谁配上(同样的数据,筛 10-05 和不筛给出不同配对——审计复现过)。
        待现场确认(还没人核对过)和作废的单据不进磅差。"""
        import datetime as _dt
        def shift(d, n):
            return (_dt.date.fromisoformat(d) + _dt.timedelta(days=n)).isoformat() if d else ""
        supplier = self._counted(self.store.query(RecordQuery(doc_type=DOC_SUPPLIER_OUT, origin_id=origin_id, ticket_from=shift(date_from, -2),
                                                              ticket_to=shift(date_to, 2), limit=None)))
        site = self._counted(self.store.query(RecordQuery(doc_type=DOC_SITE_IN, origin_id=origin_id, ticket_from=shift(date_from, -2),
                                                          ticket_to=shift(date_to, 2), limit=None)))
        th = self.thresholds()
        res = reconcile(supplier, site, th["diff_alert_pct"], th["transit_alert_minutes"], diff_alert_kg=th["diff_alert_kg"])
        res["days"] = [d for d in res["days"]
                       if d["date"] and (not date_from or d["date"] >= date_from) and (not date_to or d["date"] <= date_to)]
        return res

    @staticmethod
    def _counted(recs: list) -> list:
        """进汇总和磅差的单据:现场已确认(未审核/已审核)且没作废。待现场确认的不算——可能还没人看过识别结果。"""
        return [r for r in recs if r.stage != STAGE_DRAFT and not getattr(r, "voided_at", None)]

    def stats(self, date_from: str = "", date_to: str = "", origin_id="") -> dict:
        """统计看板:三类磅单按磅单日期取数 + 同一区间的磅差配对。
        吨位、车次、磅差只算现场已确认的;审核进度算全部(包括待现场确认),另报待确认的张数和吨位,
        让看板上的数字说清楚自己包含什么。"""
        from .domain import STAGES
        from .stats import summarize, _net
        every = {k: [r for r in self.store.query(RecordQuery(doc_type=k, origin_id=origin_id, ticket_from=date_from, ticket_to=date_to,
                                                             limit=None)) if not getattr(r, "voided_at", None)]
                 for k in DOC_TYPES}
        out = summarize({k: self._counted(v) for k, v in every.items()}, self.reconciliation(date_from, date_to, origin_id))
        for k, v in out["kinds"].items():
            v["label"] = self.settings.naming.labels[k]
            v["stages"] = {s: sum(r.stage == s for r in every[k]) for s in STAGES}
            drafts = [r for r in every[k] if r.stage == STAGE_DRAFT]
            v["draft_tickets"], v["draft_net"] = len(drafts), sum(_net(r) or 0 for r in drafts if r.status != "failed")
            v["approved_net"] = sum(_net(r) or 0 for r in every[k] if r.stage == STAGE_APPROVED and r.status != "failed")
        out["params"] = {"date_from": date_from, "date_to": date_to, "origin_id": origin_id, **self._names(),
                         **self.thresholds()}
        return out

    def reconciliation_view(self, res: dict) -> dict:
        def brief(r):
            v = self.record_view(r)
            return {k: v[k] for k in ("id", "fields", "stage", "stage_label", "status", "crop_path", "orig_path",
                                      "warnings", "weight_ok", "origin_id", "origin_name")}
        days = []
        for d in res["days"]:
            days.append({**{k: d[k] for k in ("date", "trucks", "supplier_count", "site_count", "supplier_gross", "supplier_tare",
                                               "supplier_net", "site_gross", "site_tare", "site_net", "diff_gross",
                                               "diff_tare", "diff", "diff_pct", "alerts", "unmatched")},
                         "pairs": [{**{k: x[k] for k in ("plate", "supplier_net", "site_net", "diff", "diff_pct",
                                                          "gap_min", "diff_alert", "gap_alert")},
                                    "date": x["date"].isoformat() if x["date"] else None,
                                    "supplier": brief(x["supplier"]), "site": brief(x["site"])} for x in d["pairs"]],
                         "unmatched_supplier": [brief(r) for r in d["unmatched_supplier"]],
                         "unmatched_site": [brief(r) for r in d["unmatched_site"]]})
        return {"days": days, "params": {**res["params"], **self._names()}}

    # ------------------------------------------------------------ 每日核对:主动找「悄悄丢了」的
    def verify(self, fix: bool = False) -> dict:
        """逐条核对:台账里每张单的图在不在存储里;暂存区里「处理完了」的照片,登记在不在库里;
        有没有卡在暂存区很久的;有没有缺登记编号的。fix=True 时把「处理完却找不到登记」的照片重新排队。"""
        problems = {"missing_images": [], "lost_registrations": [], "stuck_uploads": [], "missing_ref_no": []}
        exists = getattr(self.blobs, "exists", None)

        def have(key):
            if exists:
                return exists(key)
            try:
                self.blobs.open(key); return True
            except (FileNotFoundError, KeyError):
                return False
        recs = self.store.query(RecordQuery(limit=None, voided="all"))
        for r in recs:
            for k in (r.orig_key, r.crop_key, r.sig_key):
                if k and not have(k):
                    problems["missing_images"].append({"id": r.id, "ref_no": r.ref_no, "key": k})
            if not r.ref_no:
                problems["missing_ref_no"].append(r.id)
        for m in self.spool.done_items():
            gone = [rid for rid in m.get("record_ids") or [] if self.store.get(rid) is None]
            if gone or not m.get("record_ids"):
                problems["lost_registrations"].append({"upload_id": m["upload_id"], "missing": gone})
                if fix:
                    self.spool.requeue(m["upload_id"], "核对发现处理完却找不到登记,重新登记")
        cut = (self.clock() - datetime.timedelta(minutes=30)).isoformat(timespec="seconds")
        for m in self.spool.pending_items():
            if m.get("status") != "rejected" and m.get("received_at", "9") < cut:
                problems["stuck_uploads"].append({"upload_id": m["upload_id"], "since": m.get("received_at"),
                                                  "last_error": m.get("last_error")})
        return {"records": len(recs), "ok": not any(problems.values()), **problems}

    # ------------------------------------------------------------ 图片(含预览)
    def image(self, key: str) -> bytes:
        """取一张图。预览图(_t/_m)没有就从原图现做一张、存下再给——老数据第一次被看时自动补齐。"""
        from .blob_keys import is_image_key, variant_of
        from .imaging import preview
        if not is_image_key(key):
            raise RecordNotFound("文件不存在")
        try:
            return self.blobs.open(key)
        except (FileNotFoundError, KeyError):
            v = variant_of(key)
            if not v:
                raise RecordNotFound("文件不存在")
        try:
            base = self.blobs.open(v[0])
        except (FileNotFoundError, KeyError):
            raise RecordNotFound("文件不存在")
        data = preview(base, v[1])
        try:
            self.blobs.put(key, data, "image/jpeg")
        except Exception as e:                       # 存不下也照样给图,下次再做
            log.warning("预览图存不下 %s: %s", key, e)
        return data

    # ------------------------------------------------------------ 对外表示
    def url_or_none(self, key: Optional[str]) -> Optional[str]:
        return self.settings.app_path(self.blobs.url(key)) if key else None

    def record_view(self, rec: Record) -> dict:
        """HTTP/CSV/事件共用的记录表示。前 15 个键与 0.1 版响应逐一对应。"""
        return {
            "id": rec.id, "version": rec.version, "created_at": rec.created_at, "uploader": rec.uploader,
            "batch_id": rec.batch_id, "seq_in_batch": rec.seq_in_batch,
            "origin_id": rec.origin_id, "origin_name": self.origin_name(rec.origin_id),
            "orig_path": self.url_or_none(rec.orig_key), "crop_path": self.url_or_none(rec.crop_key),
            "sig_path": self.url_or_none(rec.sig_key),
            "fields": rec.fields, "warnings": rec.warnings, "weight_ok": rec.weight_ok,
            "weight_msg": rec.weight_msg, "status": rec.status, "model": rec.model, "error": rec.error,
            # 0.2.0 追加
            "seg_model": rec.seg_model, "reviewed_by": rec.reviewed_by, "reviewed_at": rec.reviewed_at,
            # 0.3.0 追加
            "doc_type": rec.doc_type, "doc_type_label": self.settings.naming.labels.get(rec.doc_type, rec.doc_type),
            "customer": rec.customer, "stage": rec.stage, "stage_label": STAGES.get(rec.stage, rec.stage),
            "submitted_by": rec.submitted_by, "submitted_at": rec.submitted_at,
            "approved_by": rec.approved_by, "approved_at": rec.approved_at,
            # 0.4.2
            "ref_no": rec.ref_no,
            # 0.5.0
            "voided_by": rec.voided_by, "voided_at": rec.voided_at, "void_reason": rec.void_reason,
            "flag_note": rec.flag_note,
            # 0.7.0 预览:列表用缩略图,详情用中图,点放大才取原图
            "thumb_path": self.url_or_none(variant_key(rec.crop_key or rec.orig_key, "t")),
            "preview_path": self.url_or_none(variant_key(rec.crop_key or rec.orig_key, "m")),
        }

    def export_csv(self, q: RecordQuery) -> str:
        data = [self.record_view(r) for r in self.store.query(RecordQuery(q.date_from, q.date_to, q.q,
                                                                          q.status, limit=None, origin_id=q.origin_id))]
        # 0.5.0 起在末尾追加单据类型、审核阶段、登记编号(前面的列与 0.1 版一致,老的对接方不受影响)
        cols = (["created_at", "uploader", "status", "weight_msg"] + FIELDS
                + ["warnings", "orig_path", "crop_path", "sig_path", "id", "doc_type_label", "stage_label", "ref_no", "origin_id", "origin_name"])
        head = (["登记时间", "上传人", "状态", "重量校验"] + FIELDS
                + ["校验警告", "原图", "单据图", "签名图", "记录ID", "单据类型", "审核阶段", "登记编号", "来源编号", "来源单位"])

        def esc(v):
            v = "" if v is None else str(v)
            if v[:1] in ("=", "+", "-", "@", "\t", "\r"):     # CSV 公式注入:Excel 会把这些开头的当公式算
                v = "'" + v
            return '"' + v.replace('"', '""') + '"'
        lines = [",".join(head)]
        for r in data:
            row = []
            for c in cols:
                if c in FIELDS: row.append(esc(r["fields"].get(c)))
                elif c == "warnings": row.append(esc(";".join(r["warnings"])))
                else: row.append(esc(r.get(c)))
            lines.append(",".join(row))
        return "﻿" + "\r\n".join(lines)

    # ------------------------------------------------------------ 事件
    def _envelope(self, etype: str, rec: Record) -> dict:
        return {
            "specversion": "1.0", "id": uuid.uuid4().hex, "source": f"/{SUBSYSTEM_ID}",
            "type": etype, "subject": rec.id,
            "time": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "datacontenttype": "application/json", "dataschema": f"weighbill/record/{__version__}",
            "data": self.record_view(rec),
        }

    def _emit(self, etype: str, rec: Record) -> None:
        try:
            self.events.publish(self._envelope(etype, rec))
            with self._ev_lock:
                self._ev_published += 1
        except Exception as e:
            # 已入账的记录不因下游通知失败而回滚,但失败必须在健康检查里看得见
            msg = f"{etype} {rec.id}: {type(e).__name__}: {e}"
            log.warning("事件投递失败 %s", msg)
            with self._ev_lock:
                self._ev_failed += 1
                self._ev_last_error = msg

    # ------------------------------------------------------------ 健康
    def health(self) -> dict:
        checks = {}
        for name, obj in (("record_store", self.store), ("blob_store", self.blobs)):
            try:
                obj.ping()
                checks[name] = {"ok": True, **describe_or_empty(obj)}
            except Exception as e:
                checks[name] = {"ok": False, "error": f"{type(e).__name__}: {e}", **describe_or_empty(obj)}
        vd = describe_or_empty(self.vision)
        vd.pop("api_key", None)
        checks["vision"] = {"ok": bool(vd.get("configured")), "probed": False, **vd}
        with self._ev_lock:
            ev = {"published": self._ev_published, "failed": self._ev_failed,
                  "last_error": self._ev_last_error}
        checks["event_sink"] = {"ok": self._ev_failed == 0, **describe_or_empty(self.events), **ev}
        checks["identity"] = {"ok": True, **describe_or_empty(self.identity)}
        # 暂存区:有积压不影响收照片,但积压超过半小时说明后面有东西坏了(库/对象存储/识别),要人看
        try:
            sp = self.spool.stats()
            old = sp["oldest_received_at"]
            stuck = bool(old) and old < (self.clock() - datetime.timedelta(minutes=30)).isoformat(timespec="seconds")
            checks["spool"] = {"ok": not stuck, "path": str(self.spool.root), **sp}
        except Exception as e:
            checks["spool"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

        ingest_ok = checks["record_store"]["ok"] and checks["blob_store"]["ok"] and checks["vision"]["ok"]
        read_ok = checks["record_store"]["ok"]
        return {
            "subsystem": SUBSYSTEM_ID, "version": __version__,
            "status": "ok" if ingest_ok and checks["event_sink"]["ok"] and checks["spool"]["ok"]
                      else ("degraded" if read_ok else "down"),
            "capabilities": {"ingest": ingest_ok, "query": read_ok, "review": read_ok, "export": read_ok},
            "checks": checks,
        }
