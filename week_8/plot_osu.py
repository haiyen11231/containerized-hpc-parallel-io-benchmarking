import matplotlib.pyplot as plt
import glob

# ============================
# Helper: parse OSU output
# ============================
def parse_osu_file(file):
    sizes = []
    values = []

    with open(file) as f:
        for line in f:
            if line.startswith('#') or line.strip() == '':
                continue
            parts = line.split()
            sizes.append(int(parts[0]))
            values.append(float(parts[1]))

    return sizes, values


# ============================
# 1. Latency (pt2pt)
# ============================
plt.figure()

for env in ["native", "container"]:
    file = f"{env}_pt2pt_intra.txt"
    sizes, lat = parse_osu_file(file)
    plt.plot(sizes, lat, label=f"{env} intra")

    file = f"{env}_pt2pt_inter.txt"
    sizes, lat = parse_osu_file(file)
    plt.plot(sizes, lat, linestyle='--', label=f"{env} inter")

plt.xscale("log")
plt.yscale("log")
plt.xlabel("Message Size (Bytes)")
plt.ylabel("Latency (us)")
plt.title("OSU Latency: Native vs Container")
plt.legend()
plt.grid()
plt.savefig("latency.png")
plt.show()


# ============================
# 2. Strong Scaling (Allreduce)
# ============================
np_list = [2, 4, 8, 16]

native = []
container = []

for np in np_list:
    _, vals = parse_osu_file(f"native_strong_np{np}.txt")
    native.append(sum(vals)/len(vals))

    _, vals = parse_osu_file(f"container_strong_np{np}.txt")
    container.append(sum(vals)/len(vals))

plt.figure()
plt.plot(np_list, native, marker='o', label="Native")
plt.plot(np_list, container, marker='x', label="Container")

plt.xlabel("Processes")
plt.ylabel("Latency (us)")
plt.title("Strong Scaling (Allreduce)")
plt.legend()
plt.grid()
plt.savefig("strong_scaling.png")
plt.show()


# ============================
# 3. Weak Scaling
# ============================
native = []
container = []

for np in np_list:
    _, vals = parse_osu_file(f"native_weak_np{np}.txt")
    native.append(sum(vals)/len(vals))

    _, vals = parse_osu_file(f"container_weak_np{np}.txt")
    container.append(sum(vals)/len(vals))

plt.figure()
plt.plot(np_list, native, marker='o', label="Native")
plt.plot(np_list, container, marker='x', label="Container")

plt.xlabel("Processes")
plt.ylabel("Latency (us)")
plt.title("Weak Scaling (Allreduce)")
plt.legend()
plt.grid()
plt.savefig("weak_scaling.png")
plt.show()