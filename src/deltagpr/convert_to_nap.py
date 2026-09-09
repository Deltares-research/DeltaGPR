"""Convert ETRS89/WGS84 latitude, longitude and ellipsoidal height to NAP height.

The vertical part of RDNAPTRANS(TM)2018 is the NLGEO2018 quasi-geoid model, which
PROJ ships as the grid file ``nl_nsgi_nlgeo2018.tif``. Without that grid PROJ
silently falls back to a "ballpark" vertical transformation that returns the
ellipsoidal height unchanged, so this module refuses to run without it.
"""

from __future__ import annotations

import argparse
import math
import os
import shutil
import urllib.request
from collections.abc import Iterable
from pathlib import Path

import pyproj
from pyproj.transformer import Transformer, TransformerGroup

from .gp2 import (
    find_column,
    find_data_header,
    format_csv_line,
    format_gpgga_with_checksum,
    parse_csv_line,
    parse_gpgga,
)
from .warnings_log import log_warning

GRID_NAME = "nl_nsgi_nlgeo2018.tif"
GRID_URL = f"https://cdn.proj.org/{GRID_NAME}"
ETRS89_3D = "EPSG:4937"  # ETRS89 geographic 3D (lat, lon, ellipsoidal height)
NAP_HEIGHT = "EPSG:5709"  # NAP height
TEST_CASE = (51.0989936, 5.8416162, 75.5546)


def proj_search_dirs() -> list[Path]:
    """Return the directories PROJ searches for grid files, in lookup order."""
    dirs = [Path(part) for part in pyproj.datadir.get_data_dir().split(os.pathsep)]
    dirs.append(Path(pyproj.datadir.get_user_data_dir()))
    return dirs


def find_grid() -> Path | None:
    """Return the path to the NLGEO2018 grid, or None if PROJ cannot see it."""
    for directory in proj_search_dirs():
        candidate = directory / GRID_NAME
        if candidate.is_file():
            return candidate
    return None


def download_grid() -> Path:
    """Download the NLGEO2018 grid into the PROJ user-writable data directory."""
    target_dir = Path(pyproj.datadir.get_user_data_dir(create=True))
    target = target_dir / GRID_NAME
    print(f"Downloading {GRID_URL}")
    print(f"         -> {target}")
    with urllib.request.urlopen(GRID_URL, timeout=120) as response:  # noqa: S310
        with target.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    return target


def ensure_grid() -> Path:
    """Return the NLGEO2018 grid, downloading it once if PROJ cannot find it."""
    grid_path = find_grid()
    if grid_path is not None:
        return grid_path

    user_dir = pyproj.datadir.get_user_data_dir()
    try:
        download_grid()
    except OSError as error:
        raise SystemExit(
            f"{GRID_NAME} is missing and could not be downloaded from {GRID_URL} "
            f"({error}). Download it manually and place it in {user_dir}."
        ) from error

    grid_path = find_grid()
    if grid_path is None:
        raise SystemExit(
            f"{GRID_NAME} was downloaded but PROJ still cannot find it in {user_dir}."
        )
    return grid_path


def print_diagnostics(grid_path: Path | None) -> None:
    print("--- diagnostics ---")
    print(f"pyproj version        : {pyproj.__version__}")
    print(f"PROJ version          : {pyproj.proj_version_str}")
    print(f"PROJ data dir         : {pyproj.datadir.get_data_dir()}")
    print(f"PROJ user data dir    : {pyproj.datadir.get_user_data_dir()}")
    print(f"PROJ_DATA env var     : {os.environ.get('PROJ_DATA', '<unset>')}")
    if grid_path is None:
        print(f"{GRID_NAME} : NOT FOUND")
    else:
        size_mb = grid_path.stat().st_size / 1024**2
        print(f"{GRID_NAME} : {grid_path} ({size_mb:.1f} MB)")


def build_transformer() -> Transformer:
    """Return the NLGEO2018-based ETRS89 -> NAP transformer, or fail loudly."""
    group = TransformerGroup(ETRS89_3D, NAP_HEIGHT, always_xy=True)
    for transformer in group.transformers:
        if "ballpark" not in transformer.description.lower():
            return transformer

    missing = sorted(
        {
            grid.short_name
            for operation in group.unavailable_operations
            for grid in operation.grids
            if not grid.available
        }
    )
    raise SystemExit(
        "No NLGEO2018 vertical transformation is available: PROJ is missing the "
        f"grid file(s) {missing or [GRID_NAME]}. Re-run with --download, or place "
        f"{GRID_NAME} in {pyproj.datadir.get_user_data_dir()}."
    )


def convert_to_nap(
    latitude: float, longitude: float, ellipsoidal_height: float
) -> tuple[float, float]:
    """Return (NAP height, geoid undulation) for an ETRS89 position.

    The undulation is the NLGEO2018 separation actually applied by PROJ, i.e.
    ellipsoidal height minus NAP height.
    """
    transformer = build_transformer()
    print(f"Coordinate operation  : {transformer.description}")

    _, _, nap_height = transformer.transform(
        longitude, latitude, ellipsoidal_height, errcheck=True
    )
    if nap_height == float("inf") or nap_height != nap_height:
        raise SystemExit(
            f"Transformation returned no result for lat={latitude}, lon={longitude}; "
            "the position is probably outside the NLGEO2018 grid extent."
        )
    if nap_height == ellipsoidal_height:
        raise SystemExit(
            "NAP height equals the input ellipsoidal height, so no vertical "
            "transformation was applied. The NLGEO2018 grid was not used."
        )
    return nap_height, ellipsoidal_height - nap_height


def gp2_heights_to_nap_in_place(
    path: Path, transformer: Transformer | None = None
) -> dict[str, int]:
    """Rewrite the GGA heights of one .gp2 file from ellipsoidal to NAP.

    The GGA sentence carries the height as altitude above mean sea level (field 9)
    plus the geoid separation the receiver used (field 11); their sum is the
    ellipsoidal height. Both fields are rewritten - field 9 to the NAP height and
    field 11 to the NLGEO2018 separation - so their sum still is the ellipsoidal
    height and re-running this does not subtract the geoid twice.

    Files whose GGA sentences carry no geoid separation are skipped, because then
    the recorded height is not ellipsoidal and the conversion would be wrong.
    """
    transformer = transformer or build_transformer()
    stats = {"converted": 0, "missing_geoid_sep": 0, "outside_grid": 0}

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    header_index = find_data_header(lines)
    if header_index is None:
        return stats

    header, _ = parse_csv_line(lines[header_index])
    gps_index = find_column(header, "gps")
    if gps_index is None:
        return stats

    records = []
    for line_index in range(header_index + 1, len(lines)):
        if not lines[line_index].strip() or lines[line_index].lstrip().startswith(";"):
            continue
        try:
            row, newline = parse_csv_line(lines[line_index])
            gga = parse_gpgga(row[gps_index])
        except (IndexError, TypeError, ValueError):
            continue
        if gga.geoid_sep_m is None or math.isnan(gga.z_m):
            stats["missing_geoid_sep"] += 1
            continue
        records.append((line_index, row, newline, gga))

    if stats["missing_geoid_sep"]:
        log_warning(
            f"{path.name}: {stats['missing_geoid_sep']} GGA sentence(s) have no geoid "
            "separation, so their height is not ellipsoidal - file left unchanged."
        )
        return stats
    if not records:
        return stats

    nap_heights = transformer.transform(
        [record[3].longitude for record in records],
        [record[3].latitude for record in records],
        [record[3].z_m for record in records],
    )[2]

    for (line_index, row, newline, gga), nap_height in zip(
        records, nap_heights, strict=True
    ):
        if not math.isfinite(nap_height):
            stats["outside_grid"] += 1
            continue
        row[gps_index] = format_gpgga_with_checksum(
            gga, gga.latitude, gga.longitude, nap_height, gga.z_m - nap_height
        )
        lines[line_index] = format_csv_line(row, newline)
        stats["converted"] += 1

    if stats["outside_grid"]:
        log_warning(
            f"{path.name}: {stats['outside_grid']} position(s) fall outside the "
            "NLGEO2018 grid extent and kept their original height."
        )
    if stats["converted"]:
        path.write_text("".join(lines), encoding="utf-8")
    return stats


def gp2_heights_to_nap(paths: Iterable[Path]) -> None:
    """Convert the GGA heights of several .gp2 files to NAP, printing per-file stats."""
    ensure_grid()
    transformer = build_transformer()
    print(f"  Coordinate operation: {transformer.description}")
    for path in paths:
        stats = gp2_heights_to_nap_in_place(path, transformer)
        print(
            f"  {path.name}: {stats['converted']} height(s) converted to NAP, "
            f"{stats['outside_grid']} outside the grid, "
            f"{stats['missing_geoid_sep']} without geoid separation"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "latitude", nargs="?", type=float, default=TEST_CASE[0], help="ETRS89 latitude"
    )
    parser.add_argument(
        "longitude",
        nargs="?",
        type=float,
        default=TEST_CASE[1],
        help="ETRS89 longitude",
    )
    parser.add_argument(
        "ellipsoidal_height",
        nargs="?",
        type=float,
        default=TEST_CASE[2],
        help="ETRS89 ellipsoidal height in metres",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help=f"Download {GRID_NAME} if PROJ cannot find it",
    )
    args = parser.parse_args()

    grid_path = find_grid()
    if grid_path is None and args.download:
        download_grid()
        grid_path = find_grid()
    print_diagnostics(grid_path)
    if grid_path is None:
        raise SystemExit(
            f"Vertical grid {GRID_NAME} is missing. Re-run with --download, or "
            f"fetch {GRID_URL} manually into "
            f"{pyproj.datadir.get_user_data_dir()}."
        )

    nap_height, undulation = convert_to_nap(
        args.latitude, args.longitude, args.ellipsoidal_height
    )

    print("--- result ---")
    print(f"Latitude (ETRS89)     : {args.latitude:.4f}")
    print(f"Longitude (ETRS89)    : {args.longitude:.4f}")
    print(f"Ellipsoidal height    : {args.ellipsoidal_height:.4f} m")
    print(f"NAP height            : {nap_height:.4f} m")
    print(f"Geoid undulation used : {undulation:.4f} m")
    print(f"Ellipsoidal - NAP     : {args.ellipsoidal_height - nap_height:.4f} m")


if __name__ == "__main__":
    main()
