#!/bin/bash
# Push the weak-scaling scripts to Aspire 2A and submit all 20 jobs.
#   2 variants (native, container) x 2 benches (allreduce, alltoall) x 5 rank counts
# Requires a working ssh connection: ssh -fN aspire2a
set -e
cd "$(dirname "$0")"
R=/home/users/ntu/haiyen00/scratch/fyp/experiments/baseline/osu/collective/intra_node/weak_scaling

ssh aspire2a "mkdir -p $R/logs"
scp weak_scaling/osu_native_collective_weak.pbs \
    weak_scaling/osu_container_collective_weak.pbs \
    weak_scaling/submit_native_collective_weak_job.sh \
    weak_scaling/submit_container_collective_weak_job.sh \
    aspire2a:"$R/"

ssh aspire2a "
  cd $R && chmod +x submit_*.sh
  rm -rf native container; rm -f logs/*.out    # clean slate
  ./submit_native_collective_weak_job.sh
  ./submit_container_collective_weak_job.sh
  echo; qstat -u haiyen02 | tail -22
"
