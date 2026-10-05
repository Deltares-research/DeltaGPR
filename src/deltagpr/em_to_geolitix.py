"""Convert layered Seequent EM XYZ models to binary Surfer grids for GeoLitix.

Export resistivity (RHO, ohm m) at every native layer midpoint by default,
or at --depth metres below local ground. Grid values are resistivity, not
elevation; depth is recorded in the filename, not as a third grid axis.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.interpolate import griddata
from scipy.spatial import Delaunay, QhullError, cKDTree

from deltagpr.ahn_to_geolitix import (
    GRID_FORMATS,
    write_surfer6_binary,
    write_surfer7_binary,
)


@dataclass
class EMModel:
    points: np.ndarray
    resistivity: np.ndarray
    tops: np.ndarray
    bottoms: np.ndarray
    doi: dict[str, np.ndarray]


def read_em_xyz(xyz_file: str | Path) -> EMModel:
    """Read slash-prefixed column headers and whitespace-separated soundings."""
    xyz_file = Path(xyz_file)
    with xyz_file.open(encoding="utf-8-sig") as handle:
        for line in handle:
            names = line.lstrip().removeprefix("/").upper().split()
            if {"X", "Y", "RHO_1"}.issubset(names):
                break
        else:
            raise ValueError(f"{xyz_file.name}: no X/Y/RHO column header found")
        data = np.genfromtxt(
            handle, comments="/", missing_values="*", filling_values=np.nan,
            ndmin=2,
        )
    if not data.size or data.shape[1] != len(names):
        raise ValueError(f"{xyz_file.name}: empty data or incorrect column count")
    if len(set(names)) != len(names):
        raise ValueError(f"{xyz_file.name}: duplicate column names")
    layers = sorted(
        int(name[4:]) for name in names if re.fullmatch(r"RHO_\d+", name)
    )
    if layers != list(range(1, len(layers) + 1)):
        raise ValueError(f"{xyz_file.name}: RHO layers must be consecutive from 1")

    def columns(column_names: list[str]) -> np.ndarray:
        missing = set(column_names) - set(names)
        if missing:
            raise ValueError(f"{xyz_file.name}: missing columns {sorted(missing)}")
        return data[:, [names.index(name) for name in column_names]]

    points = columns(["X", "Y"])
    resistivity = columns([f"RHO_{layer}" for layer in layers])
    tops = columns([f"DEP_TOP_{layer}" for layer in layers])
    bottoms = columns([f"DEP_BOT_{layer}" for layer in layers])
    if not np.isfinite(points).all():
        raise ValueError(f"{xyz_file.name}: X/Y coordinates must be finite")
    if (
        not np.isfinite(tops).all() or not np.isfinite(bottoms).all()
        or np.any(tops < 0) or np.any(bottoms <= tops)
        or np.any(tops[:, 1:] < bottoms[:, :-1])
    ):
        raise ValueError(f"{xyz_file.name}: invalid or overlapping layer depths")
    resistivity[~np.isfinite(resistivity) | (resistivity <= 0)] = np.nan
    doi = {
        kind: columns([f"DOI_{kind.upper()}"])[:, 0]
        for kind in ("standard", "conservative")
        if f"DOI_{kind.upper()}" in names
    }
    return EMModel(points, resistivity, tops, bottoms, doi)


def values_at_depth(
    model: EMModel, depth: float, doi: str = "none",
) -> np.ndarray:
    """Select each sounding's containing layer, without vertical interpolation."""
    if not np.isfinite(depth) or depth < 0:
        raise ValueError("depth must be finite and non-negative")
    selected = (model.tops <= depth) & (depth < model.bottoms)
    selected[:, -1] |= depth == model.bottoms[:, -1]
    values = np.full(model.points.shape[0], np.nan)
    rows, layers = np.nonzero(selected)
    values[rows] = model.resistivity[rows, layers]
    if doi != "none":
        if doi not in model.doi:
            raise ValueError(f"No DOI_{doi.upper()} column available")
        limit = model.doi[doi]
        values[~np.isfinite(limit) | (depth > limit)] = np.nan
    return values


def grid_em_slice(
    points: np.ndarray, values: np.ndarray, cell_size: float = 0.5,
    method: str = "linear", max_distance: float | None = None,
) -> tuple[np.ndarray, float, float, float, float]:
    """Interpolate to south-to-north nodes; blank outside hull or distance limit.

    Duplicate locations are averaged. Missing values remain missing rather
    than being removed before linear triangulation. Collinear surveys require
    nearest-neighbour gridding and are limited by distance to the track.
    """
    if not np.isfinite(cell_size) or cell_size <= 0:
        raise ValueError("cell_size must be finite and positive")
    if method not in ("linear", "nearest"):
        raise ValueError("method must be linear or nearest")
    max_distance = 2 * cell_size if max_distance is None else max_distance
    if not np.isfinite(max_distance) or max_distance <= 0:
        raise ValueError("max_distance must be finite and positive")
    points, inverse = np.unique(points, axis=0, return_inverse=True)
    finite = np.isfinite(values)
    counts = np.bincount(inverse[finite], minlength=len(points))
    totals = np.bincount(
        inverse[finite], weights=values[finite], minlength=len(points),
    )
    values = np.divide(
        totals, counts, out=np.full(len(points), np.nan), where=counts > 0,
    )
    minimum, maximum = points.min(axis=0), points.max(axis=0)
    shape = np.maximum(2, np.ceil((maximum - minimum) / cell_size) + 1)
    if np.prod(shape) > 2_000_000:
        raise ValueError("Grid exceeds 2 million nodes; increase --cell-size")
    x_nodes = minimum[0] + np.arange(int(shape[0])) * cell_size
    y_nodes = minimum[1] + np.arange(int(shape[1])) * cell_size
    x_grid, y_grid = np.meshgrid(x_nodes, y_nodes)
    targets = np.column_stack((x_grid.ravel(), y_grid.ravel()))
    try:
        hull = Delaunay(points)
    except QhullError as error:
        if method == "linear":
            raise ValueError(
                "Linear gridding needs non-collinear X/Y points; use --method nearest"
            ) from error
        hull = None
    if not np.isfinite(values).any():
        grid = np.full(x_grid.shape, np.nan)
    else:
        grid = griddata(points, values, targets, method=method)
        distances = cKDTree(points).query(targets)[0]
        grid[distances > max_distance] = np.nan
        if hull is not None:
            grid[hull.find_simplex(targets) < 0] = np.nan
        grid = grid.reshape(x_grid.shape)
    return (
        grid, float(x_nodes[0]), float(x_nodes[-1]),
        float(y_nodes[0]), float(y_nodes[-1]),
    )


def em_xyzs_to_grd(
    input_path: str | Path, depth: float | None = None,
    cell_size: float = 0.5, grid_format: str = "surfer7",
    method: str = "linear", max_distance: float | None = None,
    doi: str = "none", output_dir: str | Path | None = None,
    overwrite: bool = False, recursive: bool = False,
    name_contains: str | None = None,
) -> list[Path]:
    """Export one XYZ or matching XYZs in a folder, skipping existing outputs.

    ``recursive`` searches subfolders; ``name_contains`` filters filenames
    case-insensitively, following the AHN converter's folder-search convention.
    """
    if grid_format not in GRID_FORMATS:
        raise ValueError(f"grid_format must be one of {GRID_FORMATS}")
    if doi not in ("none", "standard", "conservative"):
        raise ValueError("doi must be none, standard or conservative")
    input_path = Path(input_path)
    if input_path.is_dir():
        candidates = input_path.rglob("*") if recursive else input_path.iterdir()
        files = sorted(
            path for path in candidates
            if path.is_file() and path.suffix.lower() == ".xyz"
            and (name_contains is None or name_contains.lower() in path.name.lower())
        )
    else:
        files = [input_path]
    if not files or any(not path.is_file() for path in files):
        raise ValueError(f"No XYZ files found at {input_path}")
    writer = write_surfer7_binary if grid_format == "surfer7" else write_surfer6_binary
    written = []
    for xyz_file in files:
        model = read_em_xyz(xyz_file)
        if depth is None:
            if not (
                np.allclose(model.tops, model.tops[0], rtol=0, atol=1e-8)
                and np.allclose(model.bottoms, model.bottoms[0], rtol=0, atol=1e-8)
            ):
                raise ValueError(
                    f"{xyz_file.name}: layer depths vary; select a slice with --depth"
                )
            slices = [
                (float((top + bottom) / 2),
                 f"layer{index:02d}_{top:g}-{bottom:g}m")
                for index, (top, bottom) in enumerate(
                    zip(model.tops[0], model.bottoms[0]), start=1,
                )
            ]
        else:
            values = values_at_depth(model, depth)
            if not np.isfinite(values).any():
                raise ValueError(
                    f"{xyz_file.name}: no valid model values at {depth:g} m"
                )
            slices = [(depth, f"depth{depth:g}m")]
        destination = Path(output_dir) if output_dir is not None else xyz_file.parent
        destination.mkdir(parents=True, exist_ok=True)
        for slice_depth, label in slices:
            mask_label = "" if doi == "none" else f"_doi-{doi}"
            grd_file = destination / f"{xyz_file.stem}_rho_{label}{mask_label}.grd"
            if grd_file.exists() and not overwrite:
                print(f"{grd_file.name} already exists, skipped")
                continue
            values = values_at_depth(model, slice_depth, doi)
            grid, x_min, x_max, y_min, y_max = grid_em_slice(
                model.points, values, cell_size, method, max_distance,
            )
            if not np.isfinite(grid).any():
                print(f"Warning: {grd_file.name} contains only blank nodes")
            writer(grd_file, grid, x_min, x_max, y_min, y_max)
            print(f"{xyz_file.name} -> {grd_file.name}")
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
            parent=root, title="Select folder with EM XYZ files",
        )
    finally:
        root.destroy()
    if not selected:
        raise SystemExit("No folder selected")
    return Path(selected)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_path", nargs="?", type=Path,
                        help="XYZ file or folder (folder picker if omitted)")
    parser.add_argument("--depth", type=float,
                        help="Depth in metres below ground (default: all layers)")
    parser.add_argument("--cell-size", type=float, default=0.5,
                        help="Grid node spacing in coordinate units (default: 0.5)")
    parser.add_argument("-f", "--format", dest="grid_format",
                        choices=GRID_FORMATS, default="surfer7")
    parser.add_argument("--method", choices=("linear", "nearest"), default="linear")
    parser.add_argument("--max-distance", type=float,
                        help="Blank beyond this distance from a sounding "
                        "(default: twice cell size)")
    parser.add_argument("--doi", choices=("none", "standard", "conservative"),
                        default="none", help="Optional DOI mask (default: none)")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--recursive", action="store_true",
                        help="Search subfolders for XYZ files")
    parser.add_argument("--name-contains",
                        help="Filter filenames by this text, case-insensitively")
    args = parser.parse_args()
    args.input_path = args.input_path or _prompt_for_input_dir()
    try:
        written = em_xyzs_to_grd(**vars(args))
    except ValueError as error:
        parser.error(str(error))
    print(f"Wrote {len(written)} .grd file(s)")


if __name__ == "__main__":
    main()
