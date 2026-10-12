# CI scheduling and agent token usage

A small, reproducible experiment: does faster CI reduce the work an agent does while waiting for verification?

Four identical GitHub Actions jobs run with a concurrency limit of either one or four. An agent observes them by repeatedly asking for status, or by letting a tool wait for completion. A separate scenario injects one predictable transient failure and permits one retry. Every condition keeps the same checks.

This measures observation overhead for an already-correct change. It does not measure coding quality, hardware scaling, or production deployment.

Read the article: [AI Made Coding Faster. Our Delivery Pipeline Had to Catch Up.](ARTICLE.md)

The [first pilot](results/README.md) contains all twelve planned trials, including one failed verification, plus separately labelled preflight attempts. Faster CI did not produce a consistent token reduction in this small sample.

## Reproduce

You need Python 3.10 or newer, Git, authenticated [GitHub CLI](https://cli.github.com/), and an authenticated [Codex CLI](https://learn.chatgpt.com/docs/non-interactive-mode). The harness uses Python's standard library. Agent runs consume your account's usage; Actions runs use your repository's runner allocation.

1. Fork this repository and clone your fork. Enable Actions if GitHub asks.
2. Check that `gh auth status` and `codex --version` work. Your GitHub account needs permission to dispatch and rerun workflows in the fork.
3. Keep local HEAD and your fork's `main` at the same commit, with tracked files clean.
4. Run the pilot, choosing a model and reasoning setting available to your account:

```sh
python3 -m unittest discover -s tests -v
python3 benchmark.py pilot --repo YOUR_USER/ci-cd-tokens-test \
  --model YOUR_MODEL --reasoning YOUR_REASONING_SETTING
```

The default pilot runs twelve fresh agent sessions sequentially: two repetitions of each concurrency and monitoring condition without faults, plus one repetition per condition with an injected fault. Paired groups and their internal order are randomized with a recorded seed. The order is planned before execution. Each job holds for 15 seconds, the observer checks every 10 seconds, and CI observation is bounded at 600 seconds per trial. Model startup and response time add to that duration; the outer process has a further 180-second allowance.

Results go to `.runs/pilot.jsonl`; the planned order goes to `.runs/pilot.plan.json`. Raw local session logs remain in the ignored `.runs/` directory. **Do not publish that directory.** The result records select only measurement fields and public metadata from the synthetic workflow. Inspect even those selected records before sharing them.

Use `--repeats 1 --fault-repeats 0` for a four-session check, or increase repetitions for a more useful estimate. Use a new `--output .runs/another-pilot.jsonl` path for another batch. The harness refuses to overwrite an existing result file.

If your host requires a setting from existing user configuration, add `--use-user-config`. For example, Codex's permission to use an already trusted symlinked home must come from user configuration, not a command-line override. This option loads the whole user configuration, so use the same setup for every condition. Model, reasoning, project-document, and sandbox overrides still apply; hooks and notification commands are disabled for each trial. Configuration contents stay private; the result records whether they were loaded.

## Larger concurrency comparison

Caps above four need a larger fixed workload. This command keeps 32 jobs in every condition and compares caps of 4, 8, 16, and 32. It runs eight fresh agent sessions and 256 job executions: one repetition per cap with polling and one with tool waiting, without injected failures.

```sh
python3 benchmark.py pilot --repo YOUR_USER/ci-cd-tokens-test \
  --model YOUR_MODEL --reasoning YOUR_REASONING_SETTING \
  --jobs 32 --caps 4 8 16 32 --repeats 1 --fault-repeats 0 \
  --output .runs/scaling.jsonl
python3 report.py .runs/scaling.jsonl
```

The plan records both the fixed job count and intended caps. Compare caps within this batch; its absolute timings are not directly comparable to the original four-job pilot. One repetition is exploratory, and larger batches consume more account usage and runner time.

[GitHub's documented standard-runner limits](https://docs.github.com/en/actions/reference/limits#job-concurrency-limits-for-github-hosted-runners) currently allow 20 concurrent jobs on Free and 40 on Pro. These are GitHub plans, separate from model subscriptions. Other workflows and runner availability can further restrict overlap. Inspect `peak_overlapping_jobs` in the records: a requested cap of 32 does not prove that 32 jobs ran together. The checks must still pass even when a cap is not reached.

## What to compare

- Elapsed agent time and CI job timing, including realized job overlap.
- Successful complete verification, failed attempts, and retries.
- Input tokens, cached input tokens, uncached input tokens, and output tokens.
- Observer invocations, API polls, and completed agent commands.

Input totals already include cached input. Reasoning output, when available, is part of output. Neither is added twice. Token counts are not subscription allowance percentages or dollar costs.

Read [the methodology](METHODOLOGY.md) before interpreting a difference. A slower workflow can cause more agent work when the agent keeps asking about it. A tool that waits may make elapsed time much less important to token usage.

Generate the numeric report using only the standard library:

```sh
python3 report.py results/pilot.jsonl
```

The published pilot used Codex CLI 0.162.1. Its records include the source commit and settings. Checking out that commit reproduces the original workflow revision; running a newer revision should be reported as a new batch. To redraw the optional figure, install matplotlib in a separate environment and run `python3 plot_results.py results/pilot.jsonl --output results/pilot.png`.

## Boundaries

The workflows use hosted runners and synthetic sleep periods. Raising `max-parallel` changes an admission limit, not machine capacity. Fixed polling intentionally creates repeated observation work. Real coding tasks also involve review, debugging, context changes, and different test costs.

Local CLI credentials are not uploaded to Actions. GitHub and model authentication remain in the local CLI setup; checkout uses GitHub's own workflow token. The observer dispatches and, when appropriate, reruns only its uniquely identified synthetic workflow. A normal failing test is not automatically retried.

The code is available under the [MIT license](LICENSE).

