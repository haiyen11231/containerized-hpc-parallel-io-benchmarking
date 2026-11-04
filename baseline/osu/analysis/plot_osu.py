"""OSU report figures -- one idea per figure, following analysis/GUIDE.md.

Trimmed to 5 figures for the report (2026-11-04): pt2pt (both scopes) and
collective Alltoall/Allreduce inter-node only. Intra-node collective scaling,
inter-node relative growth, the NP=64 appendix, and the Hockney decomposition
are no longer plotted here -- the first three are discussed in
baseline/osu/results/collective/intra_node/README.md instead; the Hockney
decomposition was dropped outright (not needed for this report).

  Fig 1A  pt2pt latency vs message size (intra/inter panels)
  Fig 1B  pt2pt bandwidth vs message size (intra/inter panels)
  Fig 2B  Allreduce, inter-node only (2/4/8 nodes)
  Fig 2D  Alltoall, inter-node only, with the failure point
  Fig 3   Alltoall port-exhaustion diagnostic

Run:  python3 analysis/plot_osu.py
"""

import glob
import math
import os
import re
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
        # Always label the endpoints -- the smallest message (where fixed
        # per-message cost dominates) and the largest (the asymptotic,
        # bandwidth-saturated regime) are the two most informative points on
        # the curve. Thin only the middle.
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



# ---------------------------------------------------------------------- Fig 3
_PORT_DIAG_LOG = os.path.join(os.path.dirname(__file__), "..", "scripts", "collective",
                               "inter_node", "diagnostics", "logs",
                               "osu_port_exhaustion_diag.out")


def _parse_port_diag(path=_PORT_DIAG_LOG):
    """Parse the real diagnostic log instead of hardcoding its numbers.

    The port limit (28,232) is not assumed: `port_exhaustion_diag.pbs` reads
    `/proc/sys/net/ipv4/ip_local_port_range` on an actual compute node and
    records it (`ports_available:` line). Each arm's PASS/FAIL verdict is not
    assumed either: the same script runs `osu_alltoall`, greps its own output
    for "Address already in use" (the real port-exhaustion error), and the
    verdict is `exit_code == 0 and data_rows >= 1` -- a real job outcome, not
    an inferred one. See that script's `run_arm()` for the exact logic.
    """
    text = open(path).read()
    ports = int(re.search(r"ports_available:\s+(\d+)", text).group(1))
    arms = {}
    for block in re.split(r"\narm:\s+", text)[1:]:
        label, rest = block.split(None, 1)
        conns = int(re.search(r"predicted_conns_node:\s+(\d+)", rest).group(1))
        passed = re.search(r"verdict:\s+(\S+)", rest).group(1) == "PASS"
        arms[label] = (conns, passed)
    return ports, arms


def fig_port():
    PORTS, diag = _parse_port_diag()
    c128_conns, c128_ok = diag["container_rpn128"]
    c64_conns, c64_ok = diag["container_rpn64"]
    _, n128_ok = diag["native_rpn128"]
    assert (not c128_ok) and c64_ok and n128_ok, (
        "port-exhaustion diagnostic verdicts changed from what this figure "
        "assumes -- re-check the log before trusting this plot")
    arms = [
        ("container\n128 ranks/node\n(512 total)", c128_conns, c128_ok, "#d62728"),
        ("container\n64 ranks/node\n(256 total)", c64_conns, c64_ok, "#2ca02c"),
        # Native's own "predicted" count in the log is the same 65408 as the
        # container arm above (the deliberate same-connection-count control),
        # but it is never real: native moves data over UCX/RDMA and opens zero
        # TCP sockets. Plotted as 0, not the log's predicted number, so the
        # bar shows what native actually does, not a hypothetical.
        ("native\n128 ranks/node\n(512 total)", 0, n128_ok, "#1f77b4"),
    ]
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
    ax.set_title("Alltoall failure: TCP ephemeral-port exhaustion", fontsize=11.5)
    fig.tight_layout()
    return C.save(fig, "fig3_port_exhaustion.png")


if __name__ == "__main__":
    print("Generating OSU report figures...")
    fig_pt2pt("latency", "fig1a_pt2pt_latency.png",
              "Point-to-point latency vs message size",
              "Latency (us)")
    fig_pt2pt("bw", "fig1b_pt2pt_bandwidth.png",
              "Point-to-point bandwidth vs message size",
              "Bandwidth (MB/s)")
    fig_collective_inter("allreduce", "fig2b_allreduce_inter.png",
                         "Allreduce, inter-node (2/4/8 nodes, 128 ranks/node)")
    fig_collective_inter("alltoall", "fig2d_alltoall_inter.png",
                         "Alltoall, inter-node (container fails beyond 256 ranks)")
    fig_port()
