# Independent read-only review of the blocked-pipe deadline fixture

Conclusion: the fixture correction is appropriate and does not weaken the behavior under test. This review did not modify product/test files or execute tests. The reviewed hashes and the product comparison against HEAD are saved in `independent-process-fixture-source.json`.

The second whole-suite run recorded 773 tests with one failure: the deadline test observed empty output instead of `partial-without-newline`. The product `tmh/platform/process_control.py` is byte-for-byte identical to HEAD `7310a820080b562e56fc16e6a958bf99c8818383`. The test diff changes only its child command and explanatory comment; no result assertion was removed or relaxed.

The replacement command is:

```sh
/bin/sh -c "trap '' TERM; printf %s partial-without-newline; exec /bin/sleep 20"
```

The shell builtins establish ignored SIGTERM and write the exact partial line before replacing the shell with the sleeping process. Ignored SIGTERM survives `exec`. Neither command consumes the 4,000,000 input bytes, so the large stdin pipe still blocks. The command uses an absolute native sleep path and an explicit printf format. The deadline and escalation contract remains exactly the original one:

- 0.25-second timeout and 0.1-second termination grace.
- Timeout reason and status 124.
- Exact raw partial output, with no newline.
- Both TERM and KILL sent.
- Completion in less than two seconds.
- Complete cleanup, no remaining owned process group, output EOF, and reaped leader.

The previous Python fixture required Python startup/imports and handler installation to complete before its 250 ms wall deadline. `reproduce-cold-start-fixture.py` explicitly adds 0.4 seconds before the old fixture installs its handler/emits output. The retained `process-fixture-red.log` reproduces the same empty-output assertion failure in 0.301 seconds. This demonstrates that a valid timeout during delayed fixture preparation can produce that failure; it does not establish the unique cause of the historical whole-suite failure.

The same reproduction harness passes the corrected fixture in 0.360 seconds (`process-fixture-final-green.log`). Its injected delay is attached to `run_python`; the corrected fixture no longer uses that helper. Therefore this green result shows removal of the Python preparation dependency, not successful output after deliberately delaying the native command beyond its deadline. Native startup can still be delayed by arbitrary OS scheduling; the change does not claim to eliminate all scheduling uncertainty or move the product timeout to begin after readiness.

The parent-run `process-targeted-final.log` records all 14 process-control tests passing in 5.401 seconds. This reviewer inspected that log and the red/green reproductions; no test was rerun during the review. The final frozen whole-suite result is separate and remains the parent agent's responsibility. No real application data, running preview service, production resource, or external model was touched.
