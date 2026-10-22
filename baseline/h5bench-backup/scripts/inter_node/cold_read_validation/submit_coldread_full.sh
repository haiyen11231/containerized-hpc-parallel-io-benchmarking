#!/bin/bash
cd "$(dirname "$0")"

# ============================================================================
# BACKUP / OPTIONAL — full cold-read coverage. NOT the default.
#
# The default calibration is submit_coldread_jobs.sh (4 configs, 8 jobs,
# 1.2 TiB). That is sufficient to prove the warm reads were a page-cache
# artifact and to report a true cold read bandwidth.
#
# Use THIS script only if you need cold READ RESULTS per configuration -- for
# example to report read bandwidth across scales, or to recover the
# collective-read finding (cold data showed COLLECTIVE_DATA=YES made reads
# ~3x SLOWER, the opposite of its effect on writes; warm reads hid this).
#
# ---------------------------------------------------------------------------
# READ THIS BEFORE RUNNING
#
# A previous attempt at full coverage FAILED. 48 jobs were submitted at once;
# 19 write jobs ran concurrently, each streaming hundreds of GiB to the same
# Lustre filesystem. They throttled each other, per-job bandwidth collapsed,
# and 13 jobs were killed at exactly 01:00:25 against a 1h walltime (PBS
# exit -29). 2.9 TB of payload had to be cleaned up by hand.
#
# Mitigations applied here:
#   1. walltime 04:00:00 everywhere (q4/q5 both allow 24h, so it is free)
#   2. BATCH_LIMIT -- submit in batches and wait, instead of all at once
#   3. FILES defaults to 3, not 10 -- a third of the data volume
#
# Do NOT run this while the main case studies are in flight. Check first:
#   qstat -u $USER
# ============================================================================

FILES=${FILES:-3}
WALLTIME=${WALLTIME:-04:00:00}
BATCH_LIMIT=${BATCH_LIMIT:-4}     # max configs submitted per batch
DRY_RUN=${DRY_RUN:-0}             # 1 = print what would be submitted

#   case        nodes  dim_1     coll_data coll_meta
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
VARIANTS=(native container)

mkdir -p logs

# ---- cost estimate up front, so nothing is a surprise -----------------------
total=0
for cfg in "${CONFIGS[@]}"; do
  read -r CASE NODES DIM1 CD CM <<< "$cfg"
  per=$(( NODES * 128 * 5 * DIM1 * 32 / 1024 / 1024 / 1024 ))
  total=$(( total + per * FILES * ${#VARIANTS[@]} ))
done
echo "Full cold-read coverage"
echo "  configs       : ${#CONFIGS[@]} x ${#VARIANTS[@]} variants = $(( ${#CONFIGS[@]} * ${#VARIANTS[@]} ))"
echo "  jobs          : $(( ${#CONFIGS[@]} * ${#VARIANTS[@]} * 2 )) (write + read each)"
echo "  FILES         : $FILES"
echo "  walltime      : $WALLTIME"
echo "  batch limit   : $BATCH_LIMIT configs at a time"
echo "  peak transient: ~$(( total / 1024 )) TiB"
echo

if [ "$DRY_RUN" = "1" ]; then
  echo "DRY_RUN=1 -- nothing submitted."
  exit 0
fi

read -r -p "Proceed? [y/N] " ans
[ "$ans" = "y" ] || { echo "aborted"; exit 0; }

# ---- submit in batches ------------------------------------------------------
submitted=0
for cfg in "${CONFIGS[@]}"; do
  read -r CASE NODES DIM1 CD CM <<< "$cfg"
  CD_L=$(echo "$CD" | tr '[:upper:]' '[:lower:]')
  CM_L=$(echo "$CM" | tr '[:upper:]' '[:lower:]')

  for V in "${VARIANTS[@]}"; do
    N="${CASE}_n${NODES}_d${CD_L}_m${CM_L}_${V}"
    VARS="VARIANT=${V},CASE=${CASE},NODE_COUNT=${NODES},DIM_1=${DIM1},COLL_DATA=${CD},COLL_META=${CM},FILES=${FILES}"
    SEL="select=${NODES}:ncpus=128:mpiprocs=128:mem=64gb"

    W=$(qsub -N "coldread_w_$N" -o "logs/coldread_w_$N.out" \
             -l "$SEL" -l walltime=$WALLTIME -v "$VARS" \
             h5bench_coldread_write.pbs)
    R=$(qsub -N "coldread_r_$N" -o "logs/coldread_r_$N.out" \
             -l "$SEL" -l walltime=$WALLTIME -v "$VARS" \
             -W "depend=afterok:${W}" h5bench_coldread_read.pbs)
    echo "  $N  write=$W  read=$R"
    submitted=$(( submitted + 1 ))
  done

  # Pause between batches so writes do not all land on Lustre together.
  if [ $(( submitted % BATCH_LIMIT )) -eq 0 ]; then
    echo "  --- batch of $BATCH_LIMIT submitted; waiting for the queue to drain below $BATCH_LIMIT running ---"
    while [ "$(qstat -u "$USER" 2>/dev/null | grep -c coldread_w)" -ge "$BATCH_LIMIT" ]; do
      sleep 120
    done
  fi
done

echo
echo "Submitted $(( submitted * 2 )) jobs."
echo "AFTER they run: check node_overlap.txt is 0 for every config before using any number."
