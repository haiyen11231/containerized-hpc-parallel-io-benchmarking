"""h5bench write, intra-node, CONTIG/CONTIG -- Native vs Container.

Reads every write_rep*.csv under
  ../scripts/intra_node/write/contig_contig/payload/{native,container}/*/
(h5bench's own per-rep summary output) and plots mean +/- 95% CI for:
  - Observed completion time (seconds)
  - Observed write rate (GB/s)

Run:  python3 analysis/plot_write_cc.py
"""

import glob
import math
import os
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
DATA_ROOT = os.path.join(HERE, "..", "scripts", "intra_node", "write", "contig_contig", "payload")
FIG_DIR = os.path.join(HERE, "figures")

VARIANTS = ["native", "container"]
COLOR = {"native": "#1f77b4", "container": "#ff7f0e"}
LABEL = {"native": "Native", "container": "Container"}

_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
        8: 2.306, 9: 2.262, 10: 2.228}


def t_crit_95(df):
    keys = sorted(k for k in _T95 if k <= df)
    return _T95[keys[-1]] if keys else 1.96


def ci95(vals):
    if len(vals) < 2:
        return 0.0
    return t_crit_95(len(vals) - 1) * st.stdev(vals) / math.sqrt(len(vals))


def parse_csv(path):
    """h5bench's own 'metric, value, unit' summary -> {metric: (float(value), unit)}.

    h5bench switches a given metric's unit between MB/s and GB/s depending on
    magnitude *within the same set of reps* -- keep the unit alongside the
    value so callers can normalize before doing any arithmetic on it.
    """
    out = {}
    for line in open(path):
        parts = [p.strip() for p in line.strip().split(",")]
        if len(parts) >= 2:
            try:
                out[parts[0]] = (float(parts[1]), parts[2] if len(parts) > 2 else "")
            except ValueError:
                continue
    return out


def to_gbps(value, unit):
    """Both 'MB/s' and 'GB/s' are binary despite the labels (1 GB/s = 1024 MB/s)."""
    if unit == "MB/s":
        return value / 1024.0
    if unit == "GB/s":
        return value
    raise ValueError(f"unexpected rate unit: {unit!r}")


def load_variant(variant):
    """All write_rep*.csv under payload/<variant>/*/ -> lists of (time, rate_gbps)."""
    pattern = os.path.join(DATA_ROOT, variant, "*", "write_rep*.csv")
    times, rates = [], []
    for f in sorted(glob.glob(pattern)):
        d = parse_csv(f)
        if "observed time" in d and "observed rate" in d:
            times.append(d["observed time"][0])
            rate_val, rate_unit = d["observed rate"]
            rates.append(to_gbps(rate_val, rate_unit))
    return times, rates


def bar_with_ci(ax, data, ylabel, title, fmt="{:.2f}"):
    variants = [v for v in VARIANTS if data[v]]
    x = range(len(variants))
    means = [st.mean(data[v]) for v in variants]
    errs = [ci95(data[v]) for v in variants]
    colors = [COLOR[v] for v in variants]
    ax.bar(x, means, yerr=errs, capsize=6, color=colors, alpha=0.88, width=0.5)
    for xi, m, v in zip(x, means, variants):
        n = len(data[v])
        ax.annotate(f"{fmt.format(m)}\n(n={n})", (xi, m), textcoords="offset points",
                    xytext=(0, 8), ha="center", fontsize=9, fontweight="bold")
    ax.set_xticks(list(x))
    ax.set_xticklabels([LABEL[v] for v in variants])
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=10.5)
    ax.grid(axis="y", alpha=0.3)
    for v in VARIANTS:
        if v not in variants:
            ax.text(0.5, 0.5, f"{LABEL[v]}: no data yet", transform=ax.transAxes,
                    ha="center", va="center", fontsize=9, color="gray", style="italic")


def main():
    os.makedirs(FIG_DIR, exist_ok=True)
    data = {v: load_variant(v) for v in VARIANTS}  # {variant: (times, rates)}

    for v in VARIANTS:
        times, rates = data[v]
        print(f"{LABEL[v]}: {len(times)} reps found" + (f" (mean time={st.mean(times):.2f}s, mean rate={st.mean(rates):.3f} GB/s)" if times else ""))

    time_data = {v: data[v][0] for v in VARIANTS}
    rate_data = {v: data[v][1] for v in VARIANTS}

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5))
    bar_with_ci(ax1, time_data, "Observed completion time (s)",
                "Observed completion time (SYNC)\nmean +/- 95% CI", fmt="{:.2f}")
    bar_with_ci(ax2, rate_data, "Observed write rate (GB/s)",
                "Observed write rate (SYNC)\nmean +/- 95% CI", fmt="{:.3f}")
    fig.suptitle("h5bench write -- intra-node, CONTIG/CONTIG, 64 ranks, 80 GB total", fontsize=11.5)
    fig.tight_layout()

    out = os.path.join(FIG_DIR, "write_cc_native_vs_container.png")
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
