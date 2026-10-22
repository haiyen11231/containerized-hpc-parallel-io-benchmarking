Yes, **moving to h5bench plots first is a great strategy.**

While IOR provides synthetic block-level I/O bounds, **h5bench** introduces realistic, application-shaped HDF5 workload patterns (simulating particle simulations like VPIC writing through MPI-IO and POSIX). Examining h5bench first allows you to complete your entire macroscopic visualization suite across both storage studies before diving into Darshan profiling for both.

---

## h5bench Plotting & Analysis Roadmap

To structure your h5bench results into clear, defensible visualizations for your report, organize your plots around the benchmark's five core studies:

### 1. Intra-Node Layout Study (Memory vs. File Patterns)

* **What to Plot:** A grouped bar chart or heatmap comparing write bandwidth across the 4 layout combinations: `CONTIG` $\times$ `CONTIG`, `CONTIG` $\times$ `INTERLEAVED`, `INTERLEAVED` $\times$ `CONTIG`, and `INTERLEAVED` $\times$ `INTERLEAVED` (at 128 ranks on 1 node).
* **What to Look For / Analyze:** How non-contiguous memory layouts or file interleaving affect HDF5's internal data conversion buffers and subsequent POSIX/MPI-IO submission efficiency to Lustre.

### 2. Weak Scaling Study (Per-Rank Work Fixed)

* **What to Plot:** Aggregate write bandwidth ($\text{GiB/s}$) vs. Node Count ($1 \rightarrow 8$ nodes), plotted alongside a dashed line for ideal linear growth (where each rank maintains a fixed $32\text{ MiB/timestep}$ load).
* **What to Look For / Analyze:** Check whether native and container curves track together, and identify the exact scale where Lustre saturates and curves flatten away from the ideal linear trajectory.

### 3. Strong Scaling Study (Total Work Fixed)

* **What to Plot:** Parallel Efficiency ($\%$ of ideal scaling) vs. Node Count ($1 \rightarrow 8$ nodes) for the fixed $128\text{ M particle}$ global workload.
* **What to Look For / Analyze:** Track efficiency drop-offs as per-rank particle shares shrink (from $1\text{ M/rank}$ on 1 node down to $128\text{ k/rank}$ on 8 nodes), highlighting when communication or metadata overhead begins to dominate.

### 4. Collective I/O Factorial Study (The $2 \times 2$ Matrix)

* **What to Plot:** A 4-category grouped bar chart at 2 nodes / 256 ranks comparing the factorial combinations:
* `dno_mno` (No Collective Data, No Collective Metadata)
* `dno_myes` (No Collective Data, Yes Collective Metadata)
* `dyes_mno` (Yes Collective Data, No Collective Metadata)
* `dyes_myes` (Yes Collective Data, Yes Collective Metadata)


* **What to Look For / Analyze:** This is a crucial mechanistic plot. It isolates whether enabling MPI collective data aggregation (`COLLECTIVE_DATA`) trades off network overhead effectively against disk access, and whether consolidating HDF5 metadata (`COLLECTIVE_METADATA`) relieves pressure on Lustre's Metadata Server (MDS).

### 5. Cold Read Validation Study (Cache Mitigation)

* **What to Plot:** A comparative bar chart contrasting intra-node read bandwidth (inflated by client-side page caching) against cross-node cold read bandwidth.
* **What to Look For / Analyze:** Use this to explicitly validate your methodology, showing that true cold reads eliminate the multi-fold cache inflation artifact and reveal realistic file system read speeds.
