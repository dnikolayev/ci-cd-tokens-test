#!/usr/bin/env python3
"""Plot stable observations across planned CI caps; requires matplotlib for the figure."""

import argparse
from pathlib import Path

from report import prepare, read_records


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("--output", type=Path, default=Path("results/pilot.png"))
    args = parser.parse_args()
    rows = [row for row in prepare(read_records(args.results)) if row["fault"] == "none"]
    if not rows:
        raise ValueError("No stable trials to plot")
    caps = rows[0]["planned_caps"]
    positions = list(range(len(caps)))
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 3, figsize=(11, 4.6))
    colors = {"poll": "#1261a0", "wait": "#b95016"}
    fields = (("elapsed_seconds", "Agent elapsed time", "seconds", 1),
              ("total_tokens", "Total token count", "thousands of tokens", 1000),
              ("uncached_input_tokens", "Uncached input", "thousands of tokens", 1000))
    for axis, (field, title, label, scale) in zip(axes, fields):
        for monitor, color in colors.items():
            repeats = sorted({row["repeat"] for row in rows if row["monitor"] == monitor})
            for index, repeat in enumerate(repeats):
                by_cap = {row["parallel"]: row for row in rows if row["monitor"] == monitor and row["repeat"] == repeat}
                observations = [by_cap.get(cap) for cap in caps]
                values = [row[field] / scale if row is not None and row[field] is not None else float("nan")
                          for row in observations]
                axis.plot(positions, values, color=color, alpha=.8,
                          marker="o" if repeat % 2 else "s", linewidth=1.5,
                          linestyle="--" if any(row is not None and not row["success"] for row in observations) else "-",
                          label=monitor if index == 0 else None)
                for position, row in enumerate(observations):
                    if row is not None and not row["success"] and row[field] is not None:
                        axis.plot(position, row[field] / scale, marker="x", color="black", markersize=10, markeredgewidth=2)
        axis.set(title=title, ylabel=label, xticks=positions, xticklabels=[str(cap) for cap in caps],
                 xlim=(-.2, len(caps) - .8), ylim=(0, None))
        axis.grid(axis="y", alpha=.2)
        axis.set_xlabel("Requested concurrency cap")
    axes[0].legend(frameon=False)
    fig.suptitle("Same checks, different CI scheduling and observation", x=.06, ha="left", fontsize=14)
    fig.text(.06, .02, f"{rows[0]['job_count']} jobs per workflow. Each line is one repetition without an injected failure. Total includes cached input.\n"
             "Dashed lines include a failed verification, marked x; its shorter duration is not a speedup.\n"
             "Gaps indicate missing or unknown values. Counts are not subscription quota or financial savings.", fontsize=9, color="#444444")
    fig.tight_layout(rect=(0, .12, 1, .91))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=170, metadata={"Software": "matplotlib"})
    plt.close(fig)


if __name__ == "__main__":
    main()
