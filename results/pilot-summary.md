# Synthetic CI pilot report

All 12 recorded trials are included; 11/12 completed verification.

Each workflow schedules 4 jobs. Intended concurrency caps: 1, 4.

Means include failed trials. A metric is unknown if any contributing trial lacks it. Tokens per success include all trials in the numerator and require complete usage; n/a means no successes. Input includes cached input. These are token counts, not allowance percentages or monetary savings.

## Timing and verification

| Fault | Monitor | Cap | N | Successes | Mean agent s | Mean CI s | Mean observer calls |
| --- | --- | --- | --- | --- | --- | --- | --- |
| none | poll | 1 | 2 | 2/2 | 104.0 | 91.5 | 5.5 |
| none | poll | 4 | 2 | 1/2 | 45.2 | unknown | 2.0 |
| none | wait | 1 | 2 | 2/2 | 108.2 | 97.7 | 1.0 |
| none | wait | 4 | 2 | 2/2 | 48.1 | 37.0 | 1.0 |
| once | poll | 1 | 1 | 1/1 | 152.4 | 128.0 | 8.0 |
| once | poll | 4 | 1 | 1/1 | 80.6 | 68.9 | 4.0 |
| once | wait | 1 | 1 | 1/1 | 153.1 | 131.7 | 1.0 |
| once | wait | 4 | 1 | 1/1 | 83.4 | 69.1 | 1.0 |

CI time runs from dispatch to observer verification, including queueing and detection delay. Agent time also includes model startup and response.

## Token usage

| Fault | Monitor | Cap | Mean input | Mean cached | Mean uncached | Mean output | Mean total | Tokens/success |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | poll | 1 | 358,884.0 | 336,512.0 | 22,372.0 | 1,180.5 | 360,064.5 | 360,064.5 |
| none | poll | 4 | 88,906.0 | 66,240.0 | 22,666.0 | 354.5 | 89,260.5 | 178,521.0 |
| none | wait | 1 | 165,771.5 | 138,816.0 | 26,955.5 | 626.0 | 166,397.5 | 166,397.5 |
| none | wait | 4 | 137,514.5 | 102,144.0 | 35,370.5 | 483.5 | 137,998.0 | 137,998.0 |
| once | poll | 1 | 234,899.0 | 206,464.0 | 28,435.0 | 1,217.0 | 236,116.0 | 236,116.0 |
| once | poll | 4 | 352,161.0 | 331,264.0 | 20,897.0 | 908.0 | 353,069.0 | 353,069.0 |
| once | wait | 1 | 127,635.0 | 108,288.0 | 19,347.0 | 566.0 | 128,201.0 | 128,201.0 |
| once | wait | 4 | 127,243.0 | 100,608.0 | 26,635.0 | 601.0 | 127,844.0 | 127,844.0 |

## Paired differences: baseline minus comparison

The baseline is the smallest intended cap, 1. Positive values mean the baseline trial used more time or tokens. Pairs retain failed and missing conditions. A failed verification is not a faster successful result; pairs containing one are not valid completion-time comparisons. These observations do not establish a general saving.

| Fault | Monitor | Repeat | Baseline cap | Comparison cap | Success baseline / comparison | Agent s | CI s | Total tokens | Uncached input | Observer calls |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | poll | 1 | 1 | 4 | yes / yes | 50.7 | 52.4 | 282,236 | 3,233 | 2 |
| none | poll | 2 | 1 | 4 | yes / no | 67.0 | unknown | 259,372 | -3,821 | 5 |
| none | wait | 1 | 1 | 4 | yes / yes | 56.7 | 58.9 | 51,769 | -17,759 | 0 |
| none | wait | 2 | 1 | 4 | yes / yes | 63.3 | 62.5 | 5,030 | 929 | 0 |
| once | poll | 1 | 1 | 4 | yes / yes | 71.8 | 59.1 | -116,953 | 7,538 | 4 |
| once | wait | 1 | 1 | 4 | yes / yes | 69.8 | 62.6 | 357 | -7,288 | 0 |

## Individual trials

| Row | Fault | Monitor | Cap | Repeat | Success | Agent s | CI s | Total tokens | Workflow |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | none | wait | 4 | 1 | yes | 52.0 | 38.9 | 127,333 | [38255971628](https://github.com/dnikolayev/ci-cd-tokens-test/actions/runs/38255971628) |
| 2 | none | wait | 1 | 1 | yes | 108.7 | 97.8 | 179,102 | [38256064162](https://github.com/dnikolayev/ci-cd-tokens-test/actions/runs/38256064162) |
| 3 | none | poll | 4 | 2 | no | 34.1 | unknown | 77,207 | [38256303070](https://github.com/dnikolayev/ci-cd-tokens-test/actions/runs/38256303070) |
| 4 | none | poll | 1 | 2 | yes | 101.1 | 90.1 | 336,579 | [38256374563](https://github.com/dnikolayev/ci-cd-tokens-test/actions/runs/38256374563) |
| 5 | once | wait | 1 | 1 | yes | 153.1 | 131.7 | 128,201 | [38256602671](https://github.com/dnikolayev/ci-cd-tokens-test/actions/runs/38256602671) |
| 6 | once | wait | 4 | 1 | yes | 83.4 | 69.1 | 127,844 | [38256892145](https://github.com/dnikolayev/ci-cd-tokens-test/actions/runs/38256892145) |
| 7 | once | poll | 4 | 1 | yes | 80.6 | 68.9 | 353,069 | [38257060782](https://github.com/dnikolayev/ci-cd-tokens-test/actions/runs/38257060782) |
| 8 | once | poll | 1 | 1 | yes | 152.4 | 128.0 | 236,116 | [38257241173](https://github.com/dnikolayev/ci-cd-tokens-test/actions/runs/38257241173) |
| 9 | none | poll | 4 | 1 | yes | 56.2 | 40.5 | 101,314 | [38257519133](https://github.com/dnikolayev/ci-cd-tokens-test/actions/runs/38257519133) |
| 10 | none | poll | 1 | 1 | yes | 106.9 | 92.9 | 383,550 | [38257632107](https://github.com/dnikolayev/ci-cd-tokens-test/actions/runs/38257632107) |
| 11 | none | wait | 4 | 2 | yes | 44.3 | 35.0 | 148,663 | [38257834106](https://github.com/dnikolayev/ci-cd-tokens-test/actions/runs/38257834106) |
| 12 | none | wait | 1 | 2 | yes | 107.6 | 97.5 | 153,693 | [38257928210](https://github.com/dnikolayev/ci-cd-tokens-test/actions/runs/38257928210) |
