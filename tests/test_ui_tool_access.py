"""Run the shipped personal-tool page JavaScript and parse its real CLI guide."""
import json
import re
import shlex
import shutil
import subprocess
import unittest

from tests.test_ui_library import HARNESS
from tmh.platform.ui_tool_access import page
from tmh.workbench import parser


DOM = HARNESS.split('const main=new Element()', 1)[0].replace('const h=', 'const escapeHtml=').replace('this._html=h(value)', 'this._html=escapeHtml(value)')
SETUP = r'''
const root=new Element();root.connected=true;
const originalQuery=Element.prototype.querySelectorAll;
Element.prototype.querySelectorAll=function(selector){const checked=selector.endsWith(':checked');selector=selector.replace(/:checked$/,'').replace(/\[name=([^"\]]+)\]/g,'[name="$1"]');return originalQuery.call(this,selector).filter(n=>!checked||n.checked)};
Element.prototype.replaceChildren=function(){this.innerHTML=''};
Element.prototype.click=function(){return this.fire('click')};
const document={querySelector:s=>root.querySelector(s),querySelectorAll:s=>root.querySelectorAll(s),createElement:tag=>new Element(tag)};
const watches=[];const setInterval=(fn,ms)=>{watches.push({fn,ms});return watches.length};const clearInterval=()=>{};
const events=new Map();document.addEventListener=(name,fn)=>events.set('document:'+name,fn);const window={addEventListener:(name,fn)=>events.set(name,fn)};
const location={pathname:'/t/alpha/tools',origin:'https://synthetic.invalid'};
const values=new Map();let failRead=false,failWrite=false,failRemove=false;
const sessionStorage={getItem:k=>{if(failRead)throw Error('synthetic storage read');return values.get(k)??null},setItem:(k,v)=>{if(failWrite)throw Error('synthetic storage write');values.set(k,String(v))},removeItem:k=>{if(failRemove)throw Error('synthetic storage remove');values.delete(k)}};
const crypto=require('node:crypto').webcrypto;
const blobs=[];URL.createObjectURL=blob=>{blobs.push(blob);return 'blob:synthetic'};URL.revokeObjectURL=()=>{};
const later=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return{promise,resolve,reject}};
const tick=()=>new Promise(r=>setImmediate(r));
let signedUser='alice',authContext='context-alice',signedTenant='alpha';
const meta=()=>({access:{user:signedUser,context_token:authContext,tenant:{id:signedTenant}}});
const records=[];
const directory=()=>({user:signedUser,context_token:authContext,projects:[{id:1,key:'APP',name:'Allowed project',role:'contributor'}],connections:records.slice()});
let getMeta=()=>meta(),getList=()=>directory(),postHandler;
const requests=[],mutations=[];
globalThis.fetch=async(path,options)=>{requests.push({path,method:options.method});if(options.method==='POST'){const body=JSON.parse(options.body);mutations.push(body);const value=await postHandler(body);return value?.httpResponse?value:{ok:true,status:200,json:async()=>value}}const value=await(path.endsWith('/api/meta')?getMeta():getList());return value?.httpResponse?value:{ok:true,status:200,json:async()=>value}};
const connection=(body,extra={})=>({id:'a'.repeat(32),user:'alice',tenant:'alpha',scope:body.scope||'read',project_ids:body.project_ids||[1],label:body.label||'Personal tool',expires_at:2000000000,status:'active',active:true,...extra});
const body=()=>({action:'create',label:'Personal tool',project_ids:[1],scope:'read',expires_days:7,request_id:'fixed-request'});
const success=(b,extra={})=>{const result={connection:connection(b),connection_id:'a'.repeat(32),token:'wbt_'+'a'.repeat(32)+'.'+'s'.repeat(43),replayed:false,...extra};const index=records.findIndex(row=>row.id===result.connection.id);if(index<0)records.push({...result.connection});else records[index]={...result.connection};return result};
postHandler=b=>success(b);
'''


@unittest.skipUnless(shutil.which('node'), 'Node.js is needed for shipped tool UI behavior')
class ToolAccessUiTest(unittest.TestCase):
    def run_js(self, checks, setup=''):
        html = page()
        script = html.split('<script>', 1)[1].split('</script>', 1)[0]
        body_html = html.split('<body>', 1)[1].split('<script>', 1)[0]
        source = DOM + SETUP + '\nroot.innerHTML=' + json.dumps(body_html) + ';\n' + setup + '\n' + script
        source += '\n(async()=>{await tick();await tick();\n' + checks + '\n})().catch(error=>{console.error(error);process.exitCode=1});'
        result = subprocess.run([shutil.which('node'), '-'], input=source, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_page_script_and_cli_guide_parse_with_shipped_parser(self):
        html = page()
        script = html.split('<script>')[1].split('</script>')[0]
        parsed = subprocess.run([shutil.which('node'), '--check'], input=script, text=True, capture_output=True)
        self.assertEqual(parsed.returncode, 0, parsed.stderr)
        result = self.run_js("await start(body());process.stdout.write($('#guide').textContent);")
        lines = [line for line in result.splitlines() if line.startswith('webuddy ')]
        self.assertEqual(len(lines), 2)
        for line in lines:
            args = shlex.split(line.split(' < ', 1)[0])[1:]
            parser().parse_args(args)
        self.assertIn('--stdin', lines[0])
        self.assertIn('mkdir -p ~/.config/webuddy', result)

    def test_unknown_result_retries_exact_original_request_after_refresh(self):
        self.run_js("postHandler=()=>{throw Error('response lost')};await start(body());assert.equal(mutations.length,1);const original=JSON.stringify(mutations[0]);await load();postHandler=b=>success(b,{token:undefined,replayed:true,credential_unavailable:true});await $('#retry').fire('click');assert.equal(mutations.length,2);assert.equal(JSON.stringify(mutations[1]),original);assert.equal(pending,null);assert.equal(values.size,0);assert.ok($('#notice').textContent.includes('不会再次显示'));assert.equal(credential,null);")

    def test_get_failure_after_success_blocks_new_post_even_after_secret_dismissed(self):
        self.run_js("getList=()=>{throw Error('listing unavailable')};await start(body());assert.equal(credential,null);assert.ok($('#notice').textContent.includes('刷新'));await $('#dismiss').fire('click');await start({...body(),request_id:'would-duplicate'});assert.equal(mutations.length,1);assert.equal($('#submit').disabled,true);assert.ok(pending);getList=()=>directory();await load();assert.equal($('#submit').disabled,true);postHandler=b=>success(b,{token:undefined,replayed:true,credential_unavailable:true});await $('#retry').fire('click');assert.equal(mutations.length,2);assert.deepEqual(mutations[1],mutations[0]);assert.equal(credential,null);assert.equal($('#submit').disabled,false);")

    def test_failed_initial_storage_read_blocks_new_write(self):
        self.run_js("assert.equal($('#submit').disabled,true);await start(body());assert.equal(mutations.length,0);assert.equal(credential,null);failRead=false;await load();await start(body());assert.equal(mutations.length,1);", setup='failRead=true;')

    def test_failed_storage_write_prevents_post_and_preserves_original_in_memory(self):
        self.run_js("failWrite=true;await start(body());assert.equal(mutations.length,0);assert.ok(pending);const original=JSON.stringify(pending);await start({...body(),request_id:'other'});assert.equal(JSON.stringify(pending),original);failWrite=false;await $('#retry').fire('click');assert.equal(mutations.length,1);assert.equal(JSON.stringify(mutations[0]),original);")

    def test_failed_cleanup_retains_only_original_pending_and_never_secret_in_storage(self):
        self.run_js("failRemove=true;await start(body());assert.equal(mutations.length,1);assert.ok(pending);assert.ok(credential);assert.ok([...values.values()].every(v=>!v.includes('wbt_')));await $('#dismiss').fire('click');await start({...body(),request_id:'new'});assert.equal(mutations.length,1);failRemove=false;postHandler=b=>success(b,{token:undefined,replayed:true,credential_unavailable:true});await $('#retry').fire('click');assert.equal(mutations.length,2);assert.equal(mutations[1].request_id,'fixed-request');assert.equal(pending,null);")

    def test_corrupt_pending_storage_is_not_discarded_or_overwritten(self):
        self.run_js("assert.equal($('#submit').disabled,true);await start(body());assert.equal(mutations.length,0);assert.equal([...values.values()][0],'{broken');", setup="values.set('webuddy.tool.pending:'+JSON.stringify(['/t/alpha','alice']),'{broken');")

    def test_post_secret_is_not_shown_when_account_changes_before_readback(self):
        self.run_js("postHandler=b=>{signedUser='bob';authContext='context-bob';return success(b)};await start(body());assert.equal(credential,null);assert.equal($('#credential').value,'');assert.equal($('#secret').hidden,true);assert.equal($('#projects').textContent,'');assert.equal($('#connections').textContent,'');assert.equal($('#submit').disabled,true);")

    def test_late_response_after_lock_cannot_repopulate_secret_or_private_dom(self):
        self.run_js("const delayed=later();postHandler=()=>delayed.promise;const writing=start(body());await tick();lock('身份变化');delayed.resolve(success(body()));await writing;assert.equal(credential,null);assert.equal($('#credential').value,'');assert.equal($('#connections').textContent,'');assert.equal($('#submit').disabled,true);")

    def test_pagehide_or_tenant_navigation_discards_late_success(self):
        self.run_js("const delayed=later();postHandler=()=>delayed.promise;const writing=start(body());await tick();events.get('pagehide')();delayed.resolve(success(body()));await writing;assert.equal(credential,null);assert.equal($('#credential').value,'');assert.equal($('#submit').disabled,true);")
        self.run_js("const delayed=later();postHandler=()=>delayed.promise;const writing=start(body());await tick();location.pathname='/t/beta/tools';delayed.resolve(success(body()));await writing;assert.equal(credential,null);assert.equal($('#connections').textContent,'');assert.equal($('#submit').disabled,true);")

    def test_wrong_owner_or_partial_receipt_never_shows_secret_and_keeps_pending(self):
        self.run_js("postHandler=b=>success(b,{connection:connection(b,{user:'bob'})});await start(body());assert.equal(credential,null);assert.ok(pending);assert.equal(mutations.length,1);assert.equal($('#submit').disabled,true);")
        self.run_js("postHandler=()=>({ok:true});await start(body());assert.equal(credential,null);assert.ok(pending);assert.equal($('#submit').disabled,true);")

    def test_visible_secret_revoke_action_explains_required_step(self):
        self.run_js("await start(body());assert.ok(credential);await start({action:'revoke',connection_id:'a'.repeat(32),request_id:'revoke-visible'});assert.equal(mutations.length,1);assert.ok($('#notice').textContent.includes('清除'));assert.ok($('#notice').textContent.includes('凭据'));")

    def test_secret_stays_only_in_memory_dom_and_explicit_download(self):
        self.run_js("await start(body());assert.ok(credential);assert.equal(values.size,0);assert.ok($('#credential').value.includes('wbt_'));await $('#download').fire('click');assert.equal(blobs.length,1);assert.ok((await blobs[0].text()).includes('wbt_'));await $('#dismiss').fire('click');assert.equal(credential,null);assert.equal($('#credential').value,'');assert.equal($('#guide').textContent,'');assert.equal($('#secret').hidden,true);")

    def test_dismiss_reports_clear_and_preserves_pending_or_refresh_warnings(self):
        self.run_js("await start(body());await $('#dismiss').fire('click');assert.equal($('#notice').textContent,'页面凭据已清除。可在列表管理连接。');assert.equal($('#notice').className,'');assert.equal(credential,null);assert.equal($('#credential').value,'');")
        self.run_js("failRemove=true;await start(body());const warning=$('#notice').textContent;assert.ok(warning.includes('未能清除重试记录'));await $('#dismiss').fire('click');assert.equal($('#notice').textContent,warning);assert.equal($('#notice').className,'error');assert.ok(pending);assert.equal(credential,null);")
        self.run_js("getList=()=>{throw Error('listing unavailable')};await start(body());const warning=$('#notice').textContent;assert.ok(warning.includes('刷新'));await $('#dismiss').fire('click');assert.equal($('#notice').textContent,warning);assert.equal($('#submit').disabled,true);assert.equal(credential,null);")

    def test_post_secret_waits_for_final_identity_and_list_readback(self):
        self.run_js("const delayed=later();getList=()=>delayed.promise;const writing=start(body());await tick();assert.equal(credential,null);assert.equal($('#credential').value,'');await $('#download').fire('click');assert.equal(blobs.length,0);delayed.resolve(directory());await writing;assert.ok(credential);await $('#dismiss').fire('click');assert.equal($('#notice').textContent,'页面凭据已清除。可在列表管理连接。');")

    def test_browser_reload_restores_original_body_without_new_request(self):
        self.run_js("assert.ok(pending);assert.equal(pending.request_id,'fixed-request');assert.equal($('#submit').disabled,true);await start({...body(),request_id:'other'});assert.equal(mutations.length,0);postHandler=b=>success(b,{token:undefined,replayed:true,credential_unavailable:true});await $('#retry').fire('click');assert.equal(mutations.length,1);assert.deepEqual(mutations[0],body());assert.equal(pending,null);", setup="values.set('webuddy.tool.pending:'+JSON.stringify(['/t/alpha','alice']),JSON.stringify(body()));")

    def test_original_pending_is_isolated_by_person_and_tenant(self):
        self.run_js("assert.equal(pending,null);assert.equal(values.size,2);assert.equal($('#submit').disabled,false);", setup="values.set('webuddy.tool.pending:'+JSON.stringify(['/t/alpha','bob']),JSON.stringify(body()));values.set('webuddy.tool.pending:'+JSON.stringify(['/t/beta','alice']),JSON.stringify(body()));")

    def test_silent_storage_failure_and_write_then_throw_never_post(self):
        self.run_js("sessionStorage.setItem=()=>{};await start(body());assert.equal(mutations.length,0);assert.ok(pending);assert.equal($('#submit').disabled,true);")
        self.run_js("const save=sessionStorage.setItem;sessionStorage.setItem=(k,v)=>{save(k,v);throw Error('write reported failure')};await start(body());assert.equal(mutations.length,0);assert.equal(values.size,1);sessionStorage.setItem=save;await $('#retry').fire('click');assert.equal(mutations.length,1);assert.deepEqual(mutations[0],body());")
        self.run_js("sessionStorage.removeItem=()=>{};await start(body());assert.ok(pending);assert.ok(credential);await $('#dismiss').fire('click');await start({...body(),request_id:'new'});assert.equal(mutations.length,1);")

    def test_storage_read_failure_during_cleanup_preserves_original_request(self):
        self.run_js("const remove=sessionStorage.removeItem;sessionStorage.removeItem=k=>{remove(k);failRead=true};await start(body());assert.ok(pending);assert.ok(credential);await $('#dismiss').fire('click');await start({...body(),request_id:'new'});assert.equal(mutations.length,1);failRead=false;sessionStorage.removeItem=remove;postHandler=b=>success(b,{token:undefined,replayed:true,credential_unavailable:true});await $('#retry').fire('click');assert.equal(mutations.length,2);assert.deepEqual(mutations[1],body());")

    def test_late_get_and_late_json_cannot_repopulate_after_identity_lock(self):
        self.run_js("const delayed=later();getList=()=>delayed.promise;const reading=load();await tick();lock('账号变化');delayed.resolve(directory());await reading;assert.equal($('#connections').textContent,'');assert.equal($('#identity').textContent,'');assert.equal($('#submit').disabled,true);")
        self.run_js("const delayed=later();postHandler=()=>({httpResponse:true,ok:true,status:200,json:()=>delayed.promise});const writing=start(body());await tick();events.get('pagehide')();delayed.resolve(success(body()));await writing;assert.equal(credential,null);assert.equal($('#submit').disabled,true);")

    def test_pending_refresh_and_double_submit_cannot_create_twice(self):
        self.run_js("const delayed=later();getList=()=>delayed.promise;const reading=load();await tick();await start(body());assert.equal(mutations.length,0);delayed.resolve(directory());await reading;const reply=later();postHandler=()=>reply.promise;const first=start(body());await tick();await start({...body(),request_id:'another'});assert.equal(mutations.length,1);reply.resolve(success(body()));await first;assert.equal(mutations.length,1);")

    def test_focus_checks_real_identity_and_clears_secret_after_account_change(self):
        self.run_js("await start(body());assert.ok(credential);signedUser='bob';authContext='bob-context';await events.get('focus')();assert.equal(credential,null);assert.equal($('#credential').value,'');assert.equal($('#connections').textContent,'');assert.equal($('#projects').textContent,'');assert.equal($('#identity').textContent,'');assert.equal($('#submit').disabled,true);assert.equal(watches[0].ms,15000);")

    def test_focus_identity_barrier_clears_secret_before_response_and_failed_check_cannot_download(self):
        self.run_js("await start(body());assert.ok(credential);signedUser='bob';authContext='bob-context';const delayed=later();getMeta=()=>delayed.promise;const checking=events.get('focus')();assert.equal(credential,null);assert.equal($('#credential').value,'');assert.equal($('#secret').hidden,true);await $('#download').fire('click');assert.equal(blobs.length,0);delayed.reject(Error('identity unavailable'));await checking;await $('#download').fire('click');assert.equal(blobs.length,0);assert.equal(credential,null);assert.equal(ready,false);")

    def test_focus_during_pending_post_prevents_late_secret_from_reappearing(self):
        self.run_js("const delayed=later();postHandler=()=>delayed.promise;const writing=start(body());await tick();assert.equal(mutations.length,1);await events.get('focus')();delayed.resolve(success(body()));await writing;assert.equal(credential,null);assert.equal($('#credential').value,'');await $('#download').fire('click');assert.equal(blobs.length,0);assert.ok($('#notice').textContent.includes('重新创建'));")

    def test_periodic_check_and_refresh_clear_old_secret_synchronously(self):
        self.run_js("await start(body());const delayed=later();getMeta=()=>delayed.promise;const checking=watches[0].fn();assert.equal(credential,null);assert.equal($('#credential').value,'');delayed.resolve(meta());await checking;assert.equal(credential,null);assert.ok($('#notice').textContent.includes('重新创建'));")
        self.run_js("await start(body());const delayed=later();getMeta=()=>delayed.promise;const reading=load();assert.equal(credential,null);assert.equal($('#credential').value,'');await $('#download').fire('click');assert.equal(blobs.length,0);delayed.resolve(meta());await reading;assert.equal(credential,null);")

    def test_blur_and_hidden_clear_secret_without_discarding_original_pending(self):
        self.run_js("failRemove=true;await start(body());assert.ok(credential);const original=JSON.stringify(pending);events.get('blur')();assert.equal(credential,null);assert.equal($('#credential').value,'');assert.equal(JSON.stringify(pending),original);assert.equal(values.size,1);await $('#download').fire('click');assert.equal(blobs.length,0);")
        self.run_js("await start(body());document.hidden=true;events.get('document:visibilitychange')();assert.equal(credential,null);assert.equal($('#secret').hidden,true);await $('#download').fire('click');assert.equal(blobs.length,0);")

    def test_latest_identity_barrier_prevents_late_post_secret_display(self):
        self.run_js("const delayed=later();let reads=0;getMeta=()=>{reads++;return reads===3?delayed.promise:meta()};const writing=start(body());await tick();assert.equal(credential,null);assert.ok(pending);signedUser='bob';authContext='bob-context';delayed.resolve(meta());await writing;assert.equal(credential,null);assert.equal($('#credential').value,'');assert.equal(locked,true);assert.equal(values.size,1);")

    def test_download_failure_keeps_visible_secret_and_explains_recovery(self):
        self.run_js("await start(body());URL.createObjectURL=()=>{throw Error('download unavailable')};await $('#download').fire('click');assert.ok(credential);assert.ok($('#credential').value.includes('wbt_'));assert.equal(values.size,0);assert.ok($('#notice').textContent.includes('复制完整凭据'));")

    def test_scope_option_exists_and_private_labels_are_escaped(self):
        self.run_js("$('#scope').value='content';assert.equal($('#scope').value,'content');records.push(connection(body(),{label:'<img src=x onerror=alert(1)>'}));await load();assert.ok($('#connections').innerHTML.includes('&lt;img'));assert.equal(root.all().filter(n=>n.tag==='img').length,0);")

    def test_readonly_project_does_not_submit_content_scope(self):
        self.run_js("getList=()=>({...directory(),projects:[{id:1,key:'APP',name:'Project',role:'viewer'}]});await load();document.querySelector('[name=project]').checked=true;$('#scope').value='content';await $('#create').fire('submit');assert.equal(mutations.length,0);assert.ok($('#notice').textContent.includes('只读项目'));")

    def test_final_list_requires_one_current_active_matching_connection(self):
        rows = {
            'missing': '[]',
            'different_id': "[{...records[0],id:'b'.repeat(32)}]",
            'duplicate': '[records[0],{...records[0]}]',
            'revoked': "[{...records[0],status:'revoked',active:false}]",
            'expired': "[{...records[0],status:'expired',active:false}]",
            'invalidated': "[{...records[0],status:'invalidated',active:false}]",
            'inactive': '[{...records[0],active:false}]',
            'truthy_active': "[{...records[0],active:'true'}]",
            'contradictory_status': "[{...records[0],status:'revoked'}]",
            'other_member': "[{...records[0],user:'bob'}]",
            'other_tenant': "[{...records[0],tenant:'beta'}]",
            'other_scope': "[{...records[0],scope:'content'}]",
            'other_projects': '[{...records[0],project_ids:[2]}]',
            'duplicate_project': '[{...records[0],project_ids:[1,1]}]',
            'string_project': "[{...records[0],project_ids:['1']}]",
            'other_label': "[{...records[0],label:'different'}]",
            'deadline_reached': '[{...records[0],expires_at:Date.now()/1000}]',
            'string_deadline': "[{...records[0],expires_at:'2000000000'}]",
            'missing_deadline': '[{...records[0],expires_at:undefined}]',
            'nonfinite_deadline': '[{...records[0],expires_at:Infinity}]',
            'different_deadline': '[{...records[0],expires_at:records[0].expires_at+1}]',
        }
        for name, expression in rows.items():
            with self.subTest(name=name):
                self.run_js(r'''
const listGate=later(),identityGate=later();let reads=0;
getList=()=>listGate.promise;getMeta=()=>++reads===3?identityGate.promise:meta();
const original=body(),writing=start(original);await tick();
assert.equal(reads,2);assert.equal(records.length,1);assert.equal(credential,null);
await $('#download').fire('click');assert.equal(blobs.length,0);
listGate.resolve({...directory(),connections:ROWS});await tick();
assert.equal(reads,3);assert.equal(credential,null);assert.equal($('#credential').value,'');
await $('#download').fire('click');assert.equal(blobs.length,0);
identityGate.resolve(meta());await writing;
assert.equal(credential,null);assert.equal($('#credential').value,'');assert.equal($('#secret').hidden,true);
await $('#download').fire('click');assert.equal(blobs.length,0);
assert.deepEqual(pending,original);assert.deepEqual(JSON.parse([...values.values()][0]),original);
await start({...body(),request_id:'must-not-duplicate'});assert.equal(mutations.length,1);
'''.replace('ROWS', expression))

    def test_fresh_post_requires_active_unexpired_well_typed_authority(self):
        for extra in ["{status:'revoked',active:false}", "{status:'expired',active:false}",
                      "{status:'invalidated',active:false}", "{active:false}", "{active:'true'}",
                      "{expires_at:Date.now()/1000}", "{expires_at:'2000000000'}",
                      "{expires_at:Infinity}", "{expires_at:undefined}", "{project_ids:['1']}"]:
            with self.subTest(extra=extra):
                self.run_js("postHandler=b=>success(b,{connection:connection(b," + extra + ")});await start(body());assert.equal(credential,null);assert.equal($('#credential').value,'');assert.equal($('#secret').hidden,true);await $('#download').fire('click');assert.equal(blobs.length,0);assert.deepEqual(pending,body());assert.equal(mutations.length,1);")

    def test_matching_final_row_accepts_same_project_set_and_scope(self):
        for scope in ('read', 'content'):
            with self.subTest(scope=scope):
                self.run_js("const original={...body(),scope:" + json.dumps(scope) + ",project_ids:[2,1]};getList=()=>({...directory(),connections:records.map(row=>({...row,project_ids:[1,2]}))});await start(original);assert.ok(credential);assert.equal(pending,null);assert.deepEqual(mutations[0],original);await $('#download').fire('click');assert.equal(blobs.length,1);assert.equal(JSON.parse(await blobs[0].text()).token,credential.token);")

    def test_expiry_crossing_final_identity_barrier_never_displays_secret(self):
        self.run_js(r'''
let now=1900000000000;Date.now=()=>now;
postHandler=b=>success(b,{connection:connection(b,{expires_at:now/1000+1})});
const finalIdentity=later();let reads=0;getMeta=()=>++reads===3?finalIdentity.promise:meta();
const writing=start(body());await tick();assert.equal(reads,3);assert.equal(credential,null);
now+=1000;finalIdentity.resolve(meta());await writing;
assert.equal(credential,null);assert.equal($('#credential').value,'');assert.equal($('#secret').hidden,true);
await $('#download').fire('click');assert.equal(blobs.length,0);assert.deepEqual(pending,body());
''')

    def test_download_rechecks_expiry_and_clears_without_another_request(self):
        self.run_js(r'''
let now=1900000000000;Date.now=()=>now;
postHandler=b=>success(b,{connection:connection(b,{expires_at:now/1000+1})});
await start(body());assert.ok(credential);await $('#download').fire('click');assert.equal(blobs.length,1);
const count=requests.length;now+=1000;await $('#download').fire('click');
assert.equal(requests.length,count);assert.equal(blobs.length,1);assert.equal(credential,null);
assert.equal($('#credential').value,'');assert.equal($('#secret').hidden,true);assert.equal($('#download').disabled,true);
assert.ok($('#notice').textContent.includes('过期'));assert.equal(pending,null);
''')

    def test_unconfirmed_final_row_retries_original_without_showing_replay_secret(self):
        for status in ('active', 'revoked', 'expired', 'invalidated'):
            with self.subTest(status=status):
                self.run_js(r'''
getList=()=>({...directory(),connections:[]});await start(body());
assert.equal(credential,null);assert.deepEqual(pending,body());assert.equal(mutations.length,1);
const original=JSON.stringify(mutations[0]);getList=()=>directory();
postHandler=b=>success(b,{connection:connection(b,{status:STATUS,active:STATUS==='active'}),token:undefined,replayed:true,credential_unavailable:true});
await $('#retry').fire('click');assert.equal(mutations.length,2);assert.equal(JSON.stringify(mutations[1]),original);
assert.equal(pending,null);assert.equal(values.size,0);assert.equal(credential,null);
await $('#download').fire('click');assert.equal(blobs.length,0);assert.ok($('#notice').textContent.includes('不会再次显示'));
'''.replace('STATUS', json.dumps(status)))


if __name__ == '__main__':
    unittest.main()
