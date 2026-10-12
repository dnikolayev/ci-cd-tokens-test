#!/usr/bin/env python3
"""Summarize recorded synthetic CI trials without dropping failed trials."""

import argparse
from collections import defaultdict
import datetime as dt
import json
import math
from pathlib import Path
import re
import sys

TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "uncached_input_tokens",
                "output_tokens", "total_tokens")
METRICS = ("elapsed_seconds", "ci_seconds", "observer_invocations", *TOKEN_FIELDS)
CAPS = (1, 4, 8, 16, 32)
SETTINGS = ("repo", "source_sha", "model", "reasoning", "cli_version",
            "hold_seconds", "poll_seconds", "timeout_seconds", "use_user_config", "job_count")


def timestamp(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("Trial timestamps must include a timezone")
    return parsed.timestamp()


def measurements(record):
    values = {field: record.get(field) for field in METRICS[:3]}
    start, end = record.get("dispatch_started"), record.get("verified_at")
    values["ci_seconds"] = timestamp(end) - timestamp(start) if start and end else None
    counters = record.get("usage")
    if counters is not None and not isinstance(counters, dict):
        raise ValueError("Usage must be an object or null")
    counters = counters or {}
    for field in TOKEN_FIELDS:
        value = counters.get(field)
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError(f"Invalid token count: {field}")
        values[field] = value
    input_count, cached, output = (values[field] for field in
                                   ("input_tokens", "cached_input_tokens", "output_tokens"))
    if input_count == 0:
        raise ValueError("Zero input tokens do not establish a usage measurement")
    if input_count is not None and cached is not None and cached > input_count:
        raise ValueError("Cached input exceeds total input")
    derived = {
        "uncached_input_tokens": input_count - cached if input_count is not None and cached is not None else None,
        "total_tokens": input_count + output if input_count is not None and output is not None else None,
    }
    for field, value in derived.items():
        if counters.get(field) is not None and counters[field] != value:
            raise ValueError(f"Inconsistent token count: {field}")
        values[field] = value
    for field in METRICS[:3]:
        value = values[field]
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
            raise ValueError(f"Invalid measurement: {field}")
    return values


def prepare(records):
    if not records:
        raise ValueError("No trial records")
    seen, identities = set(), set()
    prepared = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Each trial must be an object")
        if record.get("fault") not in ("none", "once") or record.get("monitor") not in ("poll", "wait"):
            raise ValueError("Each trial requires a valid fault and monitoring condition")
        job_count = record.get("job_count", 4)
        if type(job_count) is not int or job_count not in (4, 32):
            raise ValueError("Each trial requires a job count of 4 or 32")
        caps = record.get("planned_caps", [1, 4])
        if (not isinstance(caps, list) or not caps
                or any(type(cap) is not int or cap not in CAPS or cap > job_count for cap in caps)
                or len(set(caps)) != len(caps)):
            raise ValueError("Planned caps must be distinct supported values within the job count")
        if type(record.get("parallel")) is not int or record["parallel"] not in caps:
            raise ValueError("Each trial concurrency must belong to its planned caps")
        if type(record.get("repeat")) is not int or record["repeat"] < 1 or type(record.get("success")) is not bool:
            raise ValueError("Each trial requires a positive repetition and boolean success")
        key = tuple(record[field] for field in ("fault", "monitor", "repeat", "parallel"))
        if key in seen:
            raise ValueError("Duplicate trial condition within a pair; report separate batches separately")
        seen.add(key)
        if record.get("trial"):
            if record["trial"] in identities:
                raise ValueError("Duplicate trial identifier")
            identities.add(record["trial"])
        if record.get("run_id") is not None:
            if (type(record["run_id"]) is not int or record["run_id"] < 1
                    or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", record.get("repo", ""))):
                raise ValueError("Workflow links require a repository name and positive run ID")
        prepared.append({**record, **measurements(record), "job_count": job_count, "planned_caps": sorted(caps)})
    for field in SETTINGS:
        known = {record[field] for record in prepared if record.get(field) is not None}
        if len(known) > 1:
            raise ValueError(f"Mixed benchmark settings: {field}; report separate batches separately")
    if len({tuple(record["planned_caps"]) for record in prepared}) > 1:
        raise ValueError("Mixed planned caps; report separate batches separately")
    return prepared


def mean(rows, field):
    values = [row[field] for row in rows]
    return None if any(value is None for value in values) else math.fsum(values) / len(values)


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["fault"], row["monitor"], row["parallel"])].append(row)
    cells = []
    for key, group in sorted(groups.items()):
        successes = sum(row["success"] for row in group)
        cell = dict(zip(("fault", "monitor", "parallel"), key), n=len(group), successes=successes)
        cell.update({field: mean(group, field) for field in METRICS})
        if cell["total_tokens"] is None:
            cell["tokens_per_success"] = None
        elif successes:
            cell["tokens_per_success"] = sum(row["total_tokens"] for row in group) / successes
        else:
            cell["tokens_per_success"] = "n/a"
        cells.append(cell)
    return cells


def paired(rows):
    if not rows:
        return []
    baseline_cap, *comparison_caps = rows[0]["planned_caps"]
    groups = defaultdict(dict)
    for row in rows:
        groups[(row["fault"], row["monitor"], row["repeat"])][row["parallel"]] = row
    pairs = []
    for key, group in sorted(groups.items()):
        for comparison_cap in comparison_caps:
            baseline, comparison = group.get(baseline_cap), group.get(comparison_cap)
            pair = dict(zip(("fault", "monitor", "repeat"), key),
                        baseline_cap=baseline_cap, comparison_cap=comparison_cap)
            pair["successes"] = " / ".join("missing" if row is None else "yes" if row["success"] else "no"
                                               for row in (baseline, comparison))
            for field in METRICS:
                pair[field] = (baseline[field] - comparison[field]
                               if baseline is not None and comparison is not None
                               and baseline[field] is not None and comparison[field] is not None else None)
            pairs.append(pair)
    return pairs


def number(value):
    if value is None:
        return "unknown"
    if isinstance(value, str):
        return value
    return f"{value:,}" if isinstance(value, int) else f"{value:,.1f}"


def table(headers, rows):
    return "\n".join("| " + " | ".join(str(value) for value in row) + " |"
                     for row in (headers, ["---"] * len(headers), *rows))


def render(records):
    rows = prepare(records)
    cells = summarize(rows)
    parts = ["# Synthetic CI pilot report",
             f"All {len(rows)} recorded trials are included; {sum(row['success'] for row in rows)}/{len(rows)} completed verification.",
             f"Each workflow schedules {rows[0]['job_count']} jobs. Intended concurrency caps: "
             + ", ".join(str(cap) for cap in rows[0]["planned_caps"]) + ".",
             "Means include failed trials. A metric is unknown if any contributing trial lacks it. "
             "Tokens per success include all trials in the numerator and require complete usage; n/a means no successes. "
             "Input includes cached input. These are token counts, not allowance percentages or monetary savings.",
             "## Timing and verification",
             table(["Fault", "Monitor", "Cap", "N", "Successes", "Mean agent s", "Mean CI s", "Mean observer calls"],
                   [[cell["fault"], cell["monitor"], cell["parallel"], cell["n"], f"{cell['successes']}/{cell['n']}",
                     *[number(cell[field]) for field in METRICS[:3]]] for cell in cells]),
             "CI time runs from dispatch to observer verification, including queueing and detection delay. Agent time also includes model startup and response.",
             "## Token usage",
             table(["Fault", "Monitor", "Cap", "Mean input", "Mean cached", "Mean uncached", "Mean output", "Mean total", "Tokens/success"],
                   [[cell["fault"], cell["monitor"], cell["parallel"],
                     *[number(cell[field]) for field in (*TOKEN_FIELDS, "tokens_per_success")]] for cell in cells]),
             "## Paired differences: baseline minus comparison",
             f"The baseline is the smallest intended cap, {rows[0]['planned_caps'][0]}. "
             "Positive values mean the baseline trial used more time or tokens. Pairs retain failed and missing conditions. "
             "A failed verification is not a faster successful result; pairs containing one are not valid completion-time comparisons. "
             "These observations do not establish a general saving.",
             table(["Fault", "Monitor", "Repeat", "Baseline cap", "Comparison cap", "Success baseline / comparison", "Agent s", "CI s", "Total tokens", "Uncached input", "Observer calls"],
                   [[pair["fault"], pair["monitor"], pair["repeat"], pair["baseline_cap"], pair["comparison_cap"], pair["successes"],
                     *[number(pair[field]) for field in ("elapsed_seconds", "ci_seconds", "total_tokens", "uncached_input_tokens", "observer_invocations")]]
                    for pair in paired(rows)]),
             "## Individual trials",
             table(["Row", "Fault", "Monitor", "Cap", "Repeat", "Success", "Agent s", "CI s", "Total tokens", "Workflow"],
                   [[index, row["fault"], row["monitor"], row["parallel"], row["repeat"], "yes" if row["success"] else "no",
                     *[number(row[field]) for field in ("elapsed_seconds", "ci_seconds", "total_tokens")],
                     f"[{row['run_id']}](https://github.com/{row['repo']}/actions/runs/{row['run_id']})" if row.get("run_id") else "unavailable"]
                    for index, row in enumerate(rows, 1)])]
    return "\n\n".join(parts) + "\n"


def read_records(path):
    records = []
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except ValueError as error:
            raise ValueError(f"Invalid JSON on line {line_number}") from error
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = render(read_records(args.results))
        if args.output:
            if args.output.resolve() == args.results.resolve():
                raise ValueError("Report output must not overwrite its source measurements")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report)
        else:
            sys.stdout.write(report)
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
