# Independent Harness probe review

Reviewed local uncommitted integration against repository HEAD `1d2ea889d5dbfb76ff26c2e8e16d86dfe0cd6135`. Product files were read-only for this reviewer. The reviewer added only `tests/test_harness_probes_independent.py` plus ignored evidence files. All execution used temporary Git projects and fresh SQLite data; no production or real BOOTV2 data was modified.

Final command:

```sh
NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost data/agent-venv314/bin/python -m unittest discover -s tests -p test_harness_probes_independent.py -v
```

Result: **9 tests passed in 12.434 seconds**. The seven source/test SHA-256 values were identical before and after this run (`independent-final-source.json`). Full output: `independent-final-green.log`. `git diff --check` also passed. No remaining reproduced blocker in the reviewed scope; the parent owns the full repository suite and real application/browser acceptance.

## Reproduced issues resolved

| Boundary | Original reproduction | Verified final behavior |
| --- | --- | --- |
| Git export-ignore | `independent-snapshot-red.log` | Snapshot retains tracked runtime files even when archive attributes exclude them. |
| Git export-subst | `independent-snapshot-red.log` | Snapshot preserves original blob bytes instead of substituting commit placeholders. |
| Python optimization | `independent-optimized-red-confirmed.log` | A real application with deliberately broken search still fails business checks under `PYTHONOPTIMIZE=1`. |
| Timeout raw output | `independent-output-red-confirmed.log` | Application output containing NUL/0xff and no final newline survives group termination in its original binary log. |
| Requirement changes before publication | `independent-lifecycle-first.log` | A requirement added after the final managed process exits invalidates the result; observations remain retained. |
| Acknowledged stop before publication | `independent-final-boundaries-first.log` | An acknowledged stop cannot subsequently publish a passing experiment. |

Other passing regressions cover duplicate starts through separate Store connections, changed verification content invalidating current pass while retaining historical observations, and older source records without a verification digest remaining readable and stale.

The first `independent-optimized-red.log` was a green run with an incomplete application fixture; `independent-output-red.log` contained a fixture formatting error. They are retained for transparency but are not evidence of product defects. The `*-confirmed.log` files above contain the corrected reproductions.

## Scope and limits

This is a maintainer-owned, opt-in recipe for the BOOTV2 Python/SQLite item workflow. The real HTTP and database checks support behavior evidence for fixed source versions; they do not prove a universal software success rate, model improvement, or recursive Harness² optimization.

The candidate and its processes execute in the trusted local workspace. Fresh data and fixed source snapshots are not OS isolation from a hostile same-user process. Candidate assessments and historical probe evidence are not human acceptance, merge authorization, or release proof. CLI/MCP execution flags and the separate operator boundary remain in effect.

The compile commands in the independent lifecycle fixtures are only prerequisites for exercising lifecycle state; they are not described as business validation. The business assertions run through the separate maintained recipe against actual temporary HTTP applications and SQLite databases.
