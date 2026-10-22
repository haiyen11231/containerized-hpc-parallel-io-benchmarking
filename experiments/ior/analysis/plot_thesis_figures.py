#!/usr/bin/env python3
"""Generate the 5 thesis chapter figures.

Same safety principle as the other plotting scripts: a missing or
incomplete result file is skipped/left as NaN, never fabricated as zero.

NOTE on Figure 5: it requires container multinode_scaling data, which does
not exist yet (only native multinode scripts have been built/run so far).
The code is fully ready for when that data exists -- it will just fill in
automatically. In the meantime a substitute heatmap (5b) is generated using
1node_sweep data, which does have both native and container, so there is a
real, populated heatmap available now rather than only placeholder code.
"""
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ANALYSIS_DIR = os.path.dirname(__file__)
ONE_NODE_ROOT = os.path.join(ANALYSIS_DIR, "..", "results", "1node_sweep")
MULTI_ROOT = os.path.join(ANALYSIS_DIR, "..", "results", "multinode_scaling")
FIG_DIR = os.path.join(ANALYSIS_DIR, "figures")

MIB_PER_GIB = 1024.0  # IOR reports MiB/s; convert to GiB/s throughout

VARIANTS = ["native", "container"]
VARIANT_STYLE = {
    "native": dict(color="#1f77b4", marker="o", linestyle="-", label="Native"),
    "container": dict(color="#ff7f0e", marker="x", linestyle="--", label="Container"),
}
# For figures that overlay Write and Read in the same panel (fig3, fig4):
# color+marker identify the variant, linestyle identifies the metric, so
# both dimensions are visible at once without needing separate subplots.
VARIANT_COLOR = {"native": "#1f77b4", "container": "#ff7f0e"}
VARIANT_MARKER = {"native": "o", "container": "x"}
METRIC_LINESTYLE = {"Write": "-", "Read": "--"}
APIS = ["posix", "mpiio"]
MODELS = ["shared", "fpp"]
STRIPE_COUNTS = [1, 4, 8, 16]
T_SIZES = [("32k", 32768), ("256k", 262144), ("1m", 1048576), ("4m", 4194304)]
NODE_COUNTS = [1, 2, 4, 8]
COMBOS = [("posix", "shared"), ("posix", "fpp"), ("mpiio", "shared"), ("mpiio", "fpp")]
COMBO_LABELS = {"posix_shared": "POSIX-Shared", "posix_fpp": "POSIX-FPP",
                "mpiio_shared": "MPIIO-Shared", "mpiio_fpp": "MPIIO-FPP"}


def parse_ior_result(path):
    """Return (write_bw, read_bw) in MiB/s, taken from the LAST *completed*
    iteration's raw row for each of write/read independently -- not an
    average, and not requiring all -i 3 repetitions to have finished.

    IOR only prints a 'write ...'/'read ...' row once that phase of an
    iteration is fully done, so any such row found is a genuine completed
    measurement. Its Summary-of-all-tests row ALSO starts with 'write'/
    'read' though (reporting Max/Min/Mean, not a raw value), so that section
    is excluded before scanning -- otherwise its Max(MiB) column would win.

    If a run was killed partway through (e.g. completed iterations 0-1 but
    not 2, or completed iteration 2's write but not its read), this uses
    whatever the latest completed value is for write and read independently
    -- still never fabricating a number that wasn't actually printed by IOR.
    Returns (None, None) only if the file is missing/empty or has no
    complete row at all.
    """
    if not os.path.exists(path):
        return None, None
    with open(path) as f:
        content = f.read()
    iteration_section = content.split("Summary of all tests:", 1)[0]
    write_bw = read_bw = None
    for line in iteration_section.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "write":
            try:
                write_bw = float(parts[1])
            except ValueError:
                pass
        elif len(parts) >= 2 and parts[0] == "read":
            try:
                read_bw = float(parts[1])
            except ValueError:
                pass
    return write_bw, read_bw


def load_1node(variant, api, model, stripe, tlabel):
    path = os.path.join(ONE_NODE_ROOT, variant, api, model, f"stripe_c{stripe}", f"ior_t{tlabel}.txt")
    return parse_ior_result(path)


def load_multinode(variant, regime, api, model, n):
    path = os.path.join(MULTI_ROOT, variant, api, model, regime, f"ior_n{n}.txt")
    return parse_ior_result(path)


def savefig(fig, name, rect=None):
    os.makedirs(FIG_DIR, exist_ok=True)
    path = os.path.join(FIG_DIR, name)
    fig.tight_layout(rect=rect)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  wrote {path}")


# ---------------------------------------------------------------------------
# Figure 1: Transfer Size vs Throughput (1-Node Syscall Sensitivity)
# ---------------------------------------------------------------------------
def fig1_transfer_size_syscall(stripe=8, model="shared"):
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), sharex=True)
    any_data = False
    for row, (metric_idx, metric_name) in enumerate([(0, "Write"), (1, "Read")]):
        for col, api in enumerate(APIS):
            ax = axes[row][col]
            for variant in VARIANTS:
                xs, ys = [], []
                for tlabel, tbytes in T_SIZES:
                    w, r = load_1node(variant, api, model, stripe, tlabel)
                    val = w if metric_idx == 0 else r
                    if val is not None:
                        xs.append(tbytes)
                        ys.append(val / MIB_PER_GIB)
                if xs:
                    any_data = True
                    ax.plot(xs, ys, **VARIANT_STYLE[variant])
            ax.set_xscale("log", base=2)
            ax.set_yscale("log")
            # Only 4 transfer sizes were actually tested and they are not
            # evenly log-spaced (32k=2^15, 256k=2^18, 1m=2^20, 4m=2^22) --
            # ticking every power of 2 would misleadingly imply denser sampling.
            ax.set_xticks([b for _, b in T_SIZES])
            ax.set_xticklabels([lbl for lbl, _ in T_SIZES])
            ax.grid(True, which="both", alpha=0.3)
            ax.set_title(f"{api.upper()} ({metric_name})")
            if row == 1:
                ax.set_xlabel("Transfer Size")
            if col == 0:
                ax.set_ylabel("Bandwidth (GiB/s)")
    if not any_data:
        print("  [skip] Figure 1: no data available")
        plt.close(fig)
        return
    axes[0][0].legend()
    fig.suptitle(f"Figure 1: I/O Bandwidth vs. Transfer Size (1 Node)\n"
                 f"Native vs Container -- Stripe Count {stripe}, {model.capitalize()} File")
    savefig(fig, "fig1_transfer_size_syscall.png")


# ---------------------------------------------------------------------------
# Figure 2: Lustre Stripe Count Scaling (grouped bar chart, Native vs Container)
# ---------------------------------------------------------------------------
# Bars encode {Native,Container} x {Shared,FPP}: color=variant (matches the
# native/container color used everywhere else), hatch=model.
_FIG2_BAR_SPECS = [
    ("native", "shared", VARIANT_COLOR["native"], None),
    ("native", "fpp", VARIANT_COLOR["native"], "//"),
    ("container", "shared", VARIANT_COLOR["container"], None),
    ("container", "fpp", VARIANT_COLOR["container"], "//"),
]


def fig2_stripe_bar_chart(tlabel="4m"):
    """2x2 grid (rows=Write/Read, cols=API). x=stripe count, 4 bars/group."""
    x = np.arange(len(STRIPE_COUNTS))
    width = 0.2
    fig, axes = plt.subplots(2, 2, figsize=(13, 10), sharex=True, sharey="row")
    any_data = False
    for row, (metric_idx, metric_name) in enumerate([(0, "Write"), (1, "Read")]):
        for col, api in enumerate(APIS):
            ax = axes[row][col]
            for i, (variant, model, color, hatch) in enumerate(_FIG2_BAR_SPECS):
                ys = []
                for stripe in STRIPE_COUNTS:
                    w, r = load_1node(variant, api, model, stripe, tlabel)
                    val = w if metric_idx == 0 else r
                    ys.append(val / MIB_PER_GIB if val is not None else np.nan)
                if any(not np.isnan(y) for y in ys):
                    any_data = True
                ax.bar(x + (i - 1.5) * width, ys, width, color=color, hatch=hatch,
                       edgecolor="black", linewidth=0.5,
                       label=f"{variant.capitalize()}-{model.capitalize()}")
            ax.grid(True, axis="y", alpha=0.3)
            ax.set_title(f"{api.upper()} ({metric_name})")
            if row == 1:
                ax.set_xticks(x)
                ax.set_xticklabels([str(s) for s in STRIPE_COUNTS])
                ax.set_xlabel("Stripe Count")
            if col == 0:
                ax.set_ylabel(f"{metric_name} Bandwidth (GiB/s)")
    if not any_data:
        print("  [skip] Figure 2: no data available")
        plt.close(fig)
        return
    axes[0][0].legend(fontsize=8)
    fig.suptitle(f"Figure 2: I/O Bandwidth vs. Lustre Stripe Count (1 Node)\n"
                 f"Native vs Container, Write vs Read -- Transfer Size {tlabel.upper()}")
    savefig(fig, "fig2_stripe_bar_chart.png")


# ---------------------------------------------------------------------------
# Figure 3: Weak Scaling Performance (1-8 Nodes)
# ---------------------------------------------------------------------------
def fig3_weak_scaling():
    """2x2 grid (one panel per API x model combo). Within each panel: color
    identifies Native vs Container, linestyle identifies Write (solid) vs
    Read (dashed) -- both dimensions visible at once, no need to split
    write/read into separate subplots."""
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), sharex=True)
    any_data = False
    for idx, (api, model) in enumerate(COMBOS):
        row, col = idx // 2, idx % 2
        ax = axes[row][col]
        for variant in VARIANTS:
            for metric_name in ["Write", "Read"]:
                xs, ys = [], []
                for n in NODE_COUNTS:
                    w, r = load_multinode(variant, "weak_scaling", api, model, n)
                    val = w if metric_name == "Write" else r
                    if val is not None:
                        xs.append(n)
                        ys.append(val / MIB_PER_GIB)
                if xs:
                    any_data = True
                    ax.plot(xs, ys, color=VARIANT_COLOR[variant], marker=VARIANT_MARKER[variant],
                            linestyle=METRIC_LINESTYLE[metric_name],
                            label=f"{variant.capitalize()} ({metric_name})")
        ax.set_xscale("log", base=2)
        ax.set_yscale("log")
        ax.grid(True, which="both", alpha=0.3)
        ax.set_title(COMBO_LABELS[f"{api}_{model}"])
        if row == 1:
            ax.set_xlabel("Node Count")
        if col == 0:
            ax.set_ylabel("Aggregate Bandwidth (GiB/s)")
    if not any_data:
        print("  [skip] Figure 3: no data available")
        plt.close(fig)
        return
    axes[0][0].legend(fontsize=8)
    fig.suptitle("Figure 3: Aggregate Bandwidth vs. Node Count (Weak Scaling)\n"
                 "Native vs Container, Write vs Read -- Fixed 512MiB per Rank")
    savefig(fig, "fig3_weak_scaling.png")


# ---------------------------------------------------------------------------
# Figure 4: Strong Scaling Parallel Efficiency
# ---------------------------------------------------------------------------
def fig4_strong_scaling_efficiency():
    """2x2 grid (one panel per API x model combo), same convention as fig3:
    color identifies Native vs Container, linestyle identifies Write (solid)
    vs Read (dashed), efficiency computed independently for each metric."""
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), sharex=True, sharey=True)
    any_data = False
    for idx, (api, model) in enumerate(COMBOS):
        row, col = idx // 2, idx % 2
        ax = axes[row][col]
        for variant in VARIANTS:
            for metric_name in ["Write", "Read"]:
                w1, r1 = load_multinode(variant, "strong_scaling", api, model, 1)
                base = w1 if metric_name == "Write" else r1
                if base is None or base == 0:
                    continue
                xs, ys = [], []
                for n in NODE_COUNTS:
                    wn, rn = load_multinode(variant, "strong_scaling", api, model, n)
                    val = wn if metric_name == "Write" else rn
                    if val is not None:
                        xs.append(n)
                        ys.append((val / (n * base)) * 100)
                if xs:
                    any_data = True
                    ax.plot(xs, ys, color=VARIANT_COLOR[variant], marker=VARIANT_MARKER[variant],
                            linestyle=METRIC_LINESTYLE[metric_name],
                            label=f"{variant.capitalize()} ({metric_name})")
        ax.axhline(100, color="gray", linestyle=":", linewidth=1, label="Ideal (100%)")
        ax.set_xscale("log", base=2)
        ax.grid(True, which="both", alpha=0.3)
        ax.set_title(COMBO_LABELS[f"{api}_{model}"])
        if row == 1:
            ax.set_xlabel("Node Count")
        if col == 0:
            ax.set_ylabel("Parallel Efficiency (%)")
    if not any_data:
        print("  [skip] Figure 4: no data available")
        plt.close(fig)
        return
    axes[0][0].legend(fontsize=7)
    fig.suptitle("Figure 4: Parallel Efficiency vs. Node Count (Strong Scaling)\n"
                 "Native vs Container, Write vs Read -- Fixed 128GiB Total Dataset")
    fig.text(0.5, 0.01,
             "Caveat: each point is a single last-iteration sample (not averaged), so Read efficiency in "
             "particular can exceed 100% when the 1-node baseline read happened to be a slow sample -- "
             "read bandwidth is inherently noisier here than write due to Lustre client-side caching effects.",
             ha="center", va="bottom", fontsize=8, style="italic", color="dimgray", wrap=True)
    savefig(fig, "fig4_strong_scaling_efficiency.png", rect=[0, 0.04, 1, 1])


# ---------------------------------------------------------------------------
# Figure 5: Container Overhead Heatmap (multi-node) -- ready, but no
# container multinode data exists yet, so this will currently be all-NaN.
# ---------------------------------------------------------------------------
def _overhead_pct(native_val, container_val):
    if native_val is None or container_val is None or native_val == 0:
        return np.nan
    return (native_val - container_val) / native_val * 100


def fig5_overhead_heatmap_multinode():
    rows = []
    row_labels = []
    for regime in ["weak_scaling", "strong_scaling"]:
        for n in NODE_COUNTS:
            row_labels.append(f"{'Weak' if regime == 'weak_scaling' else 'Strong'} N={n}")
            row = []
            for api, model in COMBOS:
                wn, _ = load_multinode("native", regime, api, model, n)
                wc, _ = load_multinode("container", regime, api, model, n)
                row.append(_overhead_pct(wn, wc))
            rows.append(row)
    data = np.array(rows)

    if np.all(np.isnan(data)):
        print("  [skip] Figure 5 (multi-node): no container multinode data exists yet -- "
              "code is ready, will populate automatically once those experiments are run.")
        return

    _draw_heatmap(data, row_labels, [COMBO_LABELS[f"{a}_{m}"] for a, m in COMBOS],
                  "Figure 5: Container Overhead Heatmap (Multi-Node)", "fig5_overhead_heatmap_multinode.png")


def fig5b_overhead_heatmap_1node(tlabel="4m"):
    """Substitute heatmap using 1node_sweep data, which has real native+container
    coverage right now, unlike the multi-node case above."""
    rows = []
    row_labels = []
    for stripe in STRIPE_COUNTS:
        row_labels.append(f"stripe_c{stripe}")
        row = []
        for api, model in COMBOS:
            wn, _ = load_1node("native", api, model, stripe, tlabel)
            wc, _ = load_1node("container", api, model, stripe, tlabel)
            row.append(_overhead_pct(wn, wc))
        rows.append(row)
    data = np.array(rows)

    if np.all(np.isnan(data)):
        print("  [skip] Figure 5b: no data available")
        return

    _draw_heatmap(data, row_labels, [COMBO_LABELS[f"{a}_{m}"] for a, m in COMBOS],
                  f"Figure 5b: Container Overhead Heatmap (1-Node, t={tlabel})\n"
                  f"(Substitute for Fig 5 -- populated now; Fig 5 needs container multinode data)",
                  "fig5b_overhead_heatmap_1node.png")


def _draw_heatmap(data, row_labels, col_labels, title, filename):
    fig, ax = plt.subplots(figsize=(8, 0.5 * len(row_labels) + 2))
    cmap = matplotlib.colormaps["RdYlGn_r"].copy()
    cmap.set_bad(color="#dddddd")  # missing data shown as neutral gray, not a color-scale value
    masked = np.ma.masked_invalid(data)
    im = ax.imshow(masked, cmap=cmap, vmin=0, vmax=15, aspect="auto")

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

    cbar = fig.colorbar(im, ax=ax, label="Container Overhead (%)  [green=0%, red>=15%]")
    fig.suptitle(title)
    savefig(fig, filename)


def main():
    print("Figure 1: transfer size vs throughput (syscall sensitivity)...")
    fig1_transfer_size_syscall()
    print("Figure 2: stripe count scaling (bar chart)...")
    fig2_stripe_bar_chart()
    print("Figure 3: weak scaling...")
    fig3_weak_scaling()
    print("Figure 4: strong scaling parallel efficiency...")
    fig4_strong_scaling_efficiency()
    print("Figure 5: overhead heatmap (multi-node)...")
    fig5_overhead_heatmap_multinode()
    print("Figure 5b: overhead heatmap (1-node substitute, populated now)...")
    fig5b_overhead_heatmap_1node()
    print("Done.")


if __name__ == "__main__":
    main()
