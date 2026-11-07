import fs from 'node:fs';import {call,evaluate,ws} from './cdp.mjs';
const samples=[];
for(const concurrency of [1,4,8]){
 const result=await evaluate(`(async()=>{const latencies=[],statuses=[],started=performance.now();await Promise.all(Array.from({length:${concurrency}},async()=>{for(let i=0;i<10;i++){const t=performance.now();const r=await fetch('/api/projects');await r.text();latencies.push(performance.now()-t);statuses.push(r.status)}}));latencies.sort((a,b)=>a-b);return {concurrency:${concurrency},requests:statuses.length,statuses,seconds:(performance.now()-started)/1000,p50_ms:latencies[Math.floor(latencies.length*.5)],p95_ms:latencies[Math.floor(latencies.length*.95)],latencies_ms:latencies}})()`);
 if(result.statuses.some(x=>x!==200))throw Error(JSON.stringify(result));samples.push(result);
}
fs.writeFileSync('/private/tmp/webuddy-scenario-20261107/capacity.json',JSON.stringify({scope:'isolated Mac authenticated browsing; one synthetic session; no model/build/browser workload concurrency',executors:0,model_requests:0,samples},null,2));console.log(samples.map(x=>({concurrency:x.concurrency,requests:x.requests,p95_ms:x.p95_ms})));ws.close();
