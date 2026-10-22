#!/usr/bin/env python3
"""Plot multinode_scaling IOR results (weak and strong scaling).

NOTE: only 'native' data exists as of this writing -- no container version
of the multinode scaling experiment has been run yet. The script is still
structured to support both variants so it works unmodified once container
data exists; for now it will simply plot native alone.

Same safety principle as plot_1node_sweep.py: any missing or incomplete
result file (e.g. a crashed run with a header but no data row) is silently
skipped, never fabricated.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS_ROOT = os.path.join(os.path.dirname(__file__), "..", "results", "multinode_scaling")
FIG_DIR = os.path.join(os.path.dirname(__file__), "figures")

VARIANTS = ["native", "container"]  # container may not exist yet -- handled gracefully
VARIANT_STYLE = {
    "native": dict(color="#1f77b4", marker="o", linestyle="-", label="Native"),
    "container": dict(color="#ff7f0e", marker="x", linestyle="--", label="Container"),
}
NODE_COUNTS = [1, 2, 4, 8]
APIS = ["posix", "mpiio"]
MODELS = ["shared", "fpp"]
REGIMES = ["weak_scaling", "strong_scaling"]

missing = []


def parse_ior_result(path):
    """Return (write_bw, read_bw) in MiB/s, taken from the LAST *completed*
    iteration's raw row for each of write/read independently -- not an
    average, and not requiring all -i 3 repetitions to have finished.

    IOR only prints a 'write ...'/'read ...' row once that phase of an
    iteration is fully done, so any such row found is a genuine completed
    measurement -- even from a run killed partway through. Its Summary row
    ALSO starts with 'write'/'read' (reporting Max/Min/Mean, not a raw
    value), so that section is excluded before scanning.
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


def load_point(variant, regime, api, model, node_count):
    path = os.path.join(RESULTS_ROOT, variant, api, model, regime, f"ior_n{node_count}.txt")
    w, r = parse_ior_result(path)
    if w is None and r is None:
        missing.append(f"{variant}/{api}/{model}/{regime}/n{node_count}")
    return w, r


def savefig(fig, name):
    os.makedirs(FIG_DIR, exist_ok=True)
    path = os.path.join(FIG_DIR, name)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  wrote {path}")


def plot_scaling(regime, metric_idx, metric_name):
    """2x2 grid: rows=API, cols=model. X=node count, Y=bandwidth."""
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), sharex=True, sharey=True)
    any_data_at_all = False

    for row, api in enumerate(APIS):
        for col, model in enumerate(MODELS):
            ax = axes[row][col]
            for variant in VARIANTS:
                xs, ys = [], []
                for n in NODE_COUNTS:
                    w, r = load_point(variant, regime, api, model, n)
                    val = w if metric_idx == 0 else r
                    if val is not None:
                        xs.append(n)
                        ys.append(val)
                if xs:
                    any_data_at_all = True
                    ax.plot(xs, ys, **VARIANT_STYLE[variant])
            ax.set_xscale("log", base=2)
            ax.set_yscale("log")
            ax.grid(True, which="both", alpha=0.3)
            ax.set_title(f"{api.upper()} / {model}")
            if row == 1:
                ax.set_xlabel("Node Count")
            if col == 0:
                ax.set_ylabel(f"{metric_name} Bandwidth (MiB/s)")

    if not any_data_at_all:
        print(f"  [skip] no data at all for {regime} {metric_name} -- not writing a figure")
        plt.close(fig)
        return
    axes[0][0].legend()
    label = "Weak Scaling" if regime == "weak_scaling" else "Strong Scaling"
    fig.suptitle(f"{label} ({metric_name})")
    savefig(fig, f"multinode_{regime}_{metric_name.lower()}.png")


def main():
    for regime in REGIMES:
        for metric_idx, metric_name in [(0, "Write"), (1, "Read")]:
            plot_scaling(regime, metric_idx, metric_name)

    if missing:
        uniq = sorted(set(missing))
        print(f"\n{len(uniq)} data points were missing/incomplete and skipped:")
        for m in uniq[:20]:
            print(f"  - {m}")
        if len(uniq) > 20:
            print(f"  ... and {len(uniq) - 20} more")

    print("Done.")


if __name__ == "__main__":
    main()
