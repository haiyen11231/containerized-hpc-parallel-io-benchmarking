"""OSU optimization -- inter-node collective progress (allreduce/alltoall).

The missing half of the intra-node story in plot_optimization_intra.py:
same 5-way comparison (native, container baseline, algorithm-lock only,
UCX only, UCX+algorithm-lock), but across inter-node scale (n2/n4/n8 nodes,
128 ranks/node) instead of intra-node rank counts.

  figO7  Allreduce, inter-node: weak/strong panels, n2/n4/n8
  figO8  Alltoall,  inter-node: weak/strong panels, n2/n4/n8 -- TCP-based
         configs (container baseline AND algorithm-lock, which also rides
         on TCP) corrupt at n4/n8 regardless of forced algorithm; this is
         container TCP's connection-setup pattern hitting a scalability
         wall at Alltoall's all-pairs shape, not an algorithm-specific bug.
         UCX-only and UCX+algorithm-lock both scale cleanly to n8 -- same
         fix as everywhere else in this project (switch TCP for UCX).
         Missing baseline/alglock points at n4/n8 are that corruption, not
         a plotting bug (see the per-file skip logic in last_val_series).

Run:  python3 analysis/plot_optimization_inter.py
"""

import glob
import math
import os
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
BASE_COLL = os.path.join(HERE, "..", "..", "..", "baseline", "osu", "results", "collective", "inter_node")
OPT = os.path.join(HERE, "..", "results")
FIG_DIR = os.path.join(HERE, "figures")

NATIVE = "#1f77b4"
BASELINE = "#d62728"
ALGLOCK = "#9467bd"
UCX = "#2ca02c"
UCX_ALGLOCK = "#ff7f0e"

NODE_LIST = [2, 4, 8]

_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
        8: 2.306, 9: 2.262, 10: 2.228}


def t_crit_95(df):
    keys = sorted(k for k in _T95 if k <= df)
    return _T95[keys[-1]] if keys else 1.96


def ci95(vals):
    if len(vals) < 2:
        return 0.0
    return t_crit_95(len(vals) - 1) * st.stdev(vals) / math.sqrt(len(vals))


def last_val_series(pattern):
    """One row per file, return list of values (collective benchmarks).

    Some alglock inter-node files are corrupted by an Apptainer gRPC
    dial-timeout storm (the same TCP-exhaustion failure mode seen in the
    driver logs) instead of real OSU output -- skip unparseable lines
    rather than crash, and skip the file entirely if no valid row is found.
    """
    vals = []
    for f in sorted(glob.glob(pattern)):
        for line in open(f):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                try:
                    vals.append(float(parts[1]))
                    break
                except ValueError:
                    continue
    return vals


def save(fig, name):
    os.makedirs(FIG_DIR, exist_ok=True)
    path = os.path.join(FIG_DIR, name)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {os.path.relpath(path, HERE)}")


def fig_collective_inter_progress(bench, alg, name, title, alltoall_suffix=False):
    native_path = os.path.join(BASE_COLL, "{mode}_scaling", "native", bench, "n{n}", f"osu_{bench}_rep*.txt")
    baseline_path = os.path.join(BASE_COLL, "{mode}_scaling", "container", bench, "n{n}", f"osu_{bench}_rep*.txt")
    ucx_path = os.path.join(OPT, "collective_ucx", "{mode}", bench, "n{n}", f"osu_{bench}_rep*.txt")

    n_dir = "n{n}_alltoall" if alltoall_suffix else "n{n}"
    alglock_path = os.path.join(OPT, "collective_alglock", "{mode}", f"alg{alg}", n_dir, f"osu_{bench}_rep*.txt")
    both_path = os.path.join(OPT, "collective_ucx_alglock", "{mode}", f"alg{alg}", n_dir, f"osu_{bench}_rep*.txt")

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, mode in zip(axes, ("weak", "strong")):
        for label, color, marker, pattern_tmpl in (
            ("Native", NATIVE, "o", native_path),
            ("Container, baseline", BASELINE, "x", baseline_path),
            ("Container, algorithm-lock only", ALGLOCK, "s", alglock_path),
            ("Container, UCX only", UCX, "^", ucx_path),
            ("Container, UCX + algorithm-lock", UCX_ALGLOCK, "D", both_path),
        ):
            xs, ys, es, ns_single = [], [], [], []
            for n in NODE_LIST:
                pattern = pattern_tmpl.format(mode=mode, n=n)
                vals = last_val_series(pattern)
                if len(vals) >= 2:
                    xs.append(n); ys.append(st.mean(vals)); es.append(ci95(vals))
                elif len(vals) == 1:
                    ns_single.append((n, vals[0]))
            if xs:
                ax.errorbar(xs, ys, yerr=es, marker=marker, markersize=6, linewidth=1.8,
                            capsize=3, color=color, label=label)
            if ns_single:
                sx = [p[0] for p in ns_single]; sy = [p[1] for p in ns_single]
                ax.scatter(sx, sy, marker=marker, s=70, facecolors="none", edgecolors=color,
                           linewidths=1.8, zorder=5)
                for n, y in ns_single:
                    ax.annotate("1 rep", (n, y), textcoords="offset points", xytext=(6, -4),
                                fontsize=6.5, color=color)
        ax.set_xscale("log", base=2); ax.set_yscale("log")
        ax.set_xticks(NODE_LIST); ax.set_xticklabels([str(n) for n in NODE_LIST])
        ax.set_xlabel("Node count (128 ranks/node)")
        ax.set_title(f"{mode} scaling", fontsize=11)
        ax.grid(alpha=0.3, which="both")
        ax.legend(fontsize=7.5)
    axes[0].set_ylabel("Latency (us)")
    fig.suptitle(title, fontsize=12.5)
    fig.tight_layout()
    save(fig, name)


if __name__ == "__main__":
    print("Generating OSU inter-node collective optimization figures...")
    fig_collective_inter_progress(
        "allreduce", 6, "figO7_allreduce_inter_progress.png",
        "Figure O7 — Allreduce, inter-node: optimization progress vs baseline (128 ranks/node)")
    fig_collective_inter_progress(
        "alltoall", 2, "figO8_alltoall_inter_progress.png",
        "Figure O8 — Alltoall, inter-node: optimization progress vs baseline (128 ranks/node)\n"
        "Container baseline AND algorithm-lock (both TCP) fail to scale past n2 -- not algorithm-specific;\n"
        "UCX-only and UCX+algorithm-lock scale cleanly to n8, same fix as pt2pt/Allreduce",
        alltoall_suffix=True)
