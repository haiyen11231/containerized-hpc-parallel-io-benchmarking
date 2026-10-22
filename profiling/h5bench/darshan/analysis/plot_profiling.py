"""h5bench Darshan profiling -- comparison figures.

Data transcribed directly from darshan-parser output on the profiling jobs
(profiling/h5bench/darshan/scripts/{native,container}/...), extracted per
profiling/h5bench/GUIDE.md section 3's own grep recipes.

  figH1_H3  intra-node time share (write+meta as % of wall-clock)
  figH2_H4  SIZE_WRITE histogram, contig_contig vs contig_interleaved
  figH5_H6  weak/strong scaling, write+meta share and meta-only share

Run:  python3 analysis/plot_profiling.py
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(__file__)
FIG_DIR = os.path.join(HERE, "figures")
os.makedirs(FIG_DIR, exist_ok=True)

COMBOS = ["contig_contig", "contig_interleaved", "interleaved_contig", "interleaved_interleaved"]
COMBO_LABEL = {
    "contig_contig": "CONTIG→CONTIG",
    "contig_interleaved": "CONTIG→INTERLEAVED",
    "interleaved_contig": "INTERLEAVED→CONTIG",
    "interleaved_interleaved": "INTERLEAVED→INTERLEAVED",
}

# variant -> combo -> (runtime_s, write_time_sum, meta_time_sum, nprocs) -- mean of rep1+rep2
INTRA = {
    "native": {
        "contig_contig":             ((16.2715 + 16.8692) / 2, (1958.06 + 2055.88) / 2, (2.34271 + 2.30461) / 2, 128),
        "contig_interleaved":        ((108.9057 + 106.3175) / 2, (12336.9 + 12620.1) / 2, (2.23692 + 2.36593) / 2, 128),
        "interleaved_contig":        ((24.3773 + 21.5800) / 2, (2103.7 + 1773.09) / 2, (2.4361 + 2.3005) / 2, 128),
        "interleaved_interleaved":   ((17.5612 + 18.5728) / 2, (1894.21 + 2067.24) / 2, (2.26745 + 2.33372) / 2, 128),
    },
    "container": {
        "contig_contig":             (16.4254, 1981.38, 2.68146, 128),
        "contig_interleaved":        (108.8829, 12295.0, 2.36337, 128),
        "interleaved_contig":        (21.7170, 1787.72, 2.47412, 128),
        "interleaved_interleaved":   (15.3517, 1603.82, 2.35357, 128),
    },
}

COLOR = {"native": "#1f77b4", "container": "#d62728"}
LABEL = {"native": "Native", "container": "Container"}


def pct_write_meta(runtime, write_time, meta_time, nprocs):
    write_pct = (write_time / nprocs) / runtime * 100
    meta_pct = (meta_time / nprocs) / runtime * 100
    return write_pct, meta_pct


def fig_h1_h3():
    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(COMBOS))
    width = 0.35

    for i, variant in enumerate(["native", "container"]):
        write_pcts, meta_pcts = [], []
        for combo in COMBOS:
            runtime, wt, mt, n = INTRA[variant][combo]
            w, m = pct_write_meta(runtime, wt, mt, n)
            write_pcts.append(w)
            meta_pcts.append(m)
        offset = (i - 0.5) * width
        ax.bar(x + offset, write_pcts, width, label=f"{LABEL[variant]} -- write", color=COLOR[variant], alpha=0.85)
        ax.bar(x + offset, meta_pcts, width, bottom=write_pcts, label=f"{LABEL[variant]} -- meta", color=COLOR[variant], alpha=0.4, hatch="//")

    ax.set_xticks(x)
    ax.set_xticklabels([COMBO_LABEL[c] for c in COMBOS], rotation=15, ha="right")
    ax.set_ylabel("Share of wall-clock (%)")
    ax.set_title("h5bench write -- Darshan POSIX instrumentation, intra-node\n"
                  "1 node, 128 ranks, REPS=2 (mean)")
    ax.legend(ncol=2, fontsize=8, loc="upper left")
    ax.set_ylim(0, 105)
    fig.tight_layout()
    out = os.path.join(FIG_DIR, "figH1_H3_time_share_intra.png")
    fig.savefig(out, dpi=150)
    print(f"  wrote {out}")


# SIZE_WRITE histogram -- identical between native and container, so one set of bars
SIZE_BUCKETS = ["0_100", "100_1K", "1K_10K", "10K_100K", "100K_1M", "1M_4M", "4M_10M"]
SIZE_LABEL = {
    "0_100": "0-100B", "100_1K": "100B-1K", "1K_10K": "1K-10K", "10K_100K": "10K-100K",
    "100K_1M": "100K-1M", "1M_4M": "1M-4M", "4M_10M": "4M-10M",
}
HIST = {
    "contig_contig":      {"0_100": 8, "100_1K": 58, "1M_4M": 5120},
    "contig_interleaved": {"0_100": 9, "100_1K": 23, "100K_1M": 163840},
}


def fig_h2_h4():
    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(SIZE_BUCKETS))
    width = 0.35

    for i, combo in enumerate(["contig_contig", "contig_interleaved"]):
        counts = [HIST[combo].get(b, 0) for b in SIZE_BUCKETS]
        offset = (i - 0.5) * width
        ax.bar(x + offset, counts, width, label=COMBO_LABEL[combo])

    ax.set_xticks(x)
    ax.set_xticklabels([SIZE_LABEL[b] for b in SIZE_BUCKETS], rotation=30, ha="right")
    ax.set_yscale("log")
    ax.set_ylabel("Write call count (log scale)")
    ax.set_title("h5bench write -- POSIX_SIZE_WRITE histogram, intra-node\n"
                  "1 node, 128 ranks, REPS=2 (native and container identical)")
    ax.legend()
    fig.tight_layout()
    out = os.path.join(FIG_DIR, "figH2_H4_size_histogram.png")
    fig.savefig(out, dpi=150)
    print(f"  wrote {out}")


# variant -> mode -> n -> (runtime, write_time, meta_time, nprocs) -- mean of rep1+rep2
SCALING = {
    "native": {
        "weak":   {1: ((16.0875 + 37.1764) / 2, (1909.41 + 1981.43) / 2, (2.35595 + 2.31076) / 2, 128),
                   8: ((72.0741 + 669.5129) / 2, (36323.4 + 579128) / 2, (34.9655 + 35.685) / 2, 1024)},
        "strong": {1: ((86.5679 + 16.2074) / 2, (10714.1 + 1995.82) / 2, (2.23446 + 2.2978) / 2, 128),
                   8: ((24.0723 + 23.1618) / 2, (14605.6 + 16288.8) / 2, (41.8937 + 44.5402) / 2, 1024)},
    },
    "container": {
        "weak":   {1: (16.3216, 1961.93, 2.3955, 128),
                   8: ((60.5724 + 68.3936) / 2, (29781.1 + 30882.5) / 2, (38.4242 + 41.9303) / 2, 1024)},
        "strong": {1: (23.6770, 1890.61, 2.36132, 128),
                   8: ((20.1024 + 20.8088) / 2, (14257.2 + 14970.4) / 2, (38.073 + 40.5135) / 2, 1024)},
    },
}


def fig_h5_h6():
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))

    # Left panel: write+meta share vs node count, weak scaling
    ax = axes[0]
    for variant in ["native", "container"]:
        ns = [1, 8]
        shares = []
        for n in ns:
            runtime, wt, mt, nprocs = SCALING[variant]["weak"][n]
            w, m = pct_write_meta(runtime, wt, mt, nprocs)
            shares.append(w + m)
        ax.plot(ns, shares, marker="o", color=COLOR[variant], label=LABEL[variant])
        for xi, yi in zip(ns, shares):
            ax.annotate(f"{yi:.1f}%", (xi, yi), textcoords="offset points", xytext=(5, 5), fontsize=9, color=COLOR[variant])
    ax.set_xticks([1, 8])
    ax.set_xlabel("Node count (weak scaling, 128 ranks/node)")
    ax.set_ylabel("Write+meta share of wall-clock (%)")
    ax.set_title("Weak scaling: write+meta time share vs node count")
    ax.legend()

    # Right panel: meta-only share, weak vs strong, at n=8
    ax = axes[1]
    modes = ["weak", "strong"]
    x = np.arange(len(modes))
    width = 0.35
    for i, variant in enumerate(["native", "container"]):
        meta_pcts = []
        for mode in modes:
            runtime, wt, mt, nprocs = SCALING[variant][mode][8]
            _, m = pct_write_meta(runtime, wt, mt, nprocs)
            meta_pcts.append(m)
        offset = (i - 0.5) * width
        bars = ax.bar(x + offset, meta_pcts, width, label=LABEL[variant], color=COLOR[variant])
        ax.bar_label(bars, fmt="%.2f%%", fontsize=8, padding=2)
    ax.set_xticks(x)
    ax.set_xticklabels(["weak (32 MiB/rank)", "strong (128 KiB/rank)"])
    ax.set_ylabel("Meta-time share of wall-clock (%)")
    ax.set_title("8 nodes, 1024 ranks: meta-time share, weak vs strong")
    ax.legend()

    fig.suptitle("h5bench write -- Darshan POSIX instrumentation, inter-node scaling\n"
                  "128 ranks/node, REPS=2 (mean of 2 reps)")
    fig.tight_layout()
    out = os.path.join(FIG_DIR, "figH5_H6_scaling.png")
    fig.savefig(out, dpi=150)
    print(f"  wrote {out}")


if __name__ == "__main__":
    print("Generating h5bench Darshan profiling figures...")
    fig_h1_h3()
    fig_h2_h4()
    fig_h5_h6()
