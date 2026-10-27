"""Execute the real selection helpers; an old saved agent cannot bypass a route."""
import shutil
import subprocess
import unittest

from tmh.platform.ui import JS


@unittest.skipUnless(shutil.which('node'), 'Node.js is needed for UI behavior checks')
class AgentRouteUITest(unittest.TestCase):
    def test_ticket_agent_choice_is_scoped_to_person_tenant_and_project(self):
        helpers = JS.split('function projectAgents(', 1)[1].split('function newTicket(', 1)[0]
        source = r'''
const assert=require('node:assert/strict');
const h=x=>String(x);
const values=new Map([['tmh.agent','agent-a']]);
const localStorage={getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value)};
const S={proj:'A',projects:[
 {key:'A',agent_route:{agent:'agent-a',allowed_agents:['agent-a','agent-b']}},
 {key:'B',agent_route:{agent:'agent-b',allowed_agents:['agent-a','agent-b']}}
],meta:{user:'alice',access:{tenant:{id:'tenant-1'}},agents:[
 {name:'agent-a',title:'Agent A',available:true},{name:'agent-b',title:'Agent B',available:true}
]}};
''' + 'function projectAgents(' + helpers + r'''
assert.equal(selectedProjectAgent('A'),'agent-a');
assert.equal(selectedProjectAgent('B'),'agent-b','legacy global preference cannot override another project route');
assert.match(agentOptions('B'),/value="agent-b" selected/);
saveProjectAgent('A','agent-b');
assert.equal(selectedProjectAgent('A'),'agent-b','explicit project choice is retained');
assert.equal(selectedProjectAgent('B'),'agent-b','other project retains its route');
saveProjectAgent('B','agent-a');
assert.equal(selectedProjectAgent('B'),'agent-a');
assert.equal(selectedProjectAgent('A'),'agent-b','returning to the first project restores its choice');
S.meta.user='bob';
assert.equal(selectedProjectAgent('A'),'agent-a','another person gets the project default');
S.meta.user='alice';S.meta.access.tenant.id='tenant-2';
assert.equal(selectedProjectAgent('A'),'agent-a','another tenant gets the project default');
S.meta.access.tenant.id='tenant-1';
S.projects[0].agent_route.allowed_agents=['agent-a'];
assert.equal(selectedProjectAgent('A'),'agent-a','a saved choice cannot bypass a changed allowlist');
'''
        result = subprocess.run(['node', '-e', source], text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("saveProjectAgent(d.project.key,e.target.value)", JS)
        self.assertIn("run(m,$('#ag')?.value||defAgent(),'auto')", JS)

    def test_project_choices_saved_preferences_and_unavailable_route(self):
        helpers = JS.split('function projectAgents(', 1)[1].split('function newTicket(', 1)[0]
        source = r'''
const assert=require('node:assert/strict');
const h=x=>String(x);
const S={proj:'PPTAUTO',projects:[{key:'PPTAUTO',agent_route:{agent:'cloudwave-codex',allowed_agents:['cloudwave-codex']}},{key:'OTHER'}],meta:{agents:[{name:'claude',title:'Claude',available:true},{name:'codex',title:'Codex',available:true},{name:'cloudwave-codex',title:'Cloudwave Codex',available:true}]}};
''' + 'function projectAgents(' + helpers + r'''
assert.deepEqual(projectAgents().map(a=>a.name),['cloudwave-codex']);
assert.equal(preferredAgent('PPTAUTO','claude'),'cloudwave-codex');
assert.match(agentOptions(),/cloudwave-codex.*selected/);
assert.doesNotMatch(agentOptions(),/value="claude"/);
assert.deepEqual(projectAgents('OTHER').map(a=>a.name),['claude','codex','cloudwave-codex']);
assert.equal(preferredAgent('OTHER','codex'),'codex');
S.meta.agents[2].available=false;
assert.equal(preferredAgent(),'cloudwave-codex');
assert.match(agentOptions(),/本机未安装/);
delete S.projects[0].agent_route.allowed_agents;
S.meta.agents.pop();
assert.equal(preferredAgent(),'cloudwave-codex');
assert.equal(preferredAgent('PPTAUTO','claude'),'cloudwave-codex');
assert.equal(projectAgents()[0].available,false);
assert.match(agentOptions(),/value="cloudwave-codex" selected/);
assert.match(agentOptions(),/配置不可用/);
assert.equal(S.meta.agents.length,2);
S.projects[0].agent_route_error='配置损坏';
assert.deepEqual(projectAgents(),[]);
assert.equal(preferredAgent(),'');
assert.equal(S.meta.agents[0].name,'claude');
console.log('project route UI behavior passed');
'''
        result = subprocess.run(['node', '-e', source], text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_assistant_header_keeps_unavailable_route_and_scopes_explicit_choice(self):
        helpers = JS.split('function projectAgents(', 1)[1].split('function newTicket(', 1)[0]
        paint_head = JS.split('  paintHead(){', 1)[1].split('  setMode(', 1)[0]
        source = r'''
const assert=require('node:assert/strict');
const h=x=>String(x);
const S={proj:'ROUTED',projects:[],meta:{agents:[]}};
const saved=new Map();
const ls={get:key=>saved.get(key)||null,set:(key,value)=>value==null?saved.delete(key):saved.set(key,value)};
const elements=new Map();
const $=selector=>{if(!elements.has(selector))elements.set(selector,{hidden:true});return elements.get(selector)};
const document={querySelectorAll:()=>[]};
let modelAgent;
const modelSel=(id,agent,mode)=>{assert.equal(id,'astModel');assert.equal(mode,'ask');modelAgent=agent;return ''};
const bindModel=id=>assert.equal(id,'astModel');
Object.defineProperty($('#astHead'),'innerHTML',{set(html){
  // Recreate the select each render, as the browser does after innerHTML changes.
  const select=html.match(/<select id="astAgent"[^>]*>([\s\S]*?)<\/select>/);
  assert.ok(select,'the real header must render the agent selector');
  const options=[...select[1].matchAll(/<option value="([^"]*)"([^>]*)>([^<]*)<\/option>/g)];
  const selected=options.filter(option=>/\bselected\b/.test(option[2]));
  assert.equal(selected.length,1,'the header must select exactly one agent explicitly');
  elements.set('#astAgent',{value:selected[0][1],options});
}});
''' + 'function projectAgents(' + helpers + r'''
const A={open:true,sess:null,hist:false,view:null,paintCtx(){},paintMode(){},
  paintHead(){''' + paint_head + r'''
};
const selected=()=>{assert.equal(modelAgent,$('#astAgent').value);return $('#astAgent').value};
for(const unavailable of ['missing','installed-but-unavailable']){
  for(const allowlist of [undefined,['cloudwave-codex','claude','codex']]){
    const route={agent:'cloudwave-codex'};
    if(allowlist)route.allowed_agents=allowlist;
    S.projects=[{key:'ROUTED',agent_route:{...route}},{key:'NEXT',agent_route:{...route}},{key:'PLAIN'}];
    S.meta.agents=[{name:'claude',title:'Claude',available:true},{name:'codex',title:'Codex',available:true}];
    if(unavailable==='installed-but-unavailable')S.meta.agents.push({name:'cloudwave-codex',title:'Cloudwave Codex',available:false});
    saved.set('tmh.astAgent','claude');
    delete A.agentChoices;
    S.proj='ROUTED';
    A.paintHead();
    assert.equal(selected(),'cloudwave-codex',unavailable+' must not fall back to the old global preference');
    assert.match($('#astAgent').options.find(option=>option[1]==='cloudwave-codex')[3],/未安装/);
    assert.equal(saved.get('tmh.astAgent'),'claude','painting must not rewrite a global preference');

    $('#astAgent').onchange({target:{value:'claude'}});
    assert.equal(selected(),'claude','an allowed manual choice must survive the onchange repaint');
    assert.equal(A.agentChoices.ROUTED,'claude');
    assert.equal($('#astMoreM').hidden,false);
    A.paintHead();
    assert.equal(selected(),'claude','later repaint must preserve this project choice');

    S.proj='NEXT';
    A.paintHead();
    assert.equal(selected(),'cloudwave-codex','another project must use its own route');
    assert.equal(A.agentChoices.NEXT,undefined);
    S.proj='ROUTED';
    A.paintHead();
    assert.equal(selected(),'claude','returning to the original project restores its manual choice');

    S.proj='PLAIN';
    saved.delete('tmh.astAgent');
    A.paintHead();
    assert.equal(selected(),'codex','an ordinary project still defaults to Codex');
    saved.set('tmh.astAgent','claude');
    A.paintHead();
    assert.equal(selected(),'claude','an ordinary project still honors its legacy global preference');
  }
}
console.log('actual assistant header route behavior passed');
'''
        result = subprocess.run(['node', '-e', source], text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('actual assistant header route behavior passed', result.stdout)


if __name__ == '__main__':
    unittest.main()
