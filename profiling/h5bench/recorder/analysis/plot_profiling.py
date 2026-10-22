"""h5bench Recorder profiling -- H7 collective-I/O comparison figure.

Counts transcribed directly from recorder2text output on the 4 H7 runs
(profiling/h5bench/recorder/scripts/logs/*.out and, for native dno_mno,
a re-run of recorder2text against the correct h5bench_write trace dir --
the original log was lost to the "one level too shallow" segfault bug).

Run:  python3 analysis/plot_profiling.py
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(__file__)
FIG_DIR = os.path.join(HERE, "figures")
os.makedirs(FIG_DIR, exist_ok=True)

# (variant, coll_data) -> (collective_calls, independent_calls)
DATA = {
    ("native", "NO"):      (0, 10306),
    ("native", "YES"):     (10240, 66),
    ("container", "NO"):   (0, 10306),
    ("container", "YES"):  (10240, 66),
}

COLOR_COLL = "#2ca02c"
COLOR_INDEP = "#7f7f7f"


def main():
    fig, ax = plt.subplots(figsize=(8, 6))
    groups = [("native", "NO"), ("native", "YES"), ("container", "NO"), ("container", "YES")]
    labels = [f"{v}\nCOLLECTIVE_DATA={c}" for v, c in groups]
    x = np.arange(len(groups))

    coll = [DATA[g][0] for g in groups]
    indep = [DATA[g][1] for g in groups]

    ax.bar(x, coll, label="MPI_File_write_at_all (collective)", color=COLOR_COLL)
    ax.bar(x, indep, bottom=coll, label="MPI_File_write_at (independent)", color=COLOR_INDEP)

    for i, (c, ind) in enumerate(zip(coll, indep)):
        if c:
            ax.text(i, c / 2, str(c), ha="center", va="center", color="white", fontsize=9, fontweight="bold")
        ax.text(i, c + ind / 2, str(ind), ha="center", va="center",
                 color="white" if ind > 500 else "black", fontsize=9, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("MPI-IO write call count")
    ax.set_title("h5bench write -- Recorder MPI-IO trace, inter-node\n"
                  "2 nodes, 256 ranks, COLLECTIVE_METADATA=NO")
    ax.legend()
    fig.tight_layout()
    out = os.path.join(FIG_DIR, "figH7_collective_recorder.png")
    fig.savefig(out, dpi=150)
    print(f"  wrote {out}")


if __name__ == "__main__":
    print("Generating h5bench Recorder profiling figure (H7)...")
    main()
