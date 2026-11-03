#!/usr/bin/env python3
"""Plot the Recorder timeline of one IOR repetition: MPI-IO shared, -t 64k,
16 ranks on tate01, default OMPIO locking vs lock fix, native vs container.

Each lane is one run, seen from rank 1 -- a rank that takes no locks, so its
timestamps are reliable (see ../REPORT.md, caveats). Every
MPI_File_write_at_all call of that rank is drawn; calls >= 29 s (the NFSv4
lock back-off) are the stalls, everything else is normal writing.

Time 0 = start of the rank's first MPI_File_write_at_all.

Figure produced:
  figures/ior_recorder_timeline.png

Run:  python3 plot_timeline.py
"""
import glob
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

HERE = os.path.dirname(__file__)
RESULTS = os.path.join(HERE, "..", "results")
FIG_DIR = os.path.join(HERE, "figures")

RANK = 1
STALL_S = 29.0
VARIANT_COLOR = {"native": "#1f77b4", "container": "#ff7f0e"}
VARIANT_LABEL = {"native": "Native", "container": "Container"}
CASE_LABEL = {"mpiio_shared_t64k_lockdefault": "default locking",
              "mpiio_shared_t64k_lock3": "lock fix (alg. 3)"}
LINE = re.compile(r"^(\S+) (\S+) (\S+) ")


def write_calls(variant, case):
    paths = glob.glob(os.path.join(RESULTS, variant, case, "trace_*", "_text", f"{RANK:02d}.txt"))
    if not paths:
        return []
    calls = []
    for line in open(paths[0]):
        m = LINE.match(line)
        if m and m[3] == "MPI_File_write_at_all":
            calls.append((float(m[1]), float(m[2])))
    if not calls:
        return []
    t0 = calls[0][0]
    return [(s - t0, e - t0) for s, e in calls]


def ior_time(variant, case):
    """Total time of the IOR repetition (s), from IOR's own result line."""
    paths = glob.glob(os.path.join(RESULTS, variant, case, "ior_*.txt"))
    for line in open(paths[0]) if paths else []:
        p = line.split()
        if len(p) == 11 and p[0] == "write" and re.match(r"[0-9.]+$", p[1]):
            return float(p[9])
    return None


# Each panel covers one locking case (native + container lanes), with its
# own x-axis scaled to that case's own data -- default locking runs to ~300s,
# the lock fix to ~2s, a >100x range that a single shared linear axis can't
# show (the lock-fix lanes would be invisible slivers at x=0, as the original
# single-axis version was). Same "own scale per panel" principle already
# used elsewhere in this project's figures (e.g. IOR's own transfer-sweep
# plot) for comparisons spanning very different magnitudes.
PANELS = [
    ("default locking", "mpiio_shared_t64k_lockdefault", 310),
    ("lock fix (alg. 3)", "mpiio_shared_t64k_lock3", 2.0),
]


def plot_panel(ax, case, xmax):
    height = 0.6
    variants = ["native", "container"]
    for i, variant in enumerate(variants):
        y = len(variants) - 1 - i
        calls = write_calls(variant, case)
        if not calls:
            print(f"  [skip] {variant}/{case}: no trace")
            continue
        color = VARIANT_COLOR[variant]
        stalls = [(s, e) for s, e in calls if e - s >= STALL_S]
        others = [(s, e - s) for s, e in calls if e - s < STALL_S]
        # normal writing: thin, light band (individual calls are far too short to see)
        ax.broken_barh(others, (y - height / 4, height / 2), facecolors=color, alpha=0.35,
                       edgecolor="none")
        # stalls: full-height bars with a 2px surface gap between neighbours
        ax.broken_barh([(s, e - s) for s, e in stalls], (y - height / 2, height),
                       facecolors=color, edgecolor="white", linewidth=1.5)
        end = calls[-1][1]
        stalled = sum(e - s for s, e in stalls)
        if stalls:
            note = f"{len(stalls)} stalls = {stalled:.0f} s ({stalled / end * 100:.0f}%)"
        else:
            total = ior_time(variant, case)
            note = f"ends {end:.1f} s" + (f" (IOR total {total:.1f} s)" if total else "")
        ax.annotate(note, (end, y), textcoords="offset points", xytext=(6, -4),
                    fontsize=8, color="#333333")
    ax.set_yticks(range(len(variants)))
    ax.set_yticklabels([VARIANT_LABEL[v] for v in reversed(variants)], fontsize=9)
    ax.set_xlim(-xmax * 0.02, xmax)
    ax.set_ylim(-0.7, len(variants) - 0.3)
    ax.set_title(CASE_LABEL[case], fontsize=10)
    ax.grid(axis="x", alpha=0.3)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def main():
    fig, axes = plt.subplots(1, 2, figsize=(12, 3.6), width_ratios=[2, 1])
    for ax, (_, case, xmax) in zip(axes, PANELS):
        plot_panel(ax, case, xmax)
    fig.supxlabel("Time since first MPI_File_write_at_all (s)", fontsize=9)
    fig.suptitle("IOR MPI-IO + Shared, -t 64k -- Recorder trace, rank 1, 16 ranks (TATE)", fontsize=11)
    # Key for the two visual elements every bar is drawn from (not a finding,
    # just how to read the encoding) -- a solid full-height bar is one call
    # stalled on the NFS lock (>= 29s); the thin pale band is normal writing.
    legend_handles = [
        Patch(facecolor="#555555", label=f"stall (≥{STALL_S:.0f}s lock wait)"),
        Patch(facecolor="#555555", alpha=0.35, label="normal write"),
    ]
    fig.legend(handles=legend_handles, loc="upper center", bbox_to_anchor=(0.5, 0.88),
               ncol=2, frameon=False, fontsize=9)
    os.makedirs(FIG_DIR, exist_ok=True)
    path = os.path.join(FIG_DIR, "ior_recorder_timeline.png")
    fig.tight_layout()
    fig.subplots_adjust(top=0.72)  # reserve room above the axes for suptitle + legend
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  wrote {path}")


if __name__ == "__main__":
    main()
