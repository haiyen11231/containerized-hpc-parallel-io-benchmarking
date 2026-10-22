"""OSU report figures -- one idea per figure, following analysis/GUIDE.md.

Deliberately NOT consolidated. An earlier attempt merged these into four dense
multi-panel figures; that made each one harder to read and to caption, and one
of them compared workloads that are not comparable (pt2pt latency against
collective latency on a single bar axis). For a report, one figure answering
one question is clearer than a figure answering three.

  Fig 1A  pt2pt latency vs message size (intra/inter panels)
  Fig 1B  pt2pt bandwidth vs message size (intra/inter panels)
  Fig 2A  Allreduce, intra-node only (8 -> 128 ranks)
  Fig 2B  Allreduce, inter-node only (2/4/8 nodes)
  Fig 2C  Alltoall, intra-node only (8 -> 128 ranks)
  Fig 2D  Alltoall, inter-node only, with the failure point
  Fig 2E  inter-node growth vs node count (2 -> 8), both benches
  Fig 3   Alltoall port-exhaustion diagnostic
  Fig 4   Hockney decomposition (alpha vs B, intra/inter)

Intra and inter-node collective figures are kept SEPARATE (2A/2C vs 2B/2D)
rather than one figure spanning 8->1024 ranks on a single axis -- the earlier
combined version compressed the 5-point intra-node curve and the 3-point
inter-node curve together, with a "network starts" divider doing a lot of
work to keep them readable. Splitting removes the divider entirely: each
figure's x-axis only ever means one thing.

Appendix: Fig A1, the native NP=64 anomaly.

Run:  python3 analysis/plot_osu.py
"""

import glob
import math
import os
import statistics as st

import matplotlib.pyplot as plt
import numpy as np

import common as C

PT = os.path.join(os.path.dirname(__file__), "..", "results", "pt2pt")
CO = os.path.join(os.path.dirname(__file__), "..", "results", "collective")

INTRA_NP = [8, 16, 32, 64, 128]
INTER_N = [2, 4, 8]


def _rows(pattern):
    out = []
    for f in sorted(glob.glob(pattern)):
        for line in open(f):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            p = line.split()
            if len(p) >= 2:
                try:
                    out.append((int(p[0]), float(p[1])))
                except ValueError:
                    pass
    return out


def pt2pt(place, variant, bench):
    d = {}
    for s, v in _rows(os.path.join(PT, place, variant, bench, f"osu_{bench}_rep*.txt")):
        d.setdefault(s, []).append(v)
    return d


def coll(mode, scope, variant, bench, key):
    sub = (f"intra_node/{mode}_scaling/{variant}/{bench}/np{key}" if scope == "intra"
           else f"inter_node/{mode}_scaling/{variant}/{bench}/n{key}")
    return [v for _, v in _rows(os.path.join(CO, sub, f"osu_{bench}_rep*.txt"))]


def ci95(vals):
    """Half-width of the 95% confidence interval."""
    if len(vals) < 2:
        return 0.0
    return C.t_crit_95(len(vals) - 1) * st.stdev(vals) / math.sqrt(len(vals))


def alpha_B(mean_by_size):
    sizes = sorted(mean_by_size)
    floor = min(mean_by_size[s] for s in sizes[:8])
    flat = [mean_by_size[s] for s in sizes if s <= 1024 and mean_by_size[s] <= floor * 1.3]
    a = st.median(flat)
    big = max(mean_by_size)
    return a, big / ((mean_by_size[big] - a) * 1e-6) / 1e6


def _fmt(v):
    """Compact value label: 0.15 / 1.5 / 15 / 150 / 1.5k."""
    if v >= 10000:
        return f"{v/1000:.0f}k"
    if v >= 1000:
        return f"{v:.0f}"
    if v >= 100:
        return f"{v:.0f}"
    if v >= 10:
        return f"{v:.1f}"
    if v >= 1:
        return f"{v:.2f}"
    return f"{v:.3f}".rstrip("0")


def label_points(ax, xs, ys, variant, every=1, fmt=_fmt, dy=9):
    """Write the value beside each plotted point.

    Native labels go above the marker and container labels below, so the two
    series never collide on a log axis where the curves run close together.
    `every` thins the labels on dense series -- 23 message sizes x 2 variants
    would be 46 labels and unreadable. `dy` is the offset magnitude in points;
    sparse series (few data points, e.g. collective scaling) can pass a
    larger value for extra clearance when native and container values land
    close together, without affecting dense pt2pt sweeps that rely on the
    tighter default.
    """
    up = variant == "native"
    last = len(xs) - 1
    for i, (x, y) in enumerate(zip(xs, ys)):
        # Always label the endpoints: the first is alpha (the fixed cost) and
        # the last is the bandwidth-dominated regime -- the two values the
        # Hockney decomposition is read from. Thin only the middle.
        if i % every and i != last and i != 0:
            continue
        ax.annotate(fmt(y), (x, y), textcoords="offset points",
                    xytext=(0, dy if up else -(dy + 6)), ha="center", fontsize=6.5,
                    color=C.VARIANT_COLOR[variant], fontweight="bold", zorder=7,
                    bbox=dict(boxstyle="round,pad=0.12", fc="white",
                              ec="none", alpha=0.65))


def _two_panel(title, ylabel, logy=True):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for ax, place in zip(axes, ("intra_node", "inter_node")):
        ax.set_xscale("log", base=2)
        if logy:
            ax.set_yscale("log")
        ax.set_xlabel("Message size (bytes)")
        ax.grid(alpha=0.3, which="both")
        ax.set_title(C.PLACEMENT_LABEL[place], fontsize=11)
    axes[0].set_ylabel(ylabel)
    fig.suptitle(title, fontsize=12.5)
    return fig, axes


# ------------------------------------------------------------------ Fig 1A/1B
def fig_pt2pt(bench, name, title, ylabel):
    fig, axes = _two_panel(title, ylabel)
    for ax, place in zip(axes, ("intra_node", "inter_node")):
        for variant in C.VARIANTS:
            d = pt2pt(place, variant, bench)
            sizes = sorted(d)
            means = [st.mean(d[s]) for s in sizes]
            ax.errorbar(sizes, means, yerr=[ci95(d[s]) for s in sizes],
                        marker=C.VARIANT_MARKER[variant], markersize=4, linewidth=1.7,
                        capsize=2.5, color=C.VARIANT_COLOR[variant],
                        label=C.VARIANT_LABEL[variant])
            label_points(ax, sizes, means, variant, every=4)
        ax.legend(fontsize=9.5)
    fig.tight_layout()
    return C.save(fig, name)


# ------------------------------------------------------------------ Fig 2A/2B
def _collective_panel(ax, mode, bench, scope):
    """One (mode, scope) panel: native+container, value labels, FAILS markers.

    scope="intra" plots rank count 8..128 on one node; scope="inter" plots
    node count 2/4/8 (256..1024 ranks). Kept as one helper so the intra and
    inter figures share identical statistics/label logic and can only differ
    in which keys they iterate -- a bug fixed in one cannot silently diverge
    from the other.
    """
    keys = INTRA_NP if scope == "intra" else INTER_N
    for variant in C.VARIANTS:
        xs, ys, es, fails = [], [], [], []
        for k in keys:
            # intra: k IS the rank count. inter: k is the node count (128
            # ranks/node); x-axis is plotted in nodes, not total ranks.
            v = coll(mode, scope, variant, bench, k)
            if v:
                xs.append(k); ys.append(st.mean(v)); es.append(ci95(v))
            elif variant == "container":
                fails.append(k)
        ax.errorbar(xs, ys, yerr=es, marker=C.VARIANT_MARKER[variant], markersize=6,
                    linewidth=1.9, capsize=3, color=C.VARIANT_COLOR[variant],
                    label=C.VARIANT_LABEL[variant])
        # Extra label clearance (vs the pt2pt default): only 3-5 points per
        # series here, sometimes close in value (e.g. native/container both
        # land near 350-430us at n=8 strong), so the default pt2pt spacing
        # let the two labels touch.
        label_points(ax, xs, ys, variant, dy=18)
        for p in fails:
            top = max(ys) if ys else 1
            ax.scatter([p], [top], marker="X", s=170, color=C.VARIANT_COLOR[variant],
                       zorder=6, edgecolors="white", linewidths=0.9)
            ax.annotate("FAILS", (p, top), textcoords="offset points", xytext=(0, 11),
                        ha="center", fontsize=8.5, fontweight="bold",
                        color=C.VARIANT_COLOR[variant])
    ax.set_xscale("log", base=2); ax.set_yscale("log")
    ax.set_xlabel("Total MPI ranks" if scope == "intra" else "Nodes (128 ranks/node)")
    ax.set_title(f"{mode} scaling", fontsize=11)
    ax.grid(alpha=0.3, which="both"); ax.legend(fontsize=9.5)


def fig_collective_intra(bench, name, title):
    """Intra-node only: 8..128 ranks, one node, shared memory throughout."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for ax, mode in zip(axes, ("weak", "strong")):
        _collective_panel(ax, mode, bench, "intra")
    axes[0].set_ylabel("Latency (us)")
    fig.suptitle(title, fontsize=12.5)
    fig.tight_layout()
    return C.save(fig, name)


def fig_collective_inter(bench, name, title):
    """Inter-node only: 2/4/8 nodes, 128 ranks/node (256..1024 total)."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for ax, mode in zip(axes, ("weak", "strong")):
        _collective_panel(ax, mode, bench, "inter")
        ax.set_xticks(INTER_N); ax.set_xticklabels([str(n) for n in INTER_N])
    axes[0].set_ylabel("Latency (us)")
    fig.suptitle(title, fontsize=12.5)
    fig.tight_layout()
    return C.save(fig, name)



# ---------------------------------------------------------------- Fig 2C
def fig_internode_scaling():
    """How cost GROWS with node count, inter-node only (2 -> 8 nodes).

    Figures 2A/2B span 8 -> 1024 ranks and therefore mix intra-node and
    inter-node regimes on one axis, which is right for showing the sign flip
    but hides how steeply each benchmark degrades once the network is the only
    path. This figure isolates that: node count on x, growth relative to the
    2-node point on y, so the slope IS the scaling penalty.

    A flat line means adding nodes costs nothing. The dashed references are
    what each benchmark's workload growth alone would predict:
      weak allreduce : flat        (per-rank data constant, O(log P) rounds)
      weak alltoall  : linear in P (per-rank traffic = S x P)
      strong (both)  : flat        (total work fixed)
    Distance above the dashed line is contention, not workload.
    """
    NODES = [2, 4, 8]
    fig, axes = plt.subplots(2, 2, figsize=(12.5, 8.5))
    for row, mode in enumerate(("weak", "strong")):
        for col, bench in enumerate(("allreduce", "alltoall")):
            ax = axes[row][col]
            for variant in C.VARIANTS:
                xs, ys, fails = [], [], []
                base = None
                for n in NODES:
                    v = coll(mode, "inter", variant, bench, n)
                    if v:
                        m = st.mean(v)
                        if base is None:
                            base = m
                        xs.append(n); ys.append(m / base)
                    else:
                        fails.append(n)
                if xs:
                    ax.plot(xs, ys, marker=C.VARIANT_MARKER[variant], markersize=7,
                            linewidth=2, color=C.VARIANT_COLOR[variant],
                            label=C.VARIANT_LABEL[variant])
                    for x_, y_ in zip(xs, ys):
                        ax.annotate(f"{y_:.2f}x", (x_, y_), textcoords="offset points",
                                    xytext=(0, 9 if variant == "native" else -16),
                                    ha="center", fontsize=8.5, fontweight="bold",
                                    color=C.VARIANT_COLOR[variant])
                # Failures are pinned near the top of the native curve, not at
                # y=1.0 -- at 1.0 the marker and its label landed on the x-axis
                # tick text and rendered as "FA4LS".
                if fails:
                    ref = coll(mode, "inter", "native", bench, max(NODES))
                    base_n = coll(mode, "inter", "native", bench, NODES[0])
                    top = (st.mean(ref) / st.mean(base_n)) if ref and base_n else 2.0
                    # Sit the marker a little below the native maximum and put
                    # the caption UNDER it. Above the marker the text escaped
                    # the axes and overprinted the panel title; at y=1.0 it
                    # overprinted the x tick labels.
                    ymark = top * 0.72
                    for n in fails:
                        ax.scatter([n], [ymark], marker="X", s=150,
                                   color=C.VARIANT_COLOR[variant], zorder=6,
                                   edgecolors="white", linewidths=0.9)
                        ax.annotate("container\nFAILS", (n, ymark),
                                    textcoords="offset points", xytext=(0, -26),
                                    ha="center", fontsize=7.5, fontweight="bold",
                                    color=C.VARIANT_COLOR[variant])

            # workload-growth reference
            if mode == "weak" and bench == "alltoall":
                ax.plot(NODES, [n / 2 for n in NODES], "k--", linewidth=1.3,
                        alpha=0.6, label="workload growth (linear in P)")
            else:
                ax.axhline(1.0, color="black", linestyle="--", linewidth=1.3,
                           alpha=0.6, label="workload growth (flat)")

            ax.set_xscale("log", base=2); ax.set_yscale("log")
            ax.set_xticks(NODES); ax.set_xticklabels([f"{n}\n({n*128} ranks)" for n in NODES])
            ax.set_xlabel("Nodes"); ax.set_ylabel("Cost relative to 2 nodes")
            ax.set_title(f"{bench} — {mode} scaling", fontsize=11)
            ax.grid(alpha=0.3, which="both"); ax.legend(fontsize=8)
    fig.suptitle("Figure 2E — Inter-node growth: how cost rises as nodes are added (2 → 8)\n"
                 "dashed line is what workload growth alone predicts; distance above it is contention",
                 fontsize=12)
    fig.tight_layout()
    return C.save(fig, "fig2e_internode_growth.png")


# ---------------------------------------------------------------------- Fig 3
def fig_port():
    PORTS = 28232
    arms = [("container\n128 ranks/node\n(512 total)", 65408, False, "#d62728"),
            ("container\n64 ranks/node\n(256 total)", 16320, True, "#2ca02c"),
            ("native\n128 ranks/node\n(512 total)", 0, True, "#1f77b4")]
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    xs = np.arange(3)
    ax.bar(xs, [a[1] for a in arms], color=[a[3] for a in arms], alpha=0.85, width=0.6)
    ax.axhline(PORTS, color="black", linestyle="--", linewidth=1.7)
    ax.text(2.42, PORTS * 1.07, f"ephemeral port limit  {PORTS:,}",
            fontsize=9, ha="right", fontweight="bold")
    for i, (_, conns, ok, col) in enumerate(arms):
        if conns:
            ax.annotate(f"{conns:,}  ({conns/PORTS:.2f}x)", (i, conns),
                        textcoords="offset points", xytext=(0, 5),
                        ha="center", fontsize=9.5, fontweight="bold")
        else:
            ax.annotate("0 sockets\n(RDMA)", (i, 1800), ha="center",
                        fontsize=9, fontweight="bold", color="#1f77b4")
        ax.text(i, -5500, "PASS" if ok else "FAIL", ha="center", fontsize=11,
                fontweight="bold", color="#2ca02c" if ok else "#d62728")
    ax.set_xticks(xs); ax.set_xticklabels([a[0] for a in arms], fontsize=9)
    ax.set_ylim(-9000, 72000)
    ax.set_ylabel("Outbound TCP connections per node")
    ax.grid(axis="y", alpha=0.3)
    ax.set_title("Figure 3 — Alltoall failure is TCP port exhaustion\n"
                 "three arms, same 4 nodes, same 51 s: only the connection count differs",
                 fontsize=11.5)
    fig.tight_layout()
    return C.save(fig, "fig3_port_exhaustion.png")


# ---------------------------------------------------------------------- Fig 4
def fig_hockney():
    fig, ax = plt.subplots(figsize=(8, 5))
    ap, bp, delta = [], [], 0
    for place in ("intra_node", "inter_node"):
        an, bn = alpha_B({s: st.mean(v) for s, v in pt2pt(place, "native", "latency").items()})
        ac, bc = alpha_B({s: st.mean(v) for s, v in pt2pt(place, "container", "latency").items()})
        ap.append(ac / an); bp.append(bn / bc)
        if place == "inter_node":
            delta = ac - an
    x = np.arange(2); w = 0.35
    for bars in (ax.bar(x - w / 2, ap, w, label=r"per-message overhead  $\alpha$", color="#d62728"),
                 ax.bar(x + w / 2, bp, w, label="bandwidth  $B$", color="#1f77b4")):
        for r in bars:
            ax.annotate(f"{r.get_height():.2f}x", (r.get_x() + r.get_width() / 2, r.get_height()),
                        textcoords="offset points", xytext=(0, 3), ha="center",
                        fontsize=10.5, fontweight="bold")
    ax.axhline(1.0, color="black", linestyle="--", linewidth=1.2)
    ax.set_xticks(x); ax.set_xticklabels(["Intra-node", "Inter-node"], fontsize=10.5)
    ax.set_yscale("log"); ax.set_ylim(0.8, 20)
    ax.set_ylabel("Container penalty (x worse than native)")
    ax.legend(fontsize=10); ax.grid(axis="y", alpha=0.3, which="both")
    ax.set_title(r"Figure 4 — Hockney decomposition  $T(S)=\alpha+S/B$" "\n"
                 rf"inter-node $\alpha$ adds {delta:.1f} $\mu$s to every message, whatever its size",
                 fontsize=11.5)
    fig.tight_layout()
    return C.save(fig, "fig4_hockney_decomposition.png")


# --------------------------------------------------------------------- Fig A1
def fig_np64():
    fig, ax = plt.subplots(figsize=(8, 5))
    for variant in C.VARIANTS:
        xs, ys, es = [], [], []
        for p in INTRA_NP:
            v = coll("weak", "intra", variant, "allreduce", p)
            if v:
                xs.append(p); ys.append(st.mean(v)); es.append(ci95(v))
        ax.errorbar(xs, ys, yerr=es, marker=C.VARIANT_MARKER[variant], markersize=7,
                    linewidth=2, capsize=4, color=C.VARIANT_COLOR[variant],
                    label=C.VARIANT_LABEL[variant])
        label_points(ax, xs, ys, variant)
    ax.axvspan(48, 88, color="#d62728", alpha=0.08)
    ax.annotate("NP=64: ~4x its neighbors\nCV ~1%, both variants", xy=(64, 470),
                xytext=(14, 300), fontsize=9, color="#d62728", fontweight="bold",
                arrowprops=dict(arrowstyle="->", color="#d62728", lw=1.2))
    ax.set_xscale("log", base=2); ax.set_yscale("log")
    ax.set_xlabel("Ranks (single node)"); ax.set_ylabel("Allreduce latency (us)")
    ax.grid(alpha=0.3, which="both"); ax.legend(fontsize=9.5)
    ax.set_title("Figure A1 — Native Allreduce is non-monotonic at NP=64\n"
                 "bindings.txt rules out socket saturation; OpenMPI algorithm selection remains",
                 fontsize=11)
    fig.tight_layout()
    return C.save(fig, "figA1_np64_anomaly.png")


if __name__ == "__main__":
    print("Generating OSU report figures...")
    fig_pt2pt("latency", "fig1a_pt2pt_latency.png",
              "Figure 1A — Point-to-point latency vs message size  (mean, 95% CI)",
              "Latency (us)")
    fig_pt2pt("bw", "fig1b_pt2pt_bandwidth.png",
              "Figure 1B — Point-to-point bandwidth vs message size  (mean, 95% CI)",
              "Bandwidth (MB/s)")
    fig_collective_intra("allreduce", "fig2a_allreduce_intra.png",
                         "Figure 2A — Allreduce, intra-node  (8 to 128 ranks, 1 node, mean, 95% CI)")
    fig_collective_inter("allreduce", "fig2b_allreduce_inter.png",
                         "Figure 2B — Allreduce, inter-node  (2/4/8 nodes, 128 ranks/node, mean, 95% CI)")
    fig_collective_intra("alltoall", "fig2c_alltoall_intra.png",
                         "Figure 2C — Alltoall, intra-node  (8 to 128 ranks, 1 node, mean, 95% CI)")
    fig_collective_inter("alltoall", "fig2d_alltoall_inter.png",
                         "Figure 2D — Alltoall, inter-node  (container fails beyond 256 ranks)")
    fig_internode_scaling()
    fig_port()
    fig_hockney()
    fig_np64()
