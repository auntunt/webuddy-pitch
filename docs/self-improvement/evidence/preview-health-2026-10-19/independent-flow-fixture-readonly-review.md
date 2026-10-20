# Independent read-only review of final flow and fixture changes

This records the second review, before the subsequent ticket-preview UI recovery fix. The reviewer read the six tracked product/test diffs and the new `tests/test_preview_health_flow.py`. No product or test file was edited and no tests were rerun during this review.

No weakening of the existing acceptance assertions was found:

- `test_preview_run_binding.py` has a synthetic preview record at port 12345 and already mocks process liveness. Its new healthy observation mock is scoped only to obtaining the old URL. The original grant-cookie scope, commit replacement, 409 rejection for the old entry/open/assets/form requests, and `forward.assert_not_called()` assertions remain intact.
- The new flow test creates an isolated starter repository and candidate, runs the actual build/test and candidate verification, starts the real application, extracts its CSRF input, and saves an item over HTTP. It replaces the SQLite database path temporarily with a directory, requiring actual HTTP 503, an unavailable candidate preview, false technical readiness, and a 409 rejection of another assessment. It restores the original database and requires the same PID, original item, exact database bytes, unchanged saved preview state, unchanged business rows, and unchanged stable evidence hash.
- The technical assessment is explicitly a test-fixture observation, not a human approval or a new model-written business feature. `human_accepted` remains false.
- Treating `Set-Cookie` as optional matches this starter's server-side CSRF-token contract. The CSRF extraction and real POST status assertion remain. The first cookie-assumption error is preserved in `flow-targeted-first.log`; the subsequent `flow-green.log` records one test passing in 10.517 seconds. These are retained parent-run logs, not tests rerun by this reviewer.
- The UI additions keep the refresh/restart path and escape health errors. The product diff does not weaken operator authentication or immutable-version binding.

The earlier independent HTTP suite was actually executed by this reviewer and passed nine tests in 3.506 seconds, as separately recorded in `independent-review.md` and `independent-first-green.log`. That execution must not be confused with this read-only follow-up. Full-suite and browser results remain the parent agent's evidence.
