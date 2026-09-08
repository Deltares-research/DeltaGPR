from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

import geopandas as gpd
from pyproj import CRS
from shapely.geometry import LineString

from .gp2 import find_column, find_data_header, list_gp2_files, parse_csv_line, parse_gpgga


def _read_coordinates(path: Path) -> list[tuple[float, float]]:
    rows = path.read_text(encoding="utf-8", errors="replace").splitlines()
    header_index = find_data_header(rows)
    if header_index is None:
        return []

    header, _ = parse_csv_line(rows[header_index])
    gps_index = find_column(header, "gps")
    if gps_index is None:
        return []

    coordinates = []
    for line in rows[header_index + 1 :]:
        if not line.strip() or line.lstrip().startswith(";"):
            continue
        try:
            row, _ = parse_csv_line(line)
            gga = parse_gpgga(row[gps_index])
            coordinates.append((gga.longitude, gga.latitude))
        except (IndexError, TypeError, ValueError):
            continue
    return coordinates


def _default_output_path(files: list[Path], output_crs: object) -> Path:
    first_name = files[0].stem
    file_range = first_name if len(files) == 1 else f"{first_name}_to_{files[-1].stem}"
    crs = CRS.from_user_input(output_crs)
    epsg = crs.to_epsg()
    crs_name = f"EPSG{epsg}" if epsg else re.sub(r"\W+", "_", crs.name).strip("_")
    return files[0].parent / "shapefile" / f"{file_range}_{crs_name}.shp"


def _prompt_for_files_and_crs() -> tuple[tuple[str, ...], str]:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askopenfilenames(
            parent=root,
            title="Select GP2 files to export as tracklines",
            filetypes=(("GP2 files", "*.gp2 *.GP2"), ("All files", "*.*")),
        )
        if not selected:
            raise SystemExit("Trackline export cancelled")

        while True:
            output_crs = simpledialog.askstring(
                "Output CRS",
                "Enter an EPSG code or CRS (for example 28992):",
                initialvalue="28992",
                parent=root,
            )
            if output_crs is None:
                raise SystemExit("Trackline export cancelled")
            try:
                CRS.from_user_input(output_crs)
            except Exception:
                messagebox.showerror(
                    "Invalid CRS", "Enter a valid EPSG code or CRS.", parent=root
                )
            else:
                return selected, output_crs
    finally:
        root.destroy()


def tracklines_to_shape(
    gp2_files: str | Path | Iterable[str | Path] | None = None,
    output_path: str | Path | None = None,
    output_crs: object = "EPSG:4326",
) -> Path:
    """Write one GP2 navigation trackline per file to an ESRI shapefile.

    GP2 GPS coordinates are interpreted as WGS 84 longitude and latitude. Directories
    are searched recursively for files with a case-insensitive ``.gp2`` suffix.

    Parameters
    ----------
    gp2_files : path-like or iterable of path-like, optional
        A GP2 file, directory containing GP2 files, or iterable of GP2 files. When
        omitted, a file-selection dialog opens and the output CRS is requested.
    output_path : path-like, optional
        Output shapefile path. When omitted, a descriptive filename is created in a
        ``shapefile`` subfolder beside the first input file.
    output_crs : CRS-like, default "EPSG:4326"
        Output coordinate reference system accepted by :class:`pyproj.CRS`.

    Returns
    -------
    pathlib.Path
        Path to the written shapefile.
    """
    if gp2_files is None:
        gp2_files, output_crs = _prompt_for_files_and_crs()

    files = list_gp2_files(gp2_files)
    if not files:
        raise ValueError("No GP2 files found")

    records = []
    for path in files:
        coordinates = _read_coordinates(path)
        if len(coordinates) < 2:
            raise ValueError(f"{path} contains fewer than two valid GPS coordinates")
        records.append(
            {
                "linename": path.stem,
                "filename": path.name,
                "n_points": len(coordinates),
                "geometry": LineString(coordinates),
            }
        )

    destination = (
        Path(output_path)
        if output_path is not None
        else _default_output_path(files, output_crs)
    )
    if not destination.suffix:
        destination = destination.with_suffix(".shp")
    elif destination.suffix.lower() != ".shp":
        raise ValueError("output_path must have a .shp suffix")
    destination.parent.mkdir(parents=True, exist_ok=True)

    output_crs = CRS.from_user_input(output_crs)
    tracklines = gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
    if output_crs != tracklines.crs:
        tracklines = tracklines.to_crs(output_crs)
    tracklines.to_file(destination, driver="ESRI Shapefile", index=False)
    return destination


def main() -> None:
    destination = tracklines_to_shape()
    print(f"Trackline shapefile created: {destination}")


if __name__ == "__main__":
    main()
