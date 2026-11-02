#!/usr/bin/env python3
"""Summarise the intra-node Recorder traces on TATE, native vs container.

Reads ../results/<variant>/<case>/trace_<jobid>/_text/<rank>.txt (recorder2text
output; one call per line: "<start> <end> <function> <depth> <type> ( <args> )")
and ../results/<variant>/<case>/ior_<jobid>.txt, and prints per case:

  - IOR write bandwidth and time of the single repetition
  - fcntl calls on the IOR test file, split into lock requests (F_SETLKW,
    cmd 7) and unlocks (F_SETLK with F_UNLCK, cmd 6 / type 2), per rank
  - fcntl calls lasting >= 29 s (the NFSv4 client's maximum back-off when a
    lock request is refused) and the longest one
  - stall events (MPI_File_write_at_all >= 29 s) on a rank that takes no locks
  - the last timestamp of every rank, to check the trace's timing

Timing caveat: on the two aggregator ranks (thousands of fcntl records) some
records overlap in time and the trace runs past the end of the job, which is
impossible for one thread -- most likely a Recorder timestamp artefact. Call
COUNTS are unaffected; timings are taken from a non-aggregator rank, whose
timeline matches the run.

fcntl commands are Linux x86_64 values: F_GETLK 5, F_SETLK 6, F_SETLKW 7;
lock types F_RDLCK 0, F_WRLCK 1, F_UNLCK 2.

Run:  python3 summarize_recorder.py
"""
import collections
import glob
import os
import re

HERE = os.path.dirname(__file__)
RESULTS = os.path.join(HERE, "..", "results")

VARIANTS = ["native", "container"]
CASES = ["mpiio_shared_t64k_lockdefault", "mpiio_shared_t64k_lock3"]
STALL_S = 29.0
LINE = re.compile(r"^(\S+) (\S+) (\S+) (\d+) (\d+) \( (.*) \)$")


def one(pattern):
    paths = glob.glob(pattern)
    return paths[0] if paths else None


def ior_write(path):
    for line in open(path):
        p = line.split()
        if len(p) == 11 and p[0] == "write" and re.match(r"[0-9.]+$", p[1]):
            return float(p[1]), float(p[9])
    return None


def load_rank(path):
    calls = []
    for line in open(path):
        m = LINE.match(line.rstrip("\n"))
        if m:
            calls.append((float(m[1]), float(m[2]), m[3], int(m[4]), m[6].split()))
    return calls


def summarize(trace_text_dir):
    per_rank = {}
    for path in sorted(glob.glob(os.path.join(trace_text_dir, "*.txt"))):
        rank = int(os.path.basename(path).split(".")[0])
        c = collections.Counter()
        fcntl_max, writes_long, stalls, last = 0.0, 0, [], 0.0
        for start, end, func, depth, args in load_rank(path):
            d = end - start
            if func == "fcntl" and args and "testfile" in args[0] and ".locktest" not in args[0]:
                cmd, typ = args[1], args[2] if len(args) > 2 else ""
                if cmd == "7":
                    c["lock (F_SETLKW)"] += 1
                elif cmd == "6" and typ == "2":
                    c["unlock"] += 1
                else:
                    c[f"other cmd {cmd}"] += 1
                fcntl_max = max(fcntl_max, d)
                if d >= STALL_S:
                    c["fcntl >= 29 s"] += 1
            elif func == "MPI_File_write_at_all":
                c["MPI_File_write_at_all"] += 1
                if d >= STALL_S:
                    writes_long += 1
                    stalls.append((round(start, 1), round(end, 1)))
            last = max(last, end)
        c["write_at_all >= 29 s"] = writes_long
        per_rank[rank] = (c, fcntl_max, stalls, last)
    return per_rank


def main():
    for case in CASES:
        print(f"\n=== {case}")
        for v in VARIANTS:
            text_dir = one(os.path.join(RESULTS, v, case, "trace_*", "_text"))
            ior = one(os.path.join(RESULTS, v, case, "ior_*.txt"))
            if not text_dir:
                print(f"  [skip] {v}: no recorder2text output")
                continue
            bw = ior_write(ior) if ior else None
            per_rank = summarize(text_dir)
            tot = collections.Counter()
            for c, _, _, _ in per_rank.values():
                tot.update(c)
            lockers = sorted(r for r, (c, _, _, _) in per_rank.items() if c["lock (F_SETLKW)"])
            print(f"  {v}: IOR {bw[0]:.2f} MiB/s, {bw[1]:.1f} s" if bw else f"  {v}:")
            print(f"    fcntl on test file: {tot['lock (F_SETLKW)']} lock, {tot['unlock']} unlock"
                  + "".join(f", {tot[k]} {k}" for k in tot if k.startswith("other")))
            print(f"    ranks that lock: {lockers}")
            if lockers:
                print(f"    locks per locking rank: {[per_rank[r][0]['lock (F_SETLKW)'] for r in lockers]}")
                print(f"    fcntl calls >= 29 s per locking rank: "
                      f"{[per_rank[r][0]['fcntl >= 29 s'] for r in lockers]}, "
                      f"longest {max(per_rank[r][1] for r in lockers):.2f} s (timings unreliable, see header)")
            others = [r for r in sorted(per_rank) if r not in lockers]
            if others:
                r = others[0]
                st = per_rank[r][2]
                print(f"    stall events on rank {r} (no locks): {len(st)}, "
                      f"{sum(e - s_ for s_, e in st):.0f} s in total: {st}")
            print(f"    MPI_File_write_at_all: {tot['MPI_File_write_at_all']}, "
                  f">= 29 s: {tot['write_at_all >= 29 s']}")
            print(f"    last timestamp per rank (s): "
                  f"{ {r: round(per_rank[r][3]) for r in sorted(per_rank)} }")

if __name__ == "__main__":
    main()
