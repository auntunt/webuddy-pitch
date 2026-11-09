import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
const output=process.env.TMH_BUSINESS_OUTPUT||'target/business';fs.mkdirSync(output,{recursive:true});
const origin=process.env.TMH_ERP_ORIGIN||'http://127.0.0.1:18980';assert(['127.0.0.1','localhost'].includes(new URL(origin).hostname),'Only isolated loopback ERP is supported');
const build=JSON.parse(fs.readFileSync('target/business/build.json','utf8'));
execFileSync('git',['diff','--exit-code','HEAD','--','.']);
const source=execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim()+':'+crypto.createHash('sha256').update(execFileSync('git',['diff','--binary','--no-ext-diff','--no-textconv','HEAD'])).digest('hex');
assert.equal(source,build.source,'Source changed after prepare.py; rebuild before verification');
assert.equal(fs.readFileSync('/proc/'+build.pid+'/cmdline','utf8').split('\0').includes(path.resolve('jshERP-boot/target/jshERP.jar')),true);
assert.equal(fs.readFileSync('/proc/'+build.pid+'/stat','utf8').split(' ')[21],build.process_start);
assert.equal(crypto.createHash('sha256').update(fs.readFileSync('jshERP-boot/target/jshERP.jar')).digest('hex'),build.jar_sha256);
assert.equal(crypto.createHash('sha256').update(Buffer.from(await (await fetch(origin+'/')).arrayBuffer())).digest('hex'),build.index_sha256);
const tabs=await (await fetch('http://127.0.0.1:'+(process.env.TMH_CHROME_PORT||'18982')+'/json')).json();
const ws=new WebSocket(tabs.find(x=>x.type==='page').webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);let id=0;const pending=new Map();ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const cb=pending.get(m.id);pending.delete(m.id);m.error?cb.reject(m.error):cb.resolve(m.result)}};
const call=(method,params={})=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});ws.send(JSON.stringify({id:n,method,params}))});
const evaluate=async expression=>{const result=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw result.exceptionDetails;return result.result.value};

// Each run owns this isolated origin; discard the previous runtime's login session.
await call('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
await call('Page.navigate',{url:'about:blank'});
await call('Storage.clearDataForOrigin',{origin,storageTypes:'all'});

async function until(expression){
 const deadline=Date.now()+30000;
 while(Date.now()<deadline){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,150))}
 throw Error('Page did not reach expected state: '+expression);
}
async function flow(variant){
 const readyDeadline=Date.now()+30000;let ready=false;
 while(Date.now()<readyDeadline){
  try{const response=await fetch(origin+'/jshERP-boot/platformConfig/getPlatform/checkcodeFlag',{signal:AbortSignal.timeout(2000)});ready=response.ok&&(await response.text()).trim()==='0'}catch(error){if(Date.now()>=readyDeadline)throw error}
  if(ready)break;await new Promise(r=>setTimeout(r,200));
 }
 assert(ready,'ERP did not become ready after build');
await call('Page.navigate',{url:origin+'/'});await until("!!document.querySelector('#loginName') || !!document.querySelector('#app')?.__vue__?.$store?.getters.token");
if(await evaluate(`!!document.querySelector('#loginName')`)){
 await evaluate(`for(const [id,value]of [['loginName','jsh'],['password','123456']]){const e=document.getElementById(id);e.value=value;e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}))}document.querySelector('button[type="submit"]').click()`);
 await until("!!document.querySelector('#app')?.__vue__?.$store?.getters.token");
}
await until("document.querySelector('#app').__vue__.$route.path === '/dashboard/analysis' && document.querySelector('#app').__vue__.$store.getters.permissionList.length > 0");
await evaluate(`(async()=>{await document.querySelector('#app').__vue__.$router.push('/bill/sale_back');return true})()`);await until("[...document.querySelectorAll('button')].some(x=>x.textContent==='新增')");
await evaluate(`void [...document.querySelectorAll('button')].find(x=>x.textContent==='新增').click()`);await new Promise(r=>setTimeout(r,400));
await evaluate(`(()=>{const all=[],walk=v=>{all.push(v);v.$children.forEach(walk)};walk(document.querySelector('#app').__vue__);window.sale=all.find(v=>v.$options.name==='SaleBackModal');return !!sale})()`);
const records=[];await call('Network.enable');
ws.addEventListener('message',e=>{const m=JSON.parse(e.data);if(m.method==='Network.requestWillBeSent'&&m.params.request.url.includes('/depotHead/addDepotHeadAndDetail'))records.push({id:m.params.requestId,url:m.params.request.url,body:JSON.parse(m.params.request.postData)})});
const number='WEBUDDY-REFUND-'+Date.now();
await evaluate(`(()=>{sale.form.setFieldsValue({organId:58,number:${JSON.stringify(number)},discount:0,discountMoney:0,discountLastMoney:12.5,otherMoney:0,accountId:${variant==='multi'?0:17},changeAmount:12.5,debt:0,remark:'Webuddy隔离业务回归'});${variant==='multi'?"sale.manyAccountModalFormOk([17,18],[7.25,5.25],12.5);":""}const table=sale.$refs.materialDataTable;table.setValues([{rowKey:table.rows[0].id,values:{depotId:14,barCode:'1001',name:'商品1',unit:'个',operNumber:1,unitPrice:12.5,allPrice:12.5,taxRate:0,taxMoney:0,taxLastMoney:12.5}}]);return true})()`);
await new Promise(r=>setTimeout(r,300));
await evaluate(`document.querySelector('.introjs-skipbutton')?.click();true`);
const before=await call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(output,variant+'-input.png'),Buffer.from(before.data,'base64'));
await evaluate(`void [...document.querySelectorAll('.ant-modal button')].find(b=>b.textContent.includes('保存（')).click()`);
await until('!sale.visible && document.body.innerText.includes('+JSON.stringify(number)+')');
for(const record of records){try{record.response=JSON.parse((await call('Network.getResponseBody',{requestId:record.id})).body)}catch(error){record.error=String(error)}}
const visibleRow=await evaluate(`(()=>{const container=[...document.querySelectorAll('.ant-table')].find(t=>t.innerText.includes(${JSON.stringify(number)})),headers=[...container.querySelector('thead tr').children].map(x=>x.textContent.trim()),row=[...container.querySelectorAll('tbody tr')].find(r=>r.innerText.includes(${JSON.stringify(number)}));return {headers,cells:[...row.children].map(x=>x.innerText.trim())}})()`);
fs.writeFileSync(path.join(output,variant+'-table.json'),JSON.stringify(visibleRow,null,2));
const refundColumn=visibleRow.headers.indexOf('本次退款');assert(refundColumn>=0,'Refund column is visible');
const uiRefund=Number(visibleRow.cells[refundColumn]);assert.equal(uiRefund,12.5);
const ui=await evaluate(`document.body.innerText`);fs.writeFileSync(path.join(output,variant+'-browser.json'),JSON.stringify({number,records,ui,uiRefund},null,2));console.log(JSON.stringify({number,records,ui:ui.slice(-1400)},null,2));
const after=await call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(output,variant+'-result.png'),Buffer.from(after.data,'base64'));return {number,records,ui,uiRefund};

}
try {
const cases=[],raw=[];
const sql=query=>execFileSync('mysql',['-hwebuddy-demo-mysql','--skip-ssl','--default-character-set=utf8mb4','-uroot','-N','-B','jsh_erp','-e',query],{encoding:'utf8',env:{...process.env,MYSQL_PWD:'webuddy-isolated-test'}}).trim();
for(const variant of ['single','multi']){
 const browser=await flow(variant);
 assert.equal(browser.records.length,1);const post=browser.records[0];assert.equal(post.response.code,200);
 const info=JSON.parse(post.body.info);assert.equal(info.changeAmount,-12.5);assert(browser.ui.includes(browser.number));
 for (const [label,remark] of [['empty',''],['spaces','　 \t'],['short','退货'],['long','退'.repeat(201)]]) {
  await new Promise(r=>setTimeout(r,2100));
  const invalid=structuredClone(post.body),invalidInfo=JSON.parse(invalid.info);
  invalidInfo.number='WB-REASON-'+Date.now()+'-'+label;invalidInfo.remark=remark;invalid.info=JSON.stringify(invalidInfo);
  const response=await evaluate(`(async()=>{const token=document.querySelector('#app').__vue__.$store.getters.token;return await (await fetch('/jshERP-boot/depotHead/addDepotHeadAndDetail',{method:'POST',headers:{'X-Access-Token':token,'Content-Type':'application/json'},body:JSON.stringify(${JSON.stringify(invalid)})})).json()})()`);
  const count=Number(sql(`SELECT count(*) FROM jsh_depot_head WHERE number='${invalidInfo.number}'`));
  fs.writeFileSync(path.join(output,variant+'-reason-'+label+'.json'),JSON.stringify({input:invalid,response,count,expected:{code:8590001,count:0}},null,2));
  assert.equal(response.code,8590001,'Invalid refund reason must be rejected: '+label);assert.equal(count,0);
  cases.push({id:'refund.'+variant+'.reason.'+label,status:'pass',input:remark,expected:'明确拒绝且不写库',actual:{code:response.code,count}});
 }

 const rows=sql(`SELECT h.change_amount,h.total_price,h.account_money_list,h.status,i.oper_number,i.all_price FROM jsh_depot_head h JOIN jsh_depot_item i ON i.header_id=h.id WHERE h.number='${browser.number}'`).split('\t');
 assert.equal(Number(rows[0]),-12.5);assert.equal(Number(rows[1]),-12.5);assert.equal(rows[3],'0');assert.equal(Number(rows[4]),1);assert.equal(Number(rows[5]),12.5);
 assert.equal(rows[2],variant==='multi'?'-7.25,-5.25':'');
 const detail=await evaluate(`(async()=>{const token=document.querySelector('#app').__vue__.$store.getters.token;return await (await fetch('/jshERP-boot/depotHead/getDetailByNumber?number='+encodeURIComponent(${JSON.stringify(browser.number)}),{headers:{'X-Access-Token':token}})).json()})()`);
 assert.equal(detail.code,200);assert.equal(detail.data.number,browser.number);assert.equal(detail.data.remark,'Webuddy隔离业务回归');assert.equal(sql(`SELECT remark FROM jsh_depot_head WHERE number='${browser.number}'`),'Webuddy隔离业务回归');assert.equal(detail.data.changeAmount,12.5);
 const duplicate=await evaluate(`(async()=>{const token=document.querySelector('#app').__vue__.$store.getters.token;return await (await fetch('/jshERP-boot/depotHead/addDepotHeadAndDetail',{method:'POST',headers:{'X-Access-Token':token,'Content-Type':'application/json'},body:JSON.stringify(${JSON.stringify(post.body)})})).json()})()`);
 assert([8500022,8500032].includes(duplicate.code));
 await new Promise(r=>setTimeout(r,2100));
 const delayed=await evaluate(`(async()=>{const token=document.querySelector('#app').__vue__.$store.getters.token;return await (await fetch('/jshERP-boot/depotHead/addDepotHeadAndDetail',{method:'POST',headers:{'X-Access-Token':token,'Content-Type':'application/json'},body:JSON.stringify(${JSON.stringify(post.body)})})).json()})()`);assert.equal(delayed.code,8500022);assert.equal(sql(`SELECT count(*) FROM jsh_depot_head WHERE number='${browser.number}'`),'1');
 const rejectedBody=structuredClone(post.body),rejectedNumber='WB-NOAUTH-'+Date.now()+'-'+variant;
 const rejectedInfo=JSON.parse(rejectedBody.info);rejectedInfo.number=rejectedNumber;rejectedBody.info=JSON.stringify(rejectedInfo);
 const unauthorizedResponse=await fetch(origin+'/jshERP-boot/depotHead/addDepotHeadAndDetail',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(rejectedBody)});
 const unauthorizedText=await unauthorizedResponse.text();
 const unauthorized={httpStatus:unauthorizedResponse.status,body:unauthorizedText};
 fs.writeFileSync(path.join(output,variant+'-unauthorized.json'),JSON.stringify({request:rejectedBody,response:unauthorized},null,2));
 // LogCostFilter uses HTTP 500 + loginOut for missing authentication; request.js recognizes that contract.
 assert.equal(unauthorized.httpStatus,500);assert.equal(unauthorizedText,'loginOut');
 const unauthorizedCount=sql(`SELECT count(*) FROM jsh_depot_head WHERE number='${rejectedNumber}'`);assert.equal(unauthorizedCount,'0');
 cases.push({id:'refund.'+variant+'.unauthorized',status:'pass',input:'未携带登录凭据提交新的退款单',expected:'拒绝且数据库没有新增单据',actual:{...unauthorized,count:Number(unauthorizedCount)}});
 raw.push({variant,number:browser.number,request:post.body,response:post.response,database:rows,detail,duplicate,delayed,unauthorized});
 cases.push({id:'refund.'+variant+'.save_and_read',status:'pass',input:variant==='multi'?{amounts:[7.25,5.25],quantity:1}:{amount:12.50,quantity:1},expected:{refund:-12.5,quantity:1,uiRefund:12.5,status:'未审核'},actual:{refund:Number(rows[0]),quantity:Number(rows[4]),uiRefund:browser.uiRefund,uiContainsDocument:browser.ui.includes(browser.number),status:rows[3]},number:browser.number});
 cases.push({id:'refund.'+variant+'.duplicate',status:'pass',input:'重复提交同一单号',expected:'拒绝且数据库仍为1单',actual:{immediateCode:duplicate.code,delayedCode:delayed.code,count:1}});
}
fs.writeFileSync(path.join(output,'raw.json'),JSON.stringify(raw,null,2));fs.writeFileSync(path.join(output,'report.json'),JSON.stringify({source,build,cases},null,2));console.log(JSON.stringify({source,build,cases},null,2));ws.close();

} catch(error){const failure=await call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(output,'failure.png'),Buffer.from(failure.data,'base64'));fs.writeFileSync(path.join(output,'failure-page.json'),JSON.stringify(await evaluate('({url:location.href,text:document.body.innerText})')));fs.writeFileSync(path.join(output,'report.json'),JSON.stringify({cases:[{id:'refund.workflow',status:'fail',actual:error instanceof Error?error.message:JSON.stringify(error)}]},null,2));throw error} finally {ws.close()}
