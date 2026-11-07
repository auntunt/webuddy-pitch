import fs from 'node:fs';
import {call,evaluate,ws} from './cdp.mjs';
for(const [width,height] of [[1440,900],[390,844]]){
 await call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
 await evaluate(`document.querySelector('[data-rf-tab=scope]').click()`);
 await new Promise(r=>setTimeout(r,500));
 await evaluate(`{let e=document.querySelector('[name=scenario_rules]');for(let n=e;n;n=n.parentElement)if(n.tagName==='DETAILS')n.open=true;e.focus();e.scrollIntoView({block:'center'});}`);
 await new Promise(r=>setTimeout(r,200));
 const result=await call('Page.captureScreenshot',{format:'png'});
 fs.writeFileSync('/private/tmp/webuddy-scenario-20261107/scope-fields-'+width+'.png',Buffer.from(result.data,'base64'));
}
ws.close();
