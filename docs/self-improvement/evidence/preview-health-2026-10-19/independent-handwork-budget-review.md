# Independent read-only review of the handwork shared-budget test

Scope: the fixture in `tests/test_handwork_lifecycle.py::HandworkLifecycleTest::test_review_shares_time_spent_on_baseline_and_candidate_checks`. This reviewer reads product/test code and retained evidence only; no product or test files were modified, and no tests were rerun by this reviewer.

Final conclusion: approved. The retained delayed-preparation red/green evidence and the explicit wrong-budget mutation confirm that the corrected fixture can reach the intended reviewer scenario while still rejecting a fresh full reviewer budget. Source hashes are recorded in `independent-handwork-budget-source.json` at commit `d21e4f4da680b6649e06abd0517ca7200c714359`.

## Code review

The proposed correction is appropriate. It expands the fixture's configured total run budget from 1.2 to 3.0 seconds to give real Git worktree preparation and Python child startup room to reach the reviewer. It does not change the product implementation or merely increase the polling wait. The previous relative constraints remain: reviewer timeout is less than total budget minus 0.2 seconds, and the whole lifecycle is less than total budget plus 1.3 seconds. The independent wait helper remains bounded at five seconds.

The corrected test also strengthens proof of shared consumption:

- At least two real check attempts must exist.
- Each check must exit zero, consume at least 0.15 seconds, and report complete cleanup.
- The lifecycle must record exactly the configured 3.0-second budget.
- The reviewer's recorded timeout plus all check-attempt elapsed times must be at most the total budget plus a 0.02-second tolerance.
- The actual reviewer-start marker must exist, preventing a pre-review timeout from satisfying the scenario.
- Original failed status, exit 124, timeout reason, reviewer cleanup, and no-adoption assertions remain.

Read-only inspection of `Runner._control`, `remaining`, `run_command`, and `handwork._check1` confirms that the current product uses one run start time and passes only the remaining allowance to the reviewer. `tmh/platform/agents.py`, `tmh/platform/handwork.py`, and `tmh/platform/fixloop.py` were independently compared byte-for-byte with round base `7310a820080b562e56fc16e6a958bf99c8818383`; all are unchanged.

## Reproduction and mutation design

`reproduce-handwork-startup.py` runs the real fixture with an explicit 1.3-second delay immediately before `FixLoop.diagnose`. That can deterministically exhaust the old 1.2-second budget before the reviewer emits its marker. With the 3.0-second fixture, the same preparation cost is charged to the run and must leave only the remainder for a real reviewer that sleeps past the deadline. No success is fabricated.

`reproduce-handwork-budget-reset.py` instead resets `controls[rid]["start"]` immediately before diagnosis in its isolated test process, without adding the preparation delay. This is an explicit wrong-budget mutation; the updated test must fail on the reviewer-budget assertion. It does not edit the product files.

The fixed 0.2-second reduction alone does not prove detection of every possible intermediate-stage reset; one check plus startup cost could exceed that reduction. The added actual-check-duration constraint is stronger, and the explicit mutation tests the concrete case of a fresh full budget for review. Neither demonstration establishes the unique cause of the historical full-suite marker failure or guarantees progress under arbitrarily delayed OS scheduling.

## Execution evidence

The following parent-run logs were read in full using their absolute paths:

- `handwork-fixture-red.log`: the old test with 1.3 seconds of explicit preparation delay failed on the missing reviewer marker, one test in 2.374 seconds.
- `handwork-fixture-final-green.log`: the strengthened three-second fixture with the same explicit delay passed, one test in 3.288 seconds.
- `handwork-targeted-strengthened.log`: all five handwork lifecycle tests passed in 7.637 seconds, including build timeout, cancellation, reviewer failure, shared budget, and successful adoption.
- `handwork-budget-reset-red.log`: the isolated bad-budget mutation failed as required. The reviewer received 2.984016166999936 seconds, which violates the strict less-than-2.8 assertion. One test failed in 5.319 seconds. This is a useful negative control, not an unresolved product failure.

These results were produced by the parent and inspected by this reviewer; this follow-up did not rerun tests. The original 775-test whole-suite failure remains retained separately in `full-platform-third.log`. The final frozen whole-suite run is separate and no outcome for it is claimed here. No inference is made about when evidence files were written.
