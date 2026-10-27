"""Orchestrate one bounded isolated project run and preserve its evidence.

The caller owns personal authorization, ticket state and approval. This module
creates a proposal only; it never registers, verifies, merges or accepts it.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import time

from . import project_artifact, project_client, project_snapshot
from .project_mcp import BoundJob


def run(*, principal, project, source, image, provider_config, prompt, folder,
        seconds, authorize, source_current, ref='HEAD', cancel=lambda:False, output=lambda chunk:None,
        engine=None, profile='', model='', expected_binding=None):
    if (not callable(authorize) or not callable(source_current) or not math.isfinite(seconds) or seconds <= 0
            or not isinstance(prompt,str) or not prompt.strip()):
        raise ValueError('项目运行缺少授权、来源检查或总时限')
    folder = Path(folder)
    if not folder.is_absolute() or folder.exists():
        raise ValueError('项目运行证据目录必须是新的绝对路径')
    folder.mkdir(parents=True, mode=0o700)
    workspace = folder / 'workspace'
    job = BoundJob(principal,project,workspace,image)
    deadline=time.monotonic()+seconds
    def stopped():
        return cancel() or time.monotonic() >= deadline or not authorize(job)
    if stopped():
        raise ValueError('项目授权已失效或总时限已到')
    (folder/'prompt.md').write_text(prompt,encoding='utf-8')
    snapshot=project_snapshot.create(image,source,workspace,ref=ref,cancel=stopped,engine=engine)
    if stopped() or source_current(snapshot['commit']) is not True:
        raise ValueError('项目来源或授权已变化，未启动执行器')
    info={'schema':1,'principal':principal,'project':project,'base_commit':snapshot['commit'],
          'source_archive_sha256':snapshot['archive_sha256'],'status':'running'}
    def save():
        temp=folder/'receipt.json.tmp'
        temp.write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
        temp.replace(folder/'receipt.json')
    save()
    try:
        with (folder/'client-output.bin').open('xb') as client_log, (folder/'tool-output.bin').open('xb') as tool_log:
            def client_output(chunk):
                client_log.write(chunk);client_log.flush();output(chunk)
            def tool_output(chunk):
                tool_log.write(chunk);tool_log.flush()
            remaining=deadline-time.monotonic()
            if remaining<=0:raise ValueError('准备项目来源时已超过总时限')
            client=project_client.run(job,provider_config,prompt,remaining,base_commit=snapshot['commit'],
                                      authorize=authorize,cancel=stopped,output=client_output,
                                      tool_output=tool_output,engine=engine,profile=profile,model=model,
                                      expected_binding=expected_binding)
        info['client']=client
        if (client.get('reason')!='exited' or client.get('returncode')!=0 or
                client.get('cleanup') is not True or client.get('volume_cleanup') is not True or
                not client.get('workspace')):
            raise ValueError('客户端未形成完整、已回收的项目结果')
        if stopped() or source_current(snapshot['commit']) is not True:
            raise ValueError('项目来源或授权已变化，保留结果但不生成候选')
        artifact=project_artifact.create(image,source,workspace,snapshot['commit'],folder/'candidate',
                                         lfs=snapshot.get('lfs',{}),cancel=stopped,engine=engine)
        if stopped() or source_current(snapshot['commit']) is not True:
            raise ValueError('候选准备期间项目来源或授权已变化，结果仅供核对')
        info.update(status='proposal',candidate=artifact,
                    notice='候选产物尚未登记、验证、预览或人工验收')
        save()
        return info
    except BaseException as exc:
        info.update(status='failed',error_type=type(exc).__name__)
        save()
        raise
