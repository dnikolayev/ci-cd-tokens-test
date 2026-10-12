# AI Made Coding Faster. Our Delivery Pipeline Had to Catch Up.

A few days ago, I used roughly 30% of my weekly Pro allowance in a short stretch of work on a pull request. CI/CD problems kept the work stuck, and the PR was still unresolved.

That was what pushed me to increase the number of CI jobs we could run at once.

After the change, the allowance seemed to last longer. I wanted to understand why. The 30% figure is my observation of the weekly limit, not a reconstructed token count. But spending that much allowance without getting a PR through was a good reason to investigate.

We had already spent more than four months improving CI/CD. This latest change made a pattern much clearer: as agents got faster at writing code, more of our development speed depended on what happened after the code was written.

Writing code used to take up a large part of our development time. Coding agents changed that for us. We could get to a first implementation much faster.

Then we had to read it.

More code was ready for review, but we still had to understand it, check it, and decide whether it was safe to deliver. Producing a large diff had become much faster than reviewing it carefully. An agent giving a convincing explanation was not enough.

We invested in testing harnesses: repeatable setups that exercised the code, checked its outputs, and made failures visible. We maintained high coverage requirements and used agents in pull request reviews and discussions. They could inspect a proposed change, raise a concern, and help work through a correction.

Those discussions were useful when they led to something we could check. A reviewer pointing out a possible failure mode gave us a reason to examine a caller, improve an assertion, or reproduce a problem. Another agent agreeing with the implementation offered much weaker evidence. The quality of the checks still mattered.

Coverage helped us identify code that had not been exercised. We also needed assertions that would fail when the behavior was wrong, realistic integration checks, and human judgment about requirements. We wanted each accepted change to come with evidence we could inspect.

As this process improved, more work reached CI. Every required check still had to pass. A correction discovered during review could send the change through validation again. An agent could finish its next piece of implementation while the previous change was waiting for an answer from the pipeline.

Fast feedback was already a core engineering concern. [DORA's guidance on continuous integration](https://dora.dev/capabilities/continuous-integration/) emphasizes small changes, reliable automated tests, and feedback that arrives quickly enough to support frequent integration. Agents made the cost of slow feedback more visible in our daily work by increasing how quickly changes arrived at that stage.

Our response developed over months. First we made the delivery path more repeatable. We strengthened validation, separated work that could run independently, and made failures easier to investigate. Later we spent more time on repeated setup, test planning, scheduling restrictions, and the handoffs between successful validation and verified delivery.

These changes affected different parts of the process. A test optimization might shorten execution. A scheduling change might allow the same work to start sooner. Better deployment evidence could save us from reconstructing which version had reached the environment. Treating all three as a single CI speed number would hide where the benefit came from.

One investigation made that distinction particularly clear. We had jobs waiting, and the initial question was whether we needed more runners. The timing evidence pointed to a concurrency limit in the workflow. Jobs started as earlier jobs released their places. For that run, the admission rule was setting the pace.

A queue on a dashboard therefore needs a little investigation. It may represent a lack of available machines, a workflow limit, a dependency on another job, or contention inside the resources already running. Each explanation suggests a different change.

We also learned to be cautious about successful component benchmarks. In one small local comparison, test planning fell from roughly 123 seconds to 24 seconds while producing the same plan. Ordinary execution of the selected shard remained around 151 seconds. The planning comparison had only two runs per variant, but it showed a useful improvement in that part of the work. It did not establish a comparable improvement in the whole pipeline.

Preserving verification was part of evaluating these changes. In one retained comparison, the coverage results matched before and after the optimization. More generally, we needed to know that the same required behavior had been checked and that failures still caused the run to fail. A shorter run obtained by silently losing tests would have defeated the purpose.

Capacity needed the same care. At one point, additional concurrency created memory pressure and had to be reduced. More simultaneous jobs can increase contention or produce failures that require another attempt. The useful setting is the one that improves completed, verified work within the resources available.

The effect on our allowance was harder to measure. The work mix was changing. Models and settings could differ. Cached input and allowance resets complicated comparisons. More than four months of continuous pipeline improvements also made it difficult to isolate the effect of one recent change. A daily usage total would tell us how much we used that day without telling us how efficiently we delivered comparable work.

A slow pipeline can leave more work for an agent. While a pipeline is unresolved, an agent may check its status, interpret another log excerpt, reconsider a failure, retry an operation, or reconstruct context after an interruption. Those activities require additional model work. An avoidable infrastructure problem can create several rounds of it.

Waiting by itself does not necessarily consume more tokens. A tool can wait for completion and return the result when it is ready. The important question is what the agent does while it waits, and what additional work a delay or failure causes.

We built [ci-cd-tokens-test](https://github.com/dnikolayev/ci-cd-tokens-test) to examine that narrower question with synthetic workloads. It gives readers a way to reproduce the comparison without access to our projects, data, or infrastructure.

The workflow runs four identical small assertion jobs with a fixed hold period. One condition admits one job at a time; another admits up to four. GitHub documents this behavior through the matrix [`max-parallel` setting](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/run-job-variations). This changes the workflow's concurrency limit. Actual start times still need to be measured, because setting a limit does not guarantee that all four jobs start together.

We compare two monitoring approaches. In the polling condition, the agent receives a compact status result and makes another tool call if the workflow is still running. In the waiting condition, the observer waits inside one command. The shell tool may return a running session, which the agent still has to resume. We record observer invocations, completed commands, and token usage. The event stream does not reveal every model request.

Fixed polling deliberately creates repeated observation work. It does not represent every coding agent or every team's workflow.

A separate failure scenario allows one job to fail predictably on its first attempt and then succeed on one permitted retry. The required assertions stay the same. The benchmark uses fixed model settings, fresh sessions, randomized condition order, and a bounded number of attempts. It records elapsed time, job timings, tool activity, success, and the available token counters, with cached input distinguished from uncached input and output.

The pilot completed 11 of 12 planned verifications. One dispatch error interrupted a trial; its usage remains in the report. Three earlier preflight attempts are retained separately. Here are three complete pairs that show why a single savings percentage would be misleading:

| Condition | Agent time, cap 1 | Agent time, cap 4 | Tokens, cap 1 | Tokens, cap 4 |
| --- | --- | --- | --- | --- |
| Polling, no injected failure, first repetition | 106.9 s | 56.2 s | 383,550 | 101,314 |
| Polling, one failure and retry | 152.4 s | 80.6 s | 236,116 | 353,069 |
| Tool wait, one failure and retry | 153.1 s | 83.4 s | 128,201 | 127,844 |

Both settings run the same four jobs. Time covers the whole agent session, including startup and the final response. Every row got faster. Token usage fell sharply in one, rose in another, and barely changed in the waiting control. These are session input plus output counts, including cached input. Uncached input moved differently again. The [full results](results/README.md) show every trial and those separate counters.

This supports investigating CI as part of agent efficiency. It does not establish a dependable token reduction from adding capacity, or explain the change we thought we saw in our own allowance.

This is a small pilot. It is enough to see how the setup behaves and where measurement gets awkward. Failed attempts belong in the results. Reporting usage per completed verification must include the cost of valid attempts that did not finish successfully. A larger claim about typical savings would need more repetitions and more realistic tasks, including actual debugging and review corrections.

For engineers considering similar improvements, I would start by following a few changes all the way through delivery. Record when implementation was ready, when required jobs could start, when feedback arrived, and when the deployed behavior was verified. Count interventions and retries alongside elapsed time. That gives you a better chance of fixing the part that is actually slowing the work.

For teams with long queues, inspect admission rules and actual job overlap before choosing a capacity increase. Then check memory, database load, and failure rates as concurrency rises. A faster successful run is encouraging; a higher rate of failed runs may erase the gain across a week of work.

For teams spending a lot of agent effort on CI, inspect the conversation around a run. Repeated status checks, large log dumps, and ambiguous results are opportunities to improve the interface. A concise failure summary, an exact link to the failing check, or a tool that waits for a terminal result can remove work without changing the tests.

Measure agent usage against completed, verified changes, while keeping track of differences in task difficulty and model settings. Keep CI compute costs in view too. Additional concurrency may be worthwhile because it reduces delivery time even when token usage barely changes. That can still be a good investment. It just needs to be measured as a delivery improvement.

After more than four months of changes, we pay much closer attention to what happens after the first implementation is ready. We still need careful review and convincing tests. We also need the answers from those tests to arrive soon enough that the next change does not pile up behind them. That is where much of our development speed now comes from.
