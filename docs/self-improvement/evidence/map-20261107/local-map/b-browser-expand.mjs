import fs from 'node:fs';import {call,evaluate,ws} from './cdp.mjs';const out='/private/tmp/webuddy-map-20261107',info=JSON.parse(fs.readFileSync(out+'/b-ui-responsive.log','utf8').split('\n')[0]),origin=new URL(info.url).origin;
const wait=async expr=>{for(let i=0;i<100;i++){if(await evaluate(expr))return;await new Promise(r=>setTimeout(r,100));}throw Error(expr)};
const id=JSON.parse(fs.readFileSync(out+'/local-map-responsive-browser.json','utf8')).map_id;
await call('Page.navigate',{url:origin+'/#/maps/EXT/'+id});await wait('!!document.querySelector("#cmExpand")');
const before=await evaluate(`get('/api/projects/EXT/maps?map_id=${id}')`);await evaluate(`document.querySelector('#cmExpand').click()`);await wait(`location.hash!=='#/maps/EXT/${id}'&&!!document.querySelector('#cmNodes')`);
const nextId=await evaluate(`location.hash.split('/').at(-1)`),after=await evaluate(`get('/api/projects/EXT/maps?map_id=${nextId}')`);if(after.from_map!==id||after.provenance.index_revision!==before.provenance.index_revision||after.nodes.some(n=>before.nodes.some(b=>b.id===n.id)))throw Error('Expansion identity/scope wrong');
console.log(JSON.stringify({old_nodes:before.nodes.length,old_unexpanded:before.unexpanded.length,next_nodes:after.nodes.length,next_unexpanded:after.unexpanded.length,same_index:true,original_preserved:true}));ws.close();
