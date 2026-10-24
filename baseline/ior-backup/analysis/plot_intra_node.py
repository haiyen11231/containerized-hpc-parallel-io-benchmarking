#!/usr/bin/env python3
"""Plot intra_node (1-node) IOR sweep results: Native vs Container.

Safe to re-run at any point during data collection: a missing or
still-incomplete result file is silently skipped (common.parse_ior_summary
only returns data once IOR's own "Summary of all tests:" block exists, i.e.
the full -i 10 repetition set actually finished), never fabricated.

Every point plotted is a mean across the 10 repetitions (-i 10) with a 95%
confidence-interval error bar, computed from IOR's own per-point StdDev
(see common.ci95_halfwidth) -- not a single last-iteration sample.

Figures produced:
  1node_transfer_sweep_stripe{1,8}_{write,read}.png
      Transfer-size sweep (64k..16m) at fixed stripe count. Purpose: find
      where per-syscall overhead stops dominating -- if container tracks
      native closely at large T but lags badly at small T, the gap is a
      per-syscall/transport overhead (mechanism #1), not a throughput-ceiling
      difference.
  1node_stripe_bar_t4m.png
      Stripe count (1 vs 8) bar comparison at a fixed, stripe-aligned
      transfer size. Purpose: direct probe of mechanism #3 (Lustre
      interaction) -- does container benefit from added OST parallelism
      (c=1 -> c=8) the same way native does, or is striping itself handled
      differently under the container's bind-mounted view of /scratch?
  1node_overhead_heatmap_t4m.png
      Container overhead % (relative to native) across every combo, both
      stripe counts. Purpose: one-glance comparative summary figure.
"""
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import (
    APIS, MODELS, COMBOS, COMBO_LABELS, VARIANTS, VARIANT_COLOR, VARIANT_MARKER,
    VARIANT_LABEL, MIB_PER_GIB, RESULTS_ROOT, ci95_halfwidth, parse_ior_summary, savefig,
)

INTRA_ROOT = os.path.join(RESULTS_ROOT, "intra_node")
STRIPE_COUNTS = [1, 8]
T_SIZES = [("64k", 65536), ("256k", 262144), ("1m", 1048576), ("4m", 4194304), ("16m", 16777216)]

missing = []


def load_point(variant, api, model, stripe, tlabel):
    """Return (mean_MiB, ci_halfwidth_MiB) for write and read: {"write": (mean, ci), "read": (mean, ci)}."""
    path = os.path.join(INTRA_ROOT, variant, api, model, f"stripe_c{stripe}", f"ior_t{tlabel}.txt")
    summary = parse_ior_summary(path)
    if not summary:
        missing.append(f"{variant}/{api}/{model}/stripe_c{stripe}/t{tlabel}")
        return {}
    return {op: (mean, ci95_halfwidth(std, n)) for op, (mean, std, n) in summary.items()}


# ---------------------------------------------------------------------------
# Figure set 1: transfer-size sweep, per stripe count x metric
# ---------------------------------------------------------------------------
def plot_transfer_size_sweep(stripe, metric_name):
    """2x2 grid: rows=API, cols=model. X=transfer size (log), Y=mean bandwidth
    with 95% CI error bars, one line per variant."""
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), sharex=True, sharey=True)
    any_data = False

    for row, api in enumerate(APIS):
        for col, model in enumerate(MODELS):
            ax = axes[row][col]
            for variant in VARIANTS:
                xs, ys, yerrs = [], [], []
                for tlabel, tbytes in T_SIZES:
                    pt = load_point(variant, api, model, stripe, tlabel)
                    if metric_name.lower() not in pt:
                        continue
                    mean, ci = pt[metric_name.lower()]
                    xs.append(tbytes)
                    ys.append(mean / MIB_PER_GIB)
                    yerrs.append(ci / MIB_PER_GIB)
                if xs:
                    any_data = True
                    ax.errorbar(xs, ys, yerr=yerrs, color=VARIANT_COLOR[variant],
                                marker=VARIANT_MARKER[variant], label=VARIANT_LABEL[variant],
                                capsize=3, linewidth=1.5)
            ax.set_xscale("log", base=2)
            ax.set_yscale("log")
            ax.set_xticks([b for _, b in T_SIZES])
            ax.set_xticklabels([lbl for lbl, _ in T_SIZES])
            ax.grid(True, which="both", alpha=0.3)
            ax.set_title(f"{api.upper()} / {model}")
            if row == 1:
                ax.set_xlabel("Transfer Size")
            if col == 0:
                ax.set_ylabel(f"{metric_name} Bandwidth (GiB/s)")

    if not any_data:
        print(f"  [skip] stripe_c{stripe} {metric_name} transfer-size sweep -- no data yet")
        plt.close(fig)
        return
    axes[0][0].legend()
    fig.suptitle(f"1-Node Transfer-Size Sweep, Stripe Count {stripe} ({metric_name})\n"
                 f"Native vs Container -- error bars = 95% CI across 10 repetitions")
    savefig(fig, f"1node_transfer_sweep_stripe{stripe}_{metric_name.lower()}.png")


# ---------------------------------------------------------------------------
# Figure set 2: stripe count (1 vs 8) bar comparison at a fixed transfer size
# ---------------------------------------------------------------------------
_BAR_SPECS = [
    ("native", "shared", VARIANT_COLOR["native"], None),
    ("native", "fpp", VARIANT_COLOR["native"], "//"),
    ("container", "shared", VARIANT_COLOR["container"], None),
    ("container", "fpp", VARIANT_COLOR["container"], "//"),
]


def plot_stripe_bar_chart(tlabel="4m"):
    """2x2 grid (rows=Write/Read, cols=API). x=stripe count, 4 bars/group
    (variant x model), with 95% CI error bars on every bar."""
    x = np.arange(len(STRIPE_COUNTS))
    width = 0.2
    fig, axes = plt.subplots(2, 2, figsize=(12, 9), sharex=True, sharey="row")
    any_data = False

    for row, metric_name in enumerate(["Write", "Read"]):
        for col, api in enumerate(APIS):
            ax = axes[row][col]
            for i, (variant, model, color, hatch) in enumerate(_BAR_SPECS):
                ys, yerrs = [], []
                for stripe in STRIPE_COUNTS:
                    pt = load_point(variant, api, model, stripe, tlabel)
                    if metric_name.lower() in pt:
                        mean, ci = pt[metric_name.lower()]
                        ys.append(mean / MIB_PER_GIB)
                        yerrs.append(ci / MIB_PER_GIB)
                        any_data = True
                    else:
                        ys.append(np.nan)
                        yerrs.append(0.0)
                ax.bar(x + (i - 1.5) * width, ys, width, yerr=yerrs, capsize=3,
                       color=color, hatch=hatch, edgecolor="black", linewidth=0.5,
                       label=f"{VARIANT_LABEL[variant]}-{model.upper()}")
            ax.grid(True, axis="y", alpha=0.3)
            ax.set_title(f"{api.upper()} ({metric_name})")
            if row == 1:
                ax.set_xticks(x)
                ax.set_xticklabels([str(s) for s in STRIPE_COUNTS])
                ax.set_xlabel("Stripe Count")
            if col == 0:
                ax.set_ylabel(f"{metric_name} Bandwidth (GiB/s)")

    if not any_data:
        print(f"  [skip] stripe bar chart t={tlabel} -- no data yet")
        plt.close(fig)
        return
    axes[0][0].legend(fontsize=8)
    fig.suptitle(f"1-Node Stripe Count Comparison (c=1 vs c=8), Transfer Size {tlabel.upper()}\n"
                 f"Native vs Container -- error bars = 95% CI across 10 repetitions")
    savefig(fig, f"1node_stripe_bar_t{tlabel}.png")


# ---------------------------------------------------------------------------
# Figure set 3: container overhead heatmap (summary figure)
# ---------------------------------------------------------------------------
def _overhead_pct(native_mean, container_mean):
    if native_mean is None or container_mean is None or native_mean == 0:
        return np.nan
    return (native_mean - container_mean) / native_mean * 100


def plot_overhead_heatmap(tlabel="4m"):
    """Rows = stripe count, cols = API x model combo. Cell = % write-bandwidth
    overhead of container vs native (mean values only -- a heatmap cell
    showing both a mean and a CI is unreadable, so CI is intentionally
    omitted here; see the bar chart / sweep figures above for the full
    interval on every underlying point)."""
    rows, row_labels = [], []
    for stripe in STRIPE_COUNTS:
        row_labels.append(f"stripe_c{stripe}")
        row = []
        for api, model in COMBOS:
            pn = load_point("native", api, model, stripe, tlabel)
            pc = load_point("container", api, model, stripe, tlabel)
            wn = pn["write"][0] if "write" in pn else None
            wc = pc["write"][0] if "write" in pc else None
            row.append(_overhead_pct(wn, wc))
        rows.append(row)
    data = np.array(rows)

    if np.all(np.isnan(data)):
        print(f"  [skip] overhead heatmap t={tlabel} -- no data yet")
        return

    fig, ax = plt.subplots(figsize=(8, 0.5 * len(row_labels) + 2))
    cmap = matplotlib.colormaps["RdYlGn_r"].copy()
    cmap.set_bad(color="#dddddd")
    masked = np.ma.masked_invalid(data)
    im = ax.imshow(masked, cmap=cmap, vmin=0, vmax=15, aspect="auto")

    col_labels = [COMBO_LABELS[f"{a}_{m}"] for a, m in COMBOS]
    ax.set_xticks(range(len(col_labels)))
    ax.set_xticklabels(col_labels, rotation=30, ha="right")
    ax.set_yticks(range(len(row_labels)))
    ax.set_yticklabels(row_labels)

    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            val = data[i, j]
            text = "n/a" if np.isnan(val) else f"{val:.1f}%"
            ax.text(j, i, text, ha="center", va="center", fontsize=8,
                     color="black" if np.isnan(val) else "white")

    fig.colorbar(im, ax=ax, label="Container Write Overhead (%)  [green=0%, red>=15%]")
    fig.suptitle(f"1-Node Container Overhead Summary (Write, t={tlabel.upper()})\n"
                 f"(mean values -- see sweep/bar figures for CI on each point)")
    savefig(fig, f"1node_overhead_heatmap_t{tlabel}.png")


def main():
    print("Transfer-size sweep, per stripe count...")
    for stripe in STRIPE_COUNTS:
        for metric_name in ["Write", "Read"]:
            plot_transfer_size_sweep(stripe, metric_name)

    print("Stripe count comparison bar chart...")
    plot_stripe_bar_chart()

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
