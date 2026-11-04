"""China display and server cursors must not depend on the browser's timezone."""
import os
import shutil
import subprocess
import unittest
from tmh.platform.ui import JS
from tmh.platform.ui_time import TIME_JS
from tmh.platform.ui_work import WORK_JS

@unittest.skipUnless(shutil.which('node'), 'Node required')
class ChinaTimeTest(unittest.TestCase):
    def test_offsets_day_boundary_and_relative_time_in_three_browser_zones(self):
        ago=JS[JS.index('const ago='):JS.index('function stopPolls')]
        now=WORK_JS[WORK_JS.index('function nowStr('):WORK_JS.index('\n',WORK_JS.index('function nowStr('))]
        script="const assert=require('node:assert/strict');const S={meta:{timestamp_offset:'+00:00'}};\n"+TIME_JS+ago+now+r'''
const instant=new Date('2026-11-04T18:39:52Z');
assert.equal(chinaTime('2026-11-04 18:39:52'),'2026-11-05 02:39:52');
assert.equal(chinaTime('2026-11-05T02:39:52+08:00'),'2026-11-05 02:39:52');
assert.equal(chinaTime(instant),'2026-11-05 02:39:52');
assert.equal(chinaTime('2026-11-05'),'2026-11-05');
assert.equal(chinaTime('时间未知'),'时间未知');assert.equal(chinaTime(7),7);
assert.equal(chinaTime(''), '');assert.equal(chinaTime(null), '');
assert.equal(nowStr(instant),'2026-11-04 18:39:52');
Date.now=()=>instant.getTime()+5*60000;
assert.equal(ago('2026-11-04 18:39:52'),'5 分钟前');
S.meta.timestamp_offset='+08:00';
assert.equal(chinaTime('2026-11-05 02:39:52'),'2026-11-05 02:39:52');
assert.equal(nowStr(instant),'2026-11-05 02:39:52');
assert.equal(ago('2026-11-05 02:39:52'),'5 分钟前');
'''
        for zone in ('UTC','Asia/Shanghai','America/Los_Angeles'):
            with self.subTest(zone=zone):
                result=subprocess.run(['node','-'],input=script,text=True,capture_output=True,env=dict(os.environ,TZ=zone))
                self.assertEqual(result.returncode,0,result.stderr)

    def test_daily_counts_use_china_midnight_without_rewriting_records(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from tmh.platform.store import Store
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'platform.db')
            self.addCleanup(store.db.close)
            p=store.add_project('APP','Fixture',folder)
            t=store.create_ticket(p['id'],'Fixture','person')
            store.x("UPDATE tickets SET created=?,updated=?,status='closed' WHERE id=?",('2026-11-04 18:39:52','2026-11-04 19:00:00',t['id']))
            with patch('tmh.platform.store.timestamp_offset',return_value='+00:00'):
                stats=store.stats(p['id'])
            self.assertEqual(stats['created_by_day'],[['2026-11-05',1]])
            self.assertEqual(stats['closed_by_day'],[['2026-11-05',1]])
            self.assertEqual(store.ticket(t['id'])['created'],'2026-11-04 18:39:52')

    def test_month_filter_uses_china_calendar(self):
        from unittest.mock import patch
        from tmh.platform import metrics
        with patch.object(metrics, '_t', return_value=1793467800):
            # 2026-10-31 17:30 UTC is November in China.
            self.assertTrue(metrics._in('2026-10-31 17:30:00','2026-11'))
            self.assertFalse(metrics._in('2026-10-31 17:30:00','2026-10'))
