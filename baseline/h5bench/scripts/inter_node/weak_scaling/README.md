# Weak scaling — inter-node

Per-rank workload is held **constant** while rank count grows, so total data volume grows proportionally. Answers: *does the native/container gap widen as the job gets bigger?*

| Nodes | Ranks | Per repetition |
|---|---|---|
| 1 | 128 | 20 GiB |
| 2 | 256 | 40 GiB |
| 4 | 512 | 80 GiB |
| 8 | 1024 | 160 GiB |

`DIM_1 = "1 M"` particles/rank × 32 B = 32 MiB per rank per timestep, × 5
timesteps. 10 repetitions per job.

Access pattern is fixed at `CONTIG`/`CONTIG` so scaling behaviour is not confounded with access-pattern effects — those are isolated in `intra_node/`.

## Write and read in one config

Both benchmarks live in the same JSON, write first. The driver runs them in order within a single invocation, so the read operates on the file the write just produced. `READ_OPTION=FULL` is the only parallel-safe option (`PRL`, `RDC`, `LDC`, `CS` are documented as single-process — only rank 0 reads).

**Caveat: read bandwidth is cache-influenced.** The read immediately follows the write, and at 160 GiB against ~3.5 TB of aggregate page cache across 8 nodes the data is still resident. h5bench has no equivalent of IOR's `-C` to defeat this.
The native/container *comparison* stays valid since both sides are equally affected, but absolute read figures are inflated and should be reported as such.

## Units

h5bench switches between `MB/s` and `GB/s` depending on magnitude, and both are
**binary** despite the labels (`1004.800 MB/s` = 1004.8 MiB/s; 1 "GB" = 1024
"MB"). Any analysis script must normalise using the unit column — averaging the
bare numbers produces nonsense.

## Where results land

The driver rewrites `CSV_FILE` to `<directory>/<uuid>/<csv>`
(`src/h5bench.py:370`), so CSVs appear under
`payload/<variant>/n<N>/<uuid>/` rather than in the report directory. The
`write_repN.csv` / `read_repN.csv` naming preserves the repetition index, since
the UUIDs are random and carry no ordering.

`<variant>/n<N>/` holds the generated `config_repN.json` and `driver_repN.log`
for each repetition.

## Launch model

Same hybrid model as `intra_node/` — host `mpirun` fans ranks out via PBS, each
rank enters the container through `apptainer exec`. Required here: the
container's generic OpenMPI has no PBS `tm` support and cannot spawn ranks on
remote nodes. See `../../intra_node/README.md` for the full rationale.

Container-only MCA flags beyond the intra-node set:
`--mca btl vader,tcp,self` (tcp needed for cross-node) and
`--mca btl_tcp_if_include hsn0 --mca oob_tcp_if_include hsn0` to pin traffic to
the Slingshot interface — without these the container's OpenMPI can route via
`docker0`, which has an identical IP on every node.
