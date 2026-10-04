#!/bin/bash
cd "$(dirname "$0")"

# Every configuration from all three inter-node case studies, using the same
# parameters that study actually ran, so each cold number is directly
# comparable to its warm counterpart.
#
#   CASE        NODES  DIM_1     CD   CM    per file   mirrors
#   weak        1/2/4/8 1048576  NO   NO    20-160GiB  weak_scaling n1..n8
#   strong      1/2/4/8 varies   NO   NO    20 GiB     strong_scaling n1..n8
#   collective  2       1048576  2x2        40 GiB     collective_io all 4 cells
#
# Note weak n1 and strong n1 are the same configuration by design (the shared
# anchor between the two scaling studies); both are kept so each study has a
# self-contained validation set.
#
# FILES=N -> N independent cold reads per config, one file each, because
# re-reading a single file would only be cold the first time.
CONFIGS=(
  "weak 1 1048576 NO NO"
  "weak 2 1048576 NO NO"
  "weak 4 1048576 NO NO"
  "weak 8 1048576 NO NO"
  "strong 1 1048576 NO NO"
  "strong 2 524288 NO NO"
  "strong 4 262144 NO NO"
  "strong 8 131072 NO NO"
  "collective 2 1048576 NO NO"
  "collective 2 1048576 NO YES"
  "collective 2 1048576 YES NO"
  "collective 2 1048576 YES YES"
)

# 10 files = 10 independent cold reads per config, matching the n=10 of the
# main experiments so the cold reads get real confidence intervals. One file
# per read is mandatory: re-reading a single file would only be cold once.
FILES=${FILES:-10}
VARIANTS=(native container)

mkdir -p logs

for cfg in "${CONFIGS[@]}"; do
  read -r CASE NODES DIM1 CD CM <<< "$cfg"
  CD_L=$(echo "$CD" | tr '[:upper:]' '[:lower:]')
  CM_L=$(echo "$CM" | tr '[:upper:]' '[:lower:]')
  for V in "${VARIANTS[@]}"; do
    VARS="VARIANT=${V},CASE=${CASE},NODE_COUNT=${NODES},DIM_1=${DIM1},COLL_DATA=${CD},COLL_META=${CM},FILES=${FILES}"
    SEL="select=${NODES}:ncpus=128:mpiprocs=128:mem=64gb"

    # PBS routes on ncpus AND walltime. A 1-node job is 128 ncpus, which only
    # reaches q4 if walltime > 02:00:01; below that it falls into qdev, whose
    # 256-ncpu cap is shared across ALL users -- two such jobs fill it. From
    # 2 nodes up (256+ ncpus) the job goes to q5, which has no walltime floor.
    if [ "$NODES" -eq 1 ]; then WT=02:30:00; else WT=01:00:00; fi

    WJOB=$(qsub -N "coldread_w_${CASE}_n${NODES}_d${CD_L}_m${CM_L}_${V}" \
                -o "logs/coldread_w_${CASE}_n${NODES}_d${CD_L}_m${CM_L}_${V}.out" \
                -l "$SEL" -l walltime=$WT -v "$VARS" \
                h5bench_coldread_write.pbs)
    echo "  write: $WJOB  (${CASE} n${NODES} d${CD_L}_m${CM_L} / ${V})"

    # afterok: the read only runs if the write succeeded, and PBS will place
    # it independently -- normally on different nodes, which is the point.
    RJOB=$(qsub -N "coldread_r_${CASE}_n${NODES}_d${CD_L}_m${CM_L}_${V}" \
                -o "logs/coldread_r_${CASE}_n${NODES}_d${CD_L}_m${CM_L}_${V}.out" \
                -l "$SEL" -l walltime=$WT -v "$VARS" \
                -W "depend=afterok:${WJOB}" \
                h5bench_coldread_read.pbs)
    echo "  read : $RJOB  (depends on ${WJOB})"
  done
done

echo
echo "Submitted $(( ${#CONFIGS[@]} * ${#VARIANTS[@]} * 2 )) jobs."
echo "Read jobs stay queued (state H/Q) until their write job finishes - that is expected."
