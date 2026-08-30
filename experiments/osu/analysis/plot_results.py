#!/usr/bin/env python3
"""Plot native-vs-container OSU benchmark results.

Reads from experiments/osu/results/{native,container}/... and writes
figures to experiments/osu/analysis/figures/.
"""
import glob
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

RESULTS_ROOT = os.path.join(os.path.dirname(__file__), "..", "results")
FIG_DIR = os.path.join(os.path.dirname(__file__), "figures")

VARIANTS = ["native", "container"]
VARIANT_STYLE = {
    "native": dict(color="#1f77b4", marker="o", linestyle="-", label="Native"),
    "container": dict(color="#ff7f0e", marker="x", linestyle="--", label="Container"),
}
REGIMES = ["small", "medium", "large"]
REGIME_TITLES = {"small": "Small (8B–1KB)", "medium": "Medium (64KB–8MB)", "large": "Large (1MB–128MB)"}


def parse_osu_file(path):
    """Return (sizes, values) from an OSU benchmark output file."""
    sizes, values = [], []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            sizes.append(int(parts[0]))
            values.append(float(parts[1]))
    return sizes, values


def load_pt2pt(variant, placement, metric):
    """Aggregate the 10 repeated runs into per-size mean/std."""
    pattern = os.path.join(RESULTS_ROOT, variant, "pt2pt", metric, placement, "*_run_*.txt")
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"  [warn] no files for {variant}/{metric}/{placement}: {pattern}")
        return np.array([]), np.array([]), np.array([])

    by_size = {}
    for f in files:
        sizes, values = parse_osu_file(f)
        for s, v in zip(sizes, values):
            by_size.setdefault(s, []).append(v)

    sizes_sorted = sorted(by_size)
    means = np.array([np.mean(by_size[s]) for s in sizes_sorted])
    stds = np.array([np.std(by_size[s]) for s in sizes_sorted])
    return np.array(sizes_sorted), means, stds


def load_collective(variant, placement, scaling):
    """Return {regime: {N: latency_us}} for one variant/placement/scaling combo."""
    unit = "np" if placement == "intra" else "n"
    pattern = os.path.join(
        RESULTS_ROOT, variant, "collective", placement, f"{scaling}_scaling",
        f"allreduce_{placement}_{scaling}_*_{unit}*.txt",
    )
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"  [warn] no files for {variant}/collective/{placement}/{scaling}: {pattern}")

    name_re = re.compile(rf"allreduce_{placement}_{scaling}_(\w+)_{unit}(\d+)\.txt$")
    data = {r: {} for r in REGIMES}
    for f in files:
        m = name_re.search(os.path.basename(f))
        if not m:
            continue
        regime, n = m.group(1), int(m.group(2))
        _, values = parse_osu_file(f)
        if values:
            data[regime][n] = values[0]
    return data


def savefig(fig, name):
    os.makedirs(FIG_DIR, exist_ok=True)
    path = os.path.join(FIG_DIR, name)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  wrote {path}")


def plot_pt2pt_curves():
    for metric, ylabel in [("latency", "Latency (us)"), ("bandwidth", "Bandwidth (MB/s)")]:
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)
        for ax, placement in zip(axes, ["intra", "inter"]):
            for variant in VARIANTS:
                sizes, means, stds = load_pt2pt(variant, placement, metric)
                if len(sizes) == 0:
                    continue
                style = VARIANT_STYLE[variant]
                ax.plot(sizes, means, **style)
                ax.fill_between(sizes, means - stds, means + stds, color=style["color"], alpha=0.15)
            ax.set_xscale("log")
            ax.set_yscale("log")
            ax.set_xlabel("Message Size (Bytes)")
            ax.set_title(f"{placement.capitalize()}-node")
            ax.grid(True, which="both", alpha=0.3)
        axes[0].set_ylabel(ylabel)
        axes[0].legend()
        fig.suptitle(f"OSU {metric.capitalize()}: Native vs Container (mean ± std over 10 runs)")
        savefig(fig, f"pt2pt_{metric}.png")


def plot_pt2pt_overhead():
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for ax, (metric, ylabel) in zip(axes, [("latency", "Container / Native ratio"), ("bandwidth", "Container / Native ratio")]):
        for placement, ls in [("intra", "-"), ("inter", "--")]:
            sizes_n, means_n, _ = load_pt2pt("native", placement, metric)
            sizes_c, means_c, _ = load_pt2pt("container", placement, metric)
            if len(sizes_n) == 0 or len(sizes_c) == 0:
                continue
            common = sorted(set(sizes_n) & set(sizes_c))
            ratio = [
                means_c[list(sizes_c).index(s)] / means_n[list(sizes_n).index(s)]
                for s in common
            ]
            ax.plot(common, ratio, linestyle=ls, marker="o", markersize=3, label=f"{placement}-node")
        ax.axhline(1.0, color="gray", linewidth=1, label="parity (=1.0)")
        ax.set_xscale("log")
        ax.set_xlabel("Message Size (Bytes)")
        ax.set_ylabel(ylabel)
        ax.set_title(metric.capitalize())
        ax.grid(True, which="both", alpha=0.3)
        ax.legend()
    fig.suptitle("Containerization Overhead Ratio (pt2pt)")
    savefig(fig, "pt2pt_overhead.png")


def plot_collective_grid(placement):
    unit_label = "Processes (NP)" if placement == "intra" else "Nodes (N)"
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), sharex="col")
    for row, scaling in enumerate(["strong", "weak"]):
        native_data = load_collective("native", placement, scaling)
        container_data = load_collective("container", placement, scaling)
        for col, regime in enumerate(REGIMES):
            ax = axes[row][col]
            for variant, data in [("native", native_data), ("container", container_data)]:
                d = data[regime]
                if not d:
                    continue
                xs = sorted(d)
                ys = [d[x] for x in xs]
                ax.plot(xs, ys, **VARIANT_STYLE[variant])
            ax.set_xscale("log", base=2)
            ax.set_yscale("log")
            ax.grid(True, which="both", alpha=0.3)
            if row == 0:
                ax.set_title(REGIME_TITLES[regime])
            if col == 0:
                ax.set_ylabel(f"{scaling.capitalize()} scaling\nLatency (us)")
            if row == 1:
                ax.set_xlabel(unit_label)
    axes[0][0].legend()
    fig.suptitle(f"Allreduce Scaling ({placement}-node): Native vs Container")
    savefig(fig, f"collective_{placement}.png")


def plot_collective_overhead(placement):
    unit_label = "Processes (NP)" if placement == "intra" else "Nodes (N)"
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)
    for ax, scaling in zip(axes, ["strong", "weak"]):
        native_data = load_collective("native", placement, scaling)
        container_data = load_collective("container", placement, scaling)
        for regime in REGIMES:
            dn, dc = native_data[regime], container_data[regime]
            common = sorted(set(dn) & set(dc))
            if not common:
                continue
            ratio = [dc[n] / dn[n] for n in common]
            ax.plot(common, ratio, marker="o", markersize=4, label=REGIME_TITLES[regime])
        ax.axhline(1.0, color="gray", linewidth=1)
        ax.set_xscale("log", base=2)
        ax.set_xlabel(unit_label)
        ax.set_title(f"{scaling.capitalize()} scaling")
        ax.grid(True, which="both", alpha=0.3)
    axes[0].set_ylabel("Container / Native latency ratio")
    axes[0].legend()
    fig.suptitle(f"Containerization Overhead Ratio — Allreduce ({placement}-node)")
    savefig(fig, f"collective_overhead_{placement}.png")


def main():
    print("pt2pt curves...")
    plot_pt2pt_curves()
    print("pt2pt overhead ratio...")
    plot_pt2pt_overhead()
    print("collective scaling grids...")
    plot_collective_grid("intra")
    plot_collective_grid("inter")
    print("collective overhead ratios...")
    plot_collective_overhead("intra")
    plot_collective_overhead("inter")
    print("Done.")


if __name__ == "__main__":
    main()
