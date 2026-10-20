"""Keyboard behavior of the shipped dialog with and without the assistant.

The DOM double preserves the real document order: assistant before dialog.
Default Tab traversal is simulated after the application's handler, so a trap
that only works with an invented ordering cannot hide focus leaks.
"""
import shutil
import subprocess
import unittest

from tmh.platform.ui import JS


HARNESS = r"""
const assert=require('node:assert/strict');
const listeners={};
const document={activeElement:null,addEventListener:(name,fn)=>{(listeners[name]??=[]).push(fn)}};
let narrow=false;
const windowListeners={};
const window={matchMedia:()=>({matches:narrow}),addEventListener:(name,fn)=>{(windowListeners[name]??=[]).push(fn)}};
function resize(width){narrow=width<=1100;for(const listener of windowListeners.resize||[])listener()}
class Element {
  constructor(name,parent=null,tabIndex=0){this.name=name;this.parent=parent;this.tabIndex=tabIndex;this.hidden=false;this.inert=false;this.disabled=false;this.isConnected=true;this.attrs={};this.children=[];this.classList={values:new Set(),toggle(k,on){if(on)this.values.add(k);else this.values.delete(k)}};if(parent)parent.children.push(this)}
  focus(){if(this.isConnected&&!this.closest())document.activeElement=this}
  contains(node){for(let x=node;x;x=x.parent)if(x===this)return true;return false}
  setAttribute(k,v){this.attrs[k]=v}
  getAttribute(k){return this.attrs[k]}
  addEventListener(){}
  closest(){for(let x=this;x;x=x.parent)if(x.hidden||x.inert)return x;return null}
  getClientRects(){for(let x=this;x;x=x.parent)if(x.hidden)return[];return[{}]}
  querySelectorAll(){return this.children.flatMap(x=>[x,...x.querySelectorAll()]).filter(x=>!x.disabled&&x.tabIndex>=0)}
  set innerHTML(value){this.html=value;heading.textContent=(value.match(/<h[12]>(.*?)<\/h[12]>/)||[])[1]||''}
}
document.body=new Element('body',null,-1);
const skip=new Element('skip',document.body),top=new Element('top',document.body,-1),page=new Element('page',document.body,-1);
const main=new Element('main',page,-1),trigger=new Element('trigger',main),ast=new Element('ast',document.body,-1);
const astFirst=new Element('astFirst',ast),astLast=new Element('astLast',ast),astOpen=new Element('astOpen',document.body);
const astToggle=new Element('astToggle',top);
const overlay=new Element('modal',document.body,-1),box=new Element('box',overlay,-1),close=new Element('close',box),body=new Element('mbody',box,-1);
const field=new Element('field',body),save=new Element('save',body),heading={textContent:''};
overlay.hidden=true;ast.hidden=true;
const elements={'.skip-link':skip,'#modal':overlay,'.mbox':box,'#mbody':body,'#mbody h2':heading,'#mbody h1':null,'#page':page,'#top':top,'#astOpen':astOpen,'#ast':ast,'#main':main,'#aq':astLast,'#astToggle':astToggle};
const $=key=>elements[key];
let stopped=[];const stopPolls=tag=>stopped.push(tag);
const nativeOrder=[skip,astToggle,trigger,astFirst,astLast,astOpen,close,field,save];
function key(name,shiftKey=false){
  const event={key:name,shiftKey,prevented:false,preventDefault(){this.prevented=true}};
  for(const listener of listeners.keydown||[])listener(event);
  if(name==='Tab'&&!event.prevented){
    const items=nativeOrder.filter(x=>x.isConnected&&!x.disabled&&!x.closest());
    const index=items.indexOf(document.activeElement);
    const next=index<0?(shiftKey?items.length-1:0):(index+(shiftKey?-1:1)+items.length)%items.length;
    items[next]?.focus();
  }
  return event;
}
trigger.focus();
"""


@unittest.skipUnless(shutil.which("node"), "Node.js is needed for dialog behavior checks")
class DialogBehaviorTest(unittest.TestCase):
    def check_js(self, checks):
        source = JS.split("let modalReturnFocus=null;", 1)[1].split("const L=", 1)[0]
        toggle = "toggle(on)" + JS.split("  toggle(on)", 1)[1].split("\n  focus()", 1)[0]
        assistant = "\nconst ls={set(){}};const A={open:true,sid:null,paint(){ast.hidden=!this.open;syncDialogScope()}," + toggle + "};\n"
        result = subprocess.run(
            [shutil.which("node"), "-"],
            input=HARNESS + "\nlet modalReturnFocus=null;\n" + source + assistant + "\n" + checks,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_open_close_restores_trigger_and_background_access(self):
        self.check_js(r"""
modal('<h2>新建客户</h2>');
assert.equal(document.activeElement,box);
assert.equal(box.getAttribute('aria-label'),'新建客户');
assert.equal(box.getAttribute('aria-modal'),'true');
for(const x of [skip,page,top,astOpen])assert.equal(x.inert,true);
assert.ok(document.body.classList.values.has('dialog-open'));
save.focus();key('Tab');assert.equal(document.activeElement,close);
close.focus();key('Tab',true);assert.equal(document.activeElement,save);
key('Escape');
assert.equal(document.activeElement,trigger);
assert.equal(overlay.hidden,true);
for(const x of [skip,page,top,astOpen])assert.equal(x.inert,false);
assert.deepEqual(stopped,['modal']);
""")

    def test_replacing_dialog_content_keeps_original_return_target(self):
        self.check_js(r"""
modal('<h2>运行详情</h2>');field.focus();modal('<h2>新的验证记录</h2>',true);
assert.equal(box.getAttribute('aria-label'),'新的验证记录');
assert.ok(box.classList.values.has('wide'));
closeModal();assert.equal(document.activeElement,trigger);
""")

    def test_missing_return_target_falls_back_to_main_without_reopening(self):
        self.check_js(r"""
modal('<h2>运行详情</h2>');trigger.isConnected=false;closeModal();
assert.equal(document.activeElement,main);
skip.focus();const event=key('Escape');
assert.equal(event.prevented,false);
assert.equal(document.activeElement,skip);
""")

    def test_assistant_and_dialog_tab_cycle_never_reaches_background(self):
        self.check_js(r"""
ast.hidden=false;modal('<h2>可由助手代填的需求</h2>');
assert.equal(box.getAttribute('aria-modal'),'false');
const permitted=[close,field,save,astFirst,astLast];
for(const backwards of [false,true]){
 for(const start of permitted){
  start.focus();key('Tab',backwards);
  assert.ok(permitted.includes(document.activeElement),
    start.name+' '+(backwards?'Shift+Tab':'Tab')+' escaped to '+document.activeElement.name);
 }
}
let visited=new Set();close.focus();
for(let i=0;i<permitted.length;i++){visited.add(document.activeElement);key('Tab')}
assert.equal(visited.size,permitted.length,'all dialog and assistant fields remain reachable');
""")

    def test_mobile_overlay_assistant_excludes_covered_dialog_from_focus(self):
        self.check_js(r"""
resize(390);ast.hidden=false;A.open=true;
modal('<h2>可由助手代填的需求</h2>');
assert.equal(box.inert,true,'covered dialog must not receive keyboard input');
assert.equal(document.activeElement,astLast,'opening behind the assistant keeps visible focus');
for(const backwards of [false,true]){
 for(const start of [astFirst,astLast]){
  start.focus();key('Tab',backwards);
  assert.ok([astFirst,astLast].includes(document.activeElement),'focus stays in visible assistant');
 }
}
field.value='尚未提交的需求';key('Escape');
assert.equal(ast.hidden,true,'Escape dismisses the visible assistant first');
assert.equal(overlay.hidden,false,'the covered form remains open');
assert.equal(field.value,'尚未提交的需求','dismissal must preserve the original form input');
assert.equal(document.activeElement,box);
""")

    def test_resize_and_assistant_close_restore_the_visible_dialog_or_trigger(self):
        self.check_js(r"""
ast.hidden=false;A.open=true;modal('<h2>需求表单</h2>');save.focus();
resize(390);
assert.equal(box.inert,true);
assert.equal(document.activeElement,astLast,'resize moves focus away from the covered form');
A.toggle(false);
assert.equal(ast.hidden,true);
assert.equal(box.inert,false);
assert.equal(document.activeElement,box,'closing the assistant returns to the still-open dialog');
key('Tab');assert.equal(document.activeElement,close);
closeModal();assert.equal(document.activeElement,trigger);
ast.hidden=false;A.open=true;astFirst.focus();A.toggle(false);
assert.equal(document.activeElement,astToggle,'without a dialog, return to the header assistant control');
""")


if __name__ == "__main__":
    unittest.main()
