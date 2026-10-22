"""Shared parsing, statistics and style for the h5bench figures.

Mirrors baseline/ior/analysis/common.py so the two benchmarks' figures are
visually consistent in the thesis.

Two h5bench-specific traps are handled here, both of which silently corrupt
results if ignored:

1. UNITS. h5bench switches between "MB/s" and "GB/s" depending on magnitude,
   and both labels are BINARY (1004.800 "MB/s" is really MiB/s; 1 "GB" = 1024
   "MB"). Averaging the bare numbers mixes scales and produces nonsense -- an
   early draft of this analysis reported 497 GiB/s that way. Everything is
   normalized to GiB/s via to_gib() using the unit column.

2. CSV LOCATION. The h5bench driver rewrites CSV_FILE to
   <directory>/<uuid>/<csv> (src/h5bench.py:370), so results live under
   payload/<variant>/<key>/<random-uuid>/, not in the report directory. The
   repetition index survives only in the filename (write_rep3.csv), because
   the UUIDs are random and carry no ordering.
"""

import glob
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS_ROOT = os.path.join(os.path.dirname(__file__), "..", "results")
FIG_DIR = os.path.join(os.path.dirname(__file__), "figures")

# Same palette/markers as the IOR figures.
VARIANTS = ["native", "container"]
VARIANT_COLOR = {"native": "#1f77b4", "container": "#ff7f0e"}
VARIANT_MARKER = {"native": "o", "container": "x"}
VARIANT_LABEL = {"native": "Native", "container": "Container"}

NODE_COUNTS = [1, 2, 4, 8]

PATTERNS = ["contig_contig", "contig_interleaved",
            "interleaved_contig", "interleaved_interleaved"]
PATTERN_LABELS = {
    "contig_contig": "CONTIG→CONTIG",
    "contig_interleaved": "CONTIG→INTERLEAVED",
    "interleaved_contig": "INTERLEAVED→CONTIG",
    "interleaved_interleaved": "INTERLEAVED→INTERLEAVED",
}

COLLECTIVE_CELLS = ["dno_mno", "dno_myes", "dyes_mno", "dyes_myes"]
COLLECTIVE_LABELS = {
    "dno_mno": "data=NO\nmeta=NO",
    "dno_myes": "data=NO\nmeta=YES",
    "dyes_mno": "data=YES\nmeta=NO",
    "dyes_myes": "data=YES\nmeta=YES",
}

# t(0.975, df) -- scipy is not installed in the project venv, same as IOR.
_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
        7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179,
        13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101,
        19: 2.093, 20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064,
        25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042}


def t_crit_95(df):
    if df < 1:
        return float("nan")
    return _T95.get(df, 1.96)


def ci95_halfwidth(values):
    """95% CI half-width of the mean. NaN for n<2 (a single sample has none)."""
    n = len(values)
    if n < 2:
        return float("nan")
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return t_crit_95(n - 1) * math.sqrt(var) / math.sqrt(n)


def to_gib(value, unit):
    """Normalize an h5bench rate to GiB/s.

    h5bench's labels are binary despite looking decimal: 1 "GB" = 1024 "MB".
    Verified against the raw figures (21474836480 B / 20.382 s = 1004.8 MiB/s,
    which h5bench printed as "1004.800 MB/s").
    """
    u = (unit or "").strip().upper()
    if u.startswith("MB"):
        return value / 1024.0
    if u.startswith("KB"):
        return value / (1024.0 ** 2)
    if u.startswith("TB"):
        return value * 1024.0
    return value  # GB/s, already binary GiB/s


def parse_h5bench_csv(path):
    """Parse one h5bench CSV into {metric: (value_str, unit_str)}."""
    out = {}
    with open(path) as fh:
        for line in fh:
            fields = [f.strip() for f in line.split(",")]
            if len(fields) >= 2 and fields[1]:
                out[fields[0]] = (fields[1], fields[2] if len(fields) > 2 else "")
    return out


def rate(record, metric="observed rate"):
    """Extract a rate in GiB/s. Returns None if absent.

    'observed rate' is end-to-end (includes file create/flush/close and
    metadata) -- what the application actually experiences, and the fairer
    native/container comparison because HDF5 version differences show up in
    the metadata path. 'raw rate' isolates the data transfer.
    """
    if metric not in record:
        return None
    value, unit = record[metric]
    try:
        return to_gib(float(value), unit)
    except ValueError:
        return None


def collect(pattern, metric="observed rate"):
    """Glob for CSVs and return a sorted list of rates in GiB/s."""
    rates = []
    for path in sorted(glob.glob(pattern)):
        value = rate(parse_h5bench_csv(path), metric)
        if value is not None and value > 0:
            rates.append(value)
    return rates


def stats(values):
    """(mean, ci_halfwidth, n). mean is NaN when there are no samples."""
    n = len(values)
    if n == 0:
        return float("nan"), float("nan"), 0
    return sum(values) / n, ci95_halfwidth(values), n


# ---------------------------------------------------------------- loaders

def intra(variant, pattern, metric="observed rate"):
    return collect(os.path.join(
        RESULTS_ROOT, "intra_node", "payload", variant, pattern,
        "*", "write_rep*.csv"), metric)


def scaling(study, variant, nodes, op, metric="observed rate"):
    """study: 'weak_scaling' | 'strong_scaling'; op: 'write' | 'read'."""
    return collect(os.path.join(
        RESULTS_ROOT, "inter_node", study, "payload", variant, f"n{nodes}",
        "*", f"{op}_rep*.csv"), metric)


def collective(variant, cell, op, metric="observed rate"):
    return collect(os.path.join(
        RESULTS_ROOT, "inter_node", "collective_io", "payload", variant, cell,
        "*", f"{op}_rep*.csv"), metric)


def cold_read(case, nodes, variant, cell="dno_mno", metric="observed rate"):
    """Cold reads from the validation runs. case: weak|strong|collective."""
    key = f"{case}_n{nodes}_{cell}_{variant}"
    return collect(os.path.join(
        RESULTS_ROOT, "inter_node", "cold_read_validation", "payload", key,
        "*", "read_*.csv"), metric)


def cold_read_overlap_ok(case, nodes, variant, cell="dno_mno"):
    """True only if the read ran on nodes disjoint from the write.

    A non-zero overlap means some ranks read from page cache, so the
    measurement is warm and must not be used. Missing file -> not usable.
    """
    path = os.path.join(RESULTS_ROOT, "inter_node", "cold_read_validation",
                        variant, f"{case}_n{nodes}_{cell}", "node_overlap.txt")
    try:
        with open(path) as fh:
            return fh.read().strip() == "0"
    except OSError:
        return False


# ---------------------------------------------------------------- plotting

def savefig(fig, name, rect=None):
    os.makedirs(FIG_DIR, exist_ok=True)
    if rect:
        fig.tight_layout(rect=rect)
    else:
        fig.tight_layout()
    path = os.path.join(FIG_DIR, name)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  wrote {os.path.relpath(path)}")


def annotate_n(ax, text):
    """Record the sample size on the figure so n is never ambiguous."""
    ax.text(0.99, 0.02, text, transform=ax.transAxes,
            ha="right", va="bottom", fontsize=7, color="#555555")
