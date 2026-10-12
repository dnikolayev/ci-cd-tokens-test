# Preflight attempts

These three trial attempts preceded the planned pilot. They are retained separately because the observation protocol was still being checked and corrected. Their token counts are real, but they are not comparable treatment observations. They do not include the work of developing the benchmark.

| Attempt | Outcome | Agent seconds | Total tokens |
| --- | --- | --- | --- |
| 1 | Command could not start with user configuration excluded | 11.8 | 38,609 |
| 2 | Command-line override could not grant the host permission | 10.3 | 38,626 |
| 3 | Workflow recovered, but the observer rejected carried-forward jobs | 83.4 | 153,489 |

Total measured usage in these preflight attempts: 230,724 tokens. This is input plus output, including cached input, not a monetary cost.

The first two attempts dispatched no workflow. The third completed the intended single failed-job retry, but GitHub returned successful first-attempt jobs again with new IDs and unchanged execution timestamps. The original observer incorrectly rejected that response and double-counted the carried-forward jobs in its job-time and overlap totals. Those two fields are explicitly marked invalid in the retained record. The fixed parser validates the same response as five actual job executions, 97 total job seconds, and at most four overlapping jobs.

The planned pilot uses the corrected implementation. These original records were not relabelled as successful trials. See [the retained preflight records](preflight.jsonl) and [the correction](https://github.com/dnikolayev/ci-cd-tokens-test/pull/1).
