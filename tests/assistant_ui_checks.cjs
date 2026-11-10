const vm=require('vm'),fs=require('fs'),assert=require('assert');
const source=fs.readFileSync('tmh/platform/ui_assistant.py','utf8').split("ASSISTANT_JS = r'''")[1].split("'''")[0];
(async()=>{
 const input={value:'A的问题'},other={textContent:'',disabled:false};let resolve,calls=0;
 const ctx={pageSnap:()=>({title:'设置',route:'#/settings'}),A:{sid:1,msgs:[],load:async()=>{},loadList:async()=>{},paintMsgs(){},updateAssistant(){}},S:{proj:'A'},$:s=>s==='#aq'?input:other,ls:{get:()=>null,set(){}},crypto:{randomUUID:()=> 'uuid'},toast(){},astSend(){},post:()=>{calls++;return new Promise(r=>resolve=r)}};
 vm.createContext(ctx);vm.runInContext(source,ctx);ctx.A.paintMsgs=()=>{};
 let first=ctx.A.send('A的问题');await ctx.A.send('重复');assert.equal(calls,1);
 ctx.A.sid=2;ctx.S.proj='B';input.value='B的新草稿';resolve({message:{id:1},pending:false});await first;assert.equal(input.value,'B的新草稿');assert.equal(ctx.A.turn,null);
 ctx.A.sid=1;ctx.S.proj='A';input.value='提交内容';first=ctx.A.send('提交内容');input.value='新的输入';resolve({message:{id:1},pending:false});await first;assert.equal(input.value,'新的输入');
 ctx.A.sid=null;ctx.A.view=null;ctx.A.switchTo=async()=>{throw Error('stale switch')};first=ctx.A.send('新会话');ctx.S.proj='B';input.value='B内容';resolve({id:3});await first;assert.equal(ctx.A.sid,null);assert.equal(input.value,'B内容');
 console.log('UI_DOUBLE_SEND_PROJECT_SWITCH_NEW_INPUT_NEW_SESSION_PASS');
})().catch(e=>{console.error(e);process.exit(1)});
