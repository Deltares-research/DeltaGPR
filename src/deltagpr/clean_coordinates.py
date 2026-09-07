from __future__ import annotations

import math
import statistics
import tkinter as tk
from pathlib import Path

from .dialogs import choose_gp2_files, copy_selected_to_subfolder
from .gp2 import (
    find_column,
    find_data_header,
    format_csv_line,
    format_gpgga_with_checksum,
    parse_csv_line,
    parse_gpgga,
)

METHOD_LABELS = {
    "inner_endpoints": "Inner endpoints",
    "outer_endpoints": "Outer endpoints",
    "median": "Median",
}
METHODS = tuple(METHOD_LABELS)


def prompt_cleaning_method() -> str:
    root = tk.Tk()
    root.title("Clean GP2 Coordinates")
    root.attributes("-topmost", True)
    root.resizable(False, False)

    selected = tk.StringVar(value="inner_endpoints")
    choices = [(label, value) for value, label in METHOD_LABELS.items()]
    for index, (label, value) in enumerate(choices):
        tk.Radiobutton(root, text=label, variable=selected, value=value).grid(
            row=index, column=0, padx=12, pady=4, sticky="w"
        )

    result = {"method": None}

    def confirm() -> None:
        result["method"] = selected.get()
        root.destroy()

    tk.Button(root, text="OK", width=10, command=confirm).grid(
        row=len(choices), column=0, padx=12, pady=10
    )
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()

    if result["method"] is None:
        raise SystemExit("Coordinate cleaning cancelled")
    return result["method"]


def clean_gp2_coordinates_in_place(
    path: Path, method: str = "inner_endpoints"
) -> int:
    """Replace repeated-trace coordinates with one representative position."""
    if method not in METHODS:
        raise ValueError(f"Unknown cleaning method: {method}")

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines(
        keepends=True
    )
    header_index = find_data_header(lines)
    if header_index is None:
        return 0

    header, _ = parse_csv_line(lines[header_index])
    trace_index = find_column(header, "traces")
    gps_index = find_column(header, "gps")
    if trace_index is None or gps_index is None:
        return 0

    records = []
    for line_index in range(header_index + 1, len(lines)):
        if not lines[line_index].strip() or lines[line_index].lstrip().startswith(";"):
            continue
        try:
            row, newline = parse_csv_line(lines[line_index])
            trace = row[trace_index]
            gga = parse_gpgga(row[gps_index])
        except (IndexError, TypeError, ValueError):
            records.append(None)
            continue
        records.append((line_index, row, newline, trace, gga))

    groups = []
    group = []
    for record in records:
        if record is None:
            if group:
                groups.append(group)
                group = []
        elif group and record[3] != group[-1][3]:
            groups.append(group)
            group = [record]
        else:
            group.append(record)
    if group:
        groups.append(group)

    cleaned_rows = 0
    for group_index, group in enumerate(groups):
        if len(group) < 2:
            continue

        use_median = (
            method == "median"
            or len(groups) == 1
            or 0 < group_index < len(groups) - 1
        )
        if use_median:
            latitude = statistics.median(record[4].latitude for record in group)
            longitude = statistics.median(record[4].longitude for record in group)
            heights = [record[4].z_m for record in group]
            height = statistics.median(
                value for value in heights if not math.isnan(value)
            )
        else:
            use_last = (method == "inner_endpoints") == (group_index == 0)
            representative = group[-1] if use_last else group[0]
            latitude = representative[4].latitude
            longitude = representative[4].longitude
            height = representative[4].z_m

        for line_index, row, newline, _, gga in group:
            altitude = (
                height - gga.geoid_sep_m
                if gga.geoid_sep_m is not None
                else height
            )
            row[gps_index] = format_gpgga_with_checksum(
                gga, latitude, longitude, altitude
            )
            lines[line_index] = format_csv_line(row, newline)
            cleaned_rows += 1

    path.write_text("".join(lines), encoding="utf-8")
    return cleaned_rows


def main() -> None:
    selected = choose_gp2_files("Select GP2 files to clean coordinates")
    method = prompt_cleaning_method()
    gp2_files = copy_selected_to_subfolder(selected, "clean_coordinates")

    print(
        f"Copied {len(gp2_files)} selected file(s) to clean_coordinates folder(s)"
    )
    print(f"Cleaning method: {METHOD_LABELS[method]}")
    for path in gp2_files:
        cleaned_rows = clean_gp2_coordinates_in_place(path, method)
        print(f"  cleaned: {path.name} ({cleaned_rows} grouped rows)")
    print("Done")


if __name__ == "__main__":
    main()
