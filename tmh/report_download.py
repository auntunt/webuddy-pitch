"""Resumable local delivery of one immutable, authorized export."""
import base64
import hashlib
import json
from pathlib import Path
from .workbench_client import ClientError


def download(client, project, plan_id, export_id, directory):
    args={'project':project,'plan_id':plan_id,'export_id':export_id}
    manifest=client.call('reform_report_get',args)
    if manifest['export_id']!=export_id:raise ClientError('报告身份不匹配','report_integrity_error')
    directory=Path(directory)/export_id
    if directory.is_symlink():raise ClientError('报告目录不能是符号链接','report_integrity_error')
    directory.mkdir(parents=True,exist_ok=True)
    saved=directory/'manifest.json'
    if saved.is_symlink():raise ClientError('报告清单不能是符号链接','report_integrity_error')
    if saved.exists() and json.loads(saved.read_text())!=manifest:
        raise ClientError('冻结报告清单变化，停止下载','report_integrity_error')
    if not saved.exists():saved.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    for entry in manifest['files']:
        name=entry['name']
        if Path(name).name!=name or '/' in name or '\\' in name or name in ('.','..','manifest.json'):
            raise ClientError('附件名称不安全','report_integrity_error')
        target=directory/name;partial=directory/(name+'.part')
        if target.is_symlink() or partial.is_symlink():raise ClientError('附件路径不能是符号链接','report_integrity_error')
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest()!=entry['sha256']:raise ClientError('已有附件校验失败','report_integrity_error')
            continue
        offset=0
        if partial.exists():
            with partial.open('rb') as f:
                while body:=f.read(manifest['chunk_bytes']):
                    index=offset//manifest['chunk_bytes']
                    if index>=len(entry['chunk_sha256']) or hashlib.sha256(body).hexdigest()!=entry['chunk_sha256'][index]:
                        raise ClientError('中断文件校验失败；保留文件供核对','report_integrity_error')
                    offset+=len(body)
        while offset<entry['bytes']:
            chunk=client.call('reform_report_get',dict(args,file=name,offset=offset))
            body=base64.b64decode(chunk['data_base64'],validate=True)
            checksum=hashlib.sha256(body).hexdigest()
            if (chunk['export_id']!=export_id or chunk['file']!=name or chunk['offset']!=offset
                or not body or len(body)!=chunk['bytes'] or checksum!=chunk['sha256']
                or checksum!=entry['chunk_sha256'][offset//manifest['chunk_bytes']]):
                raise ClientError('分段校验失败；未追加损坏内容','report_integrity_error')
            with partial.open('ab') as f:f.write(body)
            offset+=len(body)
        if not partial.exists():partial.touch()
        if partial.stat().st_size!=entry['bytes'] or hashlib.sha256(partial.read_bytes()).hexdigest()!=entry['sha256']:
            raise ClientError('完整附件校验失败','report_integrity_error')
        client.call('reform_report_get',args) # live authority before final publication
        partial.replace(target)
    client.call('reform_report_get',args)
    return {'export_id':export_id,'directory':str(directory),'files':len(manifest['files']),'integrity':'verified','current_validity':'not_checked'}
