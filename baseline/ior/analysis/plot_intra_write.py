#!/usr/bin/env python3
"""Plot the IOR intra-node study: Combo A (MPI-IO + Shared) vs Combo B
(POSIX + FPP), Native vs Container, swept over transfer size (1m/4m/16m) at
a fixed stripe count (-c 4), write-only (-w).

Reads directly from ../scripts/intra_node/<variant>/<api>/<model>/ior_t<T>.txt
-- the actual output location of ior_{native,container}_intra.pbs. See that
script's README for the full experiment design.

Reuses common.py's IOR-summary parser and 95%-CI math; combo/transfer-size
constants live here since they describe this specific experiment.

Figures produced:
  intra_write_transfer_sweep.png
      1x2 grid (one panel per combo). X = transfer size (1m/4m/16m, log),
      Y = mean write bandwidth (GiB/s) with 95% CI error bars, one line per
      variant.
  intra_write_bar_t4m.png
      Grouped bar chart at the middle transfer size (4m): combo on the
      x-axis, one bar pair (native/container) per combo.

Run:  python3 plot_intra_write.py
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import MIB_PER_GIB, ci95_halfwidth, parse_ior_summary, savefig

HERE = os.path.dirname(__file__)
DATA_ROOT = os.path.join(HERE, "..", "scripts", "intra_node")

VARIANTS = ["native", "container"]
VARIANT_COLOR = {"native": "#1f77b4", "container": "#ff7f0e"}
VARIANT_MARKER = {"native": "o", "container": "x"}
VARIANT_LABEL = {"native": "Native", "container": "Container"}

COMBOS = [("mpiio", "shared"), ("posix", "fpp")]
COMBO_LABELS = {"mpiio_shared": "Combo A: MPI-IO + Shared", "posix_fpp": "Combo B: POSIX + FPP"}
T_SIZES = [("1m", 1048576), ("4m", 4194304), ("16m", 16777216)]

missing = []


def load_point(variant, api, model, tlabel):
    """Return (mean_MiB, ci_halfwidth_MiB) for the write op, or None if the
    result file is missing/incomplete."""
    path = os.path.join(DATA_ROOT, variant, api, model, f"ior_t{tlabel}.txt")
    summary = parse_ior_summary(path)
    if "write" not in summary:
        missing.append(f"{variant}/{api}/{model}/t{tlabel}")
        return None
    mean, std, n = summary["write"]
    return mean, ci95_halfwidth(std, n)


def print_table():
    header = f"{'combo':<26} {'variant':<10} {'t':>4}  {'write mean (GiB/s)':>19}  {'95% CI':>10}"
    print(header)
    print("-" * len(header))
    for api, model in COMBOS:
        for tlabel, _ in T_SIZES:
            for variant in VARIANTS:
                pt = load_point(variant, api, model, tlabel)
                label = COMBO_LABELS[f"{api}_{model}"]
                if pt is None:
                    print(f"{label:<26} {VARIANT_LABEL[variant]:<10} {tlabel:>4}  {'no data yet':>19}")
                    continue
                mean, ci = pt
                print(f"{label:<26} {VARIANT_LABEL[variant]:<10} {tlabel:>4}  "
                      f"{mean / MIB_PER_GIB:>19.3f}  {ci / MIB_PER_GIB:>10.3f}")
    print()
    for api, model in COMBOS:
        label = COMBO_LABELS[f"{api}_{model}"]
        for tlabel, _ in T_SIZES:
            pn = load_point("native", api, model, tlabel)
            pc = load_point("container", api, model, tlabel)
            if pn and pc:
                diff_pct = (pc[0] - pn[0]) / pn[0] * 100
                print(f"{label} @ t={tlabel}: container is {diff_pct:+.1f}% vs native")


def plot_transfer_sweep():
    fig, axes = plt.subplots(1, len(COMBOS), figsize=(11, 5), sharey=True)
    any_data = False

    for col, (api, model) in enumerate(COMBOS):
        ax = axes[col]
        for variant in VARIANTS:
            xs, ys, yerrs = [], [], []
            for tlabel, tbytes in T_SIZES:
                pt = load_point(variant, api, model, tlabel)
                if pt is None:
                    continue
                mean, ci = pt
                xs.append(tbytes)
                ys.append(mean / MIB_PER_GIB)
                yerrs.append(ci / MIB_PER_GIB)
            if xs:
                any_data = True
                ax.errorbar(xs, ys, yerr=yerrs, color=VARIANT_COLOR[variant],
                            marker=VARIANT_MARKER[variant], label=VARIANT_LABEL[variant],
                            capsize=4, linewidth=1.8, markersize=7)
        ax.set_xscale("log", base=2)
        ax.set_xticks([b for _, b in T_SIZES])
        ax.set_xticklabels([lbl for lbl, _ in T_SIZES])
        ax.grid(True, which="both", alpha=0.3)
        ax.set_title(COMBO_LABELS[f"{api}_{model}"])
        ax.set_xlabel("Transfer Size (-t)")
        if col == 0:
            ax.set_ylabel("Write Bandwidth (GiB/s)")

    if not any_data:
        print("  [skip] transfer-size sweep -- no data yet")
        plt.close(fig)
        return
    axes[0].legend()
    fig.suptitle("IOR Intra-Node Write, Stripe Count 4\n"
                 "Native vs Container -- error bars = 95% CI across 10 repetitions")
    savefig(fig, "intra_write_transfer_sweep.png")


def plot_combo_bar(tlabel="4m"):
    x = range(len(COMBOS))
    width = 0.32
    fig, ax = plt.subplots(figsize=(7, 5.5))
    any_data = False

    for i, variant in enumerate(VARIANTS):
        ys, yerrs = [], []
        for api, model in COMBOS:
            pt = load_point(variant, api, model, tlabel)
            if pt is None:
                ys.append(0.0)
                yerrs.append(0.0)
                continue
            mean, ci = pt
            ys.append(mean / MIB_PER_GIB)
            yerrs.append(ci / MIB_PER_GIB)
            any_data = True
        offset = (i - 0.5) * width
        xs = [xi + offset for xi in x]
        ax.bar(xs, ys, width=width, yerr=yerrs, capsize=5,
               color=VARIANT_COLOR[variant], alpha=0.88, label=VARIANT_LABEL[variant])
        for xi, y in zip(xs, ys):
            if y > 0:
                ax.annotate(f"{y:.2f}", (xi, y), textcoords="offset points",
                            xytext=(0, 6), ha="center", fontsize=9, fontweight="bold")

    if not any_data:
        print(f"  [skip] combo bar chart t={tlabel} -- no data yet")
        plt.close(fig)
        return
    ax.set_xticks(list(x))
    ax.set_xticklabels([COMBO_LABELS[f"{a}_{m}"] for a, m in COMBOS])
    ax.set_ylabel("Write Bandwidth (GiB/s)")
    ax.grid(axis="y", alpha=0.3)
    ax.legend()
    fig.suptitle(f"IOR Intra-Node Write -- Combo A vs Combo B, t={tlabel.upper()}, Stripe Count 4\n"
                 "Native vs Container -- error bars = 95% CI across 10 repetitions")
    savefig(fig, f"intra_write_bar_t{tlabel}.png")


def main():
    print_table()
    print()
    print("Transfer-size sweep...")
    plot_transfer_sweep()
    print("Combo bar chart (t=4m)...")
    plot_combo_bar()

    if missing:
        uniq = sorted(set(missing))
        print(f"\n{len(uniq)} data points had no completed Summary yet and were skipped:")
        for m in uniq:
            print(f"  - {m}")

    print("Done.")


if __name__ == "__main__":
    main()
