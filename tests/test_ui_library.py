"""Exercise the shipped project-library handlers without services or a browser."""
import shutil
import subprocess
import unittest

from tmh.platform.ui import page
from tmh.platform.ui_library import LIBRARY_JS


HARNESS = r"""
const assert=require('node:assert/strict');
const h=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const unescape=s=>s.replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&');
class Element {
 constructor(tag='div',attrs='',parent=null){this.tag=tag;this.parent=parent;this.children=[];this.attrs={};this.dataset={};this.listeners={};this.connected=false;this.hidden=false;this.disabled=false;this.checked=false;this._html='';
  for(const match of attrs.matchAll(/([\w-]+)(?:="([^"]*)"|='([^']*)'|=([^\s]+))?/g)){const key=match[1],value=unescape(match[2]??match[3]??match[4]??'');this.attrs[key]=value;if(key==='id')this.id=value;if(key==='type')this.type=value;if(key==='disabled')this.disabled=true;if(key==='hidden')this.hidden=true;if(key==='checked')this.checked=true;if(key.startsWith('data-'))this.dataset[key.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=value}
 }
 get isConnected(){return this.parent?this.parent.isConnected:this.connected}
 set innerHTML(html){for(const child of this.children)if(typeof child!=='string')child.parent=null;this.children=[];this._html=html;const stack=[this];
  for(const token of html.matchAll(/<\/?([A-Za-z][\w-]*)\b([^>]*)>|([^<]+)/g)){if(token[3]){stack.at(-1).children.push(unescape(token[3]));continue}const tag=token[1];if(token[0].startsWith('</')){const index=stack.map(n=>n.tag).lastIndexOf(tag);if(index>0)stack.length=index;continue}const node=new Element(tag,token[2],stack.at(-1));stack.at(-1).children.push(node);if(!['input','br','hr','img','meta','link'].includes(tag))stack.push(node)}
 }
 get innerHTML(){return this._html}
 get textContent(){return this.children.map(n=>typeof n==='string'?n:n.textContent).join('')}
 set textContent(value){this.children=[String(value)];this._html=h(value)}
 get value(){if(this.tag==='select'){const options=this.all().filter(n=>n.tag==='option');if(this._value!==undefined)return options.some(n=>n.attrs.value===this._value)?this._value:'';return(options.find(n=>Object.hasOwn(n.attrs,'selected'))||options[0])?.attrs.value||''}return this._value??this.attrs.value??(this.tag==='textarea'?this.textContent:'')}
 set value(value){this._value=String(value)}
 all(){return this.children.flatMap(n=>typeof n==='string'?[]:[n,...n.all()])}
 querySelectorAll(selector){return this.all().filter(n=>{if(selector.startsWith('#'))return n.id===selector.slice(1);const match=selector.match(/^\[([^=\]]+)(?:="([^"]*)")?\]$/);return match&&Object.hasOwn(n.attrs,match[1])&&(match[2]===undefined||n.attrs[match[1]]===match[2])})}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null}
 addEventListener(type,handler){(this.listeners[type]??=[]).push(handler)}
 fire(type){const event={preventDefault(){},target:this};for(const handler of this.listeners[type]||[])handler(event);return this['on'+type]?.(event)}
 focus(){document.activeElement=this}
}
const main=new Element(),overlay=new Element(),body=new Element();main.connected=true;overlay.connected=true;overlay.hidden=true;body.parent=overlay;overlay.children=[body];
const $=selector=>selector==='#main'?main:selector==='#modal'?overlay:selector==='#mbody'?body:main.querySelector(selector)||body.querySelector(selector);
const document={activeElement:null};
const modal=html=>{body.innerHTML=html;overlay.hidden=false},closeModal=()=>{overlay.hidden=true};
const location={hash:'#/library'},curView=()=>location.hash.slice(2).split('/')[0];
const S={proj:'APP',projects:[{key:'APP',name:'客户项目'},{key:'STD',name:'标品项目'},{key:'REF',name:'参考项目'}],polls:[]};
const setProj=key=>{S.proj=key},render=()=>vLibrary();let selectorsPainted=0;const paintSel=()=>{selectorsPainted++};
const poll=(fn,ms,tag)=>S.polls.push({fn,ms,tag});
const requests=[],mutations=[];let getHandler,postHandler;
const get=async url=>{requests.push(url);return getHandler(url)},post=async(url,body,headers)=>{mutations.push({url,body,...(headers&&Object.keys(headers).length?{headers}:{})});return postHandler(url,body,headers)};
const later=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return{promise,resolve,reject}};
const revision=(id='a'.repeat(32),state='ready')=>({id,commit:'b'.repeat(40),status:state,stage:'published',error:'',created:'2026-10-20',summary:{files:12,excluded:2,indexed:10,seconds:0.1}});
const overview=(key='APP',extras={})=>({project:{key,name:key+' 项目',root:'/tmp/'+key},profile:{roles:[],workflow:'development'},sources:[{id:key+'-source',root:'/tmp/source-'+key}],revisions:[revision()],references:[],derivation:null,grants:[],...extras});
let currentData=overview();
getHandler=url=>url==='/api/projects'?S.projects:url==='/api/projects/APP/library'?currentData:overview(url.split('/')[3]);
postHandler=async()=>({ok:true});
const resultItem=(project='STD',extra={})=>({revision_id:'a'.repeat(32),source_project:project,source_name:project+' 标品',commit:'b'.repeat(40),id:project+':Approval',title:'审批',path:'src/Approval.java',line:12,kind:'code',excerpt:'class Approval {}',score:1,relation:'reference',applicability:'当前项目适用性待核对',...extra});
const searchResults=(items,extra={})=>({items,references_hash:'references-1',total:items.length,offset:0,limit:20,unavailable:[],...extra});
const fileResult=(item,content,encoding='utf-8')=>({path:item.path,content,encoding,sha256:'c'.repeat(64),commit:item.commit,source_project:item.source_project,revision_id:item.revision_id});
const submit=id=>$(id).fire('submit');
"""


@unittest.skipUnless(shutil.which("node"), "Node.js is needed for shipped library UI checks")
class LibraryUiTest(unittest.TestCase):
    def run_js(self, checks):
        result = subprocess.run(
            [shutil.which("node"), "-"],
            input=HARNESS + LIBRARY_JS + "\n(async()=>{\n" + checks +
                  "\n})().catch(error=>{console.error(error);process.exitCode=1});",
            encoding="utf-8", errors="replace",
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_page_wires_library_navigation_and_parses_as_complete_script(self):
        html = page()
        self.assertIn("library:vLibrary", html)
        self.assertIn("知识与引用','#/library'", html)
        self.assertIn('data-project-library="', html)
        self.assertIn("function newProject(){return libraryRegisterProject()}", html)
        result = subprocess.run(
            [shutil.which("node"), "--check"],
            input=html.split("<script>", 1)[1].split("</script>", 1)[0],
            encoding="utf-8", errors="replace",
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_poll_updates_status_without_replacing_drafts_or_focus(self):
        self.run_js(r"""
currentData=overview('APP',{revisions:[revision('a'.repeat(32),'building')]});await vLibrary();
const fields=['#libQuery','#libScopes','#libPurpose','#libCommit'].map(id=>{const node=$(id);node.value='尚未提交 '+id;node.selectionStart=3;node.fire('input');return{id,node,value:node.value}});fields[1].node.focus();
currentData=overview('APP',{revisions:[{...revision('a'.repeat(32),'failed'),error:'解析失败：保留现场'}]});await S.polls[0].fn();
assert.ok($('#libRevisions').innerHTML.includes('解析失败：保留现场'));assert.ok($('#libRevisions').innerHTML.includes('继续构建'));
for(const {id,node,value}of fields){assert.equal($(id),node);assert.equal(node.value,value);assert.equal(node.selectionStart,3)}
assert.equal(document.activeElement,fields[1].node);assert.equal(S.polls[0].ms,5000);assert.equal(S.polls[0].tag,'page');
""")

    def test_build_double_submit_and_stale_refresh_cannot_duplicate_or_roll_back(self):
        self.run_js(r"""
await vLibrary();const pending=later();postHandler=()=>pending.promise;$('#libCommit').value='release/v5.2';
const first=submit('#libBuildForm'),second=submit('#libBuildForm');assert.equal(mutations.length,1);assert.equal($('#libBuild').disabled,true);assert.deepEqual(mutations[0],{url:'/api/projects/APP/library',body:{action:'build',commit:'release/v5.2'}});
const old=later();getHandler=()=>old.promise;const refresh=libraryRefresh(LIB.view);
currentData=overview('APP',{revisions:[revision('d'.repeat(32),'queued')]});getHandler=()=>currentData;pending.resolve(revision('d'.repeat(32),'queued'));await first;await second;
old.resolve(overview());await refresh;assert.ok($('#libRevisions').innerHTML.includes('d'.repeat(32)));assert.equal($('#libBuild').disabled,false);
""")

    def test_departed_project_and_superseded_source_responses_are_discarded(self):
        self.run_js(r"""
const initial=later();getHandler=()=>initial.promise;const loading=vLibrary();S.proj='OTHER';main.innerHTML='<div id="newPage">另一个项目</div>';initial.resolve(overview());await loading;assert.equal($('#newPage').textContent,'另一个项目');assert.equal(S.polls.length,0);
S.proj='APP';getHandler=()=>overview();await vLibrary();const old=later(),fresh=later();getHandler=url=>url.includes('/STD/')?old.promise:fresh.promise;
$('#libSource').value='STD';const a=$('#libSource').fire('change');$('#libSource').value='REF';const b=$('#libSource').fire('change');fresh.resolve(overview('REF',{revisions:[revision('e'.repeat(32))]}));await b;old.resolve(overview('STD'));await a;
assert.equal(LIB.view.sourceKey,'REF');assert.ok($('#libSourceRevision').innerHTML.includes('e'.repeat(32)));assert.ok(!$('#libSourceRevision').innerHTML.includes('a'.repeat(32)));
""")

    def test_two_references_keep_explicit_revision_scope_and_unchecked_sharing(self):
        self.run_js(r"""
await vLibrary();assert.equal($('#libGrant').checked,false);
for(const [key,id,path]of [['STD','a'.repeat(32),'src/approval'],['REF','e'.repeat(32),'docs/ui']]){
 $('#libSource').value=key;getHandler=url=>url===`/api/projects/${key}/library`?overview(key,{revisions:[revision(id)]}):currentData;await $('#libSource').fire('change');$('#libSourceRevision').value=id;$('#libSourceRevision').fire('change');
 $('#libScopes').value=path+'\nREADME.md';$('#libScopes').fire('input');$('#libPurpose').value='分别参考 '+key;$('#libGrant').checked=true;
 await submit('#libReferenceForm');assert.equal($('#libGrant').checked,false);
}
assert.deepEqual(mutations.map(x=>x.body),[
 {action:'reference',revision_id:'a'.repeat(32),scopes:['src/approval','README.md'],purpose:'分别参考 STD',grant:true},
 {action:'reference',revision_id:'e'.repeat(32),scopes:['docs/ui','README.md'],purpose:'分别参考 REF',grant:true}
]);
$('#libGrant').checked=true;$('#libScopes').value='another';$('#libScopes').fire('input');assert.equal($('#libGrant').checked,false,'edited scope requires a fresh explicit grant');
$('#libScopes').value='';$('#libGrant').checked=false;await submit('#libReferenceForm');assert.equal(mutations[2].body.grant,false);assert.deepEqual(mutations[2].body.scopes,[]);
""")

    def test_search_retains_provenance_escapes_content_and_reads_complete_version(self):
        self.run_js(r"""
await vLibrary();const unsafe='<img src=x onerror="alert(1)">',std=resultItem('STD',{title:unsafe,excerpt:unsafe,excerpt_truncated:true}),ref=resultItem('REF',{revision_id:'e'.repeat(32),commit:'f'.repeat(40)});let reading=false;const source=unsafe+'\n'+'完整原文'.repeat(12000)+'\n结束标记';
getHandler=url=>{if(url.includes('/knowledge/search'))return searchResults([std,ref]);if(url.includes('/knowledge/file')){reading=true;assert.ok(url.includes('revision_id='+std.revision_id));assert.ok(url.includes('path=src%2FApproval.java'));return fileResult(std,source)}throw Error(url)};
$('#libQuery').value='审批';await submit('#libSearchForm');const html=$('#libResults').innerHTML;assert.ok(html.includes('STD'));assert.ok(html.includes('REF'));assert.ok(html.includes(std.commit));assert.ok(html.includes(ref.commit));assert.ok(html.includes(h(unsafe)));assert.ok(!html.includes('<img'));assert.ok(html.includes('当前项目适用性待核对'));assert.ok(html.includes('前 600 个字符的片段'));assert.ok(html.includes('完整原文保留全部内容'));
await $('#libResults').querySelector('[data-lib-file="0"]').onclick();assert.equal(reading,true);assert.ok($('#libFile').innerHTML.includes(h(source)));assert.ok($('#libFile').innerHTML.includes('结束标记'));assert.ok(!$('#libFile').innerHTML.includes('<img'));
""")

    def test_reference_cards_compare_their_fixed_baselines_without_an_own_snapshot(self):
        self.run_js(r"""
const references=[{id:'standard-binding',revision_id:'a'.repeat(32),source_project:'STD',source_name:'标品',commit:'b'.repeat(40),scopes:[],purpose:'标品基线',available:true},{id:'reference-binding',revision_id:'e'.repeat(32),source_project:'REF',source_name:'参考',commit:'f'.repeat(40),scopes:['modules'],purpose:'模块参考',available:true}];currentData=overview('APP',{revisions:[],references});await vLibrary();assert.ok($('#libRevisions').textContent.includes('尚未构建固定快照'));
postHandler=async(url,body)=>body.action==='compare'?{base_commit:body.revision_id==='a'.repeat(32)?'b'.repeat(40):'f'.repeat(40),current_commit:'c'.repeat(40),changed:[{path:'modules/<Approval>.py',status:'M'}],unknown:[],note:'固定来源与当前项目的已提交差异'}:{ok:true};
for(const [index,reference]of references.entries()){const cards=$('#libReferences').querySelectorAll('[data-lib-action]');assert.equal(cards.length,2);assert.equal(cards[index].textContent,'比较当前代码');await cards[index].onclick();assert.deepEqual(mutations[index],{url:'/api/projects/APP/library',body:{action:'compare',revision_id:reference.revision_id}});assert.equal($('#libCompare').hidden,false);assert.ok($('#libCompare').innerHTML.includes(reference.commit));assert.ok($('#libCompare').innerHTML.includes('c'.repeat(40)));assert.ok($('#libCompare').innerHTML.includes(h('modules/<Approval>.py')))}
await $('#libReferences').querySelector('[data-lib-remove="reference-binding"]').onclick();assert.deepEqual(mutations[2].body,{action:'remove_reference',binding_id:'reference-binding'});assert.equal(mutations.filter(x=>x.body.action==='compare').length,2);
""")

    def test_reference_compare_deduplicates_across_refresh_and_keeps_unavailable_cards_disabled(self):
        self.run_js(r"""
const references=[{id:'blocked-binding',revision_id:'a'.repeat(32),source_project:'STD',source_name:'标品',commit:'b'.repeat(40),scopes:[],available:false},{id:'allowed-binding',revision_id:'e'.repeat(32),source_project:'REF',source_name:'参考',commit:'f'.repeat(40),scopes:[],available:true},{id:'other-binding',revision_id:'g'.repeat(32),source_project:'OTHER',source_name:'另一来源',commit:'h'.repeat(40),scopes:[],available:true}];currentData=overview('APP',{revisions:[],references});await vLibrary();let cards=$('#libReferences').querySelectorAll('[data-lib-action]');assert.equal(cards[0].disabled,true);await cards[0].onclick();assert.equal(mutations.length,0);
const pending=later();postHandler=()=>pending.promise;const work=cards[1].onclick();await cards[1].onclick();assert.equal(mutations.length,1);assert.equal(cards[1].disabled,true);assert.equal(cards[2].disabled,false);for(const button of $('#libReferences').querySelectorAll('[data-lib-remove]'))assert.equal(button.disabled,false);
await libraryRefresh(LIB.view);cards=$('#libReferences').querySelectorAll('[data-lib-action]');assert.equal(cards[0].disabled,true);assert.equal(cards[1].disabled,true);assert.equal(cards[2].disabled,false);await cards[1].onclick();assert.equal(mutations.length,1);pending.resolve({base_commit:'f'.repeat(40),current_commit:'c'.repeat(40),changed:[],unknown:[]});await work;
cards=$('#libReferences').querySelectorAll('[data-lib-action]');assert.equal(cards[0].disabled,true);assert.equal(cards[1].disabled,false);assert.equal(cards[2].disabled,false);await cards[0].onclick();assert.equal(mutations.length,1);for(const button of $('#libReferences').querySelectorAll('[data-lib-remove]'))assert.equal(button.disabled,false);
postHandler=async()=>({ok:true});await $('#libReferences').querySelector('[data-lib-remove="blocked-binding"]').onclick();assert.deepEqual(mutations[1].body,{action:'remove_reference',binding_id:'blocked-binding'});assert.equal($('#libReferences').querySelectorAll('[data-lib-action]')[0].disabled,true);
""")

    def test_reference_changes_clear_existing_comparison_and_discard_late_comparison(self):
        self.run_js(r"""
const binding={id:'binding',revision_id:'a'.repeat(32),source_project:'STD',source_name:'标品',commit:'b'.repeat(40),scopes:[],purpose:'基线参考',available:true};currentData=overview('APP',{revisions:[],references:[binding]});await vLibrary();postHandler=async()=>({base_commit:binding.commit,current_commit:'c'.repeat(40),changed:[],unknown:[],note:'完整范围的旧对照'});await $('#libReferences').querySelector('[data-lib-action="compare"]').onclick();assert.equal($('#libCompare').hidden,false);assert.ok($('#libCompare').textContent.includes('完整范围的旧对照'));
currentData=overview('APP',{revisions:[],references:[{...binding,scopes:['modules']}]});await libraryRefresh(LIB.view);assert.equal($('#libCompare').hidden,true);assert.equal($('#libCompare').innerHTML,'');
const pending=later();postHandler=()=>pending.promise;const compare=$('#libReferences').querySelector('[data-lib-action="compare"]').onclick();currentData=overview('APP',{revisions:[],references:[{...binding,scopes:['modules'],available:false}]});await libraryRefresh(LIB.view);const readCount=requests.length;pending.resolve({base_commit:binding.commit,current_commit:'c'.repeat(40),changed:[{path:'modules/private.py',status:'M'}],unknown:[],note:'撤权后迟到的对照'});await compare;
assert.equal($('#libCompare').hidden,true);assert.equal($('#libCompare').innerHTML,'');assert.equal(requests.length,readCount,'discarded response must not refresh or restore its old view');assert.equal(LIB.pending.size,0);assert.equal($('#libReferences').querySelector('[data-lib-action="compare"]').disabled,true);assert.ok(!$('#libNotice').textContent.includes('代码比较已更新'));
""")

    def test_latest_comparison_request_wins_for_both_response_orders_and_stale_errors(self):
        self.run_js(r"""
const references=[{id:'standard-binding',revision_id:'a'.repeat(32),source_project:'STD',source_name:'标品',commit:'b'.repeat(40),scopes:[],available:true},{id:'reference-binding',revision_id:'e'.repeat(32),source_project:'REF',source_name:'参考',commit:'f'.repeat(40),scopes:[],available:true}];currentData=overview('APP',{revisions:[],references});await vLibrary();const result=(index,note)=>({base_commit:references[index].commit,current_commit:'c'.repeat(40),changed:[],unknown:[],note});
for(const firstReturnsFirst of [true,false]){const first=later(),latest=later();postHandler=(url,body)=>body.revision_id===references[0].revision_id?first.promise:latest.promise;const buttons=$('#libReferences').querySelectorAll('[data-lib-action="compare"]'),older=buttons[0].onclick(),newer=buttons[1].onclick();assert.equal($('#libCompare').hidden,true);
 if(firstReturnsFirst){first.resolve(result(0,'过期的标品对照'));await older;assert.equal($('#libCompare').hidden,true);latest.resolve(result(1,'最新的参考对照'));await newer}else{latest.resolve(result(1,'最新的参考对照'));await newer;first.resolve(result(0,'过期的标品对照'));await older}
 assert.equal($('#libCompare').hidden,false);assert.ok($('#libCompare').textContent.includes('最新的参考对照'));assert.ok(!$('#libCompare').textContent.includes('过期的标品对照'));assert.equal(LIB.pending.size,0);
}
const first=later(),latest=later();postHandler=(url,body)=>body.revision_id===references[0].revision_id?first.promise:latest.promise;const buttons=$('#libReferences').querySelectorAll('[data-lib-action="compare"]'),older=buttons[0].onclick(),newer=buttons[1].onclick();latest.resolve(result(1,'最新成功结果'));await newer;const notice=$('#libNotice').textContent;first.reject(Error('过期请求的错误'));await older;assert.equal($('#libNotice').textContent,notice);assert.ok($('#libCompare').textContent.includes('最新成功结果'));assert.equal(LIB.pending.size,0);
""")

    def test_pagination_uses_the_submitted_query_and_preserves_new_query_draft(self):
        self.run_js(r"""
await vLibrary();getHandler=url=>{const offset=Number(new URL('http://local'+url).searchParams.get('offset'));return searchResults(Array.from({length:20},()=>resultItem()),{offset,total:40})};
$('#libQuery').value='审批';await submit('#libSearchForm');$('#libQuery').value='新草稿';await $('#libNext').onclick();await $('#libPrev').onclick();
assert.equal($('#libQuery').value,'新草稿');for(const url of requests.filter(x=>x.includes('/knowledge/search')))assert.equal(new URL('http://local'+url).searchParams.get('q'),'审批');
assert.equal(new URL('http://local'+requests.at(-1)).searchParams.get('offset'),'0');
""")

    def test_reference_change_invalidates_inflight_search_and_full_source_read(self):
        self.run_js(r"""
await vLibrary();const c=LIB.view,pending=later();getHandler=url=>url.includes('/knowledge/search')?pending.promise:currentData;$('#libQuery').value='审批';const search=submit('#libSearchForm');
currentData=overview('APP',{references:[{id:'new',revision_id:'e'.repeat(32),source_project:'REF',source_name:'参考',commit:'f'.repeat(40),scopes:['docs'],purpose:'参考'}]});await libraryRefresh(c);pending.resolve(searchResults([resultItem()]));await search;assert.equal($('#libResults').innerHTML,'');assert.ok($('#libSearchStatus').textContent.includes('引用集合已变化'));assert.equal($('#libSearchGo').disabled,false);
const filePending=later();getHandler=url=>url.includes('/knowledge/file')?filePending.promise:overview();const file=libraryFile(c,resultItem());await libraryRefresh(c);filePending.resolve(fileResult(resultItem(),'旧授权内容'));await file;assert.equal($('#libFile').hidden,true);assert.ok(!$('#libFile').innerHTML.includes('旧授权内容'));
""")

    def test_departed_search_and_file_callbacks_do_not_paint_the_new_page(self):
        self.run_js(r"""
await vLibrary();const c=LIB.view,pending=later();getHandler=()=>pending.promise;$('#libQuery').value='审批';const search=submit('#libSearchForm');
S.proj='OTHER';main.innerHTML='<div id="newPage">新页面</div>';pending.resolve(searchResults([resultItem()]));await search;assert.equal($('#newPage').textContent,'新页面');
S.proj='APP';getHandler=()=>overview();await vLibrary();const source=later();getHandler=()=>source.promise;const file=libraryFile(LIB.view,resultItem());location.hash='#/settings';main.innerHTML='<div id="newPage">设置页</div>';source.resolve(fileResult(resultItem(),'完整源码'));await file;assert.equal($('#newPage').textContent,'设置页');
""")

    def test_revoked_reference_is_visible_and_invalidates_loaded_and_pending_content(self):
        self.run_js(r"""
const binding={id:'binding',revision_id:'a'.repeat(32),source_project:'STD',source_name:'标品',commit:'b'.repeat(40),scopes:[],purpose:'审批参考',available:true};currentData=overview('APP',{references:[binding]});await vLibrary();
getHandler=url=>url.includes('/knowledge/search')?searchResults([resultItem()]):fileResult(resultItem(),'先前授权原文');$('#libQuery').value='Approval';await submit('#libSearchForm');await libraryFile(LIB.view,resultItem());assert.equal($('#libFile').hidden,false);
const pending=later();getHandler=url=>url.includes('/knowledge/search')?pending.promise:currentData;const search=submit('#libSearchForm');currentData=overview('APP',{references:[{...binding,available:false,reason:'共享已撤销 <script>unsafe</script>'}]});await libraryRefresh(LIB.view);pending.resolve(searchResults([resultItem()]));await search;
assert.equal($('#libResults').innerHTML,'');assert.equal($('#libFile').hidden,true);assert.ok($('#libReferences').innerHTML.includes('来源不可用'));assert.ok($('#libReferences').innerHTML.includes(h('共享已撤销 <script>unsafe</script>')));assert.ok(!$('#libReferences').innerHTML.includes('<script>'));assert.ok($('#libSearchStatus').textContent.includes('引用集合已变化'));assert.equal($('#libSearchGo').disabled,false);
""")

    def test_independent_operator_secret_is_header_only_ephemeral_and_sensitive_only(self):
        self.run_js(r"""
S.meta={login:true,operator_authenticated:false};await vLibrary();const field=$('#libOperator');assert.equal(field.type,'password');assert.equal(field.attrs.autocomplete,'off');field.value='temporary-independent-secret';field.fire('input');assert.ok(!JSON.stringify([...LIB.drafts]).includes(field.value));
await submit('#libBuildForm');assert.equal(mutations[0].headers,undefined);assert.equal(field.value,'temporary-independent-secret');await S.polls[0].fn();assert.equal($('#libOperator'),field);
$('#libProduct').checked=true;await submit('#libProfileForm');assert.deepEqual(mutations[1].headers,{'X-Webuddy-Operator-Token':'temporary-independent-secret'});assert.equal(field.value,'');assert.ok(!JSON.stringify(mutations[1].body).includes('temporary-independent-secret'));assert.ok(!JSON.stringify([...LIB.drafts]).includes('temporary-independent-secret'));
field.value='reference-secret';$('#libSource').value='STD';await $('#libSource').fire('change');$('#libSourceRevision').value='a'.repeat(32);$('#libGrant').checked=false;await submit('#libReferenceForm');assert.equal(mutations[2].headers,undefined);assert.equal(field.value,'reference-secret');$('#libGrant').checked=true;await submit('#libReferenceForm');assert.deepEqual(mutations[3].headers,{'X-Webuddy-Operator-Token':'reference-secret'});assert.equal(field.value,'');
field.value='must-not-survive-navigation';await vLibrary();assert.equal($('#libOperator').value,'');assert.ok(!JSON.stringify([...LIB.drafts]).includes('must-not-survive-navigation'));
""")

    def test_logged_in_session_needs_no_extra_secret_and_workspace_receipt_is_complete(self):
        self.run_js(r"""
S.meta={login:true,operator_authenticated:true};await vLibrary();assert.equal($('#libOperator'),null);await submit('#libProfileForm');assert.equal(mutations[0].headers,undefined);
libraryWorkspace(LIB.view,'derive','a'.repeat(32));assert.equal($('#libWorkspaceOperator'),null);assert.ok($('#libWorkspaceDialog').textContent.includes('来源任务、验收和验证记录会完整归档为来源历史'));assert.ok($('#libWorkspaceDialog').textContent.includes('知识需要在本项目重新确认'));$('#libDerivedKey').value='NEW';$('#libDerivedName').value='新客户';
const initialization=[{path:'.tmh/tasks/OLD.json',action:'archive_source_history',destination:'.tmh/source-history/<fixed>/tasks/OLD.json'},{path:'.tmh/knowledge/index.md',action:'requires_current_project_confirmation'},{path:'结束完整路径 <img src=x>',action:'archive_source_history',destination:'结束归档 <script>unsafe</script>'}];postHandler=async()=>({project:{key:'NEW',name:'新客户'},source_commit:'b'.repeat(40),import_commit:'c'.repeat(40),commit:'d'.repeat(40),initialization});getHandler=url=>url==='/api/projects'?[...S.projects,{key:'NEW',name:'新客户'}]:currentData;await submit('#libWorkspaceForm');
assert.equal(mutations[1].headers,undefined);const receipt=$('#libWorkspaceDialog').innerHTML;for(const sha of ['b','c','d'])assert.ok(receipt.includes(sha.repeat(40)));for(const record of initialization){assert.ok(receipt.includes(h(record.path)));if(record.destination)assert.ok(receipt.includes(h(record.destination)))}assert.ok(!receipt.includes('<script>'));assert.ok(!receipt.includes('<img'));assert.ok(receipt.includes('需要本项目重新确认'));
""")

    def test_workspace_dialog_sends_and_clears_only_the_selected_operator_secret(self):
        self.run_js(r"""
await vLibrary();$('#libOperator').value='page-secret';libraryWorkspace(LIB.view,'derive','a'.repeat(32));const secret=$('#libWorkspaceOperator');assert.equal(secret.type,'password');secret.value='dialog-secret';$('#libDerivedKey').value='NEW';$('#libDerivedName').value='客户';const pending=later();postHandler=()=>pending.promise;const result=submit('#libWorkspaceForm');assert.equal(secret.value,'');assert.equal($('#libOperator').value,'page-secret');assert.deepEqual(mutations[0].headers,{'X-Webuddy-Operator-Token':'dialog-secret'});assert.ok(!JSON.stringify(mutations[0].body).includes('secret'));assert.ok(!JSON.stringify([...LIB.drafts]).includes('secret'));pending.reject(Error('synthetic rejection'));await result;assert.ok($('#libWorkspaceStatus').textContent.includes('synthetic rejection'));
""")

    def test_shared_api_wrapper_forwards_optional_headers_without_changing_default_calls(self):
        script = page().split('<script>', 1)[1].split('</script>', 1)[0]
        helper = 'async function api' + script.split('async function api', 1)[1].split('function toast', 1)[0]
        result = subprocess.run(
            [shutil.which('node'), '-'],
            input="const assert=require('node:assert/strict');const S={user:'测试者'};const calls=[];"
                  "const fetch=async(p,o)=>{calls.push({p,o});return {ok:true,json:async()=>({ok:true})}};\n" + helper + r"""
(async()=>{await post('/ordinary',{action:'build'});await post('/sensitive',{action:'configure'},{'X-Webuddy-Operator-Token':'ephemeral'});await get('/ordinary-read');assert.equal(calls.length,3);for(const {o} of calls){assert.equal(o.headers['X-TMH'],'1');assert.equal(o.headers['X-TMH-User'],encodeURIComponent('测试者'))}assert.equal(calls[0].o.headers['X-Webuddy-Operator-Token'],undefined);assert.equal(calls[1].o.headers['X-Webuddy-Operator-Token'],'ephemeral');assert.deepEqual(JSON.parse(calls[1].o.body),{action:'configure'});assert.equal(calls[2].o.headers['X-Webuddy-Operator-Token'],undefined);assert.equal(calls[2].o.body,undefined)})().catch(error=>{console.error(error);process.exitCode=1});
""",
            encoding="utf-8", errors="replace", capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_full_source_rejects_mismatched_versions_and_keeps_binary_bytes(self):
        self.run_js(r"""
await vLibrary();const item=resultItem(),raw=Buffer.from([0,255,1,128,13,10]).toString('base64');getHandler=()=>fileResult(item,raw,'base64');await libraryFile(LIB.view,item);
assert.ok($('#libFile').innerHTML.includes('data:application/octet-stream;base64,'+raw));assert.ok($('#libFile').innerHTML.includes('<pre class="lib-raw">'+raw+'</pre>'));
getHandler=()=>({...fileResult(item,'错误版本的内容'),commit:'9'.repeat(40)});await libraryFile(LIB.view,item);assert.ok($('#libFile').innerHTML.includes('原文来源与所选检索结果不一致'));assert.ok(!$('#libFile').innerHTML.includes('错误版本的内容'));
""")

    def test_same_project_maintenance_and_new_customer_derivation_are_distinct(self):
        self.run_js(r"""
currentData=overview('APP',{profile:{roles:['product','reference'],workflow:'reference'}});await vLibrary();assert.equal($('#libWorkflow').disabled,true);assert.ok($('#libRevisions').innerHTML.includes('开始维护本项目'));assert.ok($('#libRevisions').innerHTML.includes('派生客户项目'));
libraryWorkspace(LIB.view,'derive','a'.repeat(32));$('#libDerivedKey').value='CLIENTA';$('#libDerivedName').value='客户甲';postHandler=async()=>({project:{key:'CLIENTA',name:'客户甲'},commit:'b'.repeat(40)});getHandler=url=>url==='/api/projects'?[...S.projects,{key:'CLIENTA',name:'客户甲'}]:currentData;
await submit('#libWorkspaceForm');assert.deepEqual(mutations[0].body,{action:'derive',revision_id:'a'.repeat(32),key:'CLIENTA',name:'客户甲'});assert.equal(S.proj,'APP');assert.ok($('#libWorkspaceDialog').innerHTML.includes('客户项目已创建'));
closeModal();libraryWorkspace(LIB.view,'maintain','a'.repeat(32));assert.equal($('#libDerivedKey'),null);postHandler=async()=>({project:{key:'APP',name:'APP 项目'},commit:'b'.repeat(40)});await submit('#libWorkspaceForm');assert.deepEqual(mutations[1].body,{action:'maintain',revision_id:'a'.repeat(32)});assert.equal(S.proj,'APP');assert.ok($('#libWorkspaceDialog').innerHTML.includes('本项目已进入维护'));
""")

    def test_registration_submits_composable_roles_without_automatic_build(self):
        self.run_js(r"""
location.hash='#/settings';libraryRegisterProject();assert.equal($('#libRegisterWorkflow').value,'development');$('#pr').value='/tmp/complex-product';$('#pr').fire('input');assert.equal($('#pk').value,'COM');$('#pk').value='STD';$('#pn').value='复杂标品';$('#libRegisterProduct').checked=true;$('#libRegisterReference').checked=true;$('#libRegisterWorkflow').value='reference';
const pending=later();postHandler=()=>pending.promise;getHandler=()=>S.projects;const first=submit('#libRegisterForm'),second=submit('#libRegisterForm');assert.equal(mutations.length,1);assert.deepEqual(mutations[0],{url:'/api/projects',body:{root:'/tmp/complex-product',key:'STD',name:'复杂标品',roles:['product','reference'],workflow:'reference'}});
pending.resolve({key:'STD',name:'复杂标品'});await first;await second;assert.equal(location.hash,'#/library');assert.equal(S.proj,'STD');assert.equal(overlay.hidden,true);assert.equal(mutations.length,1);
""")

    def test_closed_workspace_dialog_does_not_reopen_after_late_success(self):
        self.run_js(r"""
await vLibrary();libraryWorkspace(LIB.view,'derive','a'.repeat(32));$('#libDerivedKey').value='NEW';$('#libDerivedName').value='新项目';const pending=later();postHandler=()=>pending.promise;const work=submit('#libWorkspaceForm');closeModal();modal('<div id="otherDialog">另一个对话框</div>');pending.resolve({project:{key:'NEW',name:'新项目'},commit:'b'.repeat(40)});await work;assert.equal($('#otherDialog').textContent,'另一个对话框');assert.equal(S.proj,'APP');assert.equal(selectorsPainted,0);
""")

    def test_successful_derivation_keeps_receipt_when_project_list_refresh_fails(self):
        self.run_js(r"""
await vLibrary();libraryWorkspace(LIB.view,'derive','a'.repeat(32));$('#libDerivedKey').value='NEW';$('#libDerivedName').value='新项目';postHandler=async()=>({project:{key:'NEW',name:'新项目'},commit:'b'.repeat(40)});getHandler=url=>{if(url==='/api/projects')throw Error('列表读取失败');return currentData};
await submit('#libWorkspaceForm');assert.ok($('#libWorkspaceDialog').innerHTML.includes('客户项目已创建'));assert.ok($('#libWorkspaceRefresh').textContent.includes('列表读取失败'));assert.equal($('#libWorkspaceForm'),null,'successful mutation cannot be retried by submitting a stale form');assert.ok(S.projects.some(p=>p.key==='NEW'));assert.equal(mutations.length,1);
""")

    def test_reopened_registration_is_enabled_after_previous_request_finishes(self):
        self.run_js(r"""
location.hash='#/settings';libraryRegisterProject();$('#pr').value='/tmp/source';$('#pk').value='FIRST';const pending=later();postHandler=()=>pending.promise;const registration=submit('#libRegisterForm');closeModal();libraryRegisterProject();assert.equal($('#pa').disabled,true);$('#pr').value='/tmp/other';$('#pk').value='SECOND';pending.resolve({key:'FIRST',name:'先前项目'});await registration;
assert.equal($('#pa').disabled,false);assert.equal($('#pk').value,'SECOND');assert.equal(S.proj,'APP');assert.equal(location.hash,'#/settings');assert.equal(overlay.hidden,false);
""")

    def test_failed_new_search_does_not_present_old_matches_as_new_query_results(self):
        self.run_js(r"""
await vLibrary();getHandler=()=>searchResults([resultItem()]);$('#libQuery').value='旧查询';await submit('#libSearchForm');assert.ok($('#libResults').innerHTML.includes('STD'));
getHandler=()=>{throw Error('搜索暂不可用')};$('#libQuery').value='新查询';await submit('#libSearchForm');assert.equal($('#libResults').innerHTML,'');assert.ok($('#libSearchStatus').textContent.includes('搜索暂不可用'));assert.equal($('#libQuery').value,'新查询');assert.equal($('#libSearchGo').disabled,false);
""")


if __name__ == "__main__":
    unittest.main()
