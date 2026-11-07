import fs from 'node:fs';
import {call,evaluate,ws} from './cdp.mjs';
const out='/private/tmp/webuddy-scenario-20261107';
const info=JSON.parse(fs.readFileSync(out+'/ui-server-current.log','utf8').split('\n')[0]);
const wait=async expr=>{for(let i=0;i<80;i++){if(await evaluate(expr))return;await new Promise(r=>setTimeout(r,100));}throw Error('Wait failed: '+expr)};
await call('Page.navigate',{url:'http://127.0.0.1:18989/login'});
await wait('!!document.querySelector("input[name=username]")');
await evaluate(`document.querySelector('[name=username]').value='scenario-owner';document.querySelector('[name=password]').value='isolated-scenario-fixture';document.querySelector('form').requestSubmit()`);
await wait('!location.pathname.includes("login")');
await evaluate(`localStorage.setItem('tmh.scope','OTHER');localStorage.setItem('tmh.proj','OTHER')`);
await call('Page.navigate',{url:info.url});
await wait('!!document.querySelector(".rf-workspace")');
const rows=[];
for(const [width,height] of [[1440,900],[768,1024],[390,844]]){
 await call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
 await evaluate(`document.querySelector('[data-rf-tab=tasks]').click()`);
 await wait('document.querySelector(".rf-workspace")?.textContent.includes("历史已派发，批次未记录")');
 const state=await evaluate(`({project:document.querySelector('#projSel').value,start:!!document.querySelector('[data-rf-action=start]'),text:document.querySelector('.rf-workspace').textContent,width:innerWidth,scroll:document.documentElement.scrollWidth})`);
 if(state.project!=='EXT'||state.start||!state.text.includes('尚未指定负责人')||!state.text.includes('historical-creator')||state.scroll>width)throw Error(JSON.stringify(state));
 const shot=await call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(out+'/tasks-'+width+'.png',Buffer.from(shot.data,'base64'));rows.push(state);
}
await evaluate(`document.querySelector('[data-rf-tab=recovery]').click()`);await wait('!!document.querySelector("[data-rf-resume-preview]")');await evaluate(`document.querySelector('[data-rf-resume-preview]').click()`);
await wait('document.querySelector("#rfPreflight")?.textContent.includes("尚未形成检查点")');
const recovery=await evaluate(`document.querySelector('#rfPreflight').textContent`);
if(recovery.includes('missing')||recovery.includes('[]'))throw Error(recovery);
fs.writeFileSync(out+'/browser.json',JSON.stringify({synthetic_account:true,source:'current worktree',rows,recovery},null,2));
console.log(JSON.stringify({sizes:rows.map(x=>x.width),recovery}));ws.close();
