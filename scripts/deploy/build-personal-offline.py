"""Explicit, local-only wrapper around an unchanged, verified Windows customer ZIP."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import uuid
import zipfile


ROOT = Path(__file__).resolve().parents[2]
MODEL_FIELDS = ('model_provider','model','model_reasoning_effort','service_tier','model_verbosity','model_context_window','model_auto_compact_token_limit')
CLAUDE_FIELDS = ('model','modelPicker','modelSettings','effortLevel')
CLAUDE_ENV = {'API_TIMEOUT_MS','CLAUDE_CODE_MAX_OUTPUT_TOKENS','CLAUDE_CODE_MAX_CONTEXT_TOKENS','CLAUDE_CODE_AUTO_COMPACT_WINDOW','CLAUDE_CODE_MODEL_CAPABILITIES'}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def toml_value(value):
    if isinstance(value, dict):
        return '{ '+', '.join(json.dumps(k)+' = '+toml_value(v) for k,v in value.items())+' }'
    if isinstance(value, list):
        return '['+', '.join(toml_value(v) for v in value)+']'
    if isinstance(value, (str,bool,int,float)):
        return json.dumps(value, ensure_ascii=False)
    raise ValueError('Unsupported model configuration value; original files unchanged')


def build(runtime, receipt, out, codex_home, claude_settings):
    out = out.resolve()
    if out.is_relative_to(ROOT):
        raise ValueError('Personal packages must be stored outside the Git repository')
    if out.exists():
        raise ValueError('Output already exists; do not overwrite an existing personal package')
    info = json.loads(receipt.read_text(encoding='utf-8'))
    if info.get('distribution') != 'customer' or digest(runtime) != info['sha256'] or runtime.stat().st_size != info['bytes']:
        raise ValueError('Runtime ZIP does not match its customer receipt')
    with zipfile.ZipFile(runtime) as archive:
        release = json.loads(archive.read('Webuddy/release.json'))
        if release['source_commit'] != info['source_commit']:
            raise ValueError('Runtime source identity mismatch')
    codex = tomllib.loads((codex_home/'config.toml').read_text(encoding='utf-8'))
    auth = json.loads((codex_home/'auth.json').read_text(encoding='utf-8'))
    if not (auth.get('OPENAI_API_KEY') or (auth.get('tokens') or {}).get('access_token')):
        raise ValueError('Codex authentication is missing')
    claude = json.loads(claude_settings.read_text(encoding='utf-8'))
    env = {k:v for k,v in claude.get('env',{}).items() if k.startswith('ANTHROPIC_') or k in CLAUDE_ENV}
    if not (env.get('ANTHROPIC_AUTH_TOKEN') or env.get('ANTHROPIC_API_KEY')):
        raise ValueError('Claude API authentication is missing; keychain-only login requires a separate migration')
    # Include model access configuration, not projects, history, MCP OAuth, hooks or relaxed permissions.
    model_config = {k:codex[k] for k in MODEL_FIELDS if k in codex}
    model_config['cli_auth_credentials_store'] = 'file'
    if 'model_providers' in codex:
        model_config['model_providers'] = codex['model_providers']
    text = '\n'.join(json.dumps(k)+' = '+toml_value(v) for k,v in model_config.items())+'\n'
    tomllib.loads(text)
    private_claude = {k:claude[k] for k in CLAUDE_FIELDS if k in claude}
    private_claude['env'] = env
    profile_id = uuid.uuid4().hex
    packager = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    out.mkdir(parents=True,mode=0o700)
    out.chmod(0o700)
    archive_name = 'Webuddy-personal-windows-x64-'+info['source_commit'][:12]+'.zip'
    with tempfile.TemporaryDirectory(prefix='webuddy-personal-',dir=out) as folder:
        root = Path(folder)/'Webuddy-personal'
        root.mkdir(mode=0o700)
        profiles = root/'profiles'
        for name in ('codex','claude'):
            (profiles/name).mkdir(parents=True,mode=0o700)
        shutil.copyfile(codex_home/'auth.json',profiles/'codex/auth.json')
        (profiles/'codex/config.toml').write_text(text,encoding='utf-8')
        (profiles/'claude/settings.json').write_text(json.dumps(private_claude,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        required_env = {}
        import os
        for provider in codex.get('model_providers',{}).values():
            keys = [provider['env_key']] if provider.get('env_key') else []
            keys += list(provider.get('env_http_headers',{}).values())
            for key in keys:
                if key in os.environ:
                    required_env[key] = os.environ[key]
        (profiles/'environment.json').write_text(json.dumps(required_env,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        shutil.copyfile(ROOT/'scripts/deploy/personal-offline/launcher.py',root/'personal-launch.py')
        shutil.copyfile(ROOT/'scripts/deploy/personal-offline/start-personal.cmd',root/'start-personal.cmd')
        shutil.copyfile(runtime,root/runtime.name)
        (root/'README.txt').write_text('Webuddy 个人专用 Windows 离线包\n\n本包包含 Codex 和 Claude 的真实模型凭据，仅供本人使用，不得转发客户或上传仓库。\n解压整个外层ZIP，停止旧程序后双击 start-personal.cmd。首次启动会解压原始程序并创建独立AI配置，原程序ZIP不变。\n检查：start-personal.cmd check\nCursor复用目标Windows已安装的agent及现有登录，不复制Mac登录或更改Cursor配置。\n保留原有Webuddy默认业务数据；如使用外部配置，继续设置WEBUDDY_CONFIG。原客户端配置不覆盖。\n模型需要网络/内网服务与仍有效的授权；运行环境离线不表示模型离线。\n升级和回退只切程序，先停止再操作，不用旧数据库覆盖新写入。\n凭据刷新在独立目录中保存，再次启动不会用旧令牌覆盖新令牌。首次AI配置不完整时保留现场并明确失败。\n本包仍含Python源码。不代替业务验收。\n',encoding='utf-8')
        files = {p.relative_to(root).as_posix():digest(p) for p in root.rglob('*') if p.is_file()}
        manifest = dict(distribution='personal_contains_credentials',runtime_commit=info['source_commit'],packager_commit=packager,
                        runtime_archive=runtime.name,runtime_sha256=info['sha256'],profile_id=profile_id,cursor='reuse_target_device_login',files=files)
        (root/'PERSONAL.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
        for p in root.rglob('*'):
            if p.is_file():p.chmod(0o600)
        result = out/archive_name
        with zipfile.ZipFile(result,'w',compression=zipfile.ZIP_STORED) as archive:
            for p in sorted(root.rglob('*')):
                if p.is_file():archive.write(p,'Webuddy-personal/'+p.relative_to(root).as_posix())
        result.chmod(0o600)
    report = dict(distribution='personal_contains_credentials',archive=archive_name,bytes=result.stat().st_size,sha256=digest(result),
                  runtime_commit=info['source_commit'],packager_commit=packager,cursor='reuse_target_device_login',real_windows_personal_start='not_verified',real_models='not_verified')
    (out/'personal-receipt.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    (out/'personal-receipt.json').chmod(0o600)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--include-personal-credentials',action='store_true',required=True)
    p.add_argument('--runtime-zip',type=Path,required=True)
    p.add_argument('--receipt',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--codex-home',type=Path,default=Path.home()/'.codex')
    p.add_argument('--claude-settings',type=Path,default=Path.home()/'.claude/settings.json')
    args=p.parse_args()
    try:
        report=build(args.runtime_zip,args.receipt,args.out,args.codex_home,args.claude_settings)
    except (ValueError,OSError,KeyError):
        raise SystemExit('Personal build failed; source files were not changed. Inspect inputs locally; do not publish credential contents.')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
