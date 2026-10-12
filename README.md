# CI scheduling and agent token usage

A small, reproducible experiment: does faster CI reduce the work an agent does while waiting for verification?

Four identical GitHub Actions jobs run with a concurrency limit of either one or four. An agent observes them by repeatedly asking for status, or by letting a tool wait for completion. A separate scenario injects one predictable transient failure and permits one retry. Every condition keeps the same checks.

This measures observation overhead for an already-correct change. It does not measure coding quality, hardware scaling, or production deployment.

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

## What to compare

- Elapsed agent time and CI job timing, including realized job overlap.
- Successful complete verification, failed attempts, and retries.
- Input tokens, cached input tokens, uncached input tokens, and output tokens.
- Observer invocations, API polls, and completed agent commands.

Input totals already include cached input. Reasoning output, when available, is part of output. Neither is added twice. Token counts are not subscription allowance percentages or dollar costs.

Read [the methodology](METHODOLOGY.md) before interpreting a difference. A slower workflow can cause more agent work when the agent keeps asking about it. A tool that waits may make elapsed time much less important to token usage.

## Boundaries

The workflows use hosted runners and synthetic sleep periods. Raising `max-parallel` changes an admission limit, not machine capacity. Fixed polling intentionally creates repeated observation work. Real coding tasks also involve review, debugging, context changes, and different test costs.

Local CLI credentials are not uploaded to Actions. GitHub and model authentication remain in the local CLI setup; checkout uses GitHub's own workflow token. The observer dispatches and, when appropriate, reruns only its uniquely identified synthetic workflow. A normal failing test is not automatically retried.

The code is available under the [MIT license](LICENSE).

