"""Shared result-parsing and 95% confidence-interval utilities for the IOR
analysis script in this directory (plot_ior.py).

It imports from here so the parsing logic and CI math live in exactly one place.
"""
import math
import os

RESULTS_ROOT = os.path.join(os.path.dirname(__file__), "..", "results")
FIG_DIR = os.path.join(os.path.dirname(__file__), "figures")

VARIANTS = ["native", "container"]
VARIANT_COLOR = {"native": "#1f77b4", "container": "#ff7f0e"}
VARIANT_MARKER = {"native": "o", "container": "x"}
VARIANT_LABEL = {"native": "Native", "container": "Container"}
METRIC_LINESTYLE = {"Write": "-", "Read": "--"}

APIS = ["posix", "mpiio"]
MODELS = ["shared", "fpp"]
COMBOS = [("posix", "shared"), ("posix", "fpp"), ("mpiio", "shared"), ("mpiio", "fpp")]
COMBO_LABELS = {
    "posix_shared": "POSIX / Shared",
    "posix_fpp": "POSIX / FPP",
    "mpiio_shared": "MPIIO / Shared",
    "mpiio_fpp": "MPIIO / FPP",
}

MIB_PER_GIB = 1024.0  # IOR reports MiB/s; figures convert to GiB/s throughout

# Two-tailed 95% critical t-values keyed by degrees of freedom (n - 1). Every
# run in this project uses -i 10 (n=10 -> df=9 -> t=2.262), but the table
# covers the general case rather than hardcoding that one value, in case a
# future sweep changes the repetition count.
_T95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
    8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145,
    15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056,
    27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}


def t_crit_95(df):
    """Two-tailed 95% critical t-value for the given degrees of freedom.
    Falls back to the normal-approximation 1.96 for df > 30 (table coverage
    limit); returns NaN for df < 1 (no variance information available, so no
    critical value is meaningful)."""
    if df < 1:
        return float("nan")
    return _T95.get(df, 1.960)


def ci95_halfwidth(std, n):
    """95% confidence-interval half-width for a sample mean: t * std / sqrt(n).

    Returns 0.0 for n < 2 or a missing std -- a single sample carries no
    variance information, so no interval can be formed. This is a "no CI
    available" signal (plotted as a zero-length error bar), never treated as
    "the true value is known exactly"."""
    if n is None or n < 2 or std is None:
        return 0.0
    return t_crit_95(n - 1) * std / math.sqrt(n)


def parse_ior_summary(path):
    """Parse IOR's own "Summary of all tests:" block and return
        {"write": (mean, std, n), "read": (mean, std, n)}
    (mean/std in MiB/s, n = completed repetitions), using IOR's own
    Mean(MiB)/StdDev/reps columns directly -- not re-derived from the
    individual per-iteration rows above the summary, since IOR already
    computes exactly this statistic across every repetition that actually
    completed.

    Deliberately stricter than the per-iteration-row parsers used earlier in
    this project's history: if "Summary of all tests:" is absent (job
    crashed or was killed before finishing all -i repetitions), this returns
    {} for that file rather than recovering a single raw iteration value --
    a single sample carries no variance information, so it could never
    support a confidence interval anyway, and silently mixing "full 10-rep
    statistic" points with "one surviving row" points on the same plot would
    be misleading rather than honest about what was actually measured.
    """
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        content = f.read()
    if "Summary of all tests:" not in content:
        return {}
    summary_section = content.split("Summary of all tests:", 1)[1]
    result = {}
    for line in summary_section.splitlines():
        parts = line.split()
        if len(parts) < 16 or parts[0] not in ("write", "read"):
            continue
        try:
            mean = float(parts[3])
            std = float(parts[4])
            n = int(parts[15])
        except (ValueError, IndexError):
            continue
        result[parts[0]] = (mean, std, n)
    return result


def savefig(fig, name, rect=None):
    os.makedirs(FIG_DIR, exist_ok=True)
    path = os.path.join(FIG_DIR, name)
    fig.tight_layout(rect=rect)
    fig.savefig(path, dpi=150)
    import matplotlib.pyplot as plt
    plt.close(fig)
    print(f"  wrote {path}")
