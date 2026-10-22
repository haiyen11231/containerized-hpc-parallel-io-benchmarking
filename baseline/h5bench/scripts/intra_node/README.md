# Intra-node case study — setup and rationale

Setup:

Single node, 64 ranks. Sweeps the 2 access pattern configs of mem and file layout 2-D write and read, native vs container.
Total dataset size: 80 GB across 10 timesteps = 8 GB per timestep.

At any given moment, your 64 ranks are only actively holding and pushing a single timestep's worth of data (~8 GB total, or about 125 MB per rank) through the I/O pipeline to Lustre.

Once a timestep is written and flushed (H5Fflush), that memory is reused for the next timestep. Because 8 GB fits comfortably inside your 64 GB RAM limit, your job never runs out of memory.
---

- Enforce Absolute Cache Clearing & Unique Paths: Ensure each repetition writes to a distinct file path (which you are already doing with write_rep${REP}.csv), but add an explicit sync and drop-caches command if you have root access, or rely on distinct output files coupled with a sleep buffer to let Lustre client rpc queues drain.

- Increase Timesteps or Repetitions Intelligently:

Timesteps (TIMESTEPS): Keep it around 5 or increase to 10 if you want to measure sustained multi-phase write throughput stability over time rather than a single burst.

Repetitions (REPS): Keep REPS=10 so you can calculate standard deviations and error bars, but add a 5-second sleep 5 pause between iterations to let the I/O subsystem settle.

- Add Explicit Verification Criteria: Validate that each repetition starts with a clean file state.