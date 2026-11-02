#!/usr/bin/env python3
"""Summarise the intra-node Darshan profiling runs on TATE, native vs container.

Reads ../results/<variant>/<case>/<case>_<jobid>.{parsed,dxt.txt} (darshan-parser
and darshan-dxt-parser text written by the job scripts) and prints, per case:

  - Darshan counters summed over the IOR test files on /home (call counts,
    bytes, cumulative POSIX / MPI-IO time)
  - DXT: which ranks issue POSIX writes, per-call durations, MPI-IO calls
    that took >= 29 s (the NFS lock back-off), and gaps between consecutive
    POSIX writes to the shared file

Times from Darshan's shared-file records are cumulative over all ranks.
OMPIO's shared-file-pointer files (/tmp/ompi.*/...sm) are excluded.

Run:  python3 summarize_darshan.py
"""
import collections
import glob
import os

HERE = os.path.dirname(__file__)
RESULTS = os.path.join(HERE, "..", "results")

VARIANTS = ["native", "container"]
CASES = ["mpiio_shared_t64k_lockdefault", "mpiio_shared_t64k_lock3", "posix_fpp_t64k"]
COUNTERS = [
    "POSIX_OPENS", "POSIX_WRITES", "POSIX_BYTES_WRITTEN", "POSIX_FSYNCS",
    "POSIX_F_WRITE_TIME", "POSIX_F_META_TIME",
    "MPIIO_COLL_WRITES", "MPIIO_INDEP_WRITES", "MPIIO_BYTES_WRITTEN",
    "MPIIO_F_WRITE_TIME", "MPIIO_F_META_TIME",
]
STALL_S = 29.0


def one(pattern):
    paths = glob.glob(pattern)
    return paths[0] if paths else None


def is_test_file(name):
    return name.startswith("/home") and "testfile" in name and not name.endswith(".sm")


def load_counters(path):
    totals = collections.Counter()
    for line in open(path):
        if line.startswith("#"):
            continue
        p = line.rstrip("\n").split("\t")
        if len(p) < 6 or not is_test_file(p[5]):
            continue
        if p[3] in COUNTERS:
            totals[p[3]] += float(p[4])
    return totals


def load_dxt(path):
    """Return [(module, rank, op, start, end, file)] for the IOR test files."""
    recs, fname = [], None
    for line in open(path):
        if line.startswith("# DXT, file_id"):
            fname = line.split("file_name: ", 1)[1].strip()
        elif line.startswith(" X_") and fname and is_test_file(fname):
            p = line.split()
            recs.append((p[0], int(p[1]), p[2], float(p[6]), float(p[7]), fname))
    return recs


def dxt_summary(recs):
    px = [r for r in recs if r[0] == "X_POSIX" and r[2] == "write"]
    mp = [r for r in recs if r[0] == "X_MPIIO" and r[2] == "write"]
    out = {}
    ranks = collections.Counter(r[1] for r in px)
    out["POSIX writer ranks"] = (dict(sorted(ranks.items())) if len(ranks) <= 4
                                 else f"{len(ranks)} ranks")
    pd = [r[4] - r[3] for r in px]
    out["POSIX write mean (ms)"] = f"{sum(pd) / len(pd) * 1e3:.2f}"
    out["POSIX write max (ms)"] = f"{max(pd) * 1e3:.1f}"
    if mp:
        md = [r[4] - r[3] for r in mp]
        out["MPI-IO write mean (s)"] = f"{sum(md) / len(md):.3f}"
        out["MPI-IO write max (s)"] = f"{max(md):.1f}"
        out[f"MPI-IO writes >= {STALL_S:.0f} s"] = sum(d >= STALL_S for d in md)
        byfile = collections.defaultdict(list)
        for r in px:
            byfile[r[5]].append((r[3], r[4]))
        gaps = []
        for iv in byfile.values():
            iv.sort()
            gaps += [b[0] - a[1] for a, b in zip(iv, iv[1:])]
        gaps.sort()
        out["gap between POSIX writes, median (ms)"] = f"{gaps[len(gaps) // 2] * 1e3:.2f}"
        out[f"gaps >= {STALL_S:.0f} s (stall events)"] = sum(g >= STALL_S for g in gaps)
        out["time in gaps > 1 s (s)"] = f"{sum(g for g in gaps if g > 1):.0f}"
    return out


def main():
    for case in CASES:
        print(f"\n=== {case}")
        rows = {}
        for v in VARIANTS:
            parsed = one(os.path.join(RESULTS, v, case, "*.parsed"))
            dxt = one(os.path.join(RESULTS, v, case, "*.dxt.txt"))
            if not parsed or not dxt:
                print(f"  [skip] {v}: no Darshan output")
                continue
            c = load_counters(parsed)
            d = dxt_summary(load_dxt(dxt))
            for k in COUNTERS:
                if c.get(k):
                    rows.setdefault(k, {})[v] = f"{c[k]:.2f}" if "TIME" in k else f"{c[k]:.0f}"
            for k, val in d.items():
                rows.setdefault(k, {})[v] = str(val)
        for k, vals in rows.items():
            print(f"  {k:40} {vals.get('native', '-'):>22} {vals.get('container', '-'):>22}")


if __name__ == "__main__":
    main()
