# Independent correction of the operation shared-budget fixture

Outcome: the assigned test-method correction and targeted validation are complete. Only `tests/test_recheck_operations.py::RecheckOperationsTest::test_total_operation_budget_covers_multiple_commands` changed outside this ignored evidence directory. No product code changed and no whole-suite run was performed by this reviewer.

The original whole-suite failure remains unchanged in `full-platform-fourth.log`. The complete original test file was saved before editing as `test-recheck-operations-before.py`. The initial code/version manifest is `independent-recheck-budget-before.json`, based on commit `d21e4f4da680b6649e06abd0517ca7200c714359`.

## What changed and what remains enforced

The synthetic operation budget is now 3.0 seconds instead of 0.7 seconds. Real Python and supervisor startup must fit before the first command's real 0.25-second sleep. Both command bodies are unchanged. The first command must still complete successfully, and the second must still actually start, emit its exact line, ignore TERM, and reach timeout. Calling `finish(..., 0, ...)` cannot overwrite that timeout with success.

The test retains its original first-return-zero, second-timeout, final-failed, stopped-reason, complete-cleanup, and first-output assertions. It additionally requires:

- The first command's actual measured elapsed time is at least 0.25 seconds.
- The second result and final operation exit codes are 124.
- The lifecycle is finished, the operation is no longer running, and there are exactly two attempts.
- The lifecycle records the configured 3.0-second total budget.
- The second attempt's recorded timeout plus the first command's actual `ProcessResult.elapsed` is at most 3.02 seconds. This makes giving the second command a fresh full budget fail.
- The whole sealed lifecycle is less than budget plus 1.3 seconds. This allows the owned process's TERM/KILL escalation, output draining, supervisor receipt, and lifecycle publication to finish; it does not extend the command allowance.
- Both exact outputs (`first complete\n` and `second\n`) equal their persisted binary output files.

## Executed evidence

All runs below were actually executed by this independent reviewer with Python 3.14 and the local HTTP proxy exclusions set. The executable reproduction script is `reproduce-recheck-operation-budget.py`. Its patches affect only disposable test processes. Each reproduction's same-named directory retains the full operation evidence tree, result JSON, original command-output bytes, and operation rows.

| Scenario | Actual result | Log |
| --- | --- | --- |
| Original fixture, explicit 0.8-second preparation delay before the first Python command body | Expected failure, 1 test in 0.759 s; first result 124 instead of 0 | `recheck-budget-delay-red.log` |
| Corrected fixture, the identical 0.8-second delay | Pass, 1 test in 3.366 s | `recheck-budget-delay-green.log` |
| Corrected fixture, deliberately reset the operation start time immediately before command two | Expected failure, 1 test in 3.927 s; 3.3568891669856384 exceeds 3.02 | `recheck-budget-reset-red.log` |
| Entire `tests.test_recheck_operations` module, no injected delay or mutation | 14 tests passed in 3.923 s | `recheck-budget-module-green.log` |

In the corrected delayed run, command one actually completed in 1.160796458949335 seconds. Command two timed out, sent KILL during escalation, retained `second\n`, and reported complete cleanup. Both persisted binary outputs were checked. In the bad-reset run both commands also cleaned up completely; the failure is specifically the shared-budget invariant, not a missing marker or leaked process.

The delay reproduction shows a concrete way that the old short allowance expires during legitimate fixture preparation. It does not prove the unique cause of the historical whole-suite failure. The bad-reset negative control demonstrates detection of a fresh budget for the second command; it does not claim to exhaust every possible timing defect or guarantee startup under arbitrary OS scheduling delays.

## Freeze and scope verification

`independent-recheck-budget-final-source.json` records that the test and four relevant product files had identical hashes before and after the 14-test module run. All four product hashes equal the original pre-edit hashes. An AST comparison with the saved original file, excluding only the assigned method, confirms that every other test method and module element is unchanged. `git diff --check -- tests/test_recheck_operations.py` passed.

Final test-file SHA-256: `bb236c2684e79de7c2e3fef0451efe2e5a6a448b94b2d891e7d2d55bb6e0f5b7`.

The product/test files are now frozen for the parent agent's review and whole-suite run. Only this report was added after reporting the freeze. No live application data, production system, external model, or preview service was accessed.
