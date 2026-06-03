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


def format_gpgga_with_checksum(gga, latitude: float, longitude: float, altitude_msl_m: float) -> str:
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


def estimate_heading_series(xs: list[float], ys: list[float], min_baseline_m: float = 0.5, window_max: int = 50) -> list[float]:
    n = len(xs)
    raw = [math.nan] * n

    def ok(i: int) -> bool:
        return 0 <= i < n and not (math.isnan(xs[i]) or math.isnan(ys[i]))

    for i in range(n):
        if not ok(i):
            continue
        for w in range(1, window_max + 1):
            l, r = i - w, i + w
            while l >= 0 and not ok(l):
                l -= 1
            while r < n and not ok(r):
                r += 1
            if ok(l) and ok(r) and math.hypot(xs[r] - xs[l], ys[r] - ys[l]) >= min_baseline_m:
                raw[i] = math.atan2(ys[r] - ys[l], xs[r] - xs[l])
                break
        if math.isnan(raw[i]):
            if ok(i - 1):
                raw[i] = math.atan2(ys[i] - ys[i - 1], xs[i] - xs[i - 1])
            elif ok(i + 1):
                raw[i] = math.atan2(ys[i + 1] - ys[i], xs[i + 1] - xs[i])

    smooth = [math.nan] * n
    for i in range(n):
        if math.isnan(raw[i]):
            continue
        sx = sy = 0.0
        for j in range(max(0, i - 2), min(n, i + 3)):
            if not math.isnan(raw[j]):
                sx += math.cos(raw[j])
                sy += math.sin(raw[j])
        if sx or sy:
            smooth[i] = math.atan2(sy, sx)
    return smooth


def apply_offset(x: float, y: float, z: float, heading_rad: float, offset: Offset) -> tuple[float, float, float]:
    if math.isnan(heading_rad):
        return x, y, z
    fx, fy = math.cos(heading_rad), math.sin(heading_rad)
    rx, ry = math.sin(heading_rad), -math.cos(heading_rad)
    return x + offset.offset_y * fx + offset.offset_x * rx, y + offset.offset_y * fy + offset.offset_x * ry, z + offset.offset_z


def _parse_csv_line(line: str) -> tuple[list[str], str]:
    nl = "\r\n" if line.endswith("\r\n") else "\n"
    body = line[:-2] if line.endswith("\r\n") else line[:-1] if line.endswith("\n") else line
    return next(csv.reader([body])), nl


def _fmt_csv_line(row: list[str], nl: str) -> str:
    s = io.StringIO()
    csv.writer(s, lineterminator="", quoting=csv.QUOTE_MINIMAL).writerow(row)
    return s.getvalue() + nl


def process_gp2_in_place(path: Path) -> None:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    if not lines:
        return

    h = next((i for i, ln in enumerate(lines) if not ln.strip().startswith(";") and "gps" in ln.lower()), None)
    if h is None:
        return
    o = next((i for i in range(h) if lines[i].strip().lower().startswith(";offset_m=")), None)
    if o is None:
        raise ValueError(f"{path}: missing ;Offset_m=")

    header, _ = _parse_csv_line(lines[h])
    gps_idx = next((i for i, name in enumerate(header) if name.strip().lower() == "gps"), None)
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
    proj = _make_projector(statistics.mean(g.latitude for g in valid), statistics.mean(g.longitude for g in valid))

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

    hs = estimate_heading_series(xs, ys)
    xyz2 = [
        (math.nan, math.nan, math.nan)
        if any(math.isnan(v) for v in (x, y, z))
        else apply_offset(x, y, z, hrad, offset)
        for x, y, z, hrad in zip(xs, ys, zs, hs, strict=False)
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
