"""Reject partial substitutes for actual primary keys and table uniqueness."""
import sqlite3
import unittest

from tmh.platform import learning_experiments as X
from tmh.platform.errors import ApiError


class ExperimentSchemaIntegrityTests(unittest.TestCase):
    def database(self, replacements=(), extra=()):
        db = sqlite3.connect(':memory:');db.row_factory = sqlite3.Row
        self.addCleanup(db.close)
        for statement in X.DDL:
            for old, new in replacements:statement = statement.replace(old, new)
            db.execute(statement)
        for statement in extra:db.execute(statement)
        return db

    def test_partial_same_columns_cannot_replace_each_table_unique_constraint(self):
        cases = [
            ('learning_experiments', 'tenant_id,project_id,creator,request_id'),
            ('learning_experiment_slots', 'experiment_id,ordinal'),
            ('learning_experiment_slots', 'job_id,step_role')]
        for table, cols in cases:
            with self.subTest(table=table, columns=cols):
                db = self.database([(f'UNIQUE({cols})', 'CHECK(1)')],
                    [f'CREATE UNIQUE INDEX false_unique ON {table}({cols}) WHERE 0'])
                before = list(db.iterdump())
                with self.assertRaises(ApiError) as error:X.schema_state(db)
                self.assertEqual(error.exception.code, 409)
                self.assertEqual(list(db.iterdump()), before)

    def test_missing_primary_key_cannot_be_replaced_even_by_full_unique(self):
        cases = [
            ('learning_experiments', 'id', 'id TEXT PRIMARY KEY', 'id TEXT'),
            ('learning_experiment_assets', 'experiment_id,id', 'PRIMARY KEY(experiment_id,id)', 'CHECK(1)'),
            ('learning_experiment_slots', 'experiment_id,id', 'PRIMARY KEY(experiment_id,id)', 'CHECK(1)'),
            ('learning_experiment_events', 'experiment_id,seq', 'PRIMARY KEY(experiment_id,seq)', 'CHECK(1)')]
        for table, cols, old, new in cases:
            for predicate in ('', ' WHERE 0'):
                with self.subTest(table=table, predicate=predicate):
                    # Restrict replacement to its table; assets and slots share a key spelling.
                    statements = tuple(s.replace(old, new) if s.startswith('CREATE TABLE '+table+' ') else s for s in X.DDL)
                    db = sqlite3.connect(':memory:');db.row_factory=sqlite3.Row;self.addCleanup(db.close)
                    for statement in statements:db.execute(statement)
                    db.execute(f'CREATE UNIQUE INDEX false_pk ON {table}({cols})'+predicate)
                    with self.assertRaises(ApiError) as error:X.schema_state(db)
                    self.assertEqual(error.exception.code, 409)

    def test_primary_key_order_is_part_of_the_declared_contract(self):
        db = self.database([('PRIMARY KEY(experiment_id,seq)', 'PRIMARY KEY(seq,experiment_id)')],
            ['CREATE UNIQUE INDEX equivalent_unique ON learning_experiment_events(experiment_id,seq)'])
        with self.assertRaises(ApiError) as error:X.schema_state(db)
        self.assertEqual(error.exception.code, 409)

    def test_formal_schema_and_equivalent_nonpartial_unique_are_ready(self):
        self.assertEqual(X.schema_state(self.database()), 'ready')
        cols = 'tenant_id,project_id,creator,request_id'
        db = self.database([(f'UNIQUE({cols})', 'CHECK(1)')],
            [f'CREATE UNIQUE INDEX equivalent_unique ON learning_experiments({cols})'])
        self.assertEqual(X.schema_state(db), 'ready')


if __name__ == '__main__':unittest.main()
