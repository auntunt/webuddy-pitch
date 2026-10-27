import json
from pathlib import Path
import tempfile
import threading
import unittest

from tmh.platform.store import Store


class ProjectRunRegistrationTest(unittest.TestCase):
    def test_two_connections_cannot_register_two_member_runs_for_one_ticket(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);db=root/'platform.db';first=Store(db);second=Store(db)
            self.addCleanup(first.db.close);self.addCleanup(second.db.close)
            (root/'source').mkdir()
            project=first.add_project('ALPHA','alpha',str(root/'source'))
            ticket=first.create_ticket(project['id'],'task','alice')
            first.x('UPDATE tickets SET links=? WHERE id=?',(json.dumps({'hold':True}),ticket['id']))
            barrier=threading.Barrier(2);success=[];errors=[];markers=[]
            def register(store):
                barrier.wait()
                try:
                    run=store.create_run(project['id'],ticket['id'],'codex','fix','alice','task',
                        expected_root=project['root'],require_idle_ticket=True,before_commit=markers.append)
                    success.append(run['id'])
                except ValueError as exc:errors.append(str(exc))
            workers=[threading.Thread(target=register,args=(store,)) for store in (first,second)]
            for worker in workers:worker.start()
            for worker in workers:worker.join(5)
            self.assertTrue(all(not worker.is_alive() for worker in workers))
            self.assertEqual(len(success),1)
            self.assertEqual(len(errors),1)
            self.assertEqual(markers,success)
            self.assertEqual(len(first.q('SELECT id FROM runs WHERE ticket_id=?',(ticket['id'],))),1)

    def test_marker_failure_rolls_back_run(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);store=Store(root/'platform.db');self.addCleanup(store.db.close)
            (root/'source').mkdir()
            project=store.add_project('ALPHA','alpha',str(root/'source'))
            ticket=store.create_ticket(project['id'],'task','alice')
            store.x('UPDATE tickets SET links=? WHERE id=?',(json.dumps({'hold':True}),ticket['id']))
            def fail(rid):raise OSError('synthetic marker failure')
            with self.assertRaises(OSError):
                store.create_run(project['id'],ticket['id'],'codex','fix','alice','task',
                                 require_idle_ticket=True,before_commit=fail)
            self.assertEqual(store.q('SELECT id FROM runs WHERE ticket_id=?',(ticket['id'],)),[])


if __name__=='__main__':unittest.main()
