#!/usr/bin/env python3
"""Plot inter_node (multi-node) IOR scaling results: Native vs Container.

Safe to re-run at any point during data collection -- strong_scaling data in
particular may not exist yet for some/all combos while that sweep is still
queued; missing files are silently skipped (common.parse_ior_summary only
returns data once IOR's own "Summary of all tests:" block exists), never
fabricated.

Every point plotted is a mean across the 10 repetitions (-i 10) with a 95%
confidence-interval error bar, computed from IOR's own per-point StdDev
(see common.ci95_halfwidth) -- not a single last-iteration sample.

Figures produced:
  multinode_weak_scaling.png
      Aggregate bandwidth vs node count (1/2/4/8), fixed 128m/rank. Purpose:
      does per-rank throughput hold steady as concurrent ranks increase
      (ideal = flat line)? A container line that droops relative to native's
      flat line as node count grows indicates the container's MPI/network
      path (mechanism #1) or its Lustre access under more concurrent ranks
      (mechanism #2/#3) degrades disproportionately once a real multi-node
      network path is actually exercised -- intra-node sweeps can't show
      this, since they have no inter-node path at all.
  multinode_strong_scaling_bandwidth.png
      Raw bandwidth vs node count for a FIXED 64GiB total dataset (per-rank
      share shrinks as node count grows). Purpose: the primary strong-scaling
      data figure -- does total throughput actually increase as more nodes
      are thrown at the same fixed amount of work, and where (if anywhere)
      does container's curve diverge from native's.
  multinode_strong_scaling_efficiency.png
      Parallel efficiency (%) derived from the above, normalized against each
      variant's own 1-node baseline. Purpose: the classic HPC scaling
      question in relative terms -- 100% = perfect linear speedup.
      NOTE: this figure intentionally has NO confidence interval. Efficiency
      is a ratio of two noisy means (this node count's mean / baseline
      mean x node count); propagating an honest CI through that ratio needs
      more care than a quick formula, and showing a fabricated-looking
      interval here would overstate precision. See the raw bandwidth figure
      above for the real, directly-measured CI on every underlying point.
  multinode_overhead_heatmap.png
      Container overhead % (relative to native) across both scaling regimes
      and all node counts. Purpose: one-glance comparative summary figure,
      directly comparable to 1node_overhead_heatmap_t4m.png from the
      intra-node analysis.
"""
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import (
    APIS, MODELS, COMBOS, COMBO_LABELS, VARIANTS, VARIANT_COLOR, VARIANT_MARKER,
    VARIANT_LABEL, METRIC_LINESTYLE, MIB_PER_GIB, RESULTS_ROOT,
    ci95_halfwidth, parse_ior_summary, savefig,
)

INTER_ROOT = os.path.join(RESULTS_ROOT, "inter_node")
NODE_COUNTS = [1, 2, 4, 8]
REGIMES = ["weak_scaling", "strong_scaling"]

missing = []


def load_point(variant, regime, api, model, n):
    path = os.path.join(INTER_ROOT, regime, variant, api, model, f"ior_n{n}.txt")
    summary = parse_ior_summary(path)
    if not summary:
        missing.append(f"{variant}/{api}/{model}/{regime}/n{n}")
        return {}
    return {op: (mean, ci95_halfwidth(std, n_reps)) for op, (mean, std, n_reps) in summary.items()}


# ---------------------------------------------------------------------------
# Figure 1: weak scaling -- aggregate bandwidth vs node count
# ---------------------------------------------------------------------------
def plot_weak_scaling():
    """2x2 grid (one panel per API x model combo). Color = variant,
    linestyle = metric (solid=Write, dashed=Read), error bars = 95% CI."""
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), sharex=True)
    any_data = False
    for idx, (api, model) in enumerate(COMBOS):
        row, col = idx // 2, idx % 2
        ax = axes[row][col]
        for variant in VARIANTS:
            for metric_name in ["Write", "Read"]:
                xs, ys, yerrs = [], [], []
                for n in NODE_COUNTS:
                    pt = load_point(variant, "weak_scaling", api, model, n)
                    if metric_name.lower() not in pt:
                        continue
                    mean, ci = pt[metric_name.lower()]
                    xs.append(n)
                    ys.append(mean / MIB_PER_GIB)
                    yerrs.append(ci / MIB_PER_GIB)
                if xs:
                    any_data = True
                    ax.errorbar(xs, ys, yerr=yerrs, color=VARIANT_COLOR[variant],
                                marker=VARIANT_MARKER[variant], linestyle=METRIC_LINESTYLE[metric_name],
                                capsize=3, linewidth=1.5,
                                label=f"{VARIANT_LABEL[variant]} ({metric_name})")
        ax.set_xscale("log", base=2)
        ax.set_yscale("log")
        ax.set_xticks(NODE_COUNTS)
        ax.set_xticklabels([str(n) for n in NODE_COUNTS])
        ax.grid(True, which="both", alpha=0.3)
        ax.set_title(COMBO_LABELS[f"{api}_{model}"])
        if row == 1:
            ax.set_xlabel("Node Count")
        if col == 0:
            ax.set_ylabel("Aggregate Bandwidth (GiB/s)")
    if not any_data:
        print("  [skip] weak scaling -- no data yet")
        plt.close(fig)
        return
    axes[0][0].legend(fontsize=8)
    fig.suptitle("Weak Scaling: Aggregate Bandwidth vs. Node Count\n"
                 "Native vs Container, Fixed 128MiB/Rank -- error bars = 95% CI across 10 repetitions")
    savefig(fig, "multinode_weak_scaling.png")


# ---------------------------------------------------------------------------
# Figure 2: strong scaling -- raw bandwidth vs node count
# ---------------------------------------------------------------------------
def plot_strong_scaling_bandwidth():
    """Same layout/convention as weak scaling, for the fixed-total-dataset regime."""
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), sharex=True)
    any_data = False
    for idx, (api, model) in enumerate(COMBOS):
        row, col = idx // 2, idx % 2
        ax = axes[row][col]
        for variant in VARIANTS:
            for metric_name in ["Write", "Read"]:
                xs, ys, yerrs = [], [], []
                for n in NODE_COUNTS:
                    pt = load_point(variant, "strong_scaling", api, model, n)
                    if metric_name.lower() not in pt:
                        continue
                    mean, ci = pt[metric_name.lower()]
                    xs.append(n)
                    ys.append(mean / MIB_PER_GIB)
                    yerrs.append(ci / MIB_PER_GIB)
                if xs:
                    any_data = True
                    ax.errorbar(xs, ys, yerr=yerrs, color=VARIANT_COLOR[variant],
                                marker=VARIANT_MARKER[variant], linestyle=METRIC_LINESTYLE[metric_name],
                                capsize=3, linewidth=1.5,
                                label=f"{VARIANT_LABEL[variant]} ({metric_name})")
        ax.set_xscale("log", base=2)
        ax.set_xticks(NODE_COUNTS)
        ax.set_xticklabels([str(n) for n in NODE_COUNTS])
        ax.grid(True, which="both", alpha=0.3)
        ax.set_title(COMBO_LABELS[f"{api}_{model}"])
        if row == 1:
            ax.set_xlabel("Node Count")
        if col == 0:
            ax.set_ylabel("Aggregate Bandwidth (GiB/s)")
    if not any_data:
        print("  [skip] strong scaling bandwidth -- no data yet")
        plt.close(fig)
        return
    axes[0][0].legend(fontsize=8)
    fig.suptitle("Strong Scaling: Aggregate Bandwidth vs. Node Count\n"
                 "Native vs Container, Fixed 64GiB Total -- error bars = 95% CI across 10 repetitions")
    savefig(fig, "multinode_strong_scaling_bandwidth.png")


# ---------------------------------------------------------------------------
# Figure 3: strong scaling -- parallel efficiency (derived, no CI -- see docstring)
# ---------------------------------------------------------------------------
def plot_strong_scaling_efficiency():
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), sharex=True, sharey=True)
    any_data = False
    for idx, (api, model) in enumerate(COMBOS):
        row, col = idx // 2, idx % 2
        ax = axes[row][col]
        for variant in VARIANTS:
            for metric_name in ["Write", "Read"]:
                base_pt = load_point(variant, "strong_scaling", api, model, 1)
                if metric_name.lower() not in base_pt:
                    continue
                base_mean, _ = base_pt[metric_name.lower()]
                if base_mean == 0:
                    continue
                xs, ys = [], []
                for n in NODE_COUNTS:
                    pt = load_point(variant, "strong_scaling", api, model, n)
                    if metric_name.lower() not in pt:
                        continue
                    mean, _ = pt[metric_name.lower()]
                    xs.append(n)
                    ys.append((mean / (n * base_mean)) * 100)
                if xs:
                    any_data = True
                    ax.plot(xs, ys, color=VARIANT_COLOR[variant], marker=VARIANT_MARKER[variant],
                            linestyle=METRIC_LINESTYLE[metric_name],
                            label=f"{VARIANT_LABEL[variant]} ({metric_name})")
        ax.axhline(100, color="gray", linestyle=":", linewidth=1)
        ax.set_xscale("log", base=2)
        ax.set_xticks(NODE_COUNTS)
        ax.set_xticklabels([str(n) for n in NODE_COUNTS])
        ax.grid(True, which="both", alpha=0.3)
        ax.set_title(COMBO_LABELS[f"{api}_{model}"])
        if row == 1:
            ax.set_xlabel("Node Count")
        if col == 0:
            ax.set_ylabel("Parallel Efficiency (%)")
    if not any_data:
        print("  [skip] strong scaling efficiency -- no data yet")
        plt.close(fig)
        return
    axes[0][0].legend(fontsize=7)
    fig.suptitle("Strong Scaling: Parallel Efficiency vs. Node Count\n"
                 "Native vs Container, Fixed 64GiB Total (100% = ideal linear speedup)")
    fig.text(0.5, 0.01,
             "No CI shown: efficiency is a ratio of two sample means, and propagating an honest interval "
             "through that ratio needs more care than a quick formula -- see the raw bandwidth figure for "
             "the directly-measured CI on every underlying point this figure derives from.",
             ha="center", va="bottom", fontsize=8, style="italic", color="dimgray", wrap=True)
    savefig(fig, "multinode_strong_scaling_efficiency.png", rect=[0, 0.04, 1, 1])


# ---------------------------------------------------------------------------
# Figure 4: overhead heatmap across both regimes and all node counts
# ---------------------------------------------------------------------------
def _overhead_pct(native_mean, container_mean):
    if native_mean is None or container_mean is None or native_mean == 0:
        return np.nan
    return (native_mean - container_mean) / native_mean * 100


def plot_overhead_heatmap():
    rows, row_labels = [], []
    for regime in REGIMES:
        label = "Weak" if regime == "weak_scaling" else "Strong"
        for n in NODE_COUNTS:
            row_labels.append(f"{label} N={n}")
            row = []
            for api, model in COMBOS:
                pn = load_point("native", regime, api, model, n)
                pc = load_point("container", regime, api, model, n)
                wn = pn["write"][0] if "write" in pn else None
                wc = pc["write"][0] if "write" in pc else None
                row.append(_overhead_pct(wn, wc))
            rows.append(row)
    data = np.array(rows)

    if np.all(np.isnan(data)):
        print("  [skip] overhead heatmap -- no data yet")
        return

    fig, ax = plt.subplots(figsize=(8, 0.4 * len(row_labels) + 2))
    cmap = matplotlib.colormaps["RdYlGn_r"].copy()
    cmap.set_bad(color="#dddddd")
    masked = np.ma.masked_invalid(data)
    im = ax.imshow(masked, cmap=cmap, vmin=0, vmax=15, aspect="auto")

    col_labels = [COMBO_LABELS[f"{a}_{m}"] for a, m in COMBOS]
    ax.set_xticks(range(len(col_labels)))
    ax.set_xticklabels(col_labels, rotation=30, ha="right")
    ax.set_yticks(range(len(row_labels)))
    ax.set_yticklabels(row_labels, fontsize=8)

    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            val = data[i, j]
            text = "n/a" if np.isnan(val) else f"{val:.1f}%"
            ax.text(j, i, text, ha="center", va="center", fontsize=7,
                     color="black" if np.isnan(val) else "white")

    fig.colorbar(im, ax=ax, label="Container Write Overhead (%)  [green=0%, red>=15%]")
    fig.suptitle("Multi-Node Container Overhead Summary (Write)\n"
                 "(mean values -- see bandwidth figures for CI on each point)")
    savefig(fig, "multinode_overhead_heatmap.png")


def main():
    print("Weak scaling...")
    plot_weak_scaling()
    print("Strong scaling bandwidth...")
    plot_strong_scaling_bandwidth()
    print("Strong scaling parallel efficiency...")
    plot_strong_scaling_efficiency()
    print("Overhead summary heatmap...")
    plot_overhead_heatmap()

    if missing:
        uniq = sorted(set(missing))
        print(f"\n{len(uniq)} data points had no completed Summary yet and were skipped:")
        for m in uniq[:20]:
            print(f"  - {m}")
        if len(uniq) > 20:
            print(f"  ... and {len(uniq) - 20} more")

    print("Done.")


if __name__ == "__main__":
    main()
