"""Emit every measurement as one tidy CSV plus a Markdown table.

Figures are for reading; this is for quoting exact numbers in the thesis and
for anyone who wants to re-analyze without re-parsing h5bench's output.

Columns: study, config, variant, operation, cache_state, n, mean_gibs,
ci95_halfwidth, rel_ci_pct, trustworthy.

'trustworthy' is FALSE for warm reads (page-cache artifact) and for any cold
read whose job shared a node with its write job. Everything else is TRUE.
"""

import csv
import os
import numpy as np
import common as c

OUT_CSV = os.path.join(os.path.dirname(__file__), "h5bench_summary.csv")
OUT_MD = os.path.join(os.path.dirname(__file__), "h5bench_summary.md")


def rows():
    out = []

    def add(study, config, variant, op, cache, values, trustworthy):
        mean, ci, n = c.stats(values)
        if n == 0:
            return
        out.append(dict(
            study=study, config=config, variant=variant, operation=op,
            cache_state=cache, n=n,
            mean_gibs=round(mean, 4),
            ci95_halfwidth=("" if np.isnan(ci) else round(ci, 4)),
            rel_ci_pct=("" if np.isnan(ci) or mean == 0
                        else round(100 * ci / mean, 1)),
            trustworthy=str(trustworthy).upper()))

    for pattern in c.PATTERNS:
        for v in c.VARIANTS:
            add("intra_node", pattern, v, "write", "n/a",
                c.intra(v, pattern), True)

    for study, case in [("weak_scaling", "weak"), ("strong_scaling", "strong")]:
        for nodes in c.NODE_COUNTS:
            for v in c.VARIANTS:
                add(study, f"n{nodes}", v, "write", "n/a",
                    c.scaling(study, v, nodes, "write"), True)
                # in-job reads: page-cache inflated, kept for the record only
                add(study, f"n{nodes}", v, "read", "warm",
                    c.scaling(study, v, nodes, "read"), False)
                ok = c.cold_read_overlap_ok(case, nodes, v)
                add(study, f"n{nodes}", v, "read", "cold",
                    c.cold_read(case, nodes, v), ok)

    for cell in c.COLLECTIVE_CELLS:
        for v in c.VARIANTS:
            add("collective_io", cell, v, "write", "n/a",
                c.collective(v, cell, "write"), True)
            add("collective_io", cell, v, "read", "warm",
                c.collective(v, cell, "read"), False)
            ok = c.cold_read_overlap_ok("collective", 2, v, cell)
            add("collective_io", cell, v, "read", "cold",
                c.cold_read("collective", 2, v, cell), ok)
    return out


def main():
    data = rows()
    fields = ["study", "config", "variant", "operation", "cache_state", "n",
              "mean_gibs", "ci95_halfwidth", "rel_ci_pct", "trustworthy"]
    with open(OUT_CSV, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(data)
    print(f"  wrote {os.path.relpath(OUT_CSV)}  ({len(data)} rows)")

    with open(OUT_MD, "w") as fh:
        fh.write("# h5bench summary\n\n")
        fh.write("Rates in GiB/s (h5bench's binary units normalized). "
                 "`trustworthy=FALSE` marks warm reads, which were served "
                 "from page cache and never reached Lustre.\n\n")
        current = None
        for r in data:
            if r["study"] != current:
                current = r["study"]
                fh.write(f"\n## {current}\n\n")
                fh.write("| config | variant | op | cache | n | mean GiB/s "
                         "| 95% CI | rel CI | use |\n")
                fh.write("|---|---|---|---|---|---|---|---|---|\n")
            fh.write(f"| {r['config']} | {r['variant']} | {r['operation']} "
                     f"| {r['cache_state']} | {r['n']} | {r['mean_gibs']} "
                     f"| {r['ci95_halfwidth']} | {r['rel_ci_pct']}% "
                     f"| {'yes' if r['trustworthy']=='TRUE' else 'NO'} |\n")
    print(f"  wrote {os.path.relpath(OUT_MD)}")

    bad = [r for r in data if r["trustworthy"] == "FALSE"]
    print(f"  {len(data)-len(bad)} trustworthy rows, {len(bad)} excluded "
          f"(warm reads / node overlap)")


if __name__ == "__main__":
    print("summary tables:")
    main()
