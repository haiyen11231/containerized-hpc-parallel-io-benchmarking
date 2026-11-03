#!/usr/bin/env python3
"""Plot the IOR inter-node study on TATE: weak and strong scaling over 1/2/3
nodes (16 ranks/node), Combo A (MPI-IO + Shared) vs Combo B (POSIX + FPP),
Native vs Container, write-only, -t 1m, -i 5, OMPIO fs_ufs_lock_algorithm 3.

  weak:   -b 16m per rank           -> 256 / 512 / 768 MiB total
  strong: 768 MiB total, -b 768m/NP -> 48m / 24m / 16m per rank

Reads ../scripts/inter_node/<study>/<variant>[-backup]/<api>/<model>/ior_n<N>.txt.
Two rounds exist: <variant>-backup/ (round 1, jobs 159-182) and <variant>/
(round 2, jobs 183-206). Each data point comes from ONE round, chosen in
SOURCE below; see that comment for the selection.

Figures produced:
  inter_weak_scaling_write.png
  inter_strong_scaling_write.png
      1x2 grid (one panel per combo). X = node count, Y = mean write
      bandwidth (MiB/s) with 95% CI error bars over the 5 repetitions,
      one line per variant.
  inter_container_overhead.png
      1x2 grid (weak, strong). Container vs native write bandwidth (%)
      per node count, grouped by combo.

Run:  python3 plot_inter_write.py
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import ci95_halfwidth, parse_ior_summary, savefig

HERE = os.path.dirname(__file__)
DATA_ROOT = os.path.join(HERE, "..", "scripts", "inter_node")

VARIANTS = ["native", "container"]
VARIANT_COLOR = {"native": "#1f77b4", "container": "#ff7f0e"}
VARIANT_MARKER = {"native": "o", "container": "x"}
VARIANT_LABEL = {"native": "Native", "container": "Container"}

STUDIES = ["weak_scaling", "strong_scaling"]
STUDY_LABEL = {"weak_scaling": "Weak Scaling", "strong_scaling": "Strong Scaling"}
COMBOS = [("mpiio", "shared"), ("posix", "fpp")]
COMBO_LABELS = {"mpiio_shared": "Combo A: MPI-IO + Shared", "posix_fpp": "Combo B: POSIX + FPP"}
COMBO_COLOR = {"mpiio_shared": "#2ca02c", "posix_fpp": "#9467bd"}
NODE_COUNTS = [1, 2, 3]
RANKS_PER_NODE = 16

# x tick sublabels: what each node count means in data terms
XTICK_DETAIL = {
    "weak_scaling": {1: "256 MiB total", 2: "512 MiB total", 3: "768 MiB total"},
    "strong_scaling": {1: "48m/rank", 2: "24m/rank", 3: "16m/rank"},
}

# Which round each point is read from: "backup" = round 1 (<variant>-backup/),
# "latest" = round 2 (<variant>/). Chosen per point by the experimenter: every
# point uses round 1 except strong-scaling POSIX FPP, where the round with no
# single disturbed repetition was taken for each variant and node count.
_ROUND1 = {(n, v): "backup" for n in NODE_COUNTS for v in VARIANTS}
SOURCE = {
    ("weak_scaling", "mpiio", "shared"): _ROUND1,
    ("weak_scaling", "posix", "fpp"): _ROUND1,
    ("strong_scaling", "mpiio", "shared"): _ROUND1,
    ("strong_scaling", "posix", "fpp"): {
        (1, "container"): "backup", (1, "native"): "latest",
        (2, "container"): "latest", (2, "native"): "backup",
        (3, "container"): "backup", (3, "native"): "latest",
    },
}

missing = []


def result_path(study, variant, api, model, n):
    rnd = SOURCE[(study, api, model)][(n, variant)]
    vdir = f"{variant}-backup" if rnd == "backup" else variant
    return os.path.join(DATA_ROOT, study, vdir, api, model, f"ior_n{n}.txt"), rnd


def load_point(study, variant, api, model, n):
    """Return (mean_MiB, ci_halfwidth_MiB) for the write op, or None if the
    result file is missing/incomplete."""
    path, _ = result_path(study, variant, api, model, n)
    summary = parse_ior_summary(path)
    if "write" not in summary:
        missing.append(f"{study}/{variant}/{api}/{model}/n{n}")
        return None
    mean, std, reps = summary["write"]
    return mean, ci95_halfwidth(std, reps)


def print_table():
    header = (f"{'study':<15} {'combo':<26} {'N':>2}  {'native MiB/s':>16} {'(round)':>8}  "
              f"{'container MiB/s':>16} {'(round)':>8}  {'c vs n':>7}")
    print(header)
    print("-" * len(header))
    for study in STUDIES:
        for api, model in COMBOS:
            for n in NODE_COUNTS:
                cells, pts = [], {}
                for variant in VARIANTS:
                    pt = load_point(study, variant, api, model, n)
                    _, rnd = result_path(study, variant, api, model, n)
                    pts[variant] = pt
                    cells.append(f"{'no data':>16} {rnd:>8}" if pt is None
                                 else f"{pt[0]:>8.1f} ± {pt[1]:>5.1f} {rnd:>8}")
                diff = ""
                if pts["native"] and pts["container"]:
                    diff = f"{(pts['container'][0] - pts['native'][0]) / pts['native'][0] * 100:+.1f}%"
                print(f"{study:<15} {COMBO_LABELS[f'{api}_{model}']:<26} {n:>2}  "
                      f"{cells[0]}  {cells[1]}  {diff:>7}")


def label_points(ax, xs, ys, variant, dy=9):
    """Write the value beside each plotted point -- native above, container
    below, so the two series never collide (same convention as OSU's
    baseline/osu/analysis/plot_osu.py:label_points). IOR's scaling studies
    are short (3 node counts), so every point is labeled, no thinning."""
    up = variant == "native"
    for x, y in zip(xs, ys):
        ax.annotate(f"{y:.0f}" if y >= 10 else f"{y:.1f}", (x, y),
                    textcoords="offset points",
                    xytext=(0, dy if up else -(dy + 6)), ha="center", fontsize=7,
                    color=VARIANT_COLOR[variant], fontweight="bold", zorder=7,
                    bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.7))


def plot_scaling(study):
    # Not sharey: Combo B's bandwidth is ~3x Combo A's; each panel gets its
    # own y-scale, starting at 0 so flat scaling reads as flat.
    fig, axes = plt.subplots(1, len(COMBOS), figsize=(11, 5), sharey=False)
    any_data = False

    for col, (api, model) in enumerate(COMBOS):
        ax = axes[col]
        top = 0.0
        for variant in VARIANTS:
            xs, ys, yerrs = [], [], []
            for n in NODE_COUNTS:
                pt = load_point(study, variant, api, model, n)
                if pt is None:
                    continue
                xs.append(n)
                ys.append(pt[0])
                yerrs.append(pt[1])
            if xs:
                any_data = True
                top = max(top, max(y + e for y, e in zip(ys, yerrs)))
                ax.errorbar(xs, ys, yerr=yerrs, color=VARIANT_COLOR[variant],
                            marker=VARIANT_MARKER[variant], label=VARIANT_LABEL[variant],
                            capsize=4, linewidth=1.8, markersize=7)
                label_points(ax, xs, ys, variant)
        ax.set_xticks(NODE_COUNTS)
        ax.set_xticklabels([f"{n} ({n * RANKS_PER_NODE} ranks)\n{XTICK_DETAIL[study][n]}"
                            for n in NODE_COUNTS], fontsize=8)
        ax.set_xlim(0.6, 3.4)
        ax.set_ylim(0, top * 1.15 if top else 1)
        ax.grid(True, alpha=0.3)
        ax.set_title(COMBO_LABELS[f"{api}_{model}"])
        ax.set_xlabel("Nodes")
        ax.set_ylabel("Write Bandwidth (MiB/s)")  # own scale per panel
        ax.legend(loc="lower right")

    if not any_data:
        print(f"  [skip] {study} -- no data yet")
        plt.close(fig)
        return
    fig.suptitle(f"IOR Inter-Node {STUDY_LABEL[study]} Write — Native vs Container (TATE, t=1m)")
    savefig(fig, f"inter_{study}_write.png")


def plot_overhead():
    fig, axes = plt.subplots(1, len(STUDIES), figsize=(11, 4.8), sharey=True)
    width = 0.34
    for col, study in enumerate(STUDIES):
        ax = axes[col]
        for i, (api, model) in enumerate(COMBOS):
            xs, ys = [], []
            for n in NODE_COUNTS:
                pn = load_point(study, "native", api, model, n)
                pc = load_point(study, "container", api, model, n)
                if pn and pc:
                    xs.append(n + (i - 0.5) * width)
                    ys.append((pc[0] - pn[0]) / pn[0] * 100)
            key = f"{api}_{model}"
            ax.bar(xs, ys, width=width, color=COMBO_COLOR[key], alpha=0.88,
                   label=COMBO_LABELS[key])
            for xi, y in zip(xs, ys):
                ax.annotate(f"{y:+.1f}%", (xi, y), textcoords="offset points",
                            xytext=(0, 4 if y >= 0 else -12), ha="center", fontsize=8,
                            fontweight="bold")
        ax.axhline(0, color="#444444", linewidth=0.8)
        ax.set_xticks(NODE_COUNTS)
        ax.set_xticklabels([f"{n} node{'s' if n > 1 else ''}" for n in NODE_COUNTS])
        ax.set_ylim(-10, 10)
        ax.grid(axis="y", alpha=0.3)
        ax.set_title(STUDY_LABEL[study])
        if col == 0:
            ax.set_ylabel("Container vs Native Write Bandwidth (%)")
    axes[0].legend(loc="upper left", fontsize=8)
    fig.suptitle("IOR Inter-Node — Container Overhead (TATE; negative = container slower)")
    savefig(fig, "inter_container_overhead.png")


def main():
    print_table()
    print()
    for study in STUDIES:
        print(f"{STUDY_LABEL[study]}...")
        plot_scaling(study)
    print("Container overhead...")
    plot_overhead()

    if missing:
        uniq = sorted(set(missing))
        print(f"\n{len(uniq)} data points had no completed Summary and were skipped:")
        for m in uniq:
            print(f"  - {m}")

    print("Done.")


if __name__ == "__main__":
    main()
