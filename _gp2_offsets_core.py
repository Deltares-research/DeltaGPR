from __future__ import annotations

import csv
import io
import math
import statistics
from pathlib import Path
from types import SimpleNamespace

from pyproj import Transformer


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


def _nmea_to_decimal(coord: str, hemi: str) -> float:
    w = 2 if hemi.upper() in {"N", "S"} else 3
    val = int(coord[:w]) + float(coord[w:]) / 60.0
    return -val if hemi.upper() in {"S", "W"} else val


def _decimal_to_nmea(value: float, is_lat: bool) -> tuple[str, str]:
    pos, neg = ("N", "S") if is_lat else ("E", "W")
    hemi = pos if value >= 0 else neg
    width = 2 if is_lat else 3
    v = abs(value)
    deg = int(v)
    mins = (v - deg) * 60.0
    return f"{deg:0{width}d}{mins:010.7f}", hemi


def parse_gpgga(sentence: str):
    text = sentence.strip().strip('"')
    fields = text.split("*", 1)[0].split(",")
    if not text.startswith("$") or len(fields) < 15 or not fields[0].endswith("GGA"):
        raise ValueError("Invalid GGA sentence")
    alt = float(fields[9]) if fields[9] else math.nan
    geoid = float(fields[11]) if fields[11] else None
    z = alt + geoid if geoid is not None and not math.isnan(alt) else alt
    return SimpleNamespace(
        raw=text,
        fields=fields,
        latitude=_nmea_to_decimal(fields[2], fields[3]),
        longitude=_nmea_to_decimal(fields[4], fields[5]),
        altitude_msl_m=alt,
        geoid_sep_m=geoid,
        z_m=z,
    )


def format_gpgga_with_checksum(
    gga, latitude: float, longitude: float, altitude_msl_m: float
) -> str:
    fields = gga.fields.copy()
    fields[2], fields[3] = _decimal_to_nmea(latitude, True)
    fields[4], fields[5] = _decimal_to_nmea(longitude, False)
    decimals = len(gga.fields[9].split(".", 1)[1]) if "." in gga.fields[9] else 3
    fields[9] = f"{altitude_msl_m:.{decimals}f}"
    body = ",".join(fields)
    checksum = 0
    for ch in body[1:]:
        checksum ^= ord(ch)
    return f"{body}*{checksum:02X}"


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


def apply_offset(
    x: float, y: float, z: float, heading_rad: float, offset: Offset
) -> tuple[float, float, float]:
    """Translate one projected position using the GP2 forward/right offset."""
    if math.isnan(heading_rad):
        return x, y, z
    fx, fy = math.cos(heading_rad), math.sin(heading_rad)
    rx, ry = math.sin(heading_rad), -math.cos(heading_rad)
    return (
        x + offset.offset_y * fx + offset.offset_x * rx,
        y + offset.offset_y * fy + offset.offset_x * ry,
        z + offset.offset_z,
    )


def _parse_csv_line(line: str) -> tuple[list[str], str]:
    nl = "\r\n" if line.endswith("\r\n") else "\n"
    body = (
        line[:-2]
        if line.endswith("\r\n")
        else line[:-1]
        if line.endswith("\n")
        else line
    )
    return next(csv.reader([body])), nl


def _fmt_csv_line(row: list[str], nl: str) -> str:
    s = io.StringIO()
    csv.writer(s, lineterminator="", quoting=csv.QUOTE_MINIMAL).writerow(row)
    return s.getvalue() + nl


def process_gp2_in_place(path: Path) -> None:
    """Apply the GP2 header offset rigidly, then reset it to zero."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    if not lines:
        return

    h = next(
        (
            i
            for i, ln in enumerate(lines)
            if not ln.strip().startswith(";") and "gps" in ln.lower()
        ),
        None,
    )
    if h is None:
        return
    o = next(
        (i for i in range(h) if lines[i].strip().lower().startswith(";offset_m=")), None
    )
    if o is None:
        raise ValueError(f"{path}: missing ;Offset_m=")

    header, _ = _parse_csv_line(lines[h])
    gps_idx = next(
        (i for i, name in enumerate(header) if name.strip().lower() == "gps"), None
    )
    if gps_idx is None:
        return

    idxs, ggas = [], []
    for i in range(h + 1, len(lines)):
        if not lines[i].strip() or lines[i].lstrip().startswith(";"):
            continue
        idxs.append(i)
        try:
            row, _ = _parse_csv_line(lines[i])
            ggas.append(parse_gpgga(row[gps_idx]) if len(row) > gps_idx else None)
        except Exception:
            ggas.append(None)

    valid = [g for g in ggas if g is not None]
    if not valid:
        return

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

    heading = estimate_line_heading(xs, ys)
    xyz2 = [
        (math.nan, math.nan, math.nan)
        if any(math.isnan(v) for v in (x, y, z))
        else apply_offset(x, y, z, heading, offset)
        for x, y, z in zip(xs, ys, zs, strict=False)
    ]

    nl = "\r\n" if lines[o].endswith("\r\n") else "\n"
    lines[o] = f";Offset_m=0.00,0.00,0.00{nl}"

    for i, li in enumerate(idxs):
        g = ggas[i]
        x2, y2, z2 = xyz2[i]
        if g is None or any(math.isnan(v) for v in (x2, y2, z2)):
            continue
        row, row_nl = _parse_csv_line(lines[li])
        lat2, lon2 = inverse_project_xy_to_latlon(x2, y2, proj)
        alt2 = z2 - g.geoid_sep_m if g.geoid_sep_m is not None else z2
        row[gps_idx] = format_gpgga_with_checksum(g, lat2, lon2, alt2)
        lines[li] = _fmt_csv_line(row, row_nl)

    path.write_text("".join(lines), encoding="utf-8")
