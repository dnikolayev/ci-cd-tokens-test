# Synthetic CI pilot report

All 8 recorded trials are included; 8/8 completed verification.

Each workflow schedules 32 jobs. Intended concurrency caps: 4, 8, 16, 32.

Means include failed trials. A metric is unknown if any contributing trial lacks it. Tokens per success include all trials in the numerator and require complete usage; n/a means no successes. Input includes cached input. These are token counts, not allowance percentages or monetary savings.

## Timing and verification

| Fault | Monitor | Cap | N | Successes | Mean agent s | Mean CI s | Mean observer calls |
| --- | --- | --- | --- | --- | --- | --- | --- |
| none | poll | 4 | 1 | 1/1 | 194.9 | 183.4 | 12.0 |
| none | poll | 8 | 1 | 1/1 | 114.8 | 106.1 | 7.0 |
| none | poll | 16 | 1 | 1/1 | 74.7 | 57.6 | 4.0 |
| none | poll | 32 | 1 | 1/1 | 81.7 | 57.9 | 4.0 |
| none | wait | 4 | 1 | 1/1 | 194.8 | 182.2 | 1.0 |
| none | wait | 8 | 1 | 1/1 | 123.4 | 98.4 | 1.0 |
| none | wait | 16 | 1 | 1/1 | 70.1 | 56.6 | 1.0 |
| none | wait | 32 | 1 | 1/1 | 56.7 | 35.6 | 1.0 |

CI time runs from dispatch to observer verification, including queueing and detection delay. Agent time also includes model startup and response.

## Token usage

| Fault | Monitor | Cap | Mean input | Mean cached | Mean uncached | Mean output | Mean total | Tokens/success |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | poll | 4 | 446,878.0 | 423,424.0 | 23,454.0 | 1,348.0 | 448,226.0 | 448,226.0 |
| none | poll | 8 | 377,754.0 | 349,184.0 | 28,570.0 | 906.0 | 378,660.0 | 378,660.0 |
| none | poll | 16 | 127,459.0 | 108,032.0 | 19,427.0 | 465.0 | 127,924.0 | 127,924.0 |
| none | poll | 32 | 225,969.0 | 198,784.0 | 27,185.0 | 839.0 | 226,808.0 | 226,808.0 |
| none | wait | 4 | 179,158.0 | 159,104.0 | 20,054.0 | 798.0 | 179,956.0 | 179,956.0 |
| none | wait | 8 | 101,998.0 | 82,688.0 | 19,310.0 | 660.0 | 102,658.0 | 102,658.0 |
| none | wait | 16 | 122,810.0 | 117,888.0 | 4,922.0 | 423.0 | 123,233.0 | 123,233.0 |
| none | wait | 32 | 75,902.0 | 49,920.0 | 25,982.0 | 456.0 | 76,358.0 | 76,358.0 |

## Paired differences: baseline minus comparison

The baseline is the smallest intended cap, 4. Positive values mean the baseline trial used more time or tokens. Pairs retain failed and missing conditions. A failed verification is not a faster successful result; pairs containing one are not valid completion-time comparisons. These observations do not establish a general saving.

| Fault | Monitor | Repeat | Baseline cap | Comparison cap | Success baseline / comparison | Agent s | CI s | Total tokens | Uncached input | Observer calls |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | poll | 1 | 4 | 8 | yes / yes | 80.1 | 77.3 | 69,566 | -5,116 | 5 |
| none | poll | 1 | 4 | 16 | yes / yes | 120.2 | 125.8 | 320,302 | 4,027 | 8 |
| none | poll | 1 | 4 | 32 | yes / yes | 113.2 | 125.5 | 221,418 | -3,731 | 8 |
| none | wait | 1 | 4 | 8 | yes / yes | 71.4 | 83.8 | 77,298 | 744 | 0 |
| none | wait | 1 | 4 | 16 | yes / yes | 124.7 | 125.6 | 56,723 | 15,132 | 0 |
| none | wait | 1 | 4 | 32 | yes / yes | 138.1 | 146.6 | 103,598 | -5,928 | 0 |

## Individual trials

| Row | Fault | Monitor | Cap | Repeat | Success | Agent s | CI s | Total tokens | Workflow |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | none | poll | 8 | 1 | yes | 114.8 | 106.1 | 378,660 | [38261510213](https://github.com/dnikolayev/ci-cd-tokens-test/actions/runs/38261510213) |
| 2 | none | poll | 16 | 1 | yes | 74.7 | 57.6 | 127,924 | [38261753119](https://github.com/dnikolayev/ci-cd-tokens-test/actions/runs/38261753119) |
| 3 | none | poll | 32 | 1 | yes | 81.7 | 57.9 | 226,808 | [38261917901](https://github.com/dnikolayev/ci-cd-tokens-test/actions/runs/38261917901) |
| 4 | none | poll | 4 | 1 | yes | 194.9 | 183.4 | 448,226 | [38262061715](https://github.com/dnikolayev/ci-cd-tokens-test/actions/runs/38262061715) |
| 5 | none | wait | 8 | 1 | yes | 123.4 | 98.4 | 102,658 | [38262486087](https://github.com/dnikolayev/ci-cd-tokens-test/actions/runs/38262486087) |
| 6 | none | wait | 32 | 1 | yes | 56.7 | 35.6 | 76,358 | [38262718124](https://github.com/dnikolayev/ci-cd-tokens-test/actions/runs/38262718124) |
| 7 | none | wait | 16 | 1 | yes | 70.1 | 56.6 | 123,233 | [38262839713](https://github.com/dnikolayev/ci-cd-tokens-test/actions/runs/38262839713) |
| 8 | none | wait | 4 | 1 | yes | 194.8 | 182.2 | 179,956 | [38262984512](https://github.com/dnikolayev/ci-cd-tokens-test/actions/runs/38262984512) |
