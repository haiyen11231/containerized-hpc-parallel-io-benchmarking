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

HERE = os.path.dirname(__file__)
RESULTS = os.path.join(HERE, "..", "results")
FIG_DIR = os.path.join(HERE, "figures")

RANK = 1
STALL_S = 29.0
VARIANT_COLOR = {"native": "#1f77b4", "container": "#ff7f0e"}
VARIANT_LABEL = {"native": "Native", "container": "Container"}
CASE_LABEL = {"mpiio_shared_t64k_lockdefault": "default locking",
              "mpiio_shared_t64k_lock3": "lock fix (alg. 3)"}
# Top to bottom
LANES = [("native", "mpiio_shared_t64k_lockdefault"),
         ("container", "mpiio_shared_t64k_lockdefault"),
         ("native", "mpiio_shared_t64k_lock3"),
         ("container", "mpiio_shared_t64k_lock3")]
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


def main():
    fig, ax = plt.subplots(figsize=(12, 4.6))
    height = 0.6
    for i, (variant, case) in enumerate(LANES):
        y = len(LANES) - 1 - i
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
            note = (f"{len(stalls)} stalls of ~30 s = {stalled:.0f} s "
                    f"({stalled / end * 100:.0f}% of {end:.0f} s)")
        else:
            total = ior_time(variant, case)
            note = (f"no stalls: write calls end at {end:.1f} s"
                    + (f" (IOR total {total:.1f} s incl. flush at close)" if total else ""))
        ax.annotate(note, (end, y), textcoords="offset points", xytext=(8, -4),
                    fontsize=9, color="#333333")
    ax.set_yticks(range(len(LANES)))
    ax.set_yticklabels([f"{VARIANT_LABEL[v]}\n{CASE_LABEL[c]}" for v, c in reversed(LANES)],
                       fontsize=9)
    ax.set_xlim(-5, 360)
    ax.set_ylim(-0.7, len(LANES) - 0.3)
    ax.set_xlabel("Time since first MPI_File_write_at_all (s)")
    ax.grid(axis="x", alpha=0.3)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.suptitle("IOR MPI-IO + Shared, -t 64k, one repetition on tate01 (16 ranks) -- Recorder trace of rank 1\n"
                 "full bars = MPI_File_write_at_all calls >= 29 s (waiting on the NFS file lock), "
                 "thin band = normal writing", fontsize=10)
    os.makedirs(FIG_DIR, exist_ok=True)
    path = os.path.join(FIG_DIR, "ior_recorder_timeline.png")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  wrote {path}")


if __name__ == "__main__":
    main()
