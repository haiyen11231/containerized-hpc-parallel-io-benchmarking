"""OSU optimization -- intra-node progress so far.

Three things, all intra-node (1 node, shared memory only, no network):

  figO3a/O3b  pt2pt latency/bandwidth: native vs container-baseline(vader) vs
              container-UCX(no-CMA)
  figO4       Allreduce: native + 4 container variants (baseline, alglock-only,
              UCX-only, UCX+alglock), weak/strong panels
  figO5       Alltoall:  same 4-way container comparison
  figO6       Allreduce algorithm-lock diagnostic (native only): does forcing
              a fixed algorithm change the NP=64 anomaly?

Run:  python3 analysis/plot_optimization_intra.py
"""

import glob
import math
import os
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
BASE_PT2PT = os.path.join(HERE, "..", "..", "..", "baseline", "osu", "results", "pt2pt", "intra_node")
BASE_COLL = os.path.join(HERE, "..", "..", "..", "baseline", "osu", "results", "collective", "intra_node")
OPT = os.path.join(HERE, "..", "results")
FIG_DIR = os.path.join(HERE, "figures")

NATIVE = "#1f77b4"
BASELINE = "#d62728"
ALGLOCK = "#9467bd"
UCX = "#2ca02c"
UCX_ALGLOCK = "#ff7f0e"

NP_LIST = [8, 16, 32, 64, 128]

_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
        8: 2.306, 9: 2.262, 10: 2.228}


def t_crit_95(df):
    keys = sorted(k for k in _T95 if k <= df)
    return _T95[keys[-1]] if keys else 1.96


def ci95(vals):
    if len(vals) < 2:
        return 0.0
    return t_crit_95(len(vals) - 1) * st.stdev(vals) / math.sqrt(len(vals))


def rows(pattern):
    out = []
    for f in sorted(glob.glob(pattern)):
        for line in open(f):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            p = line.split()
            if len(p) >= 2:
                try:
                    out.append((int(p[0]), float(p[1])))
                except ValueError:
                    pass
    return out


def by_size(pattern):
    d = {}
    for s, v in rows(pattern):
        d.setdefault(s, []).append(v)
    return d


def last_val_series(pattern):
    """For collective benchmarks: one row per file, return list of values."""
    vals = []
    for f in sorted(glob.glob(pattern)):
        for line in open(f):
            line = line.strip()
            if line and not line.startswith("#"):
                vals.append(float(line.split()[1]))
                break
    return vals


def _fmt(v):
    if v >= 1000:
        return f"{v:.0f}"
    if v >= 10:
        return f"{v:.1f}"
    if v >= 1:
        return f"{v:.2f}"
    return f"{v:.3f}"


def save(fig, name):
    os.makedirs(FIG_DIR, exist_ok=True)
    path = os.path.join(FIG_DIR, name)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {os.path.relpath(path, HERE)}")


# ------------------------------------------------------------- Fig O3a/O3b
def fig_pt2pt_intra(bench, name, title, ylabel, logy=True):
    native = by_size(os.path.join(BASE_PT2PT, "native", bench, f"osu_{bench}_rep*.txt"))
    baseline = by_size(os.path.join(BASE_PT2PT, "container", bench, f"osu_{bench}_rep*.txt"))
    ucx = by_size(os.path.join(OPT, "container_ucx_intra_nocma", bench, f"osu_{bench}_rep*.txt"))

    fig, ax = plt.subplots(figsize=(8, 5.5))
    for label, color, marker, d in (
        ("Native", NATIVE, "o", native),
        ("Container, baseline (vader)", BASELINE, "x", baseline),
        ("Container, optimized (UCX, no-CMA)", UCX, "^", ucx),
    ):
        sizes = sorted(d)
        means = [st.mean(d[s]) for s in sizes]
        errs = [ci95(d[s]) for s in sizes]
        ax.errorbar(sizes, means, yerr=errs, marker=marker, markersize=4.5,
                    linewidth=1.7, capsize=2.5, color=color, label=label)
        for i in (0, -1):
            s = sizes[i]; m = means[i]
            ax.annotate(_fmt(m), (s, m), textcoords="offset points", xytext=(0, 8),
                        ha="center", fontsize=7.5, fontweight="bold", color=color,
                        bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.7))
    ax.set_xscale("log", base=2)
    if logy:
        ax.set_yscale("log")
    ax.set_xlabel("Message size (bytes)")
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=11.5)
    ax.grid(alpha=0.3, which="both")
    ax.legend(fontsize=9.5)
    fig.tight_layout()
    save(fig, name)


# ------------------------------------------------------------------ Fig O4/O5
def fig_collective_intra_progress(bench, alg, name, title):
    native_path = os.path.join(BASE_COLL, "{mode}_scaling", "native", bench, "np{np}", f"osu_{bench}_rep*.txt")
    baseline_path = os.path.join(BASE_COLL, "{mode}_scaling", "container", bench, "np{np}", f"osu_{bench}_rep*.txt")
    ucx_path = os.path.join(OPT, "collective_ucx_intra", "{mode}", bench, "np{np}", f"osu_{bench}_rep*.txt")
    alglock_path = os.path.join(OPT, "collective_alglock", "intra", "{mode}", bench, f"alg{alg}", "np{np}", f"osu_{bench}_rep*.txt")
    both_path = os.path.join(OPT, "collective_ucx_alglock", "intra", "{mode}", bench, f"alg{alg}", "np{np}", f"osu_{bench}_rep*.txt")

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, mode in zip(axes, ("weak", "strong")):
        for label, color, marker, pattern_tmpl in (
            ("Native", NATIVE, "o", native_path),
            ("Container, baseline", BASELINE, "x", baseline_path),
            ("Container, algorithm-lock only", ALGLOCK, "s", alglock_path),
            ("Container, UCX only", UCX, "^", ucx_path),
            ("Container, UCX + algorithm-lock", UCX_ALGLOCK, "D", both_path),
        ):
            xs, ys, es = [], [], []
            for np_ in NP_LIST:
                pattern = pattern_tmpl.format(mode=mode, np=np_)
                vals = last_val_series(pattern)
                if vals:
                    xs.append(np_); ys.append(st.mean(vals)); es.append(ci95(vals))
            if xs:
                ax.errorbar(xs, ys, yerr=es, marker=marker, markersize=6, linewidth=1.8,
                            capsize=3, color=color, label=label)
        ax.set_xscale("log", base=2); ax.set_yscale("log")
        ax.set_xlabel("Total MPI ranks")
        ax.set_title(f"{mode} scaling", fontsize=11)
        ax.grid(alpha=0.3, which="both")
        ax.legend(fontsize=8)
    axes[0].set_ylabel("Latency (us)")
    fig.suptitle(title, fontsize=12.5)
    fig.tight_layout()
    save(fig, name)


# ------------------------------------------------------------------ Fig O6
def fig_algorithm_lock_diagnostic():
    """Native only: does forcing a fixed Allreduce algorithm change the
    NP=64 anomaly, versus the baseline's default dynamic-rule selection?"""
    baseline_path = os.path.join(BASE_COLL, "weak_scaling", "native", "allreduce", "np{np}", "osu_allreduce_rep*.txt")
    alg_path = os.path.join(OPT, "allreduce_algorithm_lock", "alg{alg}", "np{np}", "osu_allreduce_rep*.txt")

    fig, ax = plt.subplots(figsize=(8, 5.5))
    for label, color, marker, alg in (
        ("Default (dynamic rule selection, baseline)", NATIVE, "o", None),
        ("Forced: recursive doubling (ALG=3)", ALGLOCK, "s", 3),
        ("Forced: Rabenseifner (ALG=6)", UCX, "^", 6),
    ):
        xs, ys, es = [], [], []
        for np_ in (32, 64, 128):
            pattern = baseline_path.format(np=np_) if alg is None else alg_path.format(alg=alg, np=np_)
            vals = last_val_series(pattern)
            if vals:
                xs.append(np_); ys.append(st.mean(vals)); es.append(ci95(vals))
        ax.errorbar(xs, ys, yerr=es, marker=marker, markersize=7, linewidth=2,
                    capsize=3, color=color, label=label)
        for x_, y_ in zip(xs, ys):
            ax.annotate(f"{y_:.0f}", (x_, y_), textcoords="offset points", xytext=(0, 9),
                        ha="center", fontsize=8, fontweight="bold", color=color)
    ax.set_xscale("log", base=2); ax.set_yscale("log")
    ax.set_xticks([32, 64, 128]); ax.set_xticklabels(["32", "64", "128"])
    ax.set_xlabel("Total MPI ranks")
    ax.set_ylabel("Latency (us)")
    ax.set_title("Figure O6 — Does locking the Allreduce algorithm remove the NP=64 spike?\n"
                  "(native only; same intra-node weak-scaling config as the baseline anomaly)",
                  fontsize=11.5)
    ax.grid(alpha=0.3, which="both")
    ax.legend(fontsize=9)
    fig.tight_layout()
    save(fig, "figO6_algorithm_lock_diagnostic.png")


if __name__ == "__main__":
    print("Generating OSU intra-node optimization progress figures...")
    fig_pt2pt_intra("latency", "figO3a_pt2pt_intra_latency.png",
                     "Figure O3A — pt2pt intra-node latency: native vs container (vader) vs container (UCX)",
                     "Latency (us)")
    fig_pt2pt_intra("bw", "figO3b_pt2pt_intra_bandwidth.png",
                     "Figure O3B — pt2pt intra-node bandwidth: native vs container (vader) vs container (UCX)",
                     "Bandwidth (MB/s)")
    fig_collective_intra_progress("allreduce", 6, "figO4_allreduce_intra_progress.png",
                                   "Figure O4 — Allreduce, intra-node: optimization progress vs baseline")
    fig_collective_intra_progress("alltoall", 2, "figO5_alltoall_intra_progress.png",
                                   "Figure O5 — Alltoall, intra-node: optimization progress vs baseline")
    fig_algorithm_lock_diagnostic()
