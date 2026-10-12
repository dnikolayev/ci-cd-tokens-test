# Methodology

## Question and treatments

The experiment asks whether CI admission and monitoring style affect the agent effort needed to observe an already-correct change through complete verification. It deliberately omits code generation and real debugging.

Each workflow has four identical jobs. Each runs the repository's tests and occupies a runner for the same fixed hold period. `strategy.max-parallel` is either 1 or 4. `fail-fast: false` ensures that an injected failure does not cancel other checks. [GitHub defines this setting as a limit on simultaneous matrix jobs](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/run-job-variations).

In `poll` mode the observer returns a small status message after each polling interval, allowing the agent to request another observation. In `wait` mode it loops inside one command until completion. A shell tool may yield while the command is running, requiring the agent to wait on its session. This is a tool-wait control, not a guarantee of zero model activity.

The `none` scenario requires all four jobs to succeed on the first attempt. The `once` scenario requires exactly the first shard to fail after its ordinary hold on attempt 1, with all others successful, followed by one successful retry of that shard. The helper requests `gh run rerun --failed` only for that exact expected failure pattern. Missing, skipped, cancelled, or unexpectedly failing checks do not establish success.

## Trial protocol

The seed fixes paired trial order before the first run. Each pair shares fault mode, monitoring style, repetition, model, settings, source, hold duration, and polling interval. Concurrency order is randomized within the pair. Pairs run sequentially to avoid intentional interference between trials.

Each trial starts one fresh `codex exec` session. The CLI ignores user configuration and execution rules, uses a workspace-write sandbox with network access for GitHub, and disables project document injection. Authentication stays in the existing CLI setup. CLI defaults, global tool availability, model service behavior, and prompt caching can still differ across installations; record the CLI version and compare conditions within the same setup.

The prompt is built in `run_trial` in [benchmark.py](benchmark.py). It tells the agent to use only the observer command, wait on a running command, and stop after verified completion or an error. The observer dispatches on its first invocation, so agent startup does not consume the CI exposure period. A unique trial name identifies the dispatch; local HEAD must match the remote branch and the workflow must report that SHA.

The observer stops after the time limit. The outer harness also has a time limit and requests cancellation of any still-running owned workflow after the agent exits. Each result retains acceptance, exit status, measurement errors, job attempts, timestamps, and the applicable bounds. A timeout without terminal token counters has unknown token usage, not zero usage.

## Usage accounting

The [Codex JSON event stream](https://learn.chatgpt.com/docs/non-interactive-mode) provides terminal usage counters. One fresh user turn must produce exactly one `turn.completed` usage event. Duplicate or missing terminal events invalidate the usage measurement. Raw transcripts are private; public results use an explicit field whitelist.

Report input and output separately. Cached input is included in input, so uncached input is input minus cached input. Reasoning output, when present, is a subset of output. Total tokens are input plus output. Missing optional fields remain null. Counts are not converted into account quota or dollars.

Completed command items and observer invocations describe visible activity. They do not count every model request or every tool-session wait. API polling inside the helper is separate from an agent invocation. Comparing these counts helps explain usage without inventing an exact model-turn count.

Job timestamps permit calculation of the total recorded job seconds, the time from the earliest job start to the latest completion, and maximum observed overlap. These include job setup and teardown. They are not billed runner minutes and do not isolate CPU work. Workflow dispatch to verification also includes queueing and the observer's detection delay. Agent elapsed time includes startup, reasoning, and the final response.

## Analysis and limits

Publish individual trials and paired differences, with all attempts retained. Summaries should separate the two fault scenarios and the two monitoring styles. Report verification successes out of all attempted trials. For usage per successful verification, include usage of valid unsuccessful trials in the numerator. If any trial lacks usage counters, that aggregate is incomplete and must be labelled accordingly.

Two repetitions per stable cell and one per fault cell are a pilot, not a reliable population estimate. Hosted runner scheduling and shared prompt caches can vary. No cache is forcibly warmed or cleared; cached and uncached counts must be visible. The deliberately repeated polling is a treatment, not a claim that every agent behaves that way.

Faster CI with similar usage in the waiting condition is a useful outcome. It would distinguish the cost of elapsed time from work performed during that time. A large polling difference would demonstrate a mechanism in this setup, not establish that adding runners caused a historical change in anyone's subscription allowance.

