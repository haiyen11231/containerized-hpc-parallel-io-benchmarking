"""OSU optimization figure -- pt2pt inter-node, three-way comparison.

  native            baseline/osu/results/pt2pt/inter_node/native       (UCX, RDMA -- the target)
  container_tcp     baseline/osu/results/pt2pt/inter_node/container    (--mca btl tcp,self -- the baseline misconfiguration)
  container_ucx     optimization/osu/results/container_ucx             (--mca pml ucx -- the fix, single flag changed)

Only the successful UCX path is analyzed here, per project decision not to
dwell on the failed bind-mount approach (see ../README.md).

Run:  python3 analysis/plot_optimization.py
"""

import glob
import math
import os
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
BASE_PT2PT = os.path.join(HERE, "..", "..", "..", "baseline", "osu", "results", "pt2pt", "inter_node")
OPT_RESULTS = os.path.join(HERE, "..", "results")
FIG_DIR = os.path.join(HERE, "figures")

COLOR = {"native": "#1f77b4", "container_tcp": "#d62728", "container_ucx": "#2ca02c"}
MARKER = {"native": "o", "container_tcp": "x", "container_ucx": "^"}
LABEL = {"native": "Native (UCX/RDMA)", "container_tcp": "Container, baseline (TCP)",
         "container_ucx": "Container, optimized (UCX)"}

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


def series(bench):
    return {
        "native": by_size(os.path.join(BASE_PT2PT, "native", bench, f"osu_{bench}_rep*.txt")),
        "container_tcp": by_size(os.path.join(BASE_PT2PT, "container", bench, f"osu_{bench}_rep*.txt")),
        "container_ucx": by_size(os.path.join(OPT_RESULTS, "container_ucx", bench, f"osu_{bench}_rep*.txt")),
    }


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


def fig_pt2pt(bench, name, title, ylabel, logy=True):
    d = series(bench)
    fig, ax = plt.subplots(figsize=(8, 5.5))
    for variant in ("native", "container_tcp", "container_ucx"):
        data = d[variant]
        sizes = sorted(data)
        means = [st.mean(data[s]) for s in sizes]
        errs = [ci95(data[s]) for s in sizes]
        ax.errorbar(sizes, means, yerr=errs, marker=MARKER[variant], markersize=4.5,
                    linewidth=1.7, capsize=2.5, color=COLOR[variant], label=LABEL[variant])
    # Label only the two endpoints per series to keep it legible.
    for variant in ("native", "container_tcp", "container_ucx"):
        data = d[variant]
        sizes = sorted(data)
        for i in (0, -1):
            s = sizes[i]
            m = st.mean(data[s])
            ax.annotate(_fmt(m), (s, m), textcoords="offset points",
                        xytext=(0, 8), ha="center", fontsize=7.5, fontweight="bold",
                        color=COLOR[variant],
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


if __name__ == "__main__":
    print("Generating OSU optimization figures...")
    fig_pt2pt("latency", "figO1a_pt2pt_latency.png",
              "Figure O1A — pt2pt inter-node latency: native vs container (TCP) vs container (UCX)",
              "Latency (us)")
    fig_pt2pt("bw", "figO1b_pt2pt_bandwidth.png",
              "Figure O1B — pt2pt inter-node bandwidth: native vs container (TCP) vs container (UCX)",
              "Bandwidth (MB/s)")
