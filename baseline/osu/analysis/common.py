"""Shared parsing, statistics and style for the OSU figures.

Mirrors baseline/h5bench/analysis/common.py and baseline/ior/analysis/common.py
so all three benchmarks' figures are visually consistent in the thesis.

Two OSU-specific points are handled here:

1. UNITS. osu_latency reports microseconds (lower is better); osu_bw reports
   MB/s (higher is better). The "better" direction flips between the two
   kernels, so every ratio in this module is expressed as a SLOWDOWN FACTOR
   (container cost / native cost) via ratio(): >1 always means the container
   is worse, for both kernels. Mixing the raw ratios would make the bandwidth
   plot read backwards against the latency plot.

2. VARIANCE MATTERS MORE THAN THE MEAN HERE. The container's intra-node
   large-message bandwidth has a coefficient of variation of 30-40% against
   native's 3-7%. A mean ratio computed over that spread is not a finding, so
   cv() is reported alongside every mean and resolvable() applies a
   Welch t-test rather than letting the eye compare two unstable numbers.
"""

import glob
import math
import os
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS_ROOT = os.path.join(os.path.dirname(__file__), "..", "results")
FIG_DIR = os.path.join(os.path.dirname(__file__), "figures")

# Same palette/markers as the IOR and h5bench figures.
VARIANTS = ["native", "container"]
VARIANT_COLOR = {"native": "#1f77b4", "container": "#ff7f0e"}
VARIANT_MARKER = {"native": "o", "container": "x"}
VARIANT_LABEL = {"native": "Native", "container": "Container"}

BENCHES = ["latency", "bw"]
BENCH_UNIT = {"latency": "Latency (us)", "bw": "Bandwidth (MB/s)"}
BENCH_LOWER_IS_BETTER = {"latency": True, "bw": False}
PLACEMENTS = ["intra_node", "inter_node"]
PLACEMENT_LABEL = {"intra_node": "Intra-node (shared memory)",
                   "inter_node": "Inter-node (Slingshot fabric)"}

# Two-sided 95% critical values, indexed by degrees of freedom. Avoids a scipy
# dependency, same approach as the h5bench analysis.
_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
        8: 2.306, 9: 2.262, 10: 2.228, 12: 2.179, 15: 2.131, 18: 2.101,
        20: 2.086, 25: 2.060, 30: 2.042, 40: 2.021, 60: 2.000}


def t_crit_95(df):
    """Two-sided 95% t critical value, rounding df down to the nearest key."""
    if df <= 0:
        return float("inf")
    keys = sorted(k for k in _T95 if k <= df)
    return _T95[keys[-1]] if keys else 1.96


def load(placement, variant, bench):
    """Parse every repetition into {message_size: [value, ...]}.

    OSU writes a '# ...' header then 'size value' rows. With -f there are extra
    columns (min/max/iterations); only the first two are read here, which is
    the average for both kernels.
    """
    pat = os.path.join(RESULTS_ROOT, "pt2pt", placement, variant, bench,
                       f"osu_{bench}_rep*.txt")
    out = {}
    for path in sorted(glob.glob(pat)):
        for line in open(path):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            try:
                out.setdefault(int(parts[0]), []).append(float(parts[1]))
            except ValueError:
                continue
    return out


def cv(values):
    """Coefficient of variation in percent. 0 for a single sample."""
    if len(values) < 2:
        return 0.0
    m = st.mean(values)
    return 100.0 * st.stdev(values) / m if m else 0.0


def ratio(native_vals, container_vals, bench):
    """Container slowdown factor: >1 means container is WORSE, both kernels.

    Latency is a cost (higher is worse) so the ratio is container/native.
    Bandwidth is a rate (higher is better) so it is inverted to native/container.
    """
    n, c = st.mean(native_vals), st.mean(container_vals)
    if not n or not c:
        return float("nan")
    return c / n if BENCH_LOWER_IS_BETTER[bench] else n / c


def resolvable(a, b):
    """Welch's t-test at 95%: is the difference bigger than the noise?

    Returns False when the two samples overlap too much to distinguish, which
    is the common case for OSU's noisier large-message bandwidth points.
    """
    if len(a) < 2 or len(b) < 2:
        return False
    va, vb = st.variance(a), st.variance(b)
    na, nb = len(a), len(b)
    se = math.sqrt(va / na + vb / nb)
    if se == 0:
        return st.mean(a) != st.mean(b)
    t = abs(st.mean(a) - st.mean(b)) / se
    num = (va / na + vb / nb) ** 2
    den = (va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1)
    df = num / den if den else 1
    return t > t_crit_95(df)


def human_size(n):
    """1048576 -> '1M'. Keeps log-axis tick labels readable."""
    for unit, div in (("M", 1 << 20), ("K", 1 << 10)):
        if n >= div:
            q = n / div
            return f"{q:.0f}{unit}" if q == int(q) else f"{q:.1f}{unit}"
    return str(n)


def ensure_fig_dir():
    os.makedirs(FIG_DIR, exist_ok=True)
    return FIG_DIR


def save(fig, name):
    path = os.path.join(ensure_fig_dir(), name)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {os.path.relpath(path, os.path.dirname(__file__))}")
    return path


# --- Collective bandwidth, derived -------------------------------------------
# OSU's collective benchmarks report LATENCY only -- there is no osu_allreduce_bw
# to match osu_bw, because a collective has no single sender/receiver pair and
# "bandwidth" is therefore convention-dependent.
#
# It is still derivable here, because these scripts pin the message size with
# -m MSG:MSG (recorded in msgsize_bytes.txt) and the rank count is in the path.
# Deriving it is what makes the collective results comparable with the pt2pt
# bandwidth figures, which are otherwise in different units.

def collective_bw_mbps(bench, msg_bytes, ranks, latency_us, convention="bus"):
    """Effective bandwidth in MB/s from a collective's reported latency.

    alltoall   every rank sends msg_bytes to each of (ranks-1) peers, so the
               per-rank volume is unambiguous and this is real throughput.

    allreduce  depends on convention, and the thesis must say which:
                 "algorithm" -> msg_bytes / t, the useful payload only
                 "bus"       -> 2*msg_bytes*(ranks-1)/ranks / t, which stays
                                comparable across rank counts (NCCL's
                                convention) because it accounts for the
                                reduce-scatter + allgather data actually moved
    """
    if latency_us <= 0 or ranks < 2:
        return float("nan")
    seconds = latency_us * 1e-6
    if bench == "alltoall":
        payload = msg_bytes * (ranks - 1)
    elif bench == "allreduce":
        if convention == "algorithm":
            payload = msg_bytes
        else:
            payload = 2.0 * msg_bytes * (ranks - 1) / ranks
    else:
        raise ValueError(f"no bandwidth convention defined for {bench!r}")
    return payload / seconds / 1e6


def load_collective(mode, variant, bench, ranks):
    """Parse one scaling point: results/collective/<mode>/<variant>/<bench>/np<N>/.

    Returns (latencies, msg_bytes). msg_bytes comes from msgsize_bytes.txt,
    which the .pbs writes alongside the data so the derivation never has to
    re-guess the weak/strong message-size rule.
    """
    base = os.path.join(RESULTS_ROOT, "collective", mode, variant, bench, f"np{ranks}")
    lat = []
    for path in sorted(glob.glob(os.path.join(base, f"osu_{bench}_rep*.txt"))):
        for line in open(path):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                try:
                    lat.append(float(parts[1]))
                except ValueError:
                    pass
    msg_path = os.path.join(base, "msgsize_bytes.txt")
    msg = int(open(msg_path).read().strip()) if os.path.exists(msg_path) else None
    return lat, msg
