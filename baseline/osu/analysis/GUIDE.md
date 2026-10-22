Here is your comprehensive, master execution plan for analyzing, plotting, and profiling your OSU Micro-Benchmarks. This plan integrates statistical rigor, the Hockney cost model, architectural runtime flags, and parallel computing profiling principles.

---

## Phase 1: Data Preprocessing & Statistical Rigor

Before generating any charts, process your raw multi-run data to ensure statistical validity across your 684 result files.

1. **Warm-Up Removal:** Discard **Run 1** (or Runs 1–2) for all latency and bandwidth metrics to eliminate cold-start noise (such as dynamic socket handshakes and lazy memory allocations). Compute all statistics over the remaining **Runs 2–10 ($N = 9$)**.
2. **Aggregation & Slowest-Rank Semantics:**
* Use the **Mean** when the Coefficient of Variation ($CV = \frac{\sigma}{\mu}$) is low ($CV < 5\%$). Report both **Mean and Median** (or Interquartile Range) if $CV > 15\%$ (such as the high-variance container intra-node large-message bandwidth).
* Ensure your timing values reflect the **slowest rank** across the communicator (matching `MPI_MAX` reduction semantics), as total parallel runtime is dictated by the lagging rank.


3. **95% Confidence Intervals (CI):** Calculate the 95% CI using the Student's $t$-distribution for $N = 9$ ($t_{0.025, 8} \approx 2.306$):

$$\text{Margin of Error (MoE)} = 2.306 \times \frac{s}{\sqrt{9}}$$



---

## Phase 2: Complete Plotting Roadmap

Organize your visualization suite into three logical groups to present a clear performance narrative.

### 1. Point-to-Point (Pt2Pt) Figures

* **Figure 1A: Latency vs. Message Size (Log-Log Scale)**
* **Axes:** X = Message Size ($1\text{ B}$ to $4\text{ MiB}$, Log scale); Y = Latency ($\mu\text{s}$, Log scale).
* **Layout:** Two panels side-by-side (Intra-Node vs. Inter-Node), comparing Native vs. Container with 95% CI error bars.


* **Figure 1B: Bandwidth vs. Message Size (Log-Linear Scale)**
* **Axes:** X = Message Size (Log scale); Y = Throughput ($\text{GB/s}$, Linear scale).
* **Focus:** Highlight bandwidth saturation points ("knees of the curve") and error-bar spreads in high-variance regions.


* **Figure 1C: Overhead Ratio Factor ($\text{Container} / \text{Native}$)**
* **Axes:** X = Message Size (Log scale); Y = Ratio Factor ($1.0\times = \text{parity}$).
* **Key Insight:** Clearly illustrates where the container penalty peaks (small messages / fixed startup latency) versus large payloads.



### 2. Collective Scaling & Efficiency Figures

* **Figure 2A & 2B: Execution Time and Scaling Efficiency vs. Ranks / Nodes**
* **Layout:** Strong and weak scaling curves for Allreduce and Alltoall (Intra-node $8 \rightarrow 128$ ranks; Inter-node $2 \rightarrow 8$ nodes).
* **Efficiency Subplot:** Plot **Efficiency vs. Rank Count ($P$)** to visually diagnose communication-bound degradation versus load-imbalance efficiency drop-offs.
* **Annotation:** Explicitly annotate the catastrophic failure point at $\ge 512$ ranks on the container Alltoall curve.


* **Figure 2C: Native Allreduce Algorithm Jump Zoom-In**
* **Focus:** Zoom in on the non-monotonic spike at $P = 64$ to showcase OpenMPI's internal tuned collective algorithm switching behavior.



### 3. Diagnostic & Failure Matrix

* **Figure 3: Alltoall Port Exhaustion Diagnostic Matrix**
* **Visualization:** Grouped bar chart comparing Pass/Fail completion status across your 3-arm diagnostic experiment (Native 512 ranks [Pass] vs. Container 512 ranks @ 128 r/node [Fail] vs. Container 512 ranks @ 64 r/node [Pass]).



---

## Phase 3: Analytical Modeling — The Hockney Model $T(S) = \alpha + \frac{S}{B}$

Move beyond qualitative descriptions by quantifying exact startup overheads and bandwidth limits.

1. **Model Fitting Method:**
* Perform linear regression ($T(S) = m \cdot S + c$) on small-to-medium message sizes ($S \le 8192\text{ Bytes}$) from your inter-node point-to-point latency data.
* **Intercept ($c$):** Represents $\alpha$ (Fixed startup/software latency in $\mu\text{s}$).
* **Slope ($m$):** $m = \frac{1}{B} \implies B = \frac{1}{m}$ (Asymptotic Bandwidth).


2. **Report Table & Takeaway:** Construct a parameter table comparing $\alpha_{\text{native}}$ vs. $\alpha_{\text{container}}$ and $B_{\text{native}}$ vs. $B_{\text{container}}$. Demonstrate that the container's inter-node penalty is dominated by an added $\sim 12\,\mu\text{s}$ fixed startup penalty ($\alpha$) from the TCP software stack rather than raw bandwidth limitations.

---

## Phase 4: Critical Profiling — Tool Selection & Hypothesis Testing

### 1. Tool Selection

* **Do NOT use Darshan:** Darshan instruments storage file system I/O (POSIX, HDF5, MPI-IO). Because OSU micro-benchmarks run purely in-memory and over the network, Darshan logs will be empty.
* **USE Recorder:** Recorder traces sequence-level MPI primitive function calls (`MPI_Isend`, `MPI_Allreduce`, `MPI_Alltoall`), parameters, timestamps, and rank-to-rank communication sequences.

### 2. Hypothesis-Driven Profiling Experiments

Execute targeted diagnostics to prove the root causes of your key findings:

| Finding | Underlying Hypothesis | Validation Method / Action |
| --- | --- | --- |
| **A. Container Allreduce is ~20% faster intra-node** | Native UCX/CMA incurs kernel syscall overhead; Container `vader` user-space ring buffer avoids context switching for small payloads. | Run `perf stat -e syscalls:sys_enter_process_vm_readv` during a 128-rank intra-node run. Native will record thousands of syscalls; Container will record **zero**. |
| **B. Native Allreduce spike at $P = 64$** | OpenMPI's tuned collective module dynamically selects a sub-optimal algorithm for the AMD EPYC NUMA topology at this specific rank count. | Set `OMPI_MCA_coll_base_verbose=10` and `OMPI_MCA_coll_tuned_use_dynamic_rules=1` to log algorithm selection IDs. Use **Recorder** to inspect sub-call sequences. |
| **C. Container Alltoall failure at $\ge 512$ ranks** | 128 ranks/node connecting to 512 peers exhausts available Linux ephemeral TCP ports ($\approx 28,232$ limit). | Monitor socket state with `ss -s` during job execution to track socket allocation growth toward the kernel limit, and inspect connection refusal stalls in **Recorder** traces. |

---

## Phase 5: Report Structure & Narrative Flow

When writing up your report, structure your findings around these three core architectural pillars:

1. **The Intra-Node Quirk:** Explain how Apptainer user-namespace restrictions disable kernel CMA, forcing `vader` into a two-copy user-space ring buffer that unexpectedly improves small collective performance by avoiding kernel context switches.
2. **The Inter-Node Penalty:** Contrast Native UCX/RDMA hardware acceleration over `hsn0` ($\approx 1.46\,\mu\text{s}$ latency) with Container TCP socket packet encapsulation over the same interface ($\approx 13.47\,\mu\text{s}$ latency).
3. **The Scaling Limit:** Conclude with the socket-exhaustion failure mode, demonstrating how software abstraction layers interact with OS kernel resource limits at scale.