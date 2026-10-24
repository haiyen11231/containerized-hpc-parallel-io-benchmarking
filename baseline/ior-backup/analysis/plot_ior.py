"""IOR report figures -- one idea per figure.

IOR's headline result is a NULL one: across 72 configurations the container
median is 1.01-1.07x and only a minority of cells resolve at 95%, in both
directions. Figures must therefore show that honestly rather than painting
run-to-run variance as an effect.

An earlier figure set included a container-overhead heatmap spanning -44% to
+29% in red/green with no significance encoding. Six of its most dramatic cells
have confidence intervals WIDER than the effect shown (one reads +12.3% with a
+-46% CI). Figure 5 replaces it.

Numbering mirrors baseline/osu/analysis/plot_osu.py so the two benchmarks read
the same way: 1x is the first study type, 2x is scaling, 3 is the key
diagnostic, A1 is an appendix caveat.

  Fig 1A  transfer-size sweep, STRIPE 1            does transfer size matter?
  Fig 1B  transfer-size sweep, STRIPE 8            same, at the other stripe count
  Fig 1C  access model -- the dominant effect      FPP vs shared-file
  Fig 2A  weak scaling vs ideal                    does Lustre absorb more load?
  Fig 2B  strong scaling efficiency                does splitting fixed work help?
  Fig A1  read cache inflation                     why reads are not reported

A container-overhead heatmap was dropped: with only 11 of 32 cells resolving at
95% it mostly rendered run-to-run Lustre variance as color. The native-vs-
container comparison now lives inside Figures 1A, 2A and 2B, where overlapping
confidence intervals state the null result directly.

Run:  python3 analysis/plot_ior.py
"""

import math
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

R = os.path.join(os.path.dirname(__file__), "..", "results")
FIGS = os.path.join(os.path.dirname(__file__), "figures")

VARIANT_COLOR = {"native": "#1f77b4", "container": "#ff7f0e"}
VARIANT_MARKER = {"native": "o", "container": "x"}
VARIANT_LABEL = {"native": "Native", "container": "Container"}
COMBOS = [("posix", "shared"), ("posix", "fpp"), ("mpiio", "shared"), ("mpiio", "fpp")]
COMBO_LABEL = {"posix_shared": "POSIX / Shared", "posix_fpp": "POSIX / FPP",
               "mpiio_shared": "MPIIO / Shared", "mpiio_fpp": "MPIIO / FPP"}
TSIZES = ["64k", "256k", "1m", "4m", "16m"]
NODES = [1, 2, 4, 8]
T95_9 = 2.262      # n=10, df=9


def parse(path):
    """IOR's 'Summary of all tests' block -> {'write': (mean, sd), 'read': ...}."""
    if not os.path.exists(path):
        return {}
    out = {}
    for line in open(path):
        m = re.match(r'^(write|read)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s', line)
        if m:
            out[m.group(1)] = (float(m.group(4)), float(m.group(5)))
    return out


def ci(sd, n=10):
    return T95_9 * sd / math.sqrt(n)


def intra(variant, api, model, stripe, t):
    return parse(f"{R}/intra_node/{variant}/{api}/{model}/stripe_{stripe}/ior_t{t}.txt")


def inter(mode, variant, api, model, n):
    return parse(f"{R}/inter_node/{mode}_scaling/{variant}/{api}/{model}/ior_n{n}.txt")


def resolvable(m1, s1, m2, s2, n=10):
    se = math.sqrt(s1 * s1 / n + s2 * s2 / n)
    return (abs(m1 - m2) / se > 2.101) if se else False


def save(fig, name):
    os.makedirs(FIGS, exist_ok=True)
    p = os.path.join(FIGS, name)
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote figures/{name}")


def label_points(ax, xs, ys, variant, fmt="{:.0f}"):
    up = variant == "native"
    for x, y in zip(xs, ys):
        ax.annotate(fmt.format(y), (x, y), textcoords="offset points",
                    xytext=(0, 8 if up else -14), ha="center", fontsize=6.5,
                    color=VARIANT_COLOR[variant], fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.7))


# ------------------------------------------------------------------- Figure 1
def _transfer_sweep(stripe, name, figlabel):
    """One row of 4 panels (API x access model) for a single stripe count.

    Stripe 1 and stripe 8 are separate figures rather than rows of one figure:
    each then fits a single row, every panel holds exactly two lines (native
    and container), and the shaded noise band is unambiguous because only one
    stripe count is present.

    The 1 MiB marker is the Lustre stripe size (-S 1m). GUIDE.md suggests it
    explains where throughput changes trajectory; checked against the data it
    does not (slopes either side: 1.06x -> 1.05x posix/shared, 0.85x -> 0.96x
    mpiio/shared). Drawn as a neutral reference, never captioned as a cause.
    """
    # 2x2 rather than 1x4: four panels in a row forces each one narrow, which
    # crowds the value labels and error bars. Two per row gives each panel
    # roughly twice the width.
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.5))
    for ax, (api, model) in zip(axes.flat, COMBOS):
        nx, lo, hi = [], [], []
        for i, t in enumerate(TSIZES):
            d = intra("native", api, model, stripe, t)
            if "write" in d:
                m, sd = d["write"]; h = ci(sd)
                nx.append(i); lo.append(m - h); hi.append(m + h)
        if nx:
            ax.fill_between(nx, lo, hi, color=VARIANT_COLOR["native"], alpha=0.17,
                            zorder=0, label="Native 95% CI")

        for variant in ("native", "container"):
            xs, ys, es = [], [], []
            for i, t in enumerate(TSIZES):
                d = intra(variant, api, model, stripe, t)
                if "write" in d:
                    xs.append(i); ys.append(d["write"][0]); es.append(ci(d["write"][1]))
            ax.errorbar(xs, ys, yerr=es, marker=VARIANT_MARKER[variant], markersize=5,
                        linewidth=1.7, capsize=3, color=VARIANT_COLOR[variant],
                        label=VARIANT_LABEL[variant])
            label_points(ax, xs, ys, variant)

        ax.axvline(TSIZES.index("1m"), color="#8c564b", linestyle=":", linewidth=1.3, zorder=1)
        ax.set_xticks(range(len(TSIZES))); ax.set_xticklabels(TSIZES, fontsize=9.5)
        ax.set_xlabel("Transfer size", fontsize=10)
        ax.set_ylabel("Write bandwidth (MiB/s)", fontsize=10)
        ax.set_title(COMBO_LABEL[f"{api}_{model}"], fontsize=11.5)
        ax.grid(alpha=0.3)
    axes.flat[0].legend(fontsize=9)
    fig.suptitle(f"IOR write -- intra-node, STRIPE COUNT {stripe[1:]}, 64 ranks\n"
                 "transfer-size sweep (64k-16m), -i 10",
                 fontsize=11.5)
    fig.tight_layout()
    save(fig, name)


def fig1a_stripe1():
    _transfer_sweep("c1", "fig1a_transfer_sweep_stripe1.png", "Figure 1A")


def fig1b_stripe8():
    _transfer_sweep("c8", "fig1b_transfer_sweep_stripe8.png", "Figure 1B")


def fig1c_access_model():
    """The access-model effect, shown for BOTH variants.

    An earlier version plotted native only, reasoning that this is a filesystem
    property rather than a container one. That was a mistake: showing both is
    what demonstrates the claim. If the same ~3.5x gap appears in the container,
    the effect is independent of containerization -- which is the point.
    """
    fig, ax = plt.subplots(figsize=(10, 5.4))
    labels, bars = [], {v: ([], []) for v in ("native", "container")}
    for api, model in COMBOS:
        labels.append(COMBO_LABEL[f"{api}_{model}"])
        for variant in ("native", "container"):
            vals, sds = [], []
            for stripe in ("c1", "c8"):
                for t in TSIZES:
                    d = intra(variant, api, model, stripe, t)
                    if "write" in d:
                        vals.append(d["write"][0]); sds.append(d["write"][1])
            bars[variant][0].append(sum(vals) / len(vals) if vals else 0)
            bars[variant][1].append(
                T95_9 * (sum(x * x for x in sds) / len(sds)) ** 0.5 / math.sqrt(len(vals))
                if vals else 0)

    x = np.arange(len(labels)); w = 0.36
    for i, variant in enumerate(("native", "container")):
        m, e = bars[variant]
        off = (-w / 2, w / 2)[i]
        ax.bar(x + off, m, w, yerr=e, capsize=5, color=VARIANT_COLOR[variant],
               alpha=0.88, label=VARIANT_LABEL[variant])
        for xi, mi in zip(x + off, m):
            ax.annotate(f"{mi:.0f}", (xi, mi), textcoords="offset points",
                        xytext=(0, 4), ha="center", fontsize=9, fontweight="bold")

    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylabel("Mean write bandwidth (MiB/s)")
    ax.grid(axis="y", alpha=0.3); ax.legend(fontsize=10)
    ax.set_title("IOR write -- intra-node, 64 ranks\n"
                 "averaged over STRIPE COUNT (1, 8) and transfer size (64k-16m), -i 10",
                 fontsize=10.5)
    fig.tight_layout()
    save(fig, "fig1c_access_model.png")


# ----------------------------------------------------------------- Figure 2A/2B
def fig2a_weak():
    """Weak scaling, one panel per configuration so native and container are
    plotted against each other rather than in separate charts.

    Per-rank work is fixed, so ideal is linear growth with node count; the
    dashed line is that ideal anchored at each series' own 1-node value.
    """
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))
    for ax, (api, model) in zip(axes.flat, COMBOS):
        base = None
        for variant in ("native", "container"):
            xs, ys, es = [], [], []
            for n in NODES:
                d = inter("weak", variant, api, model, n)
                if "write" in d:
                    xs.append(n); ys.append(d["write"][0] / 1024); es.append(ci(d["write"][1]) / 1024)
            if not xs:
                continue
            if base is None:
                base = ys[0]
            ax.errorbar(xs, ys, yerr=es, marker=VARIANT_MARKER[variant], markersize=6,
                        linewidth=1.8, capsize=3.5, color=VARIANT_COLOR[variant],
                        label=VARIANT_LABEL[variant])
            label_points(ax, xs, ys, variant, fmt="{:.1f}")
        if base:
            ax.plot(NODES, [base * n for n in NODES], "k--", linewidth=1.2,
                    alpha=0.55, label="ideal (linear)")
        ax.set_xscale("log", base=2); ax.set_yscale("log")
        ax.set_xticks(NODES); ax.set_xticklabels(NODES)
        ax.set_xlabel("Nodes (128 ranks each)"); ax.set_ylabel("Write bandwidth (GiB/s)")
        ax.set_title(COMBO_LABEL[f"{api}_{model}"], fontsize=11)
        ax.grid(alpha=0.3, which="both"); ax.legend(fontsize=8.5)
    fig.suptitle("IOR write -- weak scaling, 1/2/4/8 nodes, 128 ranks/node\n"
                 "STRIPE COUNT 8, B=128m/rank (fixed), T=4m, -i 10",
                 fontsize=11.5)
    fig.tight_layout()
    save(fig, "fig2a_weak_scaling.png")


def fig2b_strong():
    """Strong scaling, raw bandwidth -- one panel per configuration.

    Total fixed at 64 GiB split across more nodes. Ideal is linear growth in
    bandwidth (same shape as fig2a_weak's ideal line), anchored at each
    series' own 1-node value.
    """
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))
    for ax, (api, model) in zip(axes.flat, COMBOS):
        base = None
        for variant in ("native", "container"):
            xs, ys, es = [], [], []
            for n in NODES:
                d = inter("strong", variant, api, model, n)
                if "write" in d:
                    xs.append(n); ys.append(d["write"][0] / 1024); es.append(ci(d["write"][1]) / 1024)
            if not xs:
                continue
            if base is None:
                base = ys[0]
            ax.errorbar(xs, ys, yerr=es, marker=VARIANT_MARKER[variant], markersize=6,
                        linewidth=1.8, capsize=3.5, color=VARIANT_COLOR[variant],
                        label=VARIANT_LABEL[variant])
            label_points(ax, xs, ys, variant, fmt="{:.1f}")
        if base:
            ax.plot(NODES, [base * n for n in NODES], "k--", linewidth=1.2,
                    alpha=0.55, label="ideal (linear)")
        ax.set_xscale("log", base=2); ax.set_yscale("log")
        ax.set_xticks(NODES); ax.set_xticklabels(NODES)
        ax.set_xlabel("Nodes (128 ranks each)"); ax.set_ylabel("Write bandwidth (GiB/s)")
        ax.set_title(COMBO_LABEL[f"{api}_{model}"], fontsize=11)
        ax.grid(alpha=0.3, which="both"); ax.legend(fontsize=8.5)
    fig.suptitle("IOR write -- strong scaling, 1/2/4/8 nodes, 128 ranks/node\n"
                 "STRIPE COUNT 8, TOTAL=64GiB (fixed), T=4m, -i 10",
                 fontsize=11.5)
    fig.tight_layout()
    save(fig, "fig2b_strong_scaling.png")


# ------------------------------------------------------------------- Figure 5
# ------------------------------------------------------------------- Figure 6
def figA1_read_cache():
    fig, ax = plt.subplots(figsize=(9, 5))
    labels, w, r = [], [], []
    for api, model in COMBOS:
        d = intra("native", api, model, "c8", "4m")
        if "write" in d and "read" in d:
            labels.append(COMBO_LABEL[f"{api}_{model}"])
            w.append(d["write"][0] / 1024); r.append(d["read"][0] / 1024)
    x = np.arange(len(labels)); wd = 0.36
    ax.bar(x - wd / 2, w, wd, label="write (to Lustre)", color="#1f77b4")
    ax.bar(x + wd / 2, r, wd, label="read (from page cache)", color="#d62728", alpha=0.8)
    for i, (a, b) in enumerate(zip(w, r)):
        ax.annotate(f"{a:.1f}", (i - wd / 2, a), textcoords="offset points",
                    xytext=(0, 4), ha="center", fontsize=9, fontweight="bold")
        ax.annotate(f"{b:.0f}\n({b/a:.0f}x)", (i + wd / 2, b), textcoords="offset points",
                    xytext=(0, 4), ha="center", fontsize=9, fontweight="bold", color="#d62728")
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=9.5)
    ax.set_ylabel("Bandwidth (GiB/s)"); ax.set_yscale("log")
    ax.grid(axis="y", alpha=0.3, which="both"); ax.legend(fontsize=9.5)
    ax.set_title("IOR write vs read -- intra-node, STRIPE COUNT 8, T=4m, 64 ranks",
                 fontsize=11)
    fig.tight_layout()
    save(fig, "figA1_read_cache_inflation.png")


if __name__ == "__main__":
    print("Generating IOR report figures...")
    fig1a_stripe1()
    fig1b_stripe8()
    fig1c_access_model()
    fig2a_weak()
    fig2b_strong()
    figA1_read_cache()
