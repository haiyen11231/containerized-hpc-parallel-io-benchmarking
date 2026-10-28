#!/bin/bash
cd "$(dirname "$0")"

# Experiment description: Run h5bench intra-node INTERLEAVED_CONTIG case on both native and containerization
# with Recorder to trace the MPI-IO and POSIX calls for the purpose of analyzing the I/O patterns and performance characteristics.

mkdir -p logs

echo "Submitting h5bench_native_intra_recorder (MEM=INTERLEAVED FILE=CONTIG)..."
qsub -N h5bench_native_intra_recorder -o logs/h5bench_native_intra_recorder.out \
     -l select=1:ncpus=64:mpiprocs=64:mem=32gb \
     h5bench_native_intra_recorder.pbs

echo "Submitting h5bench_container_intra_recorder (MEM=INTERLEAVED FILE=CONTIG)..."
qsub -N h5bench_container_intra_recorder -o logs/h5bench_container_intra_recorder.out \
     -l select=1:ncpus=64:mpiprocs=64:mem=32gb \
     h5bench_container_intra_recorder.pbs
