Here is a structured plotting roadmap and profiling strategy tailored specifically for your **IOR parallel I/O benchmark data** on Lustre.

---

### Phase 1: The IOR Plotting Roadmap

Because IOR measures storage throughput rather than network message latency, your plots need to emphasize **aggregate bandwidth (MiB/s or GiB/s)** against transfer sizes, access patterns, and node counts.

#### 1. Intra-Node Analysis (Access Pattern & Striping)

* **Figure 1A: Bandwidth vs. Transfer Size (Log-Linear Scale)**
* **Axes:** X = Transfer Size ($64\text{ KiB}$ to $16\text{ MiB}$, Log scale); Y = Aggregate Write Bandwidth ($\text{MiB/s}$, Linear scale).
* **Series:** Compare POSIX vs. MPI-IO, and Shared File vs. File-Per-Process (FPP) at Stripe Count = 1 vs. Stripe Count = 8.
* **Key Insight:** Shows the saturation point where small per-call overhead gives way to bulk storage throughput.


* **Figure 1B: Shared File vs. FPP Speedup Bar Chart**
* **Focus:** Directly illustrate the $\sim 3.5\times$ performance gap between shared files and file-per-process, isolating Lustre lock contention effects.



#### 2. Inter-Node Scaling Studies (Weak & Strong Scaling)

* **Figure 2A: Weak Scaling Aggregate Bandwidth vs. Node Count ($1 \rightarrow 8$ Nodes)**
* **Axes:** X = Node Count (Linear/Log2); Y = Total Write Bandwidth ($\text{GiB/s}$).
* **Series:** Native vs. Container across Shared and FPP models.
* **Key Insight:** Tests whether Lustre can absorb linear work expansion as more clients are added.


* **Figure 2B: Strong Scaling Efficiency vs. Node Count**
* **Axes:** X = Node Count ($1 \rightarrow 8$); Y = Parallel Efficiency ($\%$ of ideal linear scaling for the fixed $64\text{ GiB}$ workload).
* **Key Insight:** Identifies where strong scaling efficiency drops off as per-rank chunks shrink.
--------------
# Enhancement
You **do not need to rerun your experiments or filter out data points to reduce noise.** High run-to-run variance (CV 14% to 25%, and up to 69% for File-Per-Process) is a well-known, unavoidable physical characteristic of shared, multi-tenant parallel file systems like Lustre.

Rather than modifying the data, you can make your graphs instantly clearer, scientifically rigorous, and easier to discuss in your report through a few visual and structural enhancements.

---

### 1. Enhance the Visual Layout & Formatting

* **Add a Shaded Noise / Equivalence Band:**
Because the native and container confidence intervals overlap almost everywhere, add a subtle gray shaded band across the 1.0 parity line on your ratio plots (e.g., $\pm 15\%$ or $\pm 20\%$). Label this region **"Shared Storage Noise Floor."** This instantly signals to the reader that fluctuations inside the band are non-significant storage variance rather than container overhead.


* **Highlight Key Architectural Thresholds:**
In Figure 1A, draw a vertical dashed line at **$1\text{ MiB}$** (Lustre's default stripe size `-S 1m`). This visually explains why throughput levels off or changes trajectory once the transfer size reaches or exceeds the underlying stripe alignment.


* **Clean Up Overlapping Data Labels:**
In panels where the native (blue) and container (orange) lines cross or overlap closely (such as Figure 1A POSIX FPP), offset the text annotations slightly above and below the points so numbers do not collide.

---

### 2. Group Figures by Physical Phenomena

Instead of trying to explain every crossing point individually, structure your report layout around the **three primary physical mechanisms** driving the data:

| Feature in Plot | What the Reader Sees | How to Frame it in Your Report |
| --- | --- | --- |
| **Access Pattern Gap ($3.5\times\text{--}4\times$)**<br> | Huge vertical separation between Shared File and FPP.

 | **Storage Mechanism:** FPP avoids single-file extent lock contention across Lustre OSTs.

 |
| **Overlapping Native/Container Curves**<br> | Intersecting lines with wide, overlapping 95% CIs.

 | **Runtime Mechanism:** Apptainer executes on the host kernel storage stack with zero protocol translation, leaving container overhead below the noise floor. |
| **Fluctuations Across Transfer Sizes**<br> | Jagged, non-monotonic lines at large transfer sizes.

 | **Environmental Noise:** Multi-tenant client contention and OST caching state on Aspire 2A. |

---

### 3. State the Statistical Bounds in Your Report Text

In the discussion section accompanying your figures, explicitly address the variance using statistical bounding language:

> "Due to the multi-tenant nature of the production Lustre file system, individual benchmark runs exhibit a Coefficient of Variation (CV) ranging between 14% and 25%. Because the native and container performance metrics consistently fall within each other's 95% confidence intervals, we conclude that containerization introduces no statistically significant overhead for parallel I/O. Instead, throughput is entirely governed by the file access model (`fpp` vs. `shared`)."
> 
> 

---

### Summary Recommendation

Keep the raw statistical data exactly as it is. Adding a visual **noise-floor band**, aligning text labels, and anchoring your text narrative around **Lustre lock contention vs. container parity** will transform those crossing lines from a point of confusion into a strong, defensible finding for your final report!
