"""Generic GPR processing pipeline: unzip a .gpz export, process, and QC.

Used both as a library function (``run_gpz_file``) and as the entry point for the
``deltagpr_pipeline`` command.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deltagpr.clean_coordinates import clean_gp2_coordinates
from deltagpr.headers import edit_gp2_headers
from deltagpr.logging_utils import processing_log
from deltagpr.offsets import process_gp2
from deltagpr.tracklines import tracklines_to_shape
from deltagpr.warnings_log import print_warnings_summary
from deltagpr.workspace import (
    deltagpr_output_dir,
    prepare_from_gpz,
    sort_gp2_by_channel,
)


def run_gpz_file(gpz_file: str | Path, project_name: str | None = None) -> Path | None:
    """Run the full processing pipeline for a single .gpz export.

    Output is written to ``<gpz_file.parent>/<gpz_file.stem>_deltagpr``. If that
    folder already exists, processing is skipped (no overwriting) and ``None`` is
    returned. Otherwise returns the output folder path.
    """
    gpz_file = Path(gpz_file)
    project_name = project_name or gpz_file.stem
    output_dir = deltagpr_output_dir(gpz_file)

    if output_dir.exists():
        print(f"Skipping {gpz_file.name}: {output_dir.name} already exists")
        return None

    with processing_log(output_dir):
        output_dir, gp2_files = prepare_from_gpz(gpz_file, output_dir)

        def qc_tracklines(stage: str) -> None:
            tracklines_to_shape(
                output_dir,
                output_dir / "tracklines" / f"{project_name}_{stage}.shp",
            )

        qc_tracklines("00_raw")

        print("Editing headers (latency = 0.05 s)")
        edit_gp2_headers(gp2_files, None, None, None, "0.05")
        qc_tracklines("01_edit_headers")

        print("Cleaning coordinates")
        clean_gp2_coordinates(gp2_files)
        qc_tracklines("02_clean_coordinates")

        print("Applying offsets")
        process_gp2(gp2_files)
        qc_tracklines("03_apply_offsets")

        print("Sorting lines into channel subfolders")
        sort_gp2_by_channel(output_dir, gp2_files)

        print("Done")
        print_warnings_summary()

    return output_dir


def main() -> None:
    """Process every .gpz file in the active pipeline folder."""
    if getattr(sys, "frozen", False):
        folder = Path(sys.executable).resolve().parent
    else:
        folder = Path.cwd()

    gpz_files = sorted(folder.glob("*.gpz"))
    if not gpz_files:
        print(f"No .gpz files found in {folder}")
        return

    for gpz_file in gpz_files:
        print(f"\n=== Processing {gpz_file.name} ===")
        run_gpz_file(gpz_file)


if __name__ == "__main__":
    main()
