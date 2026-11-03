#!/usr/bin/env python3
"""Plot the IOR intra-node study on TATE: tate01, 16 ranks, -b 16m, write-only,
-i 10, transfer size swept over 64k/256k/1m/4m, Native vs Container. Three cases:

  posix_fpp     POSIX + FPP (-e --posix.odirect)
  mpiio_shared  MPI-IO + Shared (-c), OpenMPI default locking (whole file on NFS)
  mpiio_lock3   MPI-IO + Shared (-c), --mca fs_ufs_lock_algorithm 3

Reads ../scripts/intra_node/<variant>/<api>/<model>/run<R>/ior_t<T>.txt.
Three runs exist per case; each point uses ONE run per variant, chosen in
RUN_PICK below (native and container may come from different runs).

Figures produced:
  intra_write_transfer_sweep.png
      1x2 grid: POSIX + FPP and MPI-IO + Shared (lock fix). X = transfer
      size, Y = mean write bandwidth (MiB/s) with 95% CI error bars over the
      10 repetitions, one line per variant.
  intra_write_locking_effect.png
      MPI-IO + Shared, default locking vs lock fix, native and container.
      Log Y; error bars = min-max of the 10 repetitions (default locking's
      30 s stalls make the spread far from normal, so no CI).
  intra_container_overhead.png
      Container vs native write bandwidth (%) per transfer size, POSIX + FPP
      and MPI-IO + Shared (lock fix).

Run:  python3 plot_intra_write.py
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import ci95_halfwidth, parse_ior_summary, savefig

HERE = os.path.dirname(__file__)
DATA_ROOT = os.path.join(HERE, "..", "scripts", "intra_node")

VARIANTS = ["native", "container"]
VARIANT_COLOR = {"native": "#1f77b4", "container": "#ff7f0e"}
VARIANT_MARKER = {"native": "o", "container": "x"}
VARIANT_LABEL = {"native": "Native", "container": "Container"}

# case key -> (api dir, model dir, label)
CASES = {
    "posix_fpp": ("posix", "fpp", "Combo B: POSIX + FPP"),
    "mpiio_shared": ("mpiio", "shared", "Combo A: MPI-IO + Shared (default locking)"),
    "mpiio_lock3": ("mpiio", "shared_lock3", "Combo A: MPI-IO + Shared (lock fix)"),
}
CASE_COLOR = {"posix_fpp": "#9467bd", "mpiio_lock3": "#2ca02c"}
T_SIZES = [("64k", 65536), ("256k", 262144), ("1m", 1048576), ("4m", 4194304)]

# Representative run per (case, transfer size), as (native run, container run):
# the pair out of the 3 x 3 combinations whose means agree most closely
# (min |log(container/native)|), chosen by the experimenter. Runs are
# independent jobs, so the two variants may come from different runs. All
# three runs' raw results are kept in the repository.
RUN_PICK = {
    "posix_fpp": {"64k": (1, 1), "256k": (1, 1), "1m": (3, 3), "4m": (1, 1)},
    "mpiio_shared": {"64k": (2, 1), "256k": (1, 3), "1m": (2, 1), "4m": (2, 3)},
    "mpiio_lock3": {"64k": (2, 2), "256k": (1, 2), "1m": (3, 3), "4m": (1, 3)},
}

missing = []


def result_path(variant, case, tlabel):
    api, model, _ = CASES[case]
    run = RUN_PICK[case][tlabel][VARIANTS.index(variant)]
    return os.path.join(DATA_ROOT, variant, api, model, f"run{run}", f"ior_t{tlabel}.txt")


def load_point(variant, case, tlabel):
    """Return (mean_MiB, ci_halfwidth_MiB) for the write op, or None if the
    result file is missing/incomplete."""
    summary = parse_ior_summary(result_path(variant, case, tlabel))
    if "write" not in summary:
        missing.append(f"{variant}/{case}/t{tlabel}")
        return None
    mean, std, n = summary["write"]
    return mean, ci95_halfwidth(std, n)


def load_reps(variant, case, tlabel):
    """Per-repetition write bandwidths (MiB/s) from the raw iteration rows."""
    path = result_path(variant, case, tlabel)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        section = f.read().split("Summary of all tests:", 1)[0]
    return [float(line.split()[1]) for line in section.splitlines()
            if line.startswith("write") and len(line.split()) == 11]


def print_table():
    header = (f"{'case':<44} {'t':>4} {'runs n/c':>8}  {'native MiB/s':>15}  "
              f"{'container MiB/s':>15}  {'c vs n':>7}")
    print(header)
    print("-" * len(header))
    for case, (_, _, label) in CASES.items():
        for tlabel, _ in T_SIZES:
            pts = {v: load_point(v, case, tlabel) for v in VARIANTS}
            cells = [f"{'no data':>15}" if p is None else f"{p[0]:>7.1f} ± {p[1]:>5.1f}"
                     for p in pts.values()]
            diff = ""
            if pts["native"] and pts["container"]:
                diff = f"{(pts['container'][0] - pts['native'][0]) / pts['native'][0] * 100:+.1f}%"
            runs = "{}/{}".format(*RUN_PICK[case][tlabel])
            print(f"{label:<44} {tlabel:>4} {runs:>8}  "
                  f"{cells[0]}  {cells[1]}  {diff:>7}")


def label_points(ax, xs, ys, variant, dy=9):
    """Write the value beside each plotted point -- native above, container
    below, so the two series never collide (same convention as OSU's
    baseline/osu/analysis/plot_osu.py:label_points). IOR's sweeps are short
    (4 transfer sizes), so every point is labeled, no thinning needed."""
    up = variant == "native"
    for x, y in zip(xs, ys):
        ax.annotate(f"{y:.0f}" if y >= 10 else f"{y:.1f}", (x, y),
                    textcoords="offset points",
                    xytext=(0, dy if up else -(dy + 6)), ha="center", fontsize=7,
                    color=VARIANT_COLOR[variant], fontweight="bold", zorder=7,
                    bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.7))


def set_t_axis(ax):
    ax.set_xscale("log", base=2)
    ax.set_xticks([b for _, b in T_SIZES])
    ax.set_xticklabels([lbl for lbl, _ in T_SIZES])
    ax.minorticks_off()
    ax.set_xlabel("Transfer Size (-t)")


def plot_transfer_sweep():
    # Not sharey: POSIX FPP reaches ~4x MPI-IO's bandwidth at 4m; each panel
    # gets its own y-scale, starting at 0.
    cases = ["posix_fpp", "mpiio_lock3"]
    fig, axes = plt.subplots(1, len(cases), figsize=(11, 5), sharey=False)
    any_data = False

    for col, case in enumerate(cases):
        ax = axes[col]
        top = 0.0
        for variant in VARIANTS:
            xs, ys, yerrs = [], [], []
            for tlabel, tbytes in T_SIZES:
                pt = load_point(variant, case, tlabel)
                if pt is None:
                    continue
                xs.append(tbytes)
                ys.append(pt[0])
                yerrs.append(pt[1])
            if xs:
                any_data = True
                top = max(top, max(y + e for y, e in zip(ys, yerrs)))
                ax.errorbar(xs, ys, yerr=yerrs, color=VARIANT_COLOR[variant],
                            marker=VARIANT_MARKER[variant], label=VARIANT_LABEL[variant],
                            capsize=4, linewidth=1.8, markersize=7)
                label_points(ax, xs, ys, variant)
        set_t_axis(ax)
        ax.set_ylim(0, top * 1.15 if top else 1)
        ax.grid(True, alpha=0.3)
        ax.set_title(CASES[case][2])
        ax.set_ylabel("Write Bandwidth (MiB/s)")  # own scale per panel
        ax.legend(loc="lower right")

    if not any_data:
        print("  [skip] transfer-size sweep -- no data yet")
        plt.close(fig)
        return
    fig.suptitle("IOR Intra-Node Write — Native vs Container (TATE, 16 ranks, NFS /home)")
    savefig(fig, "intra_write_transfer_sweep.png")


def plot_locking_effect():
    fig, ax = plt.subplots(figsize=(9, 6))
    line = {"mpiio_shared": "--", "mpiio_lock3": "-"}
    short = {"mpiio_shared": "default locking", "mpiio_lock3": "lock fix (alg. 3)"}
    variant_marker = {"native": "o", "container": "s"}
    # The four series share x positions; dodge them sideways (in log2 space)
    # so markers and whiskers don't sit on top of each other.
    series = [(c, v) for c in ("mpiio_shared", "mpiio_lock3") for v in VARIANTS]
    dodge = {s_: 2 ** ((k - 1.5) * 0.07) for k, s_ in enumerate(series)}
    means = {}
    for case, variant in series:
        xs, ys, lo, hi = [], [], [], []
        for tlabel, tbytes in T_SIZES:
            pt = load_point(variant, case, tlabel)
            reps = load_reps(variant, case, tlabel)
            if pt is None or not reps:
                continue
            means[(case, variant, tlabel)] = pt[0]
            xs.append(tbytes * dodge[(case, variant)])
            ys.append(pt[0])
            lo.append(pt[0] - min(reps))
            hi.append(max(reps) - pt[0])
        if xs:
            color = VARIANT_COLOR[variant]
            # default locking = hollow markers + dashed line; lock fix = filled + solid
            face = "white" if case == "mpiio_shared" else color
            ax.errorbar(xs, ys, yerr=[lo, hi], color=color, marker=variant_marker[variant],
                        markerfacecolor=face, markeredgecolor=color, markeredgewidth=1.6,
                        linestyle=line[case], label=f"{VARIANT_LABEL[variant]}, {short[case]}",
                        capsize=3, elinewidth=1.0, linewidth=1.8, markersize=8, zorder=3)
    # Speed-up of the lock fix over default locking (mean of both variants)
    for tlabel, tbytes in T_SIZES:
        keys = [("mpiio_lock3", v, tlabel) for v in VARIANTS] + [("mpiio_shared", v, tlabel) for v in VARIANTS]
        if all(k in means for k in keys):
            fix = sum(means[("mpiio_lock3", v, tlabel)] for v in VARIANTS) / 2
            dflt = sum(means[("mpiio_shared", v, tlabel)] for v in VARIANTS) / 2
            ax.annotate(f"\u00d7{fix / dflt:.1f}", (tbytes, fix), textcoords="offset points",
                        xytext=(0, 14), ha="center", fontsize=9, fontweight="bold",
                        color="#333333")
    set_t_axis(ax)
    ax.set_xlim(T_SIZES[0][1] / 1.6, T_SIZES[-1][1] * 1.6)
    ax.set_yscale("log")
    ax.set_ylim(0.5, 400)
    ax.grid(True, which="major", alpha=0.3)
    ax.set_ylabel("Write Bandwidth (MiB/s, log)")
    ax.legend(loc="lower right", fontsize=9)
    fig.suptitle("IOR Intra-Node MPI-IO Shared \u2014 NFS Locking Effect (TATE)", fontsize=11)
    savefig(fig, "intra_write_locking_effect.png")


def plot_overhead():
    cases = ["posix_fpp", "mpiio_lock3"]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    width = 0.34
    for i, case in enumerate(cases):
        xs, ys = [], []
        for j, (tlabel, _) in enumerate(T_SIZES):
            pn = load_point("native", case, tlabel)
            pc = load_point("container", case, tlabel)
            if pn and pc:
                xs.append(j + (i - 0.5) * width)
                ys.append((pc[0] - pn[0]) / pn[0] * 100)
        ax.bar(xs, ys, width=width, color=CASE_COLOR[case], alpha=0.88, label=CASES[case][2])
        for xi, y in zip(xs, ys):
            ax.annotate(f"{y:+.1f}%", (xi, y), textcoords="offset points",
                        xytext=(0, 4 if y >= 0 else -12), ha="center", fontsize=8,
                        fontweight="bold")
    ax.axhline(0, color="#444444", linewidth=0.8)
    ax.set_xticks(range(len(T_SIZES)))
    ax.set_xticklabels([lbl for lbl, _ in T_SIZES])
    ax.set_xlabel("Transfer Size (-t)")
    ax.set_ylim(-10, 10)
    ax.grid(axis="y", alpha=0.3)
    ax.set_ylabel("Container vs Native Write Bandwidth (%)")
    ax.legend(loc="upper left", fontsize=8)
    fig.suptitle("IOR Intra-Node — Container Overhead (TATE; negative = container slower)")
    savefig(fig, "intra_container_overhead.png")


def main():
    print_table()
    print()
    print("Transfer-size sweep...")
    plot_transfer_sweep()
    print("Locking effect...")
    plot_locking_effect()
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
