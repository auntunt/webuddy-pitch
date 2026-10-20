# -*- coding: utf-8 -*-
"""配置加载。优先级与 0.1 版一致:内置默认 < 环境变量 < config.json。

新增的两个环境变量只决定「去哪找」,不参与上面的覆盖链:
  WEIGHBILL_CONFIG    配置文件路径(默认 <项目根>/config.json)
  WEIGHBILL_DATA_DIR  数据目录(默认 <项目根>/data)
"""
from __future__ import annotations

import json, os
from dataclasses import dataclass, field, fields as dc_fields
from pathlib import Path
from typing import Mapping, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SECRET_KEYS = ("api_key", "webhook_secret", "capture_links", "gateway_secret", "s3_access_key", "s3_secret_key",
               "db_password")


@dataclass
class Settings:
    # 视觉模型:openai_compatible(大模型,走 API)或 cpu_ocr(无显卡,数据不出服务器)
    vision_adapter: str = "openai_compatible"
    base_url: str = "https://openrouter.ai/api/v1"
    api_key: str = ""
    seg_model: str = "google/gemini-3.8-flash"
    rec_model: str = "qwen/qwen3-vl-30b-a3b-instruct"
    enhance: bool = True
    max_side: int = 2000
    # cpu_ocr:一张照片里按标题切单的关键字;单号固定前缀(点阵 C/G 混时按它纠正,如 ["CZD"])
    ocr_anchors: list = field(default_factory=lambda: ["称重单", "过磅单", "磅单", "称量单"])
    serial_prefixes: list = field(default_factory=list)
    # 存储
    record_store: str = "sqlite"
    blob_store: str = "local"
    data_dir: str = ""                 # 空 = <项目根>/data
    # 原样带前缀的部署路径；空字符串保持根部署。
    base_path: str = ""
    # 仅回环代理预览可用：精确 Origin 白名单，不读取转发 Host。
    local_preview_origins: list = field(default_factory=list)
    # 身份
    identity_header: str = "X-Portal-User"
    anonymous_name: str = "匿名"
    # 网关共享密钥:配了以后,只有带着 X-Gateway-Secret(由 Caddy/nginx 加上)的请求,操作人头才算数;
    # 本机别的程序、借别的服务转发过来的请求一律当匿名(匿名永远不是审核员)。空 = 不检查(本地开发)。
    gateway_secret: str = ""
    # 只给本机开发/演示用:没有网关、请求里也没有操作人头时,当作这个人(否则本机打开页面谁都审核不了)。
    # 生产不要配——配了 gateway_secret 时它不起作用。
    local_user: str = ""
    # 每条现场链接 / 每个登录用户每小时最多上传几次(链接泄露了也只能这么多,不至于无限占 CPU、占磁盘)
    upload_limit_per_hour: int = 200
    # 服务器暂存区:照片先落本机磁盘再回「已收到」,识别/写库/存图失败就自动重试。多台节点时每台用自己的本地盘。
    spool_dir: str = ""            # 空 = 数据目录下的 spool/
    # 数据库(record_store = "oceanbase")
    db_host: str = ""
    db_port: int = 2881
    db_user: str = ""              # OceanBase 的用户写成 用户名@租户,如 root@weighbill
    db_password: str = ""
    db_name: str = "weighbill"
    # 对象存储(blob_store = "s3")
    s3_endpoint: str = ""          # 如 http://10.0.0.21:9000
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "weighbill"
    s3_region: str = "us-east-1"
    blob_cache_dir: str = ""       # 本机读缓存;空 = 数据目录下的 blob-cache/
    blob_cache_mb: int = 2048
    spool_keep_days: int = 7       # 处理完的照片在暂存区再留几天(第二份保险)
    spool_sync_wait: int = 90      # 上传时最多当场等多少秒出结果;超时就先回「已收到」,后台接着做
    # 事件
    event_sink: str = "null"           # null | jsonl | webhook
    events_path: str = ""              # 空 = <data_dir>/events.jsonl
    webhook_url: str = ""
    webhook_secret: str = ""
    # 入站限制
    max_upload_bytes: int = 30 * 1024 * 1024
    # 流程与权限(0.3.0)
    # 审核员:能批量审核、能改已提交的单据。空 = 所有登录用户都是审核员(试用期默认)
    reviewers: list = field(default_factory=list)
    # 现场上传链接:{"<随机令牌>": {"label": "厂商现场", "doc_type": "supplier_out"}};
    # 监磅员用 /c/<令牌> 直接拍,不用登录。doc_type 可省略,省略则页面上自己选
    capture_links: dict = field(default_factory=dict)
    # 磅差:单车 |磅差率| 超过这个百分比标红;时间差超过这个分钟数标红,0 = 不标(会上结论:时间不准,只作参考)
    diff_alert_pct: float = 1.0
    # 同时还要超过这么多 kg 才标红,0 = 只看百分比。这两个是默认值,审核员可在页面上改(存在数据目录 thresholds.json)
    diff_alert_kg: float = 0
    # 名字全在这里配,代码里不写具体厂商(2026-10-14):
    # supplier_name 厂商(出厂单那一方),site_name 我们的场;页签默认「{厂商}出厂 / {场}进场 / {场}出场」
    origins: list = field(default_factory=list)  # [{id, name, enabled}]; stable IDs, never reuse
    supplier_name: str = "厂商"
    site_name: str = "本场"
    # 可选覆盖:{"supplier_out": "...", "site_in": "...", "site_out": "..."}
    doc_labels: dict = field(default_factory=dict)
    doc_titles: dict = field(default_factory=dict)       # Excel 每天一张表的大标题
    summary_titles: dict = field(default_factory=dict)   # Excel 月度汇总表标题,{m} 处填月份
    summary_sheets: dict = field(default_factory=dict)   # Excel 月度汇总表的工作表名
    customers: list = field(default_factory=list)        # 出场单客户快捷选项
    doc_notes: dict = field(default_factory=dict)        # Excel 每天一张表末尾的填表说明
    out_sheet_suffix: str = "（{customer}）"              # 出场单 Excel 分表名后缀
    ref_prefixes: dict = field(default_factory=dict)     # 登记编号前缀,默认 厂商出厂 CC / 进场 JC / 出场 CK
    transit_alert_minutes: int = 0
    # 来源说明(不参与业务,只给健康检查与排障用)
    config_file: str = ""

    @property
    def validated_base_path(self) -> str:
        import re
        value = self.base_path
        if not isinstance(value, str) or (value and (
                not re.fullmatch(r"(?:/[A-Za-z0-9_-][A-Za-z0-9_.-]*)+", value)
                or any(p in (".", "..") for p in value.split("/")))):
            raise ValueError("base_path 必须为空或无尾斜杠的绝对路径，不允许转义、查询或路径穿越")
        return value

    def app_path(self, path: str) -> str:
        """Only local absolute URLs belong to this app; preserve external/S3 URLs."""
        return self.validated_base_path + path if path.startswith("/") and not path.startswith("//") else path

    @property
    def origin_catalog(self) -> list:
        import re
        rows = self.origins or [{"id": "legacy", "name": self.supplier_name, "enabled": True}]
        out, seen = [], set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("origins 必须是包含 id/name 的对象列表")
            key, name = row.get("id"), row.get("name")
            enabled = row.get("enabled", True)
            if not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", key) or key in seen:
                raise ValueError("来源 id 必须唯一，为 1~40 位字母数字、下划线或短横线")
            if not isinstance(name, str) or not name.strip() or len(name) > 100 or not isinstance(enabled, bool):
                raise ValueError("来源 name 不能为空且不超过100字，enabled 必须为布尔值")
            seen.add(key); out.append({"id": key, "name": name.strip(), "enabled": enabled})
        if "legacy" not in seen:
            raise ValueError("origins 必须保留 legacy（历史来源）；停用时设置 enabled=false，不删除或复用编号")
        return out

    @property
    def naming(self):
        from .domain import Naming
        return Naming.build(self.supplier_name, self.site_name, self.doc_labels, self.doc_titles,
                            self.summary_titles, self.customers, self.doc_notes, self.out_sheet_suffix,
                            self.summary_sheets, self.ref_prefixes)

    @property
    def blob_cache_path(self) -> Path:
        return Path(self.blob_cache_dir) if self.blob_cache_dir else self.data_path / "blob-cache"

    @property
    def spool_path(self) -> Path:
        return Path(self.spool_dir) if self.spool_dir else self.data_path / "spool"

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir) if self.data_dir else PROJECT_ROOT / "data"

    @property
    def events_file(self) -> Path:
        return Path(self.events_path) if self.events_path else self.data_path / "events.jsonl"

    def public(self) -> dict:
        """可以对外展示的配置:密钥只报是否已设置。"""
        out = {}
        for f in dc_fields(self):
            v = getattr(self, f.name)
            out[f.name] = ("<set>" if v else "<unset>") if f.name in SECRET_KEYS else v
        return out


_ENV = {"base_url": "LLM_BASE_URL", "api_key": "LLM_API_KEY",
        "seg_model": "SEG_MODEL", "rec_model": "REC_MODEL"}


def load_settings(env: Optional[Mapping[str, str]] = None, config_path: Optional[Path] = None) -> Settings:
    env = os.environ if env is None else env
    s = Settings()
    for attr, var in _ENV.items():
        if env.get(var):
            setattr(s, attr, env[var])
    if env.get("WEIGHBILL_DATA_DIR"):
        s.data_dir = env["WEIGHBILL_DATA_DIR"]

    path = Path(config_path or env.get("WEIGHBILL_CONFIG") or PROJECT_ROOT / "config.json")
    if path.exists():
        data = json.loads(path.read_text("utf-8"))
        known = {f.name for f in dc_fields(Settings)}
        unknown = sorted(set(data) - known)
        if unknown:   # 拼错的键静默忽略 = 以为配上了其实没配
            raise ValueError(f"{path} 含未知配置项: {unknown};可用项见 weighbill manifest 的 config_keys")
        for k, v in data.items():
            setattr(s, k, v)
        s.config_file = str(path)
    return s
