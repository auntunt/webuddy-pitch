import fs from 'node:fs';
import {call,evaluate,ws} from './cdp.mjs';
const out='/private/tmp/webuddy-map-20261107';
const info=JSON.parse(fs.readFileSync(out+'/atlas-server.log','utf8').split('\n')[0]);
const wait=async expr=>{for(let i=0;i<100;i++){if(await evaluate(expr))return;await new Promise(r=>setTimeout(r,100));}throw Error('Wait failed: '+expr)};
await call('Page.navigate',{url:new URL(info.url).origin+'/login'});await wait('!!document.querySelector("input[name=username]")||!location.pathname.includes("login")');
if(await evaluate('!!document.querySelector("input[name=username]")'))await evaluate(`document.querySelector('[name=username]').value='scenario-owner';document.querySelector('[name=password]').value='isolated-scenario-fixture';document.querySelector('form').requestSubmit()`);await wait('!location.pathname.includes("login")');
await call('Page.navigate',{url:new URL(info.url).origin+'/#/atlas'});await wait('typeof AT!=="undefined"&&AT.d?.built');
await evaluate(`atlFlow('flow:refund')`);await wait('AT.flow?.steps.length===60');
const edges=await evaluate(`AT.E`);
if(edges.some(e=>e.a==='fn:step00'&&e.b==='fn:step01')||edges.some(e=>e.a.startsWith('fn:')&&e.b==='tbl:budget'))throw Error('Invented relationship');
if(!edges.some(e=>e.a==='fn:step00'&&e.b==='fn:step02'&&e.label==='静态调用'))throw Error('Missing static edge');
if(!edges.some(e=>e.a==='ep'&&e.b==='tbl:budget'&&e.label.includes('方法未知')))throw Error('Missing unknown attribution');
await evaluate(`Array.from(document.querySelectorAll('#atlTl button')).find(b=>b.textContent==='下一组').click()`);await wait('AT.flow?.offset===60');
if(await evaluate('AT.flow.steps.length')!==5)throw Error('Lost remaining steps');
for(const [width,height] of [[1440,900],[390,844]]){await call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});const shot=await call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(out+'/atlas-'+width+'.png',Buffer.from(shot.data,'base64'));}
fs.writeFileSync(out+'/atlas-browser.json',JSON.stringify({synthetic:true,edges,shown:5,total:65},null,2));console.log('Actual Atlas static edges, unknown flow IO and 60+5 paging passed');ws.close();
