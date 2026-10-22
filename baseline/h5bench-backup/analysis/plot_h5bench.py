"""h5bench report figures -- one idea per figure, following analysis/GUIDE.md.

Numbering and style mirror ../../osu/analysis/plot_osu.py and
../../ior/analysis/plot_ior.py so all three benchmarks read the same way:
1x = the first study type, 2x = scaling, 3 = the key diagnostic, A1 = appendix.

  Fig 1A  intra-node layout study      how do MEM x FILE patterns interact?
  Fig 2A  weak scaling vs ideal        can Lustre absorb more load?
  Fig 2B  strong scaling efficiency    does splitting fixed work help?
  Fig 3   collective I/O 2x2 factorial the mechanistic study

The cold-read validation has no figure. It measured 31x page-cache inflation
but two of its four cells were void (PBS reused the write nodes for the read
job), so it justifies excluding reads rather than producing a finding. A plot
documenting its own partial failure would obscure that; it lives in the README
as a methodological note instead.

All values are GiB/s normalized through common.to_gib(), because h5bench
labels binary units as decimal and switches between MB/s and GB/s by
magnitude -- averaging the raw numbers mixes scales.

Run:  python3 analysis/plot_h5bench.py
"""

import matplotlib.pyplot as plt
import numpy as np

import common as C

VARIANTS = ["native", "container"]
VCOLOR = {"native": "#1f77b4", "container": "#ff7f0e"}
VMARK = {"native": "o", "container": "x"}
VLABEL = {"native": "Native", "container": "Container"}
NODES = [1, 2, 4, 8]

PATTERNS = ["contig_contig", "contig_interleaved",
            "interleaved_contig", "interleaved_interleaved"]
PLABEL = {"contig_contig": "CONTIG mem\nCONTIG file",
          "contig_interleaved": "CONTIG mem\nINTERLEAVED file",
          "interleaved_contig": "INTERLEAVED mem\nCONTIG file",
          "interleaved_interleaved": "INTERLEAVED mem\nINTERLEAVED file"}

CELLS = ["dno_mno", "dno_myes", "dyes_mno", "dyes_myes"]
CLABEL = {"dno_mno": "data NO\nmeta NO", "dno_myes": "data NO\nmeta YES",
          "dyes_mno": "data YES\nmeta NO", "dyes_myes": "data YES\nmeta YES"}


def _bars(ax, keys, klabel, getter, ylabel, fmt="{:.2f}"):
    """Grouped native/container bars with 95% CI and value labels."""
    x = np.arange(len(keys)); w = 0.36
    for i, v in enumerate(VARIANTS):
        means, errs = [], []
        for k in keys:
            m, h, n = getter(v, k)
            means.append(0 if m != m else m)
            errs.append(0 if h != h else h)
        off = (-w / 2, w / 2)[i]
        ax.bar(x + off, means, w, yerr=errs, capsize=4,
               color=VCOLOR[v], alpha=0.88, label=VLABEL[v])
        for xi, mi in zip(x + off, means):
            if mi:
                ax.annotate(fmt.format(mi), (xi, mi), textcoords="offset points",
                            xytext=(0, 4), ha="center", fontsize=8.5, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels([klabel[k] for k in keys], fontsize=8.5)
    ax.set_ylabel(ylabel); ax.grid(axis="y", alpha=0.3); ax.legend(fontsize=9)


# ------------------------------------------------------------------ Fig 1A
def fig1a_layout():
    fig, ax = plt.subplots(figsize=(10, 5.4))
    _bars(ax, PATTERNS, PLABEL,
          lambda v, k: C.stats(C.intra(v, k)),
          "Write bandwidth (GiB/s)")
    ax.set_title("h5bench write -- intra-node, 1 node, 128 ranks\n"
                 "MEM_PATTERN x FILE_PATTERN sweep, REPS=10",
                 fontsize=11)
    C.savefig(fig, "fig1a_intra_layout.png")


# ------------------------------------------------------------------ Fig 2A
def fig2a_weak():
    fig, ax = plt.subplots(figsize=(9.5, 5.4))
    base = None
    for v in VARIANTS:
        xs, ys, es = [], [], []
        for n in NODES:
            m, h, k = C.stats(C.scaling("weak_scaling", v, n, "write"))
            if m == m:
                xs.append(n); ys.append(m); es.append(0 if h != h else h)
        if not xs:
            continue
        if base is None:
            base = ys[0]
        ax.errorbar(xs, ys, yerr=es, marker=VMARK[v], markersize=7, linewidth=1.9,
                    capsize=4, color=VCOLOR[v], label=VLABEL[v])
        for xi, yi in zip(xs, ys):
            ax.annotate(f"{yi:.2f}", (xi, yi), textcoords="offset points",
                        xytext=(0, 9 if v == "native" else -16), ha="center",
                        fontsize=8, fontweight="bold", color=VCOLOR[v])
    if base:
        ax.plot(NODES, [base * n for n in NODES], "k--", linewidth=1.3,
                alpha=0.6, label="ideal (linear)")
    ax.set_xscale("log", base=2); ax.set_yscale("log")
    ax.set_xticks(NODES); ax.set_xticklabels(NODES)
    ax.set_xlabel("Nodes (128 ranks each)"); ax.set_ylabel("Write bandwidth (GiB/s)")
    ax.grid(alpha=0.3, which="both"); ax.legend(fontsize=9.5)
    ax.set_title("h5bench write -- weak scaling, 1/2/4/8 nodes, 128 ranks/node\n"
                 "DIM_1 fixed at 1M particles/rank (32 MiB/rank/timestep), REPS=10",
                 fontsize=11)
    C.savefig(fig, "fig2a_weak_scaling.png")


# ------------------------------------------------------------------ Fig 2B
def fig2b_strong():
    fig, ax = plt.subplots(figsize=(9.5, 5.4))
    for v in VARIANTS:
        vals = {}
        for n in NODES:
            m, _, _ = C.stats(C.scaling("strong_scaling", v, n, "write"))
            if m == m:
                vals[n] = m
        if len(vals) < 2:
            continue
        b = vals[min(vals)]
        xs = sorted(vals)
        eff = [100 * vals[n] / (b * n) for n in xs]
        ax.plot(xs, eff, marker=VMARK[v], markersize=7, linewidth=1.9,
                color=VCOLOR[v], label=VLABEL[v])
        for xi, ei in zip(xs, eff):
            ax.annotate(f"{ei:.0f}%", (xi, ei), textcoords="offset points",
                        xytext=(0, 9 if v == "native" else -16), ha="center",
                        fontsize=8.5, fontweight="bold", color=VCOLOR[v])
    ax.axhline(100, color="black", linestyle="--", linewidth=1.2, alpha=0.6)
    ax.text(1.03, 103, "ideal", fontsize=8.5, color="#555555")
    ax.set_xscale("log", base=2); ax.set_xticks(NODES); ax.set_xticklabels(NODES)
    ax.set_ylim(0, 120)
    ax.set_xlabel("Nodes (128 ranks each)"); ax.set_ylabel("Parallel efficiency (%)")
    ax.grid(alpha=0.3); ax.legend(fontsize=9.5)
    ax.set_title("h5bench write -- strong scaling, 1/2/4/8 nodes, 128 ranks/node\n"
                 "TOTAL_PARTICLES fixed at 128M (DIM_1 = 1,048,576 -> 131,072 as nodes grow), REPS=10",
                 fontsize=11)
    C.savefig(fig, "fig2b_strong_scaling.png")


# ------------------------------------------------------------------- Fig 3
def fig3_collective():
    fig, ax1 = plt.subplots(figsize=(8, 5.4))
    _bars(ax1, CELLS, CLABEL,
          lambda v, k: C.stats(C.collective(v, k, "write")),
          "Write bandwidth (GiB/s)")
    ax1.set_title("h5bench write -- collective I/O, 2 nodes, 256 ranks, CONTIG/CONTIG\n"
                  "COLLECTIVE_DATA x COLLECTIVE_METADATA sweep, REPS=10",
                  fontsize=11)
    C.savefig(fig, "fig3_collective_io.png")


# ------------------------------------------------------------------ Fig A1
if __name__ == "__main__":
    print("Generating h5bench report figures...")
    fig1a_layout()
    fig2a_weak()
    fig2b_strong()
    fig3_collective()
