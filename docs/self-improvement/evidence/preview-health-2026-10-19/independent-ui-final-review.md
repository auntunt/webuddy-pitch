# Independent ticket-preview UI review

Scope: read-only review of the UI increment that shares one preview response between the ticket top summary and preview panel. Product and test files are not owned or modified by this reviewer. Initial reviewed source digests are recorded in `independent-ui-review-source.json`; final corrected-source digests are in `independent-ui-final-source.json`, against HEAD `7310a820080b562e56fc16e6a958bf99c8818383`.

Final conclusion: the reproduced draft-loss regression is fixed, and no remaining blocker was found in this UI increment. The independent final script passed its five groups of behavior assertions with Node exit code 0. The two product files and main UI test file had identical hashes before and after this execution. No product or test file was modified by this reviewer; only ignored reproduction and report artifacts were written.

## Reproduced blocking regression: unsaved preview configuration

The new call chain `ticketSummarySync -> ticketTopWire -> pvLoad` refreshes the whole preview panel whenever a background ticket summary changes. Unlike the previous top-only refresh, `pvLoad` replaces `#pvc.innerHTML`, deleting the open `#pvF` form and unsaved `#pvCmd` and `#pvReady` fields. The existing four new tests protect comment and acceptance-note fields but do not cover this form.

The isolated Node reproduction loads the actual shipped `pvLoad` and `ticketTopWire` functions, opens the configuration form, enters two draft values, models replacement of the top summary, and calls `ticketTopWire` again. Its DOM double recursively removes descendant nodes when `innerHTML` is replaced, matching the relevant browser behavior. Both input fields disappear. The script exited 1; the Python wrapper only captured its result and does not indicate a pass.

- Script: `independent-ui-config-draft-repro.js`
- Red result: `independent-ui-config-draft-red.log`
- No real browser, service, network endpoint, application database, or production resource was contacted by this reproduction.

The parent accepted the regression and now preserves the original form DOM node across state rendering. A fresh script extracted the corrected shipped functions and checked the same field-identity/value assertions, plus the retained save handler and exact posted draft values. It passed. The original red script and log have not been overwritten.

## Executed final independent checks

The script `independent-ui-final-checks.js` uses only an isolated Node DOM/HTTP fixture. Its output is retained in `independent-ui-final-green.log`:

1. A background summary refresh retains the preview-configuration form, both input nodes and values, and save handler; saving submits exactly those draft values.
2. A detached form's old save handler cannot submit after switching tickets.
3. A delayed configuration response cannot populate the destination ticket's form.
4. Initial top wiring makes one preview read; a superseded starting-state timer does not read again, while the current timer updates both top and panel from the healthy response.
5. Starting-state timers stop after a different view, a replacement DOM for the same ticket, or another ticket.

These assertions complement the main UI tests; they are not a real browser or whole-repository test run. The parent retained six main UI tests passing in 1.607 seconds in `ui-stale-final-green.log`; that log was inspected, not rerun by this reviewer.

## Other reviewed behavior

- Initial ticket rendering still calls `ticketTopWire`, so removing the duplicate direct `pvLoad` call does not omit the initial preview load. `ticketTop` consistently supplies `#ttPv`.
- The shared response updates top and panel together. Request sequence, current ticket, current view, and both DOM identities guard late responses.
- Starting-state polling is guarded by that same request identity; stale timers cannot poll a replaced page. A newer successful starting-state read schedules its own poll.
- A network read failure becomes a checking state, removes stale opening links, and retains an explicit refresh action. Error content is escaped.
- Comment and acceptance-note nodes sit outside the replaced preview panel and remain intact. Preview configuration was the missing draft scope identified above and is now retained as the same DOM node.
- Configuration reads and saves now check form identity, ticket, and view. The retained form is allowed to survive a top-summary replacement, but detached forms and responses cannot act on another page. Late configuration and detached-save behavior were executed in the final independent script.

Evidence distinction: the first four main UI tests' red and green logs were inspected (three failures, then four passes), followed by the six-test green log after the draft fix. They were run by the parent, not rerun in this independent review. This reviewer executed the isolated red draft reproduction and the fresh final five-group script. The earlier flow/fixture read-only findings are separately recorded in `independent-flow-fixture-readonly-review.md`. Whole-repository testing and real-browser acceptance remain the parent agent's evidence.
