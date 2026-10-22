# Port-exhaustion diagnostic

A supplementary experiment, not a measurement. It exists to turn one observation into a demonstrated cause.

## What it tests

The inter-node collective sweep showed **container Alltoall failing at 4 and 8 nodes**:

```
bind on local address (10.150.2.70:0) failed: Address already in use (98)
```

The hypothesis was TCP ephemeral-port exhaustion. Alltoall requires every rank to connect to every peer, and all 128 ranks on a node share that node's single `hsn0` IP, so a node needs `ranks_per_node × (total_ranks − 1)` outbound connections against a ~28,232-port range.

That arithmetic fits the observed pattern, but fitting is not proving — a reader could still object that 512 ranks is simply too many, or that those particular nodes were unhealthy.

## Design — three arms, one allocation

All three run on **the same four nodes within the same job**, so hardware, background load and timing are held constant. Only one variable changes per comparison:

| arm | ranks/node | total | conns/node | vs ports | purpose |
|---|---|---|---|---|---|
| `container_rpn128` | 128 | 512 | 65,408 | 2.32× | reproduce the failure |
| `container_rpn64` | **64** | 256 | 16,320 | 0.58× | **isolate the connection count** |
| `native_rpn128` | 128 | 512 | 65,408 | — | **control: same scale, no TCP** |

Arm 2 differs from arm 1 **only** in how many connections are needed — same container, same binary, same message size, same nodes. Arm 3 runs the identical 512 ranks that broke the container, under UCX/RDMA which opens no per-peer sockets.

## Result

| arm | exit | port errors | data rows | verdict |
|---|---|---|---|---|
| `container_rpn128` | 16 | **512** | 0 | **FAIL** |
| `container_rpn64` | 0 | 0 | 1 | **PASS** |
| `native_rpn128` | 0 | 0 | 1 | **PASS** |

Measured on the compute node: `ip_local_port_range = 32768 60999` (**28,232 ports**), `tcp_tw_reuse = 2`. Runtime 51 s.

Halving the connection count fixes it; holding the connection count and removing TCP also fixes it. Scale and node health are both excluded.

> **The container's lack of UCX imposes a hard scalability ceiling on all-to-all communication, not merely a performance penalty.**

## Two implementation details worth keeping

**A failing arm is an expected result, not a job error.** Each run is wrapped in `set +e` and its exit code, port-error count and data-row count are recorded. Arm 1 *must* fail for the experiment to mean anything, so the job has to survive it and continue to arms 2 and 3.

**System limits are measured, not assumed.** The port range is read from `/proc/sys/net/ipv4/` on the compute node and written to `system_limits.txt`, so the number the whole argument depends on is evidence from the hardware that ran the test — not a login-node value assumed to apply.

## Running it

```bash
qsub port_exhaustion_diag.pbs     # 4 nodes, ~1 min of actual work
```

Output lands in `results/`: one `.log` and one `.summary` per arm, plus `nodes.txt` and `system_limits.txt`.

Confirmation looks like: `container_rpn128=FAIL`, `container_rpn64=PASS`, `native_rpn128=PASS`.
