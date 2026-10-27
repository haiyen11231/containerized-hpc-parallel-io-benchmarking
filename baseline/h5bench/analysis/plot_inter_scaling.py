"""h5bench write, inter-node weak/strong scaling -- Native vs Container (DRAFT).

Draft plot over whatever node-count tiers currently have results under
  ../scripts/inter_node/{weak,strong}_scaling/payload/{native,container}/n<N>/*/
(h5bench's own per-rep write_rep*.csv summaries). Missing tiers (e.g.
weak_scaling n4 while that rerun is still in flight, or any study's n8,
removed entirely -- see ../scripts/inter_node/*/README.md) are simply
skipped, not treated as zero.

Plots observed write rate (GB/s) vs node count, mean +/- 95% CI, one line
per variant, for each study.

Run:  python3 analysis/plot_inter_scaling.py
"""

import glob
import math
import os
import re
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
INTER_ROOT = os.path.join(HERE, "..", "scripts", "inter_node")
FIG_DIR = os.path.join(HERE, "figures")

STUDIES = {
    "weak_scaling": "Weak scaling (per-rank work fixed, total grows)",
    "strong_scaling": "Strong scaling (total work fixed, per-rank shrinks)",
}
VARIANTS = ["native", "container"]
COLOR = {"native": "#1f77b4", "container": "#ff7f0e"}
MARKER = {"native": "o", "container": "s"}
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


def load_tier(study, variant, node_count):
    """All write_rep*.csv under payload/<variant>/n<N>/*/ -> (times, rates_gbps)."""
    pattern = os.path.join(INTER_ROOT, study, "payload", variant, f"n{node_count}", "*", "write_rep*.csv")
    times, rates = [], []
    for f in sorted(glob.glob(pattern)):
        d = parse_csv(f)
        if "observed time" in d and "observed rate" in d:
            times.append(d["observed time"][0])
            rate_val, rate_unit = d["observed rate"]
            rates.append(to_gbps(rate_val, rate_unit))
    return times, rates


def available_node_counts(study, variant):
    tier_re = re.compile(r"^n(\d+)$")
    base = os.path.join(INTER_ROOT, study, "payload", variant)
    if not os.path.isdir(base):
        return []
    counts = []
    for name in os.listdir(base):
        m = tier_re.match(name)
        if m:
            counts.append(int(m.group(1)))
    return sorted(counts)


def plot_study(study, title):
    data = {}  # variant -> {node_count: (times, rates)}
    for variant in VARIANTS:
        data[variant] = {}
        for n in available_node_counts(study, variant):
            times, rates = load_tier(study, variant, n)
            if times:
                data[variant][n] = (times, rates)

    all_counts = sorted(set(n for v in data.values() for n in v))
    if not all_counts:
        print(f"{study}: no data found, skipping")
        return

    fig, ax = plt.subplots(figsize=(7, 5))
    means_by_variant = {}
    for variant in VARIANTS:
        tiers = data[variant]
        if not tiers:
            continue
        xs = sorted(tiers)
        means = [st.mean(tiers[n][1]) for n in xs]
        errs = [ci95(tiers[n][1]) for n in xs]
        means_by_variant[variant] = dict(zip(xs, means))
        ax.errorbar(xs, means, yerr=errs, label=f"{LABEL[variant]}", marker=MARKER[variant],
                    color=COLOR[variant], capsize=5, linewidth=1.8, markersize=7)

    # Stack labels above/below per x so two close values at the same node
    # count don't overlap -- whichever variant is higher at that x gets the
    # label above its marker, the other gets it below.
    for variant in VARIANTS:
        tiers = data[variant]
        if not tiers:
            continue
        for x in sorted(tiers):
            m = means_by_variant[variant][x]
            n = len(tiers[x][1])
            others = [means_by_variant[ov][x] for ov in VARIANTS if ov != variant and x in means_by_variant.get(ov, {})]
            above = not others or m >= others[0]
            ax.annotate(f"{m:.3f} (n={n})", (x, m), textcoords="offset points",
                        xytext=(0, 10 if above else -18), ha="center", fontsize=8.5,
                        va="bottom" if above else "top")

    for variant in VARIANTS:
        missing = sorted(set(all_counts) - set(data[variant]))
        if missing:
            print(f"{study}/{variant}: no data yet for node count(s) {missing} -- skipped, not plotted as zero")

    ax.set_xticks(all_counts)
    ax.set_xlabel("Node count")
    ax.set_ylabel("Observed write rate (GB/s)")
    ax.set_title(f"h5bench inter-node write -- {title}\nmean +/- 95% CI (DRAFT, partial data)", fontsize=10.5)
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()

    os.makedirs(FIG_DIR, exist_ok=True)
    out = os.path.join(FIG_DIR, f"inter_{study}_draft.png")
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")


def main():
    for study, title in STUDIES.items():
        plot_study(study, title)


if __name__ == "__main__":
    main()
