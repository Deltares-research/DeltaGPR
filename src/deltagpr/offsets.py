from __future__ import annotations

import math
import statistics
from collections.abc import Iterable
from pathlib import Path

from pyproj import Transformer

from .dialogs import choose_gp2_files, copy_selected_to_subfolder
from .gp2 import (
    find_column,
    find_data_header,
    format_csv_line,
    format_gpgga_with_checksum,
    parse_csv_line,
    parse_gpgga,
)


class Offset:
    __slots__ = ("offset_x", "offset_y", "offset_z")

    def __init__(self, offset_x: float, offset_y: float, offset_z: float):
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.offset_z = offset_z


def parse_offset_line(line: str) -> Offset:
    text = line.strip().lower()
    if not text.startswith(";offset_m="):
        raise ValueError("Not an Offset_m line")
    x, y, z = [float(v.strip()) for v in text.split("=", 1)[1].split(",")]
    return Offset(x, y, z)


def _make_projector(lat_ref: float, lon_ref: float):
    zone = max(1, min(60, int((lon_ref + 180.0) // 6.0) + 1))
    epsg = 32600 + zone if lat_ref >= 0 else 32700 + zone
    return {
        "lat0": lat_ref,
        "lon0": lon_ref,
        "fwd": Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True),
        "inv": Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True),
    }


def project_latlon_to_xy(lat: float, lon: float, projector) -> tuple[float, float]:
    x, y = projector["fwd"].transform(lon, lat)
    return float(x), float(y)


def inverse_project_xy_to_latlon(x: float, y: float, projector) -> tuple[float, float]:
    lon, lat = projector["inv"].transform(x, y)
    return float(lat), float(lon)


def estimate_line_heading(xs: list[float], ys: list[float]) -> float:
    """Return the directed principal-axis heading of a survey line in radians.

    One file-wide heading ensures that its offset is a rigid translation. Local
    headings would deform the line where stationary GPS fixes are noisy.
    """
    valid = [
        (x, y)
        for x, y in zip(xs, ys, strict=False)
        if not (math.isnan(x) or math.isnan(y))
    ]
    if len(valid) < 2:
        return math.nan

    mean_x = statistics.mean(x for x, _ in valid)
    mean_y = statistics.mean(y for _, y in valid)
    covariance_xx = sum((x - mean_x) ** 2 for x, _ in valid)
    covariance_yy = sum((y - mean_y) ** 2 for _, y in valid)
    covariance_xy = sum((x - mean_x) * (y - mean_y) for x, y in valid)
    heading = 0.5 * math.atan2(2.0 * covariance_xy, covariance_xx - covariance_yy)

    start_x, start_y = valid[0]
    end_x, end_y = valid[-1]
    if (
        math.cos(heading) * (end_x - start_x) + math.sin(heading) * (end_y - start_y)
        < 0
    ):
        heading += math.pi
    return heading


def estimate_heading_series(
    xs: list[float], ys: list[float], min_baseline_m: float = 0.5
) -> list[float]:
    """Estimate local track headings without using near-stationary GPS fixes."""
    n = len(xs)
    headings = [math.nan] * n

    def valid(index: int) -> bool:
        return 0 <= index < n and not (
            math.isnan(xs[index]) or math.isnan(ys[index])
        )

    for index in range(n):
        if not valid(index):
            continue

        left = next(
            (
                candidate
                for candidate in range(index - 1, -1, -1)
                if valid(candidate)
                and math.hypot(
                    xs[index] - xs[candidate], ys[index] - ys[candidate]
                )
                >= min_baseline_m
            ),
            None,
        )
        right = next(
            (
                candidate
                for candidate in range(index + 1, n)
                if valid(candidate)
                and math.hypot(
                    xs[candidate] - xs[index], ys[candidate] - ys[index]
                )
                >= min_baseline_m
            ),
            None,
        )
        if left is not None and right is not None:
            headings[index] = math.atan2(
                ys[right] - ys[left], xs[right] - xs[left]
            )

    reliable = [
        index for index, heading in enumerate(headings) if not math.isnan(heading)
    ]
    if not reliable:
        fallback = estimate_line_heading(xs, ys)
        return [fallback if valid(index) else math.nan for index in range(n)]

    first, last = reliable[0], reliable[-1]
    for index in range(first):
        if valid(index):
            headings[index] = headings[first]
    for index in range(last + 1, n):
        if valid(index):
            headings[index] = headings[last]

    return headings


def apply_offset(
    x: float, y: float, z: float, heading_rad: float, offset: Offset
) -> tuple[float, float, float]:
    """Translate a GNSS position to the sensor using the GP2 antenna offset."""
    if math.isnan(heading_rad):
        return x, y, z
    fx, fy = math.cos(heading_rad), math.sin(heading_rad)
    rx, ry = math.sin(heading_rad), -math.cos(heading_rad)
    return (
        x - offset.offset_y * fx - offset.offset_x * rx,
        y - offset.offset_y * fy - offset.offset_x * ry,
        z - offset.offset_z,
    )


def process_gp2_in_place(path: Path) -> Offset | None:
    """Apply the GP2 header offset along the local track, then reset it to zero.

    Returns the ``Offset`` (in meters) that was applied, or ``None`` if the file
    had no valid GPS fixes to apply it to.
    """
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    if not lines:
        return None

    h = find_data_header(lines)
    if h is None:
        return None
    o = next(
        (i for i in range(h) if lines[i].strip().lower().startswith(";offset_m=")), None
    )
    if o is None:
        raise ValueError(f"{path}: missing ;Offset_m=")

    header, _ = parse_csv_line(lines[h])
    gps_idx = find_column(header, "gps")
    if gps_idx is None:
        return None

    idxs, ggas = [], []
    for i in range(h + 1, len(lines)):
        if not lines[i].strip() or lines[i].lstrip().startswith(";"):
            continue
        idxs.append(i)
        try:
            row, _ = parse_csv_line(lines[i])
            ggas.append(parse_gpgga(row[gps_idx]) if len(row) > gps_idx else None)
        except Exception:
            ggas.append(None)

    valid = [g for g in ggas if g is not None]
    if not valid:
        return None

    offset = parse_offset_line(lines[o])
    proj = _make_projector(
        statistics.mean(g.latitude for g in valid),
        statistics.mean(g.longitude for g in valid),
    )

    xs, ys, zs = [], [], []
    for g in ggas:
        if g is None:
            xs.append(math.nan)
            ys.append(math.nan)
            zs.append(math.nan)
            continue
        x, y = project_latlon_to_xy(g.latitude, g.longitude, proj)
        xs.append(x)
        ys.append(y)
        zs.append(g.z_m)

    headings = estimate_heading_series(xs, ys)
    xyz2 = [
        (math.nan, math.nan, math.nan)
        if any(math.isnan(v) for v in (x, y, z))
        else apply_offset(x, y, z, heading, offset)
        for x, y, z, heading in zip(xs, ys, zs, headings, strict=False)
    ]

    nl = "\r\n" if lines[o].endswith("\r\n") else "\n"
    lines[o] = f";Offset_m=0.00,0.00,0.00{nl}"

    for i, li in enumerate(idxs):
        g = ggas[i]
        x2, y2, z2 = xyz2[i]
        if g is None or any(math.isnan(v) for v in (x2, y2, z2)):
            continue
        row, row_nl = parse_csv_line(lines[li])
        lat2, lon2 = inverse_project_xy_to_latlon(x2, y2, proj)
        alt2 = z2 - g.geoid_sep_m if g.geoid_sep_m is not None else z2
        row[gps_idx] = format_gpgga_with_checksum(g, lat2, lon2, alt2)
        lines[li] = format_csv_line(row, row_nl)

    path.write_text("".join(lines), encoding="utf-8")
    return offset


def process_gp2(paths: Iterable[Path]) -> None:
    """Apply GP2 header offsets in place for multiple files."""
    for path in paths:
        offset = process_gp2_in_place(path)
        if offset is None:
            print(f"  {path.name}: skipped (no valid GPS fixes)")
        else:
            print(
                f"  {path.name}: offset x={offset.offset_x:+.2f} m, "
                f"y={offset.offset_y:+.2f} m, "
                f"z={offset.offset_z:+.2f} m applied, header offset reset to 0"
            )


def main() -> None:
    selected = choose_gp2_files("Select GP2 files to offset-correct")
    gp2_files = copy_selected_to_subfolder(selected, "offset_corrected")

    print(f"Copied {len(gp2_files)} selected file(s) to offset_corrected folder(s)")
    print(f"Applying offsets to {len(gp2_files)} file(s)...")
    process_gp2(gp2_files)
    print("Done")


if __name__ == "__main__":
    main()
