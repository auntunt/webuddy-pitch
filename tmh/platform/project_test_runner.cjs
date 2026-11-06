// Operator-owned adapter. Commands write logs and reports; only this adapter emits receipts.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const {spawn, spawnSync} = require('node:child_process');
const plan = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const root = fs.realpathSync(process.cwd());
const work = plan.artifact_dir || fs.mkdtempSync(path.join(os.tmpdir(), 'tmh-project-tests-'));
if(plan.artifact_dir) fs.mkdirSync(work);
const inside = p => {const rel = path.relative(root, p); return rel && !rel.startsWith('..' + path.sep) && rel !== '..' && !path.isAbsolute(rel);};
function signature(p) {
  if (!fs.existsSync(p)) return null;
  if (!inside(fs.realpathSync(p)) || !fs.statSync(p).isFile()) throw Error('报告路径越出工作目录或不是文件');
  const s = fs.statSync(p, {bigint:true});
  return [s.ino.toString(), s.mtimeNs.toString(), s.ctimeNs.toString(), crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex')].join(':');
}
function reportFiles(pattern) {
  let paths = [root];
  for (const segment of pattern.split('/')) {
    const next = [];
    for (const parent of paths) {
      if (!fs.existsSync(parent)) continue;
      const safeParent = fs.realpathSync(parent);
      if (safeParent !== root && !inside(safeParent)) throw Error('报告目录越出工作目录');
      if (segment.includes('*')) {
        const expression = new RegExp('^' + segment.split('*').map(p=>p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('.*') + '$');
        for (const name of fs.readdirSync(parent).sort()) if(expression.test(name)) next.push(path.join(parent, name));
      } else next.push(path.join(parent, segment));
    }
    paths = next;
  }
  return paths.filter(p=>fs.existsSync(p));
}
function codeIdentity() {
  const output = path.join(work, 'git-diff');
  const fd = fs.openSync(output, 'w');
  try {
    let command = spawnSync('git', ['add', '-A', '-N', '.'], {stdio:'ignore'});
    if(command.status !== 0) throw Error('无法记录测试代码版本');
    fs.ftruncateSync(fd,0);
    command = spawnSync('git', ['diff', '--binary', '--no-ext-diff', '--no-textconv', 'HEAD'], {stdio:['ignore',fd,fd]});
    if(command.status !== 0) throw Error('无法读取测试代码差异');
  } finally {fs.closeSync(fd);}
  const head = spawnSync('git', ['rev-parse', 'HEAD'], {encoding:'utf8'});
  if(head.status !== 0) throw Error('无法读取测试基准版本');
  return head.stdout.trim() + ':' + crypto.createHash('sha256').update(fs.readFileSync(output)).digest('hex');
}
function killChildren() {
  const listing = spawnSync('ps', ['-axo', 'pid=,pgid='], {encoding:'utf8'});
  if(listing.status !== 0) throw Error('无法核对执行器进程组');
  const members = listing.stdout.trim().split('\n').map(line=>line.trim().split(/\s+/).map(Number));
  for(const [pid,group] of members) if(group === process.pid && pid !== process.pid) {
    try {process.kill(pid, 'SIGKILL');} catch(error) {if(error.code !== 'ESRCH') throw error;}
  }
}
if(process.platform !== 'win32') {
  const group = spawnSync('ps', ['-p', String(process.pid), '-o', 'pgid='], {encoding:'utf8'});
  if(group.status !== 0 || Number(group.stdout.trim()) !== process.pid) throw Error('执行器必须由独立进程组监管启动');
}
let activeKill = process.platform === 'win32' ? () => {} : killChildren;
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => {activeKill(); console.error('项目测试已停止，原始日志：' + work); process.exit(130);});
function run(command, timeout, logfile) {
  return new Promise(resolve => {
    const fd = fs.openSync(logfile, 'w');
    const win = process.platform === 'win32';
    const child = spawn(command, {shell:true, env:{...process.env,TMH_TEST_RUN:plan.nonce}, stdio:['ignore', fd, fd], windowsHide:true});
    let timedOut = false;
    const kill = () => {
      if (!child.pid) return;
      if (win) spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], {stdio:'ignore'});
      else killChildren();
    };
    activeKill = kill;
    const timer = setTimeout(() => {timedOut = true; kill();}, timeout * 1000);
    child.on('error', error => {clearTimeout(timer); fs.closeSync(fd); resolve({exit_code:127,error:error.message});});
    child.on('exit', code => {clearTimeout(timer); activeKill = win ? () => {} : killChildren; fs.closeSync(fd); resolve({exit_code:timedOut ? 124 : code === null ? 1 : code,error:timedOut ? '阶段超时，已终止进程树' : ''});});
  });
}
(async () => {
  const initialCode = codeIdentity();
  const stages = [];
  let codeChanged = false;
  for (const s of plan.stages) {
    const start = Date.now(), logfile = path.join(work, s.id + '.log');
    const report = s.report ? s.report.path : null;
    let record = {id:s.id,exit_code:1,error:'',log:'',seconds:0,execution_status:'not_run'}, before;
    try {
      before = new Map(report ? reportFiles(report).map(p=>[p,signature(p)]) : []);
      const blocked = (s.depends_on || []).some(id => stages.find(x=>x.id===id)?.exit_code !== 0);
      codeChanged ||= initialCode !== codeIdentity();
      if ((blocked || codeChanged) && s.kind !== 'cleanup') {
        record.error = codeChanged ? '代码版本已变化，未执行' : '依赖阶段未成功，未执行';
        record.failure_kind = codeChanged ? 'code_changed' : 'dependency';
      } else {
        Object.assign(record, await run(s.command, s.timeout, logfile));
        record.execution_status = record.exit_code === 0 ? 'completed' : [124,127].includes(record.exit_code) ? 'blocked' : 'failed';
        if(record.exit_code !== 0) record.failure_kind = record.exit_code === 124 ? 'timeout' : record.exit_code === 127 ? 'environment' : 'command';
      }
      codeChanged ||= initialCode !== codeIdentity();
      if (report) {
        const files = reportFiles(report);
        if (!files.length) record.report_error = '缺少报告';
        else {
          record.reports = [];
          for (const file of files) {
            const after = signature(file);
            if (before.get(file) === after) record.report_error = '报告未更新，不能使用旧结果：' + path.relative(root, file);
            record.reports.push({path:path.relative(root, file),raw:fs.readFileSync(file).toString('base64')});
          }
        }
      }
    } catch(error) {record.error = error.message; record.exit_code = 1; record.execution_status = 'blocked'; record.failure_kind = 'environment';}
    record.seconds = (Date.now() - start) / 1000;
    stages.push(record);
  }
  if(process.platform !== 'win32') killChildren();
  for(const record of stages) {const logfile=path.join(work,record.id+'.log');if(fs.existsSync(logfile))record.log=fs.readFileSync(logfile).toString('base64');}
  process.stdout.write('TMH_PROJECT_TESTS_' + plan.nonce + ':' + Buffer.from(JSON.stringify({stages,code_changed:codeChanged || initialCode !== codeIdentity(),code_identity:initialCode,artifact_dir:work})).toString('base64') + '\n');
  if(plan.artifact_dir) fs.rmSync(work, {recursive:true});
})().catch(error => {if(process.platform !== 'win32') killChildren(); console.error('项目测试执行错误，原始日志：' + work, error); process.exitCode = 1;});
