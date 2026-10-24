"""h5bench write, intra-node -- CONTIG/CONTIG vs INTERLEAVED/CONTIG, Native vs Container.

Reads every write_rep*.csv under both combos'
  ../scripts/intra_node/write/{contig_contig,interleaved_contig}/payload/{native,container}/*/
and compares, across all four (combo, variant) cells:
  - Observed completion time (seconds)
  - Observed write rate (GB/s)

Prints a summary table (mean +/- 95% CI, n) and writes a grouped bar chart.

Run:  python3 analysis/plot_write_comparison.py
"""

import glob
import math
import os
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
WRITE_ROOT = os.path.join(HERE, "..", "scripts", "intra_node", "write")
FIG_DIR = os.path.join(HERE, "figures")

COMBOS = ["contig_contig", "interleaved_contig"]
COMBO_LABEL = {"contig_contig": "CONTIG/CONTIG", "interleaved_contig": "INTERLEAVED/CONTIG"}
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


def load_cell(combo, variant):
    """All write_rep*.csv for one (combo, variant) -> lists of (time, rate_gbps)."""
    pattern = os.path.join(WRITE_ROOT, combo, "payload", variant, "*", "write_rep*.csv")
    times, rates = [], []
    for f in sorted(glob.glob(pattern)):
        d = parse_csv(f)
        if "observed time" in d and "observed rate" in d:
            times.append(d["observed time"][0])
            rate_val, rate_unit = d["observed rate"]
            rates.append(to_gbps(rate_val, rate_unit))
    return times, rates


def print_table(data):
    header = f"{'combo':<20} {'variant':<10} {'n':>3}  {'time mean (s)':>16}  {'time 95% CI':>12}  {'rate mean (GB/s)':>17}  {'rate 95% CI':>12}"
    print(header)
    print("-" * len(header))
    for combo in COMBOS:
        for variant in VARIANTS:
            times, rates = data[(combo, variant)]
            if not times:
                print(f"{COMBO_LABEL[combo]:<20} {LABEL[variant]:<10} {'--':>3}  {'no data yet':>16}")
                continue
            print(f"{COMBO_LABEL[combo]:<20} {LABEL[variant]:<10} {len(times):>3}  "
                  f"{st.mean(times):>16.2f}  {ci95(times):>12.2f}  "
                  f"{st.mean(rates):>17.3f}  {ci95(rates):>12.3f}")

    # Native-vs-container gap per combo, since that's the actual comparison of interest.
    print()
    for combo in COMBOS:
        nt, nr = data[(combo, "native")]
        ct, cr = data[(combo, "container")]
        if nt and ct:
            dt = (st.mean(ct) - st.mean(nt)) / st.mean(nt) * 100
            dr = (st.mean(cr) - st.mean(nr)) / st.mean(nr) * 100
            print(f"{COMBO_LABEL[combo]}: container is {dt:+.1f}% on time, {dr:+.1f}% on rate, vs. native")


def grouped_bar(ax, data_by_combo, ylabel, title, fmt="{:.2f}"):
    n_combo = len(COMBOS)
    width = 0.35
    x = range(n_combo)
    for i, variant in enumerate(VARIANTS):
        means = [st.mean(data_by_combo[combo][variant]) if data_by_combo[combo][variant] else 0 for combo in COMBOS]
        errs = [ci95(data_by_combo[combo][variant]) for combo in COMBOS]
        offset = (i - 0.5) * width
        xs = [xi + offset for xi in x]
        bars = ax.bar(xs, means, width=width, yerr=errs, capsize=5,
                       color=COLOR[variant], alpha=0.88, label=LABEL[variant])
        for xi, m, combo in zip(xs, means, COMBOS):
            n = len(data_by_combo[combo][variant])
            if n:
                ax.annotate(f"{fmt.format(m)}\n(n={n})", (xi, m), textcoords="offset points",
                            xytext=(0, 6), ha="center", fontsize=8, fontweight="bold")
    ax.set_xticks(list(x))
    ax.set_xticklabels([COMBO_LABEL[c] for c in COMBOS])
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=10.5)
    ax.grid(axis="y", alpha=0.3)
    ax.legend(fontsize=9)


def main():
    os.makedirs(FIG_DIR, exist_ok=True)
    data = {(combo, variant): load_cell(combo, variant) for combo in COMBOS for variant in VARIANTS}

    print_table(data)

    time_by_combo = {combo: {v: data[(combo, v)][0] for v in VARIANTS} for combo in COMBOS}
    rate_by_combo = {combo: {v: data[(combo, v)][1] for v in VARIANTS} for combo in COMBOS}

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5.5))
    grouped_bar(ax1, time_by_combo, "Observed completion time (s)",
                "Observed completion time (SYNC)\nmean +/- 95% CI", fmt="{:.2f}")
    grouped_bar(ax2, rate_by_combo, "Observed write rate (GB/s)",
                "Observed write rate (SYNC)\nmean +/- 95% CI", fmt="{:.3f}")
    fig.suptitle("h5bench write -- intra-node, 64 ranks, 80 GB total\nCONTIG/CONTIG vs INTERLEAVED/CONTIG, Native vs Container", fontsize=11.5)
    fig.tight_layout()

    out = os.path.join(FIG_DIR, "write_comparison_cc_vs_ic.png")
    fig.savefig(out, dpi=150)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
