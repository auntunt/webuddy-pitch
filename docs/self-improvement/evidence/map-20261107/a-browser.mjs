import fs from 'node:fs';
import {call,evaluate,ws} from './cdp.mjs';
const out='/private/tmp/webuddy-map-20261107';
const info=JSON.parse(fs.readFileSync(out+'/ui-server-fixed.log','utf8').split('\n')[0]);
const wait=async expr=>{for(let i=0;i<100;i++){if(await evaluate(expr))return;await new Promise(r=>setTimeout(r,100));}throw Error('Wait failed: '+expr)};
await call('Page.navigate',{url:new URL(info.url).origin+'/login'});await wait('!!document.querySelector("input[name=username]")||!location.pathname.includes("login")');
if(await evaluate('!!document.querySelector("input[name=username]")'))await evaluate(`document.querySelector('[name=username]').value='scenario-owner';document.querySelector('[name=password]').value='isolated-scenario-fixture';document.querySelector('form').requestSubmit()`);await wait('!location.pathname.includes("login")');
await call('Page.navigate',{url:info.url});await wait('!!document.querySelector(".rf-workspace")');await evaluate(`document.querySelector('[data-rf-tab=scope]').click()`);await wait('!!document.querySelector("#rfSuccessor")');
await evaluate(`{const f=document.querySelector('#rfSuccessor');f.elements.goal.value='新政策退款场景；原任务保留';f.elements.reason.value='合成政策v2';f.dispatchEvent(new Event('input',{bubbles:true}));f.requestSubmit()}`);
await wait(`location.hash!==${JSON.stringify(new URL(info.url).hash)}&&!!document.querySelector('.rf-workspace')`);
await evaluate(`document.querySelector('[data-rf-tab=scope]').click()`);await wait('!!document.querySelector("#rfEdit")');
await evaluate(`{const f=document.querySelector('#rfEdit');for(const [k,v] of Object.entries({source_version:${JSON.stringify(info.sha)},target_environment:'隔离测试环境',target:'updated',dependencies:'等待独立业务规则',criteria:'退款12.50元',scenario_rules:'退款以分为单位，1250分',scenario_regressions:'原分页和权限保持',scenario_expectation_sources:'合成独立政策v2',scenario_sources:JSON.stringify([{id:'policy',kind:'policy',reference:'fixture://policy',version:'v2'}]),reason:'补充场景记录'}))f.elements[k].value=v;f.dispatchEvent(new Event('input',{bubbles:true}));f.requestSubmit()}`);
await wait('document.querySelector(".rf-workspace")?.textContent.includes("修订 2")');
const id=await evaluate(`location.hash.split('/').at(-1)`);
const packet=await evaluate(`fetch('/api/projects/EXT/reforms?plan_id='+${JSON.stringify(id)}).then(r=>r.json())`);
if(packet.source_version!==info.sha||packet.target_environment!=='隔离测试环境')throw Error('条件未保存');
if(packet.scenario.rules[0]!=='退款以分为单位，1250分'||packet.scenario_record.confirmation_status!=='not_confirmed_by_this_record')throw Error(JSON.stringify(packet));
await evaluate(`document.querySelector('#rfReport').click()`);await wait('!!document.querySelector("#rfExportFiles")');
await call('Page.setDownloadBehavior',{behavior:'allow',downloadPath:out+'/browser-downloads'});
const downloadName=await evaluate(`document.querySelector('#rfExportFiles button').textContent.split(' · ')[0]`);await evaluate(`document.querySelector('#rfExportFiles button').click()`);
await wait(`document.querySelector('#rfExportFiles button').textContent.startsWith('再次下载')`);
for(let i=0;i<50&&!fs.existsSync(out+'/browser-downloads/'+downloadName);i++)await new Promise(r=>setTimeout(r,100));
if(!fs.existsSync(out+'/browser-downloads/'+downloadName))throw Error('No actual downloaded original');

const report=await evaluate(`fetch('/api/tickets/EXT-1/delivery').then(r=>r.json())`);
if(!report.report_markdown||report.ready_to_merge!==null)throw Error('bad report');
fs.writeFileSync(out+'/scenario-report.md',report.report_markdown);fs.writeFileSync(out+'/scenario-report.json',JSON.stringify(report,null,2));
for(const [width,height] of [[1440,900],[390,844]]){await call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await evaluate(`document.querySelector('[data-rf-tab=scope]').click()`);await wait('document.querySelector(".rf-workspace")?.textContent.includes("原分页和权限保持")');const state=await evaluate(`({width:innerWidth,scroll:document.documentElement.scrollWidth,project:document.querySelector('#projSel').value})`);if(state.scroll>width||state.project!=='EXT')throw Error(JSON.stringify(state));const shot=await call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(out+'/scenario-'+width+'.png',Buffer.from(shot.data,'base64'));}
fs.writeFileSync(out+'/scenario-browser.json',JSON.stringify({synthetic:true,successor:id,scenario:packet.scenario,original:packet.supersedes,confirmed:packet.scenario_record.confirmation_status},null,2));console.log('Successor, scoped edit, saved report and two browser sizes passed');ws.close();
