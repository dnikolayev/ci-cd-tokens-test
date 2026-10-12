#!/usr/bin/env python3
"""A bounded, synthetic comparison of CI scheduling and agent observation."""

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import random
import re
import signal
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parent
TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
                "output_tokens", "reasoning_output_tokens")


def expected_jobs(count=4):
    if type(count) is not int or count not in (4, 32):
        raise ValueError("Workload must contain 4 or 32 jobs")
    return {f"synthetic ({n})" for n in range(1, count + 1)}


def command(args, **kwargs):
    return subprocess.run(args, text=True, capture_output=True, check=True,
                          timeout=60, **kwargs).stdout


def gh(*args):
    return command(["gh", *args])


def api(path):
    return json.loads(gh("api", path))


def save(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n")
    tmp.replace(path)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def epoch(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def clean_job(job, attempt):
    # Only public workflow metadata is retained, never log text or runner labels.
    steps = {step["name"]: step.get("conclusion") for step in job.get("steps", [])}
    return {"attempt": attempt, **{key: job.get(key) for key in
            ("id", "name", "status", "conclusion", "created_at", "started_at", "completed_at")},
            "checks_conclusion": steps.get("Run unchanged checks"),
            "hold_conclusion": steps.get("Hold and optionally fail")}


def matches_jobs(jobs, expected, attempt):
    return (len(jobs) == len(expected) and {j["name"] for j in jobs} == set(expected)
            and all(j.get("status") == "completed" and j.get("attempt") == attempt
                    and j.get("conclusion") == expected[j["name"]]
                    and j.get("checks_conclusion") == "success"
                    and j.get("hold_conclusion") == expected[j["name"]] for j in jobs))


def carried_forward(job, first):
    fields = ("name", "status", "conclusion", "checks_conclusion", "hold_conclusion",
              "started_at", "completed_at")
    return any(old.get("conclusion") == "success" and old.get("started_at") and old.get("completed_at")
               and all(job.get(field) == old.get(field) for field in fields) for old in first)


def accepted(attempts, fault, job_count=4):
    if not attempts or len(attempts) != (2 if fault == "once" else 1):
        return False
    names = expected_jobs(job_count)
    expected = {name: "success" for name in names}
    if fault == "once":
        expected["synthetic (1)"] = "failure"
    if not matches_jobs(attempts[0], expected, 1):
        return False
    if fault == "once":
        retry = attempts[1]
        if len(retry) != len({j["name"] for j in retry}) or any(j["name"] not in names for j in retry):
            return False
        if not matches_jobs(retry, {j["name"]: "success" for j in retry}, 2):
            return False
        executed = [j for j in retry if not carried_forward(j, attempts[0])]
        return matches_jobs(executed, {"synthetic (1)": "success"}, 2)
    return True


def usage(events):
    completed = [e for e in events if e.get("type") == "turn.completed"]
    if len(completed) != 1:
        raise ValueError("Expected one terminal usage event from one fresh agent turn")
    data = completed[0]["usage"]
    result = {field: data.get(field) for field in TOKEN_FIELDS}
    for field, value in result.items():
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError(f"Invalid usage field: {field}")
    if not result["input_tokens"] or result["output_tokens"] is None:
        raise ValueError("Missing required token counters")
    cached = result["cached_input_tokens"]
    if cached is not None and cached > result["input_tokens"]:
        raise ValueError("Cached input exceeds total input")
    result["uncached_input_tokens"] = (None if cached is None else result["input_tokens"] - cached)
    result["total_tokens"] = result["input_tokens"] + result["output_tokens"]
    return result


def observe(path):
    state = json.loads(path.read_text())
    names = expected_jobs(state.get("job_count", 4))
    state["observer_invocations"] += 1
    if state.get("terminal"):
        print(json.dumps({"terminal": True, "accepted": state["accepted"]}))
        save(path, state)
        return
    base = f"repos/{state['repo']}/actions"
    if not state.get("dispatch_started"):
        state["dispatch_started"] = now()
        save(path, state)  # Never silently dispatch twice after an uncertain API outcome.
        gh("workflow", "run", "synthetic.yml", "--repo", state["repo"], "--ref", state["ref"],
           "-f", f"trial={state['trial']}", "-f", f"parallel={state['parallel']}",
           "-f", f"jobs={state.get('job_count', 4)}",
           "-f", f"hold={state['hold_seconds']}", "-f", f"fault={state['fault']}")
    deadline = epoch(state["dispatch_started"]) + state["timeout_seconds"]
    while time.time() < deadline:
        time.sleep(state["poll_seconds"])
        state["api_polls"] += 1
        if not state.get("run_id"):
            runs = api(f"{base}/workflows/synthetic.yml/runs?event=workflow_dispatch&per_page=100")["workflow_runs"]
            matches = [r for r in runs if r["display_title"] == f"trial-{state['trial']}"]
            if len(matches) > 1:
                raise ValueError("Ambiguous dispatch identifier")
            if matches:
                state["run_id"] = matches[0]["id"]
        if state.get("run_id"):
            run = api(f"{base}/runs/{state['run_id']}")
            if run["head_sha"] != state["source_sha"]:
                raise ValueError("Workflow source changed before dispatch")
            state["workflow_created_at"] = run["created_at"]
            state["workflow_updated_at"] = run["updated_at"]
            attempt = run["run_attempt"]
            if run["status"] == "completed":
                jobs = api(f"{base}/runs/{state['run_id']}/attempts/{attempt}/jobs?per_page=100")["jobs"]
                if len(state["attempts"]) < attempt:
                    cleaned = [clean_job(j, attempt) for j in jobs]
                    if attempt > 1 and state["attempts"]:
                        for job in cleaned:
                            if carried_forward(job, state["attempts"][0]):
                                job["carried_forward_from_attempt"] = 1
                    state["attempts"].append(cleaned)
                expected_failure = (state["fault"] == "once" and attempt == 1
                    and matches_jobs(state["attempts"][0],
                        {name: "failure" if name == "synthetic (1)" else "success" for name in names}, 1))
                if expected_failure and not state.get("retry_requested"):
                    state["retry_requested"] = now()
                    save(path, state)
                    gh("run", "rerun", str(state["run_id"]), "--failed", "--repo", state["repo"])
                elif expected_failure and state.get("retry_requested"):
                    pass  # The rerun request can take a moment to become visible.
                else:
                    state["accepted"] = accepted(state["attempts"], state["fault"], state.get("job_count", 4))
                    state["terminal"] = True
                    state["verified_at"] = now()
            state["last_status"] = run["status"]
        save(path, state)
        if state.get("terminal") or state["monitor"] == "poll":
            print(json.dumps({"terminal": bool(state.get("terminal")),
                              "accepted": bool(state.get("accepted")),
                              "status": state.get("last_status", "dispatching")}))
            return
    state.update(terminal=True, accepted=False, timed_out=True, verified_at=now())
    save(path, state)
    print(json.dumps({"terminal": True, "accepted": False, "status": "timeout"}))


def job_metrics(attempts):
    jobs = [j for attempt in attempts for j in attempt if not j.get("carried_forward_from_attempt")]
    intervals = [(epoch(j["started_at"]), epoch(j["completed_at"])) for j in jobs
                 if j.get("started_at") and j.get("completed_at")]
    if any(end < start for start, end in intervals):
        raise ValueError("Job completion precedes its start")
    changes = sorted([(start, 1) for start, end in intervals] + [(end, -1) for start, end in intervals])
    current = peak = 0
    for _, delta in changes:
        current += delta
        peak = max(peak, current)
    return {"job_seconds": sum(end - start for start, end in intervals),
            "peak_overlapping_jobs": peak,
            "job_span_seconds": (max(end for _, end in intervals) - min(start for start, _ in intervals)) if intervals else None}


def run_trial(args, spec, order):
    trial = uuid.uuid4().hex
    directory = ROOT / ".runs" / trial
    directory.mkdir(parents=True)
    path = directory / "state.json"
    source = command(["git", "rev-parse", "HEAD"], cwd=ROOT).strip()
    remote = api(f"repos/{args.repo}/git/ref/heads/{args.ref}")["object"]["sha"]
    if source != remote:
        raise ValueError("Local HEAD must match the remote workflow branch")
    command(["git", "diff", "--exit-code", "HEAD"], cwd=ROOT)
    state = dict(spec, trial=trial, repo=args.repo, ref=args.ref, source_sha=source,
                 order=order, hold_seconds=args.hold, poll_seconds=args.poll,
                 timeout_seconds=args.timeout, observer_invocations=0, api_polls=0, attempts=[])
    save(path, state)
    relative = path.relative_to(ROOT).as_posix()
    prompt = ("This is a bounded CI observation task. Run exactly this command, repeating it only when it returns terminal=false: "
              f"python3 benchmark.py observe {relative}\n"
              "If the shell tool yields a running session, wait on that same session with the longest supported wait. "
              "Do not start another command while it runs. The helper dispatches one synthetic workflow, verifies its jobs, "
              "and handles its single permitted retry. Do not inspect files, edit code, use other commands, browse, "
              "delegate, or manually retry a workflow. When terminal=true, reply exactly VERIFIED if accepted=true, "
              "otherwise FAILED. If the command errors, reply FAILED. No commentary or extra investigation is needed.")
    save(directory / "prompt.json", {"prompt": prompt})
    cli = ["codex", "exec", "--ignore-rules", "--ephemeral",
           "--json", "--color", "never", "--sandbox", "workspace-write",
           "--disable", "hooks", "-c", "notify=[]",
           "-c", "sandbox_workspace_write.network_access=true", "-c", "project_doc_max_bytes=0",
           "-m", args.model, "-c", f'model_reasoning_effort="{args.reasoning}"', prompt]
    if not args.use_user_config:
        cli.insert(2, "--ignore-user-config")
    start = time.monotonic()
    started_at = now()
    timed_out = False
    with (directory / "events.jsonl").open("w") as out, (directory / "stderr.log").open("w") as err:
        process = subprocess.Popen(cli, cwd=ROOT, stdout=out, stderr=err, start_new_session=True)
        try:
            exit_code = process.wait(timeout=args.timeout + 180)
        except subprocess.TimeoutExpired:
            timed_out, exit_code = True, None
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    elapsed = time.monotonic() - start
    state = json.loads(path.read_text())
    events = []
    malformed_events = 0
    for line in (directory / "events.jsonl").read_text().splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            malformed_events += 1
    items = [e["item"] for e in events if e.get("type") == "item.completed"]
    messages = [i.get("text", "") for i in items if i.get("type") == "agent_message"]
    counters, measurement_error = None, None
    try:
        counters = usage(events)
    except (ValueError, KeyError):
        measurement_error = "missing_or_invalid_terminal_usage"
    # Explicit public whitelist: no transcript, local paths, account state or environment.
    result = {key: state.get(key) for key in
              ("trial", "repo", "ref", "source_sha", "order", "repeat", "parallel", "monitor", "fault",
               "job_count", "planned_caps",
               "hold_seconds", "poll_seconds", "timeout_seconds", "observer_invocations", "api_polls",
               "run_id", "dispatch_started", "workflow_created_at", "workflow_updated_at", "verified_at", "attempts")}
    result.update(model=args.model, reasoning=args.reasoning,
                  use_user_config=args.use_user_config,
                  cli_version=command(["codex", "--version"]).strip(), started_at=started_at,
                  elapsed_seconds=round(elapsed, 3), usage=counters,
                  measurement_error=measurement_error, malformed_events=malformed_events,
                  agent_exit_code=exit_code, agent_timed_out=timed_out,
                  completed_agent_commands=sum(i.get("type") == "command_execution" for i in items),
                  verified=bool(state.get("accepted")),
                  success=bool(state.get("accepted")) and exit_code == 0 and bool(messages) and messages[-1].strip() == "VERIFIED",
                  **job_metrics(state["attempts"]))
    save(directory / "result.json", result)
    try:
        if not state.get("run_id") and state.get("dispatch_started"):
            runs = api(f"repos/{args.repo}/actions/workflows/synthetic.yml/runs?event=workflow_dispatch&per_page=100")["workflow_runs"]
            owned = [r for r in runs if r["display_title"] == f"trial-{trial}"]
            if len(owned) > 1:
                raise ValueError("Ambiguous dispatch during cleanup")
            if owned:
                state["run_id"] = result["run_id"] = owned[0]["id"]
        if state.get("run_id"):
            endpoint = f"repos/{args.repo}/actions/runs/{state['run_id']}"
            current = api(endpoint)
            if current["status"] != "completed":
                gh("run", "cancel", str(state["run_id"]), "--repo", args.repo)
                result["cleanup_cancel_requested"] = True
                for _ in range(6):
                    time.sleep(2)
                    current = api(endpoint)
                    if current["status"] == "completed":
                        break
            result["cleanup_terminal_confirmed"] = current["status"] == "completed"
    except (subprocess.SubprocessError, ValueError, KeyError) as error:
        result["cleanup_error_type"] = type(error).__name__
    save(directory / "result.json", result)
    return result


def pilot(args):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo):
        raise ValueError("Expected owner/repository")
    if not 5 <= args.hold <= 60 or not 5 <= args.poll <= 60:
        raise ValueError("Hold and poll must be between 5 and 60 seconds")
    if not 0 <= args.repeats <= 20 or not 0 <= args.fault_repeats <= 20 or not args.repeats + args.fault_repeats:
        raise ValueError("Use 0 to 20 repetitions per scenario and at least one overall")
    if not 60 <= args.timeout <= 1800:
        raise ValueError("Timeout must be between 60 and 1800 seconds")
    expected_jobs(args.jobs)
    if (not args.caps or len(set(args.caps)) != len(args.caps)
            or any(cap not in (1, 4, 8, 16, 32) or cap > args.jobs for cap in args.caps)):
        raise ValueError("Caps must be distinct supported values no larger than the fixed workload")
    rng = random.Random(args.seed)
    groups = [(fault, repeat, monitor) for fault, count in (("none", args.repeats), ("once", args.fault_repeats))
              for repeat in range(1, count + 1) for monitor in ("poll", "wait")]
    rng.shuffle(groups)
    specs = []
    for fault, repeat, monitor in groups:
        caps = list(args.caps)
        rng.shuffle(caps)
        specs.extend(dict(fault=fault, repeat=repeat, monitor=monitor, parallel=cap,
                          job_count=args.jobs, planned_caps=sorted(args.caps)) for cap in caps)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise ValueError("Refusing to overwrite an existing result file")
    save(args.output.with_suffix(".plan.json"), dict(seed=args.seed, trials=specs))
    with args.output.open("x") as output:
        for order, spec in enumerate(specs, 1):
            print(json.dumps({"starting": order, "total": len(specs), **spec}), flush=True)
            try:
                result = run_trial(args, spec, order)
            except Exception as error:
                output.write(json.dumps({**spec, "order": order, "success": False, "usage": None,
                                         "measurement_error": "harness_error", "error_type": type(error).__name__}) + "\n")
                output.flush()
                raise
            output.write(json.dumps(result) + "\n")
            output.flush()
            print(json.dumps({"finished": order, "success": result["success"],
                              "elapsed_seconds": result["elapsed_seconds"], "usage": result["usage"]}), flush=True)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    observer = commands.add_parser("observe", help="Internal command used by the agent")
    observer.add_argument("state", type=Path)
    run = commands.add_parser("pilot", help="Run paired trials sequentially; uses authenticated gh and codex")
    run.add_argument("--repo", required=True)
    run.add_argument("--ref", default="main")
    run.add_argument("--model", required=True)
    run.add_argument("--reasoning", required=True)
    run.add_argument("--use-user-config", action="store_true",
                     help="Load existing user configuration when required by your host; record this choice")
    run.add_argument("--repeats", type=int, default=2)
    run.add_argument("--fault-repeats", type=int, default=1)
    run.add_argument("--jobs", type=int, choices=(4, 32), default=4,
                     help="Keep this workload size fixed across all caps")
    run.add_argument("--caps", type=int, nargs="+", choices=(1, 4, 8, 16, 32), default=[1, 4])
    run.add_argument("--hold", type=int, default=15)
    run.add_argument("--poll", type=int, default=10)
    run.add_argument("--timeout", type=int, default=600)
    run.add_argument("--seed", type=int, default=20261012)
    run.add_argument("--output", type=Path, default=Path(".runs/pilot.jsonl"))
    args = parser.parse_args()
    if args.command == "observe":
        observe(args.state)
    else:
        pilot(args)


if __name__ == "__main__":
    main()
