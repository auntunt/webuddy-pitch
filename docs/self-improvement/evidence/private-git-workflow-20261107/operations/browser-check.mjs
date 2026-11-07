import fs from 'node:fs';
import assert from 'node:assert/strict';
import {call,evaluate,ws} from '/Users/auntlee/Desktop/workspace/运维智能体/部署包/jenkins-erp-demo-20261106/proof/git-workflow-20261107/browser-cdp.mjs';
const root='/Users/auntlee/Desktop/workspace/运维智能体/部署包/jenkins-erp-demo-20261106';
const out=root+'/proof/git-workflow-20261107/webuddy-browser';fs.mkdirSync(out,{recursive:true});
const accounts=JSON.parse(fs.readFileSync(root+'/private/accounts.json'));
const wait=async e=>{for(let i=0;i<100;i++){if(await evaluate(e))return;await new Promise(r=>setTimeout(r,150))}throw Error(e)};
try{
await call('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
await call('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:out});
await call('Page.navigate',{url:'http://127.0.0.1:18986/login'});await wait('!!document.querySelector("input[name=username]") || !location.pathname.includes("login")');
if(await evaluate('!!document.querySelector("input[name=username]")'))await evaluate(`document.querySelector('input[name=username]').value='demo-owner';document.querySelector('input[name=password]').value=${JSON.stringify(accounts.admin_password)};document.querySelector('form').requestSubmit()`);
await wait('!location.pathname.includes("login")');
await call('Page.navigate',{url:'http://127.0.0.1:18986/#/t/ERP-1'});await wait('!!document.querySelector("#taskDeliveryDownload")');
await evaluate(`document.querySelector('[data-task-tab=evidence]').click();document.querySelector('#taskDeliveryDownload').click();true`);
for(let i=0;i<80&&!fs.existsSync(out+'/ERP-1-delivery.json');i++)await new Promise(r=>setTimeout(r,150));
const packet=JSON.parse(fs.readFileSync(out+'/ERP-1-delivery.json'));assert.equal(packet.ready_to_merge,null);assert.equal(packet.current_validity,'not_checked');assert.equal(packet.development.state,'clarifying');assert.equal(packet.runs.length,2);assert(packet.runs.every(r=>r.run.mode==='external_test'));
for(const [width,height]of [[1440,900],[768,1024],[390,844]]){await call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await new Promise(r=>setTimeout(r,250));const shot=await call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(out+'/task-'+width+'.png',Buffer.from(shot.data,'base64'));}
fs.writeFileSync(out+'/check.json',JSON.stringify({ticket:packet.ticket.key,development:packet.development.state,imported_runs:packet.runs.length,ready_to_merge:packet.ready_to_merge,current_validity:packet.current_validity},null,2));console.log('WEB_DELIVERY_REAL_DOWNLOAD_PASS');
}finally{ws.close()}
