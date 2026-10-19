"""Archive this round verbatim; archived copies require an explicit repo root."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import shutil
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--repo-root', type=Path, required=True)
args = parser.parse_args()
root = args.repo_root.resolve()
source = root / 'data/weighbill-acceptance-20261019'
target = root / 'docs/self-improvement/evidence/weighbill-acceptance-2026-10-19'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')

candidate = json.loads((source / 'candidate-final-check.json').read_text())
previous = json.loads((source / 'candidate-current.json').read_text())
expected_commit = 'ab9601e305bf9efdf908554174c56ca101194405'
expected_evidence = '6641fbcaaa745ab5496b022c61cd08d3f2e88c0248165bafe6e1e5731e002b8c'
for key in ('id', 'commit', 'requirement_hash', 'verification_hash', 'preview_hash', 'evidence_hash'):
    assert candidate[key] == previous[key], key
assert candidate['id'] == 4 and candidate['commit'] == expected_commit
assert candidate['evidence_hash'] == expected_evidence
assert candidate['state'] == 'awaiting_human' and candidate['human_accepted'] is False
assert all(candidate[key] is True for key in (
    'current', 'verification_passed', 'preview_ready', 'technical_acceptance', 'ready_for_human'))
preservation = json.loads((source / 'preservation-report.json').read_text())
assert all(preservation[key] is True for key in ('head', 'status', 'tracked', 'local'))
assert all(preservation['platform_existing_rows'].values())
assert not target.exists(), 'An existing archive must not be overwritten.'
files = sorted(p for p in source.rglob('*') if p.is_file())
assert not any(p.is_symlink() for p in source.rglob('*')), 'Explicitly resolve any symlinks first.'
for src in files:
    dst = target / src.relative_to(source)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    assert src.read_bytes() == dst.read_bytes(), str(src)

metadata = {
    'archived_at_utc': datetime.now(timezone.utc).isoformat(),
    'platform_start_commit': '2b3cb103689d994cef96a478f0412609019ee870',
    'platform_head_at_archive': subprocess.check_output(['git','rev-parse','HEAD'], cwd=root).decode().strip(),
    'business_commit': expected_commit,
    'ticket': 'WBILL-1', 'candidate': 4, 'run': 10, 'verification_operation': 4,
    'evidence_hash': expected_evidence,
    'verification_hash': candidate['verification_hash'],
    'preview_hash': candidate['preview_hash'],
    'state': candidate['state'], 'technical_acceptance': True, 'human_accepted': False,
    'source': str(source),
    'raw_files_copied': len(files),
    'raw_bytes_copied': sum(p.stat().st_size for p in files),
    'copy_policy': 'All source files copied byte-for-byte. No compression, image conversion, truncation, or filtering.',
    'source_code_archive': '../weighbill-pilot-2026-10-19/',
    'limits': ['Local synthetic data; OCR disabled.', 'No new full test run or code change this round.',
               'Native-modal recovery cause unknown; not proof of unattended operation.',
               'Application approved record is not human candidate acceptance.', 'No merge, push, or production release.'],
}
write_json(target / 'archive-metadata.json', metadata)
(target / 'README.md').write_text('''# 磅单浏览器闭环接续证据

本轮接续同一 WBILL-1 候选4，业务提交 `ab9601e305bf9efdf908554174c56ca101194405`。浏览器完成核对保存、单独审核、旧页面审核拒绝、刷新持久化和完整原图打开；CLI/MCP 技术验收通过，等待用户对这个版本的业务确认。

- [本轮验证记录](../../verification-weighbill-acceptance-2026-10-19.md)：路径、结论与限制。
- [独立只读复核](independent/REVIEW.md)：实际 HTTP/SQLite、浏览器证据与运行版本交叉核对。
- `browser-timeline.json`：完整 DOM 操作记录；`browser-approved.jpg`、`browser-original.jpg`：工具返回的原始截图字节。
- `preview-before-resume.json`、`preview-after-reconciled-save.json`、`preview-after-approval.json`、`preview-after-stale-approval.json`：实际业务记录及历史；`preview-final-snapshot.db`：一致数据库备份。
- `candidate-before.json`、`mcp-before-acceptance.json`：本轮起点，保留 A3 unknown。
- `assessment-results.json`、`record-technical-acceptance.py`、`mcp-technical-acceptance.json`、`mcp-record.log`：逐项技术观察及完整 MCP 回执。
- `candidate-current.json`、`candidate-final-check.json`：两次 CLI 读取均为 `awaiting_human`、`technical_acceptance=true`、`human_accepted=false`。
- `preservation-*.json`：原仓库文件、原有平台数据行保持；`bootv2-before.json` / `bootv2-after.json`：已接受 BOOTV2 未变。
- `preview-runtime.log`、`preview-runtime-final.log`：两个时点的完整运行日志，未以摘要替代原文。
- `independent/`：独立脚本、完整 HTTP 原始响应、数据库行、过程输出及报告；一致性断言数量不代表业务覆盖率或提效比例。
- [前轮完整归档](../weighbill-pilot-2026-10-19/README.md)：固定候选源码、Git bundle、全量测试及原生弹窗故障。前轮材料未改写，本轮未重新执行全量。

`archive-metadata.json` 记录来源和版本；`manifest.json` 包含每个文件的字节数和 SHA-256（不含 manifest 自身）。整个原始目录逐文件原样复制，没有过滤、裁剪、截断、重编码或压缩。截图只在查看器里按显示区域呈现，文件保持原始字节。

本轮是本地隔离合成台账，真实 OCR 关闭。旧 API 省略条件仍兼容且不具客户端版本保护，草稿只保存在页面内存。弹窗恢复原因未知，不声称全程无人值守。合成记录内部“已审核”不等于用户对项目版本验收，未合并、推送或发布。

脚本保留执行时原貌：`preserve.py` 等依赖原先的 `data/weighbill-acceptance-20261019` 层级；回放时先复制回该位置或显式修改路径，并先检查本地状态。`record-technical-acceptance.py` 会记录观察，不能当只读检查重复执行。`archive.py --repo-root <仓库绝对路径>` 拒绝覆盖既有归档。
''')
verification = {
    'copied_source_files': len(files),
    'every_source_file_byte_equal': all(p.read_bytes() == (target / p.relative_to(source)).read_bytes() for p in files),
    'current_candidate_bindings_unchanged': True,
    'technical_acceptance_passed': True,
    'human_acceptance_not_inferred': True,
    'preservation_report_passed': True,
}
write_json(target / 'archive-verification.json', verification)
manifest = {str(p.relative_to(target)): {'bytes':p.stat().st_size, 'sha256':sha(p)}
            for p in sorted(target.rglob('*')) if p.is_file()}
write_json(target / 'manifest.json', manifest)
assert set(manifest) == {str(p.relative_to(target)) for p in target.rglob('*') if p.is_file() and p.name != 'manifest.json'}
assert all((target / name).stat().st_size == entry['bytes'] and sha(target / name) == entry['sha256'] for name,entry in manifest.items())
print(json.dumps({'path':str(target),'manifest_files':len(manifest),
                  'total_bytes':sum(p.stat().st_size for p in target.rglob('*') if p.is_file()),**verification},ensure_ascii=False))
