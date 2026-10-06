#!/bin/bash
# Push the strong-scaling scripts to Aspire 2A and submit all 20 jobs.
#   2 variants (native, container) x 2 benches (allreduce, alltoall) x 5 rank counts
# Total problem fixed at 8 MiB, so the per-rank message SHRINKS as NP grows:
#   NP=8 -> 1024 KiB ... NP=128 -> 64 KiB (which equals the weak-scaling size,
#   giving a deliberate cross-study consistency check at that point).
#
# Requires a working ssh connection: ssh -fN aspire2a
set -e
cd "$(dirname "$0")"
R=/home/users/ntu/haiyen00/scratch/fyp/experiments/baseline/osu/collective/intra_node/strong_scaling

ssh aspire2a "mkdir -p $R/logs"
scp strong_scaling/osu_native_collective_strong.pbs \
    strong_scaling/osu_container_collective_strong.pbs \
    strong_scaling/submit_native_collective_strong_job.sh \
    strong_scaling/submit_container_collective_strong_job.sh \
    aspire2a:"$R/"

ssh aspire2a "
  cd $R && chmod +x submit_*.sh
  rm -rf native container; rm -f logs/*.out    # clean slate
  ./submit_native_collective_strong_job.sh
  ./submit_container_collective_strong_job.sh
"
