"""Convert AHN GeoTIFF height rasters to Surfer binary .grd files for GeoLitix.

Reads every .tif/.tiff in a folder and writes ``<name>.grd`` next to each raster.
This is a one-time conversion: rasters whose .grd already exists are skipped.

GeoLitix only reads binary Surfer grids, so the default is Surfer 7 binary
("DSRB"); Surfer 6 binary ("DSBB") is available as a fallback.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

import numpy as np
import rasterio
import rasterio.windows

SURFER_BLANK = 1.70141e38
TIFF_SUFFIXES = {".tif", ".tiff"}
GRID_FORMATS = ("surfer7", "surfer6")


def list_tiff_files(input_dir: str | Path) -> list[Path]:
    """Return the GeoTIFF files directly inside ``input_dir``, sorted by name."""
    return sorted(
        path
        for path in Path(input_dir).iterdir()
        if path.is_file() and path.suffix.lower() in TIFF_SUFFIXES
    )


def read_ahn_tiff(
    tiff_file: Path,
    select_x_min: float | None = None,
    select_x_max: float | None = None,
    select_y_min: float | None = None,
    select_y_max: float | None = None,
) -> tuple[np.ndarray, float, float, float, float]:
    """Read band 1 as a south-to-north grid plus its node-centre bounds.

    If any of the ``select_*`` bounds are given, only the overlapping window
    is read from disk instead of the full raster.
    """
    with rasterio.open(tiff_file) as raster:
        transform = raster.transform
        window = None
        if None not in (select_x_min, select_x_max, select_y_min, select_y_max):
            window = rasterio.windows.from_bounds(
                select_x_min, select_y_min, select_x_max, select_y_max, transform
            ).round_lengths().round_offsets()
            transform = raster.window_transform(window)
        values = raster.read(1, window=window, masked=True).astype("float64")

    if transform.b or transform.d:
        raise ValueError(
            f"{tiff_file.name} is rotated; only north-up grids are supported"
        )

    grid = np.ma.filled(values, np.nan)
    # Surfer grids run south to north, GeoTIFF rows run north to south.
    if transform.e < 0:
        grid = grid[::-1, :]
    if transform.a < 0:
        grid = grid[:, ::-1]

    rows, cols = grid.shape
    x_size, y_size = abs(transform.a), abs(transform.e)
    x_min = min(transform.c, transform.c + transform.a * cols) + x_size / 2
    y_min = min(transform.f, transform.f + transform.e * rows) + y_size / 2
    x_max = x_min + (cols - 1) * x_size
    y_max = y_min + (rows - 1) * y_size
    return grid, x_min, x_max, y_min, y_max


def _z_range(grid: np.ndarray) -> tuple[float, float]:
    finite = grid[np.isfinite(grid)]
    if not finite.size:
        return 0.0, 0.0
    return float(finite.min()), float(finite.max())


def write_surfer7_binary(
    grd_file: Path,
    grid: np.ndarray,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
) -> None:
    """Write a south-to-north grid as a Surfer 7 binary (DSRB) .grd file."""
    rows, cols = grid.shape
    z_min, z_max = _z_range(grid)
    x_size = (x_max - x_min) / (cols - 1) if cols > 1 else 1.0
    y_size = (y_max - y_min) / (rows - 1) if rows > 1 else 1.0
    values = np.where(np.isfinite(grid), grid, SURFER_BLANK).astype("<f8")

    with grd_file.open("wb") as handle:
        handle.write(struct.pack("<4sll", b"DSRB", 4, 2))
        handle.write(struct.pack("<4sl", b"GRID", 72))
        handle.write(
            struct.pack(
                "<ll8d",
                rows,
                cols,
                x_min,
                y_min,
                x_size,
                y_size,
                z_min,
                z_max,
                0.0,
                SURFER_BLANK,
            )
        )
        handle.write(struct.pack("<4sl", b"DATA", values.nbytes))
        handle.write(values.tobytes())


def write_surfer6_binary(
    grd_file: Path,
    grid: np.ndarray,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
) -> None:
    """Write a south-to-north grid as a Surfer 6 binary (DSBB) .grd file."""
    rows, cols = grid.shape
    if rows > 32767 or cols > 32767:
        raise ValueError(
            f"{grd_file.name}: {cols}x{rows} exceeds the Surfer 6 limit; use surfer7"
        )
    z_min, z_max = _z_range(grid)
    values = np.where(np.isfinite(grid), grid, SURFER_BLANK).astype("<f4")

    with grd_file.open("wb") as handle:
        handle.write(struct.pack("<4shh6d", b"DSBB", cols, rows, x_min, x_max,
                                 y_min, y_max, z_min, z_max))
        handle.write(values.tobytes())


def ahn_tiffs_to_grd(
    input_dir: str | Path,
    grid_format: str = "surfer7",
    select_x_min: float | None = None,
    select_x_max: float | None = None,
    select_y_min: float | None = None,
    select_y_max: float | None = None,
) -> list[Path]:
    """Convert each GeoTIFF in ``input_dir`` to a .grd beside it, skipping existing.

    Parameters
    ----------
    input_dir : path-like
        Folder holding the AHN GeoTIFF files.
    grid_format : {'surfer7', 'surfer6'}
        Binary Surfer grid flavour to write. GeoLitix reads both; 'surfer6' is
        single precision and limited to 32767 rows/columns.
    select_x_min, select_x_max, select_y_min, select_y_max : float, optional
        Bounding box to crop each raster to before writing. Leave all as
        ``None`` to convert the full tile.

    Returns
    -------
    list[pathlib.Path]
        The .grd files written by this call (already existing ones are skipped).
    """
    if grid_format not in GRID_FORMATS:
        raise ValueError(f"grid_format must be one of {GRID_FORMATS}")
    writer = write_surfer7_binary if grid_format == "surfer7" else write_surfer6_binary

    input_dir = Path(input_dir)
    tiff_files = list_tiff_files(input_dir)
    if not tiff_files:
        raise SystemExit(f"No .tif/.tiff files found in {input_dir}")

    written = []
    for tiff_file in tiff_files:
        grd_file = tiff_file.with_suffix(".grd")
        if grd_file.exists():
            print(f"{grd_file.name} already exists, skipped")
            continue
        grid, x_min, x_max, y_min, y_max = read_ahn_tiff(
            tiff_file, select_x_min, select_x_max, select_y_min, select_y_max
        )
        writer(grd_file, grid, x_min, x_max, y_min, y_max)
        print(f"{tiff_file.name} -> {grd_file.name}")
        written.append(grd_file)
    return written


def _prompt_for_input_dir() -> Path:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(
            parent=root, title="Select folder with AHN GeoTIFF files"
        )
    finally:
        root.destroy()

    if not selected:
        raise SystemExit("No folder selected")
    return Path(selected)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input_dir",
        nargs="?",
        type=Path,
        help="Folder with AHN GeoTIFF files (a folder picker opens if omitted)",
    )
    parser.add_argument(
        "-f",
        "--format",
        dest="grid_format",
        choices=GRID_FORMATS,
        default="surfer7",
        help="Binary Surfer grid flavour to write (default: surfer7)",
    )
    parser.add_argument("--xmin", dest="select_x_min", type=float, default=None,
                        help="Crop to this minimum X (default: whole tile)")
    parser.add_argument("--xmax", dest="select_x_max", type=float, default=None,
                        help="Crop to this maximum X (default: whole tile)")
    parser.add_argument("--ymin", dest="select_y_min", type=float, default=None,
                        help="Crop to this minimum Y (default: whole tile)")
    parser.add_argument("--ymax", dest="select_y_max", type=float, default=None,
                        help="Crop to this maximum Y (default: whole tile)")
    args = parser.parse_args()

    input_dir = args.input_dir or _prompt_for_input_dir()
    if not input_dir.is_dir():
        raise SystemExit(f"Not a folder: {input_dir}")

    written = ahn_tiffs_to_grd(
        input_dir,
        args.grid_format,
        args.select_x_min,
        args.select_x_max,
        args.select_y_min,
        args.select_y_max,
    )
    print(f"Wrote {len(written)} .grd file(s)")


if __name__ == "__main__":
    main()
