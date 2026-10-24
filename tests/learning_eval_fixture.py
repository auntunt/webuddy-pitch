"""Persist previously prepared evaluator fixtures through real registration.

The old pure evaluator tests already prepared a frozen input, sometimes before
usage or new cards changed. Only that preparation and the unavailable provider
configuration are substituted; job/capture/case registration is the real path.
No thread, CLI, or model is started. Dedicated capture tests use unpatched
preparation and mutate only the persisted options after registration.
"""
import copy
import uuid
from unittest.mock import patch

from tmh.platform import learning_eval as E, learning_runs as R


def registered_job(P, project, revision, options):
    def prepared(_P, _p, _r, configured):
        return dict(configured, **copy.deepcopy(options))
    config = {"agent": "claude", "model": "synthetic-fixture", "configuration": {"isolated": True},
              "executable": "never-executed", "prompt_version": R.PROMPT_VERSION}
    with patch.object(R, "_configuration", return_value=config), patch.object(E, "validate_options", side_effect=prepared):
        job = R.start(P, project, "evaluate", revision["id"], options, "operator", uuid.uuid4().hex, launch=False)
    # The evaluator is driven synchronously by a stub in these tests. Release
    # the queue slot so subsequent independent cases can register their jobs.
    P.store.x("UPDATE learning_jobs SET status='not_passed' WHERE id=?", (job["id"],))
    return R._decode(P.store.one("SELECT * FROM learning_jobs WHERE id=?", (job["id"],)))
