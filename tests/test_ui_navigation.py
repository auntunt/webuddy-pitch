"""Current navigation follows management routes without changing project tabs."""
import shutil
import subprocess
import unittest

from tmh.platform.ui_work import WORK_JS


@unittest.skipUnless(shutil.which('node'), 'Node.js is needed for navigation checks')
class NavigationTests(unittest.TestCase):
    def test_primary_and_management_routes_have_one_current_link(self):
        source = WORK_JS.split('// ---------- the workbench:', 1)[1]
        source = 'function workIcon' + source.split('function workIcon', 1)[1].split('const STL=', 1)[0]
        harness = r'''
const assert=require('node:assert/strict');
let view='workspace';
const S={meta:{access:{can_manage:true}}},document={activeElement:null};
const nav={dataset:{},innerHTML:'',contains:()=>false};
const $=()=>nav,curView=()=>view;
'''
        checks = r'''
const routes={workspace:'workspace',today:'workspace',tickets:'tasks',t:'tasks',projects:'projects',team:'team',memory:'memory',kb:'memory',deliveries:'deliveries',delivery:'deliveries',clients:'clients',c:'clients',settings:'settings',access:'access'};
for(const [route,current] of Object.entries(routes)){
 view=route;paintNav();
 const selected=[...nav.innerHTML.matchAll(/<a\b[^>]*aria-current="page"[^>]*>/g)];
 assert.equal(selected.length,1,route+' must have exactly one current link');
 assert.ok(selected[0][0].includes('data-n="'+current+'"'),route+' points to '+current);
 assert.ok(selected[0][0].includes('class="on"'),route+' has visible selected styling');
}
assert.equal(navOf('settings'),'projects','existing project tab grouping is unchanged');
S.meta.access.can_manage=false;view='settings';paintNav();
assert.ok(!nav.innerHTML.includes('href="#/access"'),'admin entry remains permission gated');
assert.ok(nav.innerHTML.includes('href="#/settings" class="on"'),'settings stays current');
'''
        result = subprocess.run(['node', '-e', harness + source + checks], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
