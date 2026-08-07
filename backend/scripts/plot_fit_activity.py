"""绘制一条 COROS FIT 运动记录的测试概览图。

默认从 data/running/exportfrom20260806 中随机抽取一个 FIT 文件；也可通过
--file 指定文件名或完整路径。输出 PNG 默认保存到 backend/output/fit_plots。
"""

from __future__ import annotations

import argparse
import random
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from fitparse import FitFile


PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_DIR / "data" / "running" / "exportfrom20260806"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "backend" / "output" / "fit_plots"
SEMICIRCLES_PER_DEGREE = 2**31 / 180


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse and plot one COROS FIT activity.")
    parser.add_argument("--file", help="FIT filename in the data directory, or an absolute path")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output", type=Path, help="Output PNG path")
    parser.add_argument("--show", action="store_true", help="Display the figure after saving")
    return parser.parse_args()


def select_file(file_arg: str | None, data_dir: Path) -> Path:
    if file_arg:
        candidate = Path(file_arg)
        if not candidate.is_absolute():
            candidate = data_dir / candidate
        if candidate.suffix.lower() != ".fit" or not candidate.is_file():
            raise FileNotFoundError(f"FIT file not found: {candidate}")
        return candidate

    files = sorted(data_dir.glob("*.fit"))
    if not files:
        raise FileNotFoundError(f"No .fit files found in: {data_dir}")
    return random.choice(files)


def num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def parse_fit(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    session: dict[str, Any] = {}
    fit = FitFile(str(path))
    for message in fit.get_messages():
        values = message.get_values()
        if message.name == "record" and values.get("timestamp"):
            records.append(values)
        elif message.name == "session" and not session:
            session = values
    if not records:
        raise ValueError("This FIT file contains no timestamped record messages.")
    return records, session


def field_values(records: list[dict[str, Any]], name: str, scale: float = 1.0) -> list[float]:
    return [(num(record.get(name)) or float("nan")) * scale for record in records]


def session_title(session: dict[str, Any]) -> str:
    distance_km = (num(session.get("total_distance")) or 0) / 1000
    elapsed_s = num(session.get("total_timer_time")) or num(session.get("total_elapsed_time")) or 0
    duration = f"{int(elapsed_s // 3600):02d}:{int(elapsed_s % 3600 // 60):02d}:{int(elapsed_s % 60):02d}"
    sport = session.get("sport", "activity")
    return f"{sport} | {distance_km:.2f} km | {duration}"


def plot_activity(path: Path, records: list[dict[str, Any]], session: dict[str, Any], output: Path) -> None:
    timestamps = [record["timestamp"] for record in records]
    start = timestamps[0]
    minutes = [(timestamp - start).total_seconds() / 60 for timestamp in timestamps]
    distance_km = field_values(records, "distance", 0.001)
    speed_mps = field_values(records, "enhanced_speed")
    if all(value != value for value in speed_mps):
        speed_mps = field_values(records, "speed")
    pace = [1000 / (speed * 60) if speed and speed > 0 else float("nan") for speed in speed_mps]
    heart_rate = field_values(records, "heart_rate")
    altitude = field_values(records, "enhanced_altitude")
    if all(value != value for value in altitude):
        altitude = field_values(records, "altitude")

    lat = [((num(r.get("position_lat")) or float("nan")) / SEMICIRCLES_PER_DEGREE) for r in records]
    lon = [((num(r.get("position_long")) or float("nan")) / SEMICIRCLES_PER_DEGREE) for r in records]

    fig, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    fig.suptitle(f"COROS FIT: {path.name}\n{session_title(session)}", fontsize=14, fontweight="bold")

    ax = axes[0, 0]
    ax.plot(lon, lat, color="#1677ff", linewidth=1.2)
    ax.scatter(lon[0], lat[0], color="#2ca02c", label="Start", zorder=3)
    ax.scatter(lon[-1], lat[-1], color="#d62728", label="Finish", zorder=3)
    ax.set(title="GPS route", xlabel="Longitude", ylabel="Latitude")
    ax.legend()
    ax.set_aspect("equal", adjustable="datalim")

    ax = axes[0, 1]
    ax.plot(minutes, pace, color="#ff7f0e", linewidth=1)
    ax.set(title="Pace", xlabel="Elapsed time (min)", ylabel="min / km")
    ax.invert_yaxis()
    ax.grid(alpha=0.25)

    ax = axes[1, 0]
    ax.plot(minutes, heart_rate, color="#d62728", linewidth=1, label="Heart rate")
    ax.set(title="Heart rate and altitude", xlabel="Elapsed time (min)", ylabel="Heart rate (bpm)")
    ax.grid(alpha=0.25)
    altitude_ax = ax.twinx()
    altitude_ax.plot(minutes, altitude, color="#7f7f7f", linewidth=0.9, alpha=0.8, label="Altitude")
    altitude_ax.set_ylabel("Altitude (m)")

    ax = axes[1, 1]
    cadence = field_values(records, "cadence")
    power = field_values(records, "power")
    ax.plot(distance_km, cadence, color="#9467bd", linewidth=1, label="Cadence")
    ax.set(title="Cadence and power", xlabel="Distance (km)", ylabel="Cadence (spm)")
    ax.grid(alpha=0.25)
    power_ax = ax.twinx()
    power_ax.plot(distance_km, power, color="#2ca02c", linewidth=1, alpha=0.8, label="Power")
    power_ax.set_ylabel("Power (W)")

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=160, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    path = select_file(args.file, args.data_dir)
    records, session = parse_fit(path)
    output = args.output or DEFAULT_OUTPUT_DIR / f"{path.stem}_overview.png"
    plot_activity(path, records, session, output)
    print(f"Selected: {path}")
    print(f"Records: {len(records)}; {session_title(session)}")
    print(f"Plot saved: {output}")
    if args.show:
        image = plt.imread(output)
        plt.figure(figsize=(14, 9))
        plt.imshow(image)
        plt.axis("off")
        plt.show()


if __name__ == "__main__":
    main()
