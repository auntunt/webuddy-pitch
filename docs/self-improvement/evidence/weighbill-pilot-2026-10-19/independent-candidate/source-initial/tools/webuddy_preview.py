"""Isolated local collaboration preview; no production config, data or OCR.

Run from a fixed Git checkout. The coordinator passes a dedicated data directory.
The first run seeds explicit synthetic records; later runs preserve edits.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from weighbill.adapters.vision_scripted import ScriptedVision
from weighbill.bootstrap import build_service
from weighbill.config import Settings
from weighbill.domain import Record, STAGE_SUBMITTED, STATUS_REVIEWED
from weighbill.http_api import create_app


class NoPreviewOCR(ScriptedVision):
    def describe(self):
        return {'adapter': 'scripted-preview-disabled', 'configured': False,
                'note': '合成台账验收；未连接真实识别服务，上传识别不可用'}


def prepare(data_dir: Path, prefix: str):
    marker = data_dir / 'webuddy-preview.json'
    if data_dir.is_symlink():
        raise ValueError('预览数据目录不能是符号链接')
    if data_dir.exists() and any(data_dir.iterdir()) and not marker.is_file():
        raise ValueError('已有非预览数据，拒绝初始化；请指定新的专用目录')
    if marker.exists() and json.loads(marker.read_text()).get('kind') != 'weighbill-synthetic-preview-v1':
        raise ValueError('预览数据标记不匹配')
    settings = Settings(data_dir=str(data_dir), base_path=prefix,
                        local_preview_origins=['http://127.0.0.1:8793'],
                        local_user='本地验收员', reviewers=['本地验收员', 'reviewer-A', 'reviewer-B'],
                        site_name='协作验收（合成数据）', supplier_name='合成来源',
                        doc_labels={'site_in': '协作验收 · 合成台账'},
                        capture_links={}, api_key='')
    service = build_service(settings, vision=NoPreviewOCR())
    if not marker.exists():
        # These are newly generated test images, not transformed user originals.
        from tests.fixtures import photo
        today = date.today().isoformat()
        day_key = today.replace('-', '')
        records = []
        for i in range(1, 4):
            batch = f'{i:012x}'
            key = f'images/{day_key}/{batch}_orig.jpg'
            raw = photo(1, seed=900+i)
            service.blobs.put(key, raw, 'image/jpeg')
            fields = {'序号':f'SYNTHETIC-{i:03}', '日期':today, '入站时间':f'08:0{i}', '出站时间':f'08:1{i}',
                      '车号':f'验收{i:03}', '货名':'协作验收原料', '总重':'11000', '皮重':'10000', '净重':'1000',
                      '供应商':'合成来源', '备注':'隔离合成数据；本预览不提供真实 OCR。'}
            record = Record(id=f'wbill-preview-{i}', created_at=today+f'T08:1{i}:00', uploader='验收夹具',
                            batch_id=batch, seq_in_batch=1, orig_key=key, crop_key=key, sig_key=None,
                            fields=fields, warnings=[], weight_ok=1, status=STATUS_REVIEWED,
                            stage=STAGE_SUBMITTED, submitted_by='验收夹具', submitted_at=today+'T08:00:00',
                            ref_no=f'WB-{day_key}-{i:04}', model='synthetic-fixture')
            service.store.insert(record)
            records.append({'id':record.id, 'original_key':key, 'original_sha256':hashlib.sha256(raw).hexdigest(), 'bytes':len(raw)})
        marker.write_text(json.dumps({'kind':'weighbill-synthetic-preview-v1', 'records':records,
                                     'origin':'new synthetic fixtures; no source business data copied',
                                     'ocr_available':False}, ensure_ascii=False,indent=2)+'\n')
    return service


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--data-dir', type=Path, required=True)
    args = parser.parse_args()
    service = prepare(args.data_dir.absolute(), args.prefix)
    import uvicorn
    uvicorn.run(create_app(service), host='127.0.0.1', port=args.port, proxy_headers=False)


if __name__ == '__main__':
    main()
