#!/usr/bin/env python3
"""
Analyze a recorder2timeline Chrome-Trace-Format JSON: per-category time/count,
top slowest individual calls, per-rank totals (fastest/slowest rank), and the
largest idle gaps on the slowest rank (stall detection).
"""
import json
import sys
from collections import defaultdict

def analyze(path, label):
    print(f"\n{'='*70}\n{label}  ({path})\n{'='*70}")
    with open(path) as f:
        data = json.load(f)
    events = [e for e in data["traceEvents"] if e.get("ph") == "X"]
    print(f"total events: {len(events)}")

    cat_dur = defaultdict(float)
    cat_count = defaultdict(int)
    rank_dur = defaultdict(float)
    for e in events:
        cat_dur[e.get("cat", "?")] += e.get("dur", 0.0)
        cat_count[e.get("cat", "?")] += 1
        rank_dur[e.get("pid", -1)] += e.get("dur", 0.0)

    print("\n-- time spent per category (seconds, summed across all ranks) --")
    for cat, dur in sorted(cat_dur.items(), key=lambda x: -x[1]):
        print(f"  {cat:10s}  {dur/1e6:10.3f}s   calls={cat_count[cat]}")

    print("\n-- top 10 longest individual calls --")
    top = sorted(events, key=lambda e: -e.get("dur", 0))[:10]
    for e in top:
        args = e.get("args", {}).get("args", [])
        print(f"  rank={e.get('pid')} {e.get('name'):20s} dur={e.get('dur',0)/1e6:.4f}s  args={args[:3]}")

    print("\n-- rank totals: fastest / slowest --")
    ranked = sorted(rank_dur.items(), key=lambda x: x[1])
    print(f"  fastest rank={ranked[0][0]}  total_dur={ranked[0][1]/1e6:.3f}s")
    print(f"  slowest rank={ranked[-1][0]}  total_dur={ranked[-1][1]/1e6:.3f}s")
    print(f"  spread={-(ranked[0][1]-ranked[-1][1])/1e6:.3f}s")

    # gap analysis on the slowest rank
    slow_rank = ranked[-1][0]
    rank_events = sorted([e for e in events if e.get("pid") == slow_rank], key=lambda e: e.get("ts", 0))
    gaps = []
    for i in range(1, len(rank_events)):
        prev_end = rank_events[i-1].get("ts", 0) + rank_events[i-1].get("dur", 0)
        gap = rank_events[i].get("ts", 0) - prev_end
        if gap > 0:
            gaps.append((gap, rank_events[i-1].get("name"), rank_events[i].get("name"), prev_end))
    gaps.sort(key=lambda x: -x[0])
    print(f"\n-- top 5 largest idle gaps on slowest rank (rank {slow_rank}) --")
    for gap, before, after, t in gaps[:5]:
        print(f"  gap={gap/1e6:.4f}s  between '{before}' -> '{after}'  at t={t/1e6:.3f}s")

if __name__ == "__main__":
    base = "/Users/haiyen11231/Study/School/FYP/containerized-hpc-parallel-io-benchmarking/profiling/h5bench/recorder/results/timelines"
    analyze(f"{base}/native_contig_contig_run3_timeline.json", "NATIVE contig_contig (run3)")
    analyze(f"{base}/container_contig_contig_timeline.json", "CONTAINER contig_contig (current)")
    analyze(f"{base}/native_interleaved_contig_timeline.json", "NATIVE interleaved_contig (current)")
    analyze(f"{base}/container_interleaved_contig_run2_timeline.json", "CONTAINER interleaved_contig (run2)")
