from __future__ import annotations

import csv
import io
import math
from types import SimpleNamespace


def nmea_to_decimal(coordinate: str, hemisphere: str) -> float:
    degree_width = 2 if hemisphere.upper() in {"N", "S"} else 3
    value = int(coordinate[:degree_width]) + float(coordinate[degree_width:]) / 60.0
    return -value if hemisphere.upper() in {"S", "W"} else value


def decimal_to_nmea(value: float, is_latitude: bool) -> tuple[str, str]:
    positive, negative = ("N", "S") if is_latitude else ("E", "W")
    hemisphere = positive if value >= 0 else negative
    width = 2 if is_latitude else 3
    absolute = abs(value)
    degrees = int(absolute)
    minutes = (absolute - degrees) * 60.0
    return f"{degrees:0{width}d}{minutes:010.7f}", hemisphere


def parse_gpgga(sentence: str):
    text = sentence.strip().strip('"')
    fields = text.split("*", 1)[0].split(",")
    if not text.startswith("$") or len(fields) < 15 or not fields[0].endswith("GGA"):
        raise ValueError("Invalid GGA sentence")
    altitude = float(fields[9]) if fields[9] else math.nan
    geoid_separation = float(fields[11]) if fields[11] else None
    height = (
        altitude + geoid_separation
        if geoid_separation is not None and not math.isnan(altitude)
        else altitude
    )
    return SimpleNamespace(
        raw=text,
        fields=fields,
        latitude=nmea_to_decimal(fields[2], fields[3]),
        longitude=nmea_to_decimal(fields[4], fields[5]),
        altitude_msl_m=altitude,
        geoid_sep_m=geoid_separation,
        z_m=height,
    )


def format_gpgga_with_checksum(
    gga, latitude: float, longitude: float, altitude_msl_m: float
) -> str:
    fields = gga.fields.copy()
    fields[2], fields[3] = decimal_to_nmea(latitude, True)
    fields[4], fields[5] = decimal_to_nmea(longitude, False)
    decimals = len(gga.fields[9].split(".", 1)[1]) if "." in gga.fields[9] else 3
    fields[9] = f"{altitude_msl_m:.{decimals}f}"
    body = ",".join(fields)
    checksum = 0
    for character in body[1:]:
        checksum ^= ord(character)
    return f"{body}*{checksum:02X}"


def parse_csv_line(line: str) -> tuple[list[str], str]:
    newline = "\r\n" if line.endswith("\r\n") else "\n"
    body = (
        line[:-2]
        if line.endswith("\r\n")
        else line[:-1]
        if line.endswith("\n")
        else line
    )
    return next(csv.reader([body])), newline


def format_csv_line(row: list[str], newline: str) -> str:
    stream = io.StringIO()
    csv.writer(stream, lineterminator="", quoting=csv.QUOTE_MINIMAL).writerow(row)
    return stream.getvalue() + newline


def find_data_header(lines: list[str]) -> int | None:
    return next(
        (
            index
            for index, line in enumerate(lines)
            if not line.strip().startswith(";") and "gps" in line.lower()
        ),
        None,
    )


def find_column(header: list[str], name: str) -> int | None:
    return next(
        (
            index
            for index, value in enumerate(header)
            if value.strip().lower() == name.lower()
        ),
        None,
    )


def update_existing_header(
    lines: list[str], keys: list[str], value: str, data_header_index: int, newline: str
) -> bool:
    prefixes = [f";{key}=".lower() for key in keys]
    for index in range(data_header_index):
        stripped = lines[index].strip()
        if not any(stripped.lower().startswith(prefix) for prefix in prefixes):
            continue
        existing_key = stripped.split("=", 1)[0]
        lines[index] = f"{existing_key}={value}{newline}"
        return True
    return False
