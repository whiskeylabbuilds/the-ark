"""The Ark: tiny GPU and power reader for the dashboard. Works on any hardware.

Samples every SAMPLE_SECONDS in a background thread and serves the latest numbers as JSON, so a
dashboard request never waits on a sensor. Standard library only.

GPU:   NVIDIA (nvidia-smi), AMD Radeon (Linux amdgpu sysfs), Intel or other graphics (name only),
       or none. Missing readings show as "n/a".
Power: CPU package and platform ("psys") energy counters from Linux powercap (Intel, most AMD
       Ryzen). Total = platform + GPU when the platform counter exists, otherwise CPU + GPU.

  GET /  ->  {"gpu": "GTX 1660 Ti", "gpu_util": "3%", "gpu_mem": "0.1 / 6 GB", "gpu_temp": "52°C",
              "gpu_power": "6.0 W", "cpu_power": "8.0 W", "total_power": "26.6 W", ... plus raw numbers}
"""
import glob, json, os, re, shutil, subprocess, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SAMPLE_SECONDS = float(os.environ.get("SAMPLE_SECONDS", "5"))
SYS = os.environ.get("HOST_SYS", "/host/sys")          # the host's /sys, mounted read-only
PORT = int(os.environ.get("PORT", "9100"))
NA = "n/a"

latest = {"status": "starting"}


# ---------- power (Linux powercap / RAPL) ----------
def rapl_zones():
    zones = {}
    for name_file in sorted(glob.glob(os.path.join(SYS, "class/powercap/*/name"))):
        d = os.path.dirname(name_file)
        try:
            name = open(name_file).read().strip()
            open(os.path.join(d, "energy_uj")).read()
        except OSError:
            continue
        if name == "package-0":
            zones.setdefault("cpu_power_w", d)
        elif name == "psys":
            zones.setdefault("platform_power_w", d)
    return zones


def read_energy(d):
    with open(os.path.join(d, "energy_uj")) as f:
        e = int(f.read())
    try:
        with open(os.path.join(d, "max_energy_range_uj")) as f:
            wrap = int(f.read())
    except OSError:
        wrap = 2 ** 32
    return e, wrap


# ---------- GPU ----------
def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def read_file_num(path, scale=1.0):
    try:
        v = num(open(path).read().strip())
        return v * scale if v is not None else None
    except OSError:
        return None


def read_nvidia():
    q = "name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw"
    out = subprocess.run(["nvidia-smi", f"--query-gpu={q}", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True, timeout=10).stdout.strip().splitlines()
    if not out:
        return None
    name, util, used, total, temp, power = [x.strip() for x in out[0].split(",", 5)]
    used, total = num(used), num(total)
    return {"gpu_vendor": "nvidia", "gpu_name": name, "gpu_util_pct": num(util),
            "vram_used_gb": used / 1024 if used is not None else None,
            "vram_total_gb": total / 1024 if total is not None else None,
            "gpu_temp_c": num(temp), "gpu_power_w": num(power)}


def drm_cards():
    """[(vendor_id, device_dir)] for display cards found in sysfs."""
    cards = []
    for v in sorted(glob.glob(os.path.join(SYS, "class/drm/card[0-9]*/device/vendor"))):
        if re.search(r"/card\d+-", v):  # connectors such as card0-HDMI-A-1
            continue
        try:
            cards.append((open(v).read().strip(), os.path.dirname(v)))
        except OSError:
            pass
    return cards


def read_amd(dev):
    hw = (glob.glob(os.path.join(dev, "hwmon/hwmon*")) or [None])[0]
    power = None
    if hw:
        power = read_file_num(os.path.join(hw, "power1_average"), 1e-6) or read_file_num(os.path.join(hw, "power1_input"), 1e-6)
    try:
        name = open(os.path.join(dev, "product_name")).read().strip() or "AMD Radeon"
    except OSError:
        name = "AMD Radeon"
    return {"gpu_vendor": "amd", "gpu_name": name,
            "gpu_util_pct": read_file_num(os.path.join(dev, "gpu_busy_percent")),
            "vram_used_gb": read_file_num(os.path.join(dev, "mem_info_vram_used"), 1 / 1024 ** 3),
            "vram_total_gb": read_file_num(os.path.join(dev, "mem_info_vram_total"), 1 / 1024 ** 3),
            "gpu_temp_c": read_file_num(os.path.join(hw, "temp1_input"), 1e-3) if hw else None,
            "gpu_power_w": power}


VENDORS = {"0x10de": "NVIDIA graphics", "0x1002": "AMD Radeon", "0x8086": "Intel graphics"}
GPU_KIND = None  # decided once at start: "nvidia", ("amd", dir), ("other", name) or "none"


def detect_gpu():
    if shutil.which("nvidia-smi"):
        try:
            if read_nvidia():
                return "nvidia"
        except Exception:
            pass
    cards = drm_cards()
    for vendor, dev in cards:
        if vendor == "0x1002" and os.path.exists(os.path.join(dev, "gpu_busy_percent")):
            return ("amd", dev)
    if cards:
        return ("other", VENDORS.get(cards[0][0], "Built-in graphics"))
    return "none"


def read_gpu():
    if GPU_KIND == "nvidia":
        return read_nvidia() or {}
    if isinstance(GPU_KIND, tuple) and GPU_KIND[0] == "amd":
        return read_amd(GPU_KIND[1])
    if isinstance(GPU_KIND, tuple):
        return {"gpu_vendor": "other", "gpu_name": GPU_KIND[1]}
    return {"gpu_vendor": "none", "gpu_name": "No graphics card"}


# ---------- display strings (the dashboard shows them as-is) ----------
def fmt(v, pattern):
    return pattern.format(v) if isinstance(v, (int, float)) else NA


def display(s):
    used, total = s.get("vram_used_gb"), s.get("vram_total_gb")
    s["gpu"] = s.get("gpu_name", NA).replace("NVIDIA ", "").replace("GeForce ", "").strip()
    s["gpu_util"] = fmt(s.get("gpu_util_pct"), "{:.0f}%")
    s["gpu_mem"] = f"{used:.1f} / {total:.0f} GB" if isinstance(used, float) and isinstance(total, float) else NA
    s["gpu_temp"] = fmt(s.get("gpu_temp_c"), "{:.0f}°C")
    s["gpu_power"] = fmt(s.get("gpu_power_w"), "{:.1f} W")
    s["cpu_power"] = fmt(s.get("cpu_power_w"), "{:.1f} W")
    base = s.get("platform_power_w") if s.get("platform_power_w") is not None else s.get("cpu_power_w")
    parts = [p for p in (base, s.get("gpu_power_w")) if p is not None]
    s["total_power_w"] = round(sum(parts), 1) if parts else None
    s["total_power"] = fmt(s["total_power_w"], "{:.1f} W")
    return s


def sampler():
    global latest, GPU_KIND
    GPU_KIND = detect_gpu()
    zones = rapl_zones()
    prev = {}
    for key, d in zones.items():
        try:
            prev[key] = (read_energy(d), time.monotonic())
        except OSError:
            pass
    while True:
        time.sleep(SAMPLE_SECONDS)
        sample = {"status": "ok", "updated": int(time.time())}
        for key, d in zones.items():
            try:
                (e, wrap), now = read_energy(d), time.monotonic()
                if key in prev:
                    (e0, _), t0 = prev[key]
                    de = e - e0 if e >= e0 else e + wrap - e0   # counter wrapped around
                    sample[key] = round(de / 1e6 / (now - t0), 1)
                prev[key] = ((e, wrap), now)
            except OSError:
                pass
        try:
            sample.update(read_gpu())
        except Exception as exc:  # sensor hiccup: keep the power numbers
            sample["gpu_error"] = str(exc)[:200]
        latest = display(sample)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(latest).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    threading.Thread(target=sampler, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
