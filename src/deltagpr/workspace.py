from __future__ import annotations

import re
import shutil
import zipfile
from collections.abc import Iterable
from pathlib import Path

from .warnings_log import log_warning


def prepare_from_gpz(gpz_file: str | Path, output_dir: str | Path) -> Path:
    """Unpack an Ekko_Project .gpz export and flatten its lines into one folder.

    A raw .gpz export is a plain zip archive containing a ``Lineset`` folder with
    the line files either directly inside it or in one subfolder per survey line.
    Some exports are instead already split into category folders (e.g. one per
    antenna) by the proprietary software before being exported - these have no
    ``Lineset`` folder, and a warning is printed when that's detected. Either way,
    this extracts the archive next to itself, then copies every line file found
    (at any depth) into ``output_dir``, so the result contains only .dt1/.hd/.gp2
    files. The extracted archive folder is removed afterwards.

    Parameters
    ----------
    gpz_file : path-like
        Path to the .gpz archive.
    output_dir : path-like
        Folder to copy the flattened line files into. Created if missing.

    Returns
    -------
    pathlib.Path
        ``output_dir``, containing the flattened line files.
    """
    gpz_file = Path(gpz_file)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    extract_dir = gpz_file.parent / gpz_file.stem
    with zipfile.ZipFile(gpz_file) as archive:
        archive.extractall(extract_dir)

    lineset_dir = next(
        (path for path in extract_dir.rglob("*") if path.is_dir() and path.name.lower() == "lineset"),
        None,
    )
    if lineset_dir is not None:
        source_dirs = [lineset_dir]
    else:
        category_dirs = [path for path in extract_dir.iterdir() if path.is_dir()]
        log_warning(
            f"{gpz_file.name} has no 'Lineset' folder, so it is NOT a raw export from the GPR "
            "equipment - it looks like it was already opened and sorted into categories "
            f"({', '.join(sorted(d.name for d in category_dirs))}) by the proprietary software."
        )
        source_dirs = category_dirs

    for source_dir in source_dirs:
        for file in source_dir.rglob("*"):
            if file.is_file():
                shutil.copy2(file, output_dir / file.name)

    shutil.rmtree(extract_dir)

    return output_dir


def sort_gp2_by_channel(deltagpr_dir: str | Path, gp2_files: Iterable[Path]) -> None:
    """Move each line's files into a chN subfolder, based on the channel in its file name.

    Exports that were already split into categories before flattening (see
    ``prepare_from_gpz``) can be re-grouped afterwards using the "-chN" suffix in
    each file name, since that channel number is a stable stand-in for whatever
    category (antenna, frequency, ...) the proprietary software originally used.
    """
    deltagpr_dir = Path(deltagpr_dir)
    for gp2_file in gp2_files:
        match = re.search(r"-ch(\d+)$", gp2_file.stem, re.IGNORECASE)
        if match is None:
            print(f"  Warning: no channel found in name for {gp2_file.name}, skipping")
            continue
        target_dir = deltagpr_dir / f"ch{match.group(1)}"
        target_dir.mkdir(exist_ok=True)
        for file in deltagpr_dir.glob(f"{gp2_file.stem}.*"):
            shutil.move(str(file), target_dir / file.name)
