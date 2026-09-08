from __future__ import annotations

import shutil
import zipfile
from pathlib import Path


def prepare_from_gpz(gpz_file: str | Path, output_dir: str | Path) -> Path:
    """Unpack an Ekko_Project .gpz export and flatten its Lineset into one folder.

    A .gpz file is a plain zip archive containing a ``Lineset`` folder with one
    subfolder per survey line. This extracts the archive next to itself, then
    copies the files from within each Lineset subfolder (not the subfolders
    themselves) into ``output_dir``, so the result contains only .dt1/.hd/.gp2
    files.

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
        path for path in extract_dir.rglob("*") if path.is_dir() and path.name.lower() == "lineset"
    )
    for subfolder in lineset_dir.iterdir():
        if subfolder.is_dir():
            for file in subfolder.iterdir():
                if file.is_file():
                    shutil.copy2(file, output_dir / file.name)

    return output_dir
