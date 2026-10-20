# Independent preview health review

Base: `7310a820080b562e56fc16e6a958bf99c8818383`. Product files were read only; this reviewer owns only `tests/test_preview_health_independent.py` and the evidence files in this directory.

The saved baseline module `preview-before.py` came from Git HEAD. It was loaded into a separate Python test process, without changing product files. The independent suite produced 14 failures including subtests across 9 tests (`independent-baseline-red.log`). This captured the old state reporting a preview as up without checking its endpoint, and the watcher treating a successful unrelated root page as readiness despite a failing configured prefixed endpoint.

Against the updated implementation, all **9 tests passed in 3.506 seconds**, with no failures (`independent-first-green.log`). The review source hashes are in `independent-review-source.json`; `git diff --check` passed. Full repository testing and real browser acceptance remain with the parent agent.

The tests use real HTTP fixture servers and temporary state only. They cover:

- HTTP 401, 404 and 503 are unavailable; a precise prefixed direct 200 response is usable.
- Redirect responses 301/302/303/307/308 are unavailable and their destination is not contacted.
- A live preview becoming unavailable and recovering does not mutate business records or its saved preview identity.
- Environment proxy variables do not intercept the local health request.
- An incomplete 200 response is unavailable, completes within the bounded wait, and closes its connection.
- Repeated complete error responses release HTTP connections.
- An old commit address is rejected before reaching a replacement application's server.
- Readiness cannot fall back to an unrelated successful root path.

Read-only review of preview.py, candidates.py, ui.py and ui_work.py found no remaining blocker in this scope. The body completion check, total-deadline timer, direct local connection and finally-block resource closure match the declared health contract. Candidate preview hashes still include stable version/process/configuration fields and exclude volatile health timestamps, elapsed time and response hashes, so normal polling does not invalidate unchanged approval evidence. The interface treats unavailable/checking separately and does not offer an opening link as if the preview had passed.

Limits: the check proves only that the configured endpoint supplied a complete direct 2xx response within the deadline. It does not prove application or database correctness. Health is sampled on state reads; this change does not introduce continuous automatic HTTP monitoring. A recovered identical process retains its earlier approval history. PID ownership in these tests uses the test process hosting the fixture servers; the watcher test uses an explicit process double and does not claim to exercise real process termination. No production access, external model execution or BOOTV2 data mutation occurred.
