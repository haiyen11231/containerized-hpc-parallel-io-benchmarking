"""OSU optimization -- transport architecture diagram.

A schematic, not a data plot: shows WHY the three configurations in
figO1a/figO1b perform the way they do, by drawing the actual software path
each one takes from the benchmark call down to the NIC.

  native            OpenMPI 4.1.2-hpe (Cray build) -- UCX PML -- RDMA verbs
  container_tcp     OpenMPI 4.1.2 (generic apt build) -- TCP BTL -- kernel sockets
  container_ucx     the SAME container image as container_tcp -- only the
                     mpirun flag changes -- UCX PML -- RDMA verbs (same path as native)

The point the diagram has to make visually: container_tcp and container_ucx
share one container image (there was never a rebuild); the only difference
is which transport OpenMPI was told to use, and that choice is what routes
container_ucx onto the same short RDMA path as native instead of through
three extra layers of kernel networking.

Run:  python3 analysis/plot_architecture.py
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

HERE = os.path.dirname(__file__)
FIG_DIR = os.path.join(HERE, "figures")

NATIVE = "#1f77b4"
TCP = "#d62728"
UCX = "#2ca02c"
NEUTRAL = "#555555"
BOXFACE = "#f7f7f7"


def box(ax, x, y, w, h, text, ec=NEUTRAL, fc=BOXFACE, fontsize=9, fontweight="normal", lw=1.6):
    patch = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                            linewidth=lw, edgecolor=ec, facecolor=fc, zorder=3)
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
             fontsize=fontsize, fontweight=fontweight, color="black", zorder=4,
             wrap=True)
    return patch


def arrow(ax, x, y0, y1, color=NEUTRAL, style="-", lw=2.0):
    a = FancyArrowPatch((x, y0), (x, y1), arrowstyle="-|>", mutation_scale=14,
                         linewidth=lw, color=color, linestyle=style, zorder=2)
    ax.add_patch(a)


def fig_architecture():
    fig, ax = plt.subplots(figsize=(13, 9.5))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 11)
    ax.axis("off")

    col_x = {"native": (0.4, 3.6), "tcp": (4.2, 7.4), "ucx": (8.0, 11.2)}
    col_color = {"native": NATIVE, "tcp": TCP, "ucx": UCX}
    col_title = {"native": "Native", "tcp": "Container, baseline (TCP)", "ucx": "Container, optimized (UCX)"}

    # Row 0: shared application layer
    box(ax, 0.4, 9.6, 10.8, 0.9, "OSU Micro-Benchmarks 8.0rc  —  osu_latency / osu_bw",
        ec=NEUTRAL, fc="#e8e8e8", fontsize=10.5, fontweight="bold")
    for key, (x0, x1) in col_x.items():
        arrow(ax, (x0 + x1) / 2, 9.6, 8.6, color=col_color[key])

    # Column headers -- white-boxed so the arrow passing behind stays legible
    for key, (x0, x1) in col_x.items():
        ax.text((x0 + x1) / 2, 9.15, col_title[key], ha="center", va="center",
                fontsize=11, fontweight="bold", color=col_color[key], zorder=5,
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.85))

    # Row 1: MPI library -- the container columns share ONE image
    bx0, _ = col_x["native"]
    box(ax, bx0, 7.5, 3.2, 1.1, "OpenMPI 4.1.2-hpe\n(Cray build, host)",
        ec=NATIVE, fontsize=9)
    box(ax, 4.2, 7.5, 7.0, 1.1,
        "OpenMPI 4.1.2 (generic apt build, Ubuntu 22.04)  —  ONE container image, built once",
        ec=NEUTRAL, fc="#eef4ff", fontsize=9.5, fontweight="bold")
    for key in ("native", "tcp", "ucx"):
        x0, x1 = col_x[key]
        arrow(ax, (x0 + x1) / 2, 7.5, 6.7, color=col_color[key])

    # Row 2: the ONE flag that diverges
    box(ax, col_x["native"][0], 5.9, 3.2, 0.9, "--mca pml ucx\n(default)", ec=NATIVE, fontsize=9)
    box(ax, col_x["tcp"][0], 5.9, 3.2, 0.9, "--mca btl tcp,self\n--mca btl_tcp_if_include hsn0",
        ec=TCP, fontsize=8.5)
    box(ax, col_x["ucx"][0], 5.9, 3.2, 0.9, "--mca pml ucx\n(flag changed -- matches native)",
        ec=UCX, fontsize=8.5, fontweight="bold")
    for key in ("native", "tcp", "ucx"):
        x0, x1 = col_x[key]
        arrow(ax, (x0 + x1) / 2, 5.9, 5.1, color=col_color[key])

    # Row 3: transport path taken
    box(ax, col_x["native"][0], 4.0, 3.2, 1.1, "UCX PML\nrc_verbs / ud_verbs (RDMA)",
        ec=NATIVE, fontsize=9)
    box(ax, col_x["tcp"][0], 3.5, 3.2, 1.6,
        "OB1 PML\n↓\nTCP BTL\n↓\nkernel socket stack\n(extra copies + syscalls)",
        ec=TCP, fontsize=8.5)
    box(ax, col_x["ucx"][0], 4.0, 3.2, 1.1, "UCX PML\nrc_verbs / ud_verbs (RDMA)",
        ec=UCX, fontsize=9, fontweight="bold")
    arrow(ax, (col_x["native"][0] + col_x["native"][1]) / 2, 4.0, 3.2, color=NATIVE)
    arrow(ax, (col_x["tcp"][0] + col_x["tcp"][1]) / 2, 3.5, 3.0, color=TCP)
    arrow(ax, (col_x["ucx"][0] + col_x["ucx"][1]) / 2, 4.0, 3.2, color=UCX)

    # Row 4: device access
    box(ax, col_x["native"][0], 2.0, 3.2, 1.0,
        "ibverbs → mlx5_0\n(host device, direct)", ec=NATIVE, fontsize=8.5)
    box(ax, col_x["tcp"][0], 2.0, 3.2, 1.0,
        "hsn0 IP interface\n(TCP/IP over the NIC)", ec=TCP, fontsize=8.5)
    box(ax, col_x["ucx"][0], 2.0, 3.2, 1.0,
        "ibverbs → mlx5_0\nvia Apptainer /dev passthrough\n(zero binds needed)", ec=UCX, fontsize=8)
    for key in ("native", "tcp", "ucx"):
        x0, x1 = col_x[key]
        arrow(ax, (x0 + x1) / 2, 2.0, 1.45, color=col_color[key])

    # Measured 1-byte latency, tying the diagram back to the data in figO1a.
    ax.text((col_x["native"][0] + col_x["native"][1]) / 2, 1.28, "1.46 µs",
            ha="center", fontsize=10.5, fontweight="bold", color=NATIVE)
    ax.text((col_x["tcp"][0] + col_x["tcp"][1]) / 2, 1.28, "17.10 µs",
            ha="center", fontsize=10.5, fontweight="bold", color=TCP)
    ax.text((col_x["ucx"][0] + col_x["ucx"][1]) / 2, 1.28, "1.67 µs",
            ha="center", fontsize=10.5, fontweight="bold", color=UCX)

    # Row 5: shared physical fabric
    box(ax, 0.4, 0.15, 10.8, 0.95,
        "Mellanox ConnectX-5 NIC (mlx5_0)  —  same physical card for all three cases",
        ec=NEUTRAL, fc="#e8e8e8", fontsize=10, fontweight="bold")

    fig.suptitle(
        "Figure O2 — Same container image, same NIC: the transport flag is the only difference\n"
        "(1-byte inter-node latency shown at the base of each path)",
        fontsize=12.5, y=0.985)

    os.makedirs(FIG_DIR, exist_ok=True)
    path = os.path.join(FIG_DIR, "figO2_architecture.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {os.path.relpath(path, HERE)}")


if __name__ == "__main__":
    print("Generating OSU optimization architecture diagram...")
    fig_architecture()
