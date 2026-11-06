import fs from 'node:fs';
import assert from 'node:assert/strict';
import {call,evaluate,ws} from './knowledge-cdp.mjs';
const info=JSON.parse(fs.readFileSync('/private/tmp/knowledge-preview-info.json'));
const base=`http://127.0.0.1:${info.port}`, tenant=base+'/t/'+info.tenant;
const out=process.cwd()+'/docs/self-improvement/evidence/knowledge-collaboration-20261107/browser';fs.mkdirSync(out,{recursive:true});
const wait=async e=>{for(let i=0;i<100;i++){if(await evaluate(e))return;await new Promise(r=>setTimeout(r,100))}throw Error(e+' '+await evaluate('document.body.innerText'))};
try{
 await call('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
 await call('Network.clearBrowserCookies');
 await call('Page.navigate',{url:base+'/login'});await wait('!!document.querySelector("input[name=username]")');
 await evaluate(`document.querySelector('input[name=username]').value='alice';document.querySelector('input[name=password]').value='synthetic-password';document.querySelector('form').requestSubmit()`);
 await wait('!location.pathname.includes("login")');
 await call('Page.navigate',{url:tenant+'/#/memory/knowledge'});await wait('!!document.querySelector("#memProject")');
 console.log(await evaluate('document.body.innerText'));
 await evaluate(`document.querySelector('#memProject').value='';document.querySelector('#memProject').dispatchEvent(new Event('change'))`);
 await wait(`document.querySelector('#memProject')?.value==='' && document.body.innerText.includes('退款规则')`);
 assert(!await evaluate(`document.querySelector('#memContent').innerText.includes('不可访问的内部规则')`));
 assert.deepEqual(await evaluate(`Array.from(document.querySelector('#memProject').options).map(x=>x.value)`),['','SAME']);
 for(const [width,height] of [[1440,900],[390,844]]){
  await call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
  const shot=await call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(out+'/catalog-'+width+'.png',Buffer.from(shot.data,'base64'));
 }
 await evaluate(`document.querySelector('#memProject').value='SAME';document.querySelector('#memProject').dispatchEvent(new Event('change'))`);
 await wait('!!document.querySelector("[data-mem-feedback]")');
 await evaluate(`document.querySelector('[data-mem-feedback]').click()`);await wait('!!document.querySelector("#nb")');
 assert((await evaluate(`document.querySelector('#nb').value`)).includes('decisions.md'));
 console.log('FEEDBACK_DRAFT_SOURCE_PASS');
 await evaluate(`document.querySelector('#modal .close, .modal .close, [onclick="closeModal()"]').click()`);
 await call('Page.navigate',{url:tenant+'/#/library'});await wait('!!document.querySelector("#libReferences")');
 assert((await evaluate(`document.querySelector('#libReferences').innerText`)).includes('来源已有新版本'));
 for(const [width,height] of [[1440,900],[390,844]]){
  await call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
  await evaluate(`document.querySelector('#libReferences').scrollIntoView({block:'start'})`);
  const shot=await call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(out+'/references-final-'+width+'.png',Buffer.from(shot.data,'base64'));
 }
 await evaluate(`document.querySelector('[data-lib-prepare]').click()`);
 assert.equal(await evaluate(`document.querySelector('#libSourceRevision').value`),'demo-revision-2');
 assert.equal(await evaluate(`document.querySelector('#libGrant').checked`),false);
 assert((await evaluate(`document.querySelector('#libReferences').innerText`)).includes('demo-revision-1'));
 assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth`));
 console.log('PREPARE_ONLY_NO_ADOPTION_PASS');
 console.log('CATALOG_SCOPE_AND_PINNED_UPDATE_PASS');
}finally{ws.close()}
