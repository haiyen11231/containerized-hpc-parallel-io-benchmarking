"""Shared IOR result-parsing and 95% confidence-interval utilities.

Kept intentionally small: just what plot_intra_write.py needs to parse
IOR's own "Summary of all tests:" block and compute a 95% CI from it. No
design-specific constants (combos, stripe counts, paths) live here -- those
belong in the plotting script that actually describes the current
experiment, not in a shared module several redesigns could drift out of
sync with.
"""
import math
import os

FIG_DIR = os.path.join(os.path.dirname(__file__), "figures")

MIB_PER_GIB = 1024.0  # IOR reports MiB/s; figures convert to GiB/s throughout

# Two-tailed 95% critical t-values keyed by degrees of freedom (n - 1). Every
# run in this project uses -i 10 (n=10 -> df=9 -> t=2.262), but the table
# covers the general case rather than hardcoding that one value.
_T95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
    8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145,
    15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
}


def t_crit_95(df):
    """Two-tailed 95% critical t-value for the given degrees of freedom.
    Falls back to the normal-approximation 1.96 for df > 20 (table coverage
    limit); returns NaN for df < 1 (no variance information available)."""
    if df < 1:
        return float("nan")
    return _T95.get(df, 1.960)


def ci95_halfwidth(std, n):
    """95% confidence-interval half-width for a sample mean: t * std / sqrt(n).

    Returns 0.0 for n < 2 or a missing std -- a single sample carries no
    variance information, so no interval can be formed."""
    if n is None or n < 2 or std is None:
        return 0.0
    return t_crit_95(n - 1) * std / math.sqrt(n)


def parse_ior_summary(path):
    """Parse IOR's own "Summary of all tests:" block and return
        {"write": (mean, std, n), "read": (mean, std, n)}
    (mean/std in MiB/s, n = completed repetitions), using IOR's own
    Mean(MiB)/StdDev/reps columns directly.

    Returns {} if the file doesn't exist or the job didn't finish all -i
    repetitions (no "Summary of all tests:" block yet) -- never recovers a
    single raw iteration value, since that would carry no variance
    information to support a CI.
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


def savefig(fig, name):
    os.makedirs(FIG_DIR, exist_ok=True)
    path = os.path.join(FIG_DIR, name)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    import matplotlib.pyplot as plt
    plt.close(fig)
    print(f"  wrote {path}")
