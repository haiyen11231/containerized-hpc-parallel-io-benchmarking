#!/bin/bash
cd "$(dirname "$0")"

# Cold-read calibration: 2 node counts x 2 variants = 4 configs, 8 jobs.
#
# Two points are enough. n1 is the most cache-inflated case (20 GiB fits
# easily in one node's 440 GB RAM); n2 spreads the same per-rank work over
# twice the memory. The TREND between them is the evidence that the warm
# reads were a cache effect, not slow I/O.
#
# Deliberately excludes 4- and 8-node configs: at FILES=10 an 8-node job
# writes 1.56 TiB, and running those concurrently throttled the filesystem
# badly enough that 13 jobs were killed on walltime in an earlier attempt.
# The calibration does not need scale coverage.
#
# FILES=N -> N independent cold reads, ONE FILE EACH. Re-reading a single
# file would only be cold on the first pass; that pass fills the cache for
# the rest.

NODE_COUNTS=(1 2)
VARIANTS=(native container)
FILES=${FILES:-10}

mkdir -p logs

for NODES in "${NODE_COUNTS[@]}"; do
  # 128 ncpus (1 node) only reaches q4 if walltime > 02:00:01; below that it
  # falls into qdev, whose 256-ncpu cap is shared cluster-wide. 2 nodes is
  # 256 ncpus -> q5, which has no walltime floor.
  # Both tiers get 02:30:00. n1 NEEDS >2h to reach q4 instead of qdev; n2 is
  # q5 (no walltime floor) so the longer request is free, and it buys margin
  # against filesystem contention when many jobs run concurrently -- an
  # earlier batch was killed at 01:00:25 for exactly that reason.
  WT=02:30:00

  for V in "${VARIANTS[@]}"; do
    N="weak_n${NODES}_dno_mno_${V}"
    VARS="VARIANT=${V},CASE=weak,NODE_COUNT=${NODES},DIM_1=1048576,COLL_DATA=NO,COLL_META=NO,FILES=${FILES}"
    SEL="select=${NODES}:ncpus=128:mpiprocs=128:mem=64gb"

    W=$(qsub -N "coldread_w_$N" -o "logs/coldread_w_$N.out" \
             -l "$SEL" -l walltime=$WT -v "$VARS" \
             h5bench_coldread_write.pbs)

    # afterok: the read runs only if the write succeeded. PBS schedules it
    # independently, which is what normally places it on different nodes.
    R=$(qsub -N "coldread_r_$N" -o "logs/coldread_r_$N.out" \
             -l "$SEL" -l walltime=$WT -v "$VARS" \
             -W "depend=afterok:${W}" \
             h5bench_coldread_read.pbs)

    echo "  $N  (${NODES} node, wt=$WT)  write=$W  read=$R"
  done
done

echo
echo "Submitted $(( ${#NODE_COUNTS[@]} * ${#VARIANTS[@]} * 2 )) jobs, FILES=$FILES."
echo "Read jobs stay in state H until their write partner finishes - that is the dependency."
echo "AFTER they run: check node_overlap.txt is 0 for every config before using any number."
