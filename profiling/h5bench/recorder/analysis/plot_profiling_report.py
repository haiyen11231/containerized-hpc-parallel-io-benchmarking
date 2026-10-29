#!/usr/bin/env python3
"""
Intra-node profiling comparison: contig_contig and interleaved_contig,
native vs container.

Panel A (performance, the actual finding): Darshan's agg_time_by_slowest
(seconds) -- the only timing source trusted for performance comparison in
this project. Recorder's own completion-timing was independently confirmed
to be unreliable (every Recorder-instrumented run, both variants, reported
7-11x the throughput Darshan measured for the identical write -- a
measurement artifact, not real I/O speed), so Recorder's own wall-clock
numbers are deliberately NOT used here for the performance claim.

Panel B (mechanism evidence): Recorder's POSIX/MPI/MPI-IO/HDF5 call counts,
from the matched native+container run submitted together in the same batch.
This is NOT a timing comparison -- it's call-structure content, confirmed
stable to within <0.1% across 5 independent repeated runs for native, and
bit-for-bit IDENTICAL across all 5 runs for container -- so which run it's
drawn from does not affect the conclusion.
"""
import matplotlib.pyplot as plt
import numpy as np

COMBOS = ["contig_contig", "interleaved_contig"]
COMBO_LABELS = ["CONTIG_CONTIG", "INTERLEAVED_CONTIG"]

# ---- Panel A: Darshan agg_time_by_slowest (seconds), POSIX module ----
# Source: profiling/h5bench/darshan/results/{native,container}/<combo>/darshan_perf_summary.txt
darshan_time_s = {
    "native":    [79.386387, 91.854356],
    "container": [118.768835, 159.329036],
}

# ---- Panel B: Recorder call counts, matched current run ----
# Source: profiling/h5bench/recorder/results/{native,container}/<combo>/recorder_summary.txt
# Confirmed stable: container identical across all 5 repeated runs;
# native varies by <0.1% across all 5 repeated runs.
recorder_counts = {
    "native": {
        "contig_contig":      {"POSIX": 1888, "MPI": 1472, "MPI-IO": 1248, "HDF5": 8768},
        "interleaved_contig": {"POSIX": 246598, "MPI": 1472, "MPI-IO": 245984, "HDF5": 6720},
    },
    "container": {
        "contig_contig":      {"POSIX": 1829, "MPI": 1472, "MPI-IO": 1248, "HDF5": 8768},
        "interleaved_contig": {"POSIX": 246565, "MPI": 1472, "MPI-IO": 245984, "HDF5": 6720},
    },
}

LAYERS = ["POSIX", "MPI", "MPI-IO", "HDF5"]
LAYER_COLORS = {"POSIX": "#4C72B0", "MPI": "#DD8452", "MPI-IO": "#55A868", "HDF5": "#C44E52"}
NATIVE_COLOR = "#2E7D32"
CONTAINER_COLOR = "#C62828"

fig, axes = plt.subplots(2, 2, figsize=(12, 9))

# --- Panel A: performance (Darshan) ---
for col, combo in enumerate(COMBOS):
    ax = axes[0, col]
    vals = [darshan_time_s["native"][col], darshan_time_s["container"][col]]
    bars = ax.bar(["Native", "Container"], vals, color=[NATIVE_COLOR, CONTAINER_COLOR], width=0.5)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 2, f"{v:.1f}s", ha="center", fontsize=10, fontweight="bold")
    slowdown = vals[1] / vals[0]
    ax.set_title(f"{COMBO_LABELS[col]}\nPerformance (Darshan, agg_time_by_slowest)\ncontainer is {slowdown:.2f}x slower", fontsize=10)
    ax.set_ylabel("Seconds (lower = better)")
    ax.set_ylim(0, max(darshan_time_s["container"]) * 1.25)
    ax.grid(axis="y", alpha=0.3)

# --- Panel B: call structure (Recorder) ---
for col, combo in enumerate(COMBOS):
    ax = axes[1, col]
    x = np.arange(2)
    bottoms = np.zeros(2)
    for layer in LAYERS:
        vals = [recorder_counts["native"][combo][layer], recorder_counts["container"][combo][layer]]
        ax.bar(x, vals, bottom=bottoms, label=layer, color=LAYER_COLORS[layer], width=0.5)
        bottoms += np.array(vals)
    ax.set_xticks(x)
    ax.set_xticklabels(["Native", "Container"])
    totals = bottoms
    for xi, t in zip(x, totals):
        ax.text(xi, t * 1.01, f"{int(t):,}", ha="center", fontsize=9, fontweight="bold")
    ax.set_title(f"{COMBO_LABELS[col]}\nCall structure (Recorder trace, call counts)", fontsize=10)
    ax.set_ylabel("Total calls traced")
    ax.set_ylim(0, max(totals) * 1.18)
    ax.grid(axis="y", alpha=0.3)
    if col == 0:
        ax.legend(fontsize=8, loc="lower right")

fig.suptitle(
    "Intra-node Native vs Container: Performance (Darshan) and Call Structure (Recorder)",
    fontsize=13, y=0.985,
)
fig.text(
    0.5, 0.945,
    "Performance verdict uses Darshan only -- Recorder's own completion-timing was confirmed unreliable\n"
    "(7-11x inflated vs Darshan on identical writes, every run); Recorder is used here for call-structure\n"
    "evidence only, confirmed stable across 5 independent repeated runs.",
    fontsize=9, ha="center", va="top", style="italic", color="#444444",
)
fig.tight_layout(rect=[0, 0, 1, 0.87])

out = "figures/intra_native_vs_container_profiling_report.png"
fig.savefig(out, dpi=150)
print(f"wrote {out}")
