from __future__ import annotations

from pathlib import Path

from _gp2_common import choose_folder, copy_to_subfolder, find_gp2_files
from _gp2_offsets_core import (
    Offset,
    _make_projector,
    apply_offset,
    estimate_heading_series,
    format_gpgga_with_checksum,
    inverse_project_xy_to_latlon,
    parse_gpgga,
    parse_offset_line,
    process_gp2_in_place,
    project_latlon_to_xy,
)


def main() -> None:
    repo_dir = Path(__file__).resolve().parent
    source = choose_folder(
        title="Select data folder to offset-correct",
        fallback_dirs=(repo_dir / "example", repo_dir / "data"),
    )
    out = copy_to_subfolder(source, "offset corrected")

    gp2_files = find_gp2_files(out)
    if not gp2_files:
        raise SystemExit(f"No .gp2 files found in {out}")

    print(f"Copied to: {out}")
    print(f"Applying offsets to {len(gp2_files)} file(s)...")
    for p in gp2_files:
        process_gp2_in_place(p)
        print(f"  processed: {p.name}")
    print("Done")


if __name__ == "__main__":
    main()
