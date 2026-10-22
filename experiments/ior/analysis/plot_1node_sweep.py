#!/usr/bin/env python3
"""Plot 1node_sweep IOR results (native vs container).

Designed to be safe to re-run at any point during data collection: any
missing or incomplete result file is silently skipped (never fabricated),
so the same script produces a sparse-but-honest plot now and a fuller one
later without needing changes.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS_ROOT = os.path.join(os.path.dirname(__file__), "..", "results", "1node_sweep")
FIG_DIR = os.path.join(os.path.dirname(__file__), "figures")

VARIANTS = ["native", "container"]
VARIANT_STYLE = {
    "native": dict(color="#1f77b4", marker="o", linestyle="-", label="Native"),
    "container": dict(color="#ff7f0e", marker="x", linestyle="--", label="Container"),
}
STRIPE_COUNTS = [1, 4, 8, 16]
# (label, bytes) so the x-axis is genuinely log-scaled, not just categorical
T_SIZES = [("32k", 32768), ("256k", 262144), ("1m", 1048576), ("4m", 4194304)]
APIS = ["posix", "mpiio"]
MODELS = ["shared", "fpp"]

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


def load_point(variant, api, model, stripe, tlabel):
    path = os.path.join(RESULTS_ROOT, variant, api, model, f"stripe_c{stripe}", f"ior_t{tlabel}.txt")
    w, r = parse_ior_result(path)
    if w is None and r is None:
        missing.append(f"{variant}/{api}/{model}/stripe_c{stripe}/t{tlabel}")
    return w, r


def savefig(fig, name):
    os.makedirs(FIG_DIR, exist_ok=True)
    path = os.path.join(FIG_DIR, name)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  wrote {path}")


def plot_transfer_size_sweep(stripe, metric_idx, metric_name):
    """2x2 grid: rows=API, cols=model. X=transfer size, Y=bandwidth."""
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), sharex=True, sharey=True)
    any_data_at_all = False

    for row, api in enumerate(APIS):
        for col, model in enumerate(MODELS):
            ax = axes[row][col]
            for variant in VARIANTS:
                xs, ys = [], []
                for tlabel, tbytes in T_SIZES:
                    w, r = load_point(variant, api, model, stripe, tlabel)
                    val = w if metric_idx == 0 else r
                    if val is not None:
                        xs.append(tbytes)
                        ys.append(val)
                if xs:
                    any_data_at_all = True
                    ax.plot(xs, ys, **VARIANT_STYLE[variant])
            ax.set_xscale("log")
            ax.set_yscale("log")
            ax.grid(True, which="both", alpha=0.3)
            ax.set_title(f"{api.upper()} / {model}")
            if row == 1:
                ax.set_xlabel("Transfer Size (Bytes)")
            if col == 0:
                ax.set_ylabel(f"{metric_name} Bandwidth (MiB/s)")

    if not any_data_at_all:
        print(f"  [skip] no data at all for stripe_c{stripe} {metric_name} sweep -- not writing a figure")
        plt.close(fig)
        return
    axes[0][0].legend()
    fig.suptitle(f"Transfer Size Sweep, stripe_c{stripe} ({metric_name})")
    savefig(fig, f"1node_transfer_sweep_stripe{stripe}_{metric_name.lower()}.png")


def plot_stripe_scaling(tlabel, metric_idx, metric_name):
    """2x2 grid: rows=API, cols=model. X=stripe count, Y=bandwidth."""
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), sharex=True, sharey=True)
    any_data_at_all = False

    for row, api in enumerate(APIS):
        for col, model in enumerate(MODELS):
            ax = axes[row][col]
            for variant in VARIANTS:
                xs, ys = [], []
                for stripe in STRIPE_COUNTS:
                    w, r = load_point(variant, api, model, stripe, tlabel)
                    val = w if metric_idx == 0 else r
                    if val is not None:
                        xs.append(stripe)
                        ys.append(val)
                if xs:
                    any_data_at_all = True
                    ax.plot(xs, ys, **VARIANT_STYLE[variant])
            ax.set_xscale("log", base=2)
            ax.set_yscale("log")
            ax.grid(True, which="both", alpha=0.3)
            ax.set_title(f"{api.upper()} / {model}")
            if row == 1:
                ax.set_xlabel("Stripe Count")
            if col == 0:
                ax.set_ylabel(f"{metric_name} Bandwidth (MiB/s)")

    if not any_data_at_all:
        print(f"  [skip] no data at all for t={tlabel} {metric_name} stripe-scaling -- not writing a figure")
        plt.close(fig)
        return
    axes[0][0].legend()
    fig.suptitle(f"Stripe Count Scaling, transfer size={tlabel} ({metric_name})")
    savefig(fig, f"1node_stripe_scaling_t{tlabel}_{metric_name.lower()}.png")


def main():
    print("Transfer-size sweep, per stripe count...")
    for stripe in STRIPE_COUNTS:
        for metric_idx, metric_name in [(0, "Write"), (1, "Read")]:
            plot_transfer_size_sweep(stripe, metric_idx, metric_name)

    print("Stripe-count scaling, per transfer size...")
    for tlabel, _ in T_SIZES:
        for metric_idx, metric_name in [(0, "Write"), (1, "Read")]:
            plot_stripe_scaling(tlabel, metric_idx, metric_name)

    if missing:
        print(f"\n{len(missing)} data points were missing/incomplete and skipped (expected while data collection is ongoing):")
        for m in sorted(set(missing))[:20]:
            print(f"  - {m}")
        if len(set(missing)) > 20:
            print(f"  ... and {len(set(missing)) - 20} more")

    print("Done.")


if __name__ == "__main__":
    main()
