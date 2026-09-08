from __future__ import annotations

import tkinter as tk
from collections.abc import Iterable
from pathlib import Path
from tkinter import messagebox

from .dialogs import choose_gp2_files, copy_selected_to_subfolder
from .gp2 import find_data_header, find_header_value, update_existing_header


def prompt_header_values() -> tuple[str | None, str | None, str | None, str | None]:
    root = tk.Tk()
    root.title("Edit GP2 Headers")
    root.attributes("-topmost", True)
    root.resizable(False, False)

    fields = ["X offset", "Y offset", "Z offset", "Latency"]

    entries: list[tk.Entry] = []
    for i, label in enumerate(fields):
        tk.Label(root, text=label, anchor="w", width=12).grid(
            row=i, column=0, padx=8, pady=5, sticky="w"
        )
        e = tk.Entry(root, width=18)
        e.grid(row=i, column=1, padx=8, pady=5)
        entries.append(e)

    tk.Label(
        root,
        text="Leave a field blank to keep its existing value unchanged.",
        anchor="w",
        fg="gray",
    ).grid(row=len(fields), column=0, columnspan=2, padx=8, sticky="w")

    result: dict[str, tuple[str | None, str | None, str | None, str | None] | None] = {
        "values": None
    }

    def on_ok() -> None:
        vals = [e.get().strip() or None for e in entries]
        try:
            for val in vals:
                if val is not None:
                    float(val)
        except ValueError:
            messagebox.showerror(
                "Invalid value",
                "Please enter numeric values, or leave a field blank.",
                parent=root,
            )
            return
        result["values"] = (vals[0], vals[1], vals[2], vals[3])
        root.destroy()

    def on_cancel() -> None:
        root.destroy()

    btn_frame = tk.Frame(root)
    btn_frame.grid(row=len(fields) + 1, column=0, columnspan=2, pady=(6, 10))
    tk.Button(btn_frame, text="OK", width=10, command=on_ok).pack(side="left", padx=6)
    tk.Button(btn_frame, text="Cancel", width=10, command=on_cancel).pack(
        side="left", padx=6
    )

    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.mainloop()

    if result["values"] is None:
        raise SystemExit("Header edit cancelled")
    return result["values"]


def edit_gp2_headers_in_place(
    path: Path,
    x_off: str | None,
    y_off: str | None,
    z_off: str | None,
    latency: str | None,
) -> tuple[bool, bool]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    if not lines:
        return False, False

    nl = "\r\n" if any(line.endswith("\r\n") for line in lines[:10]) else "\n"
    data_header_idx = find_data_header(lines)
    if data_header_idx is None:
        data_header_idx = len(lines)

    offset_updated = False
    if x_off is not None or y_off is not None or z_off is not None:
        existing_offset = find_header_value(lines, ["Offset_m"], data_header_idx)
        existing_parts = existing_offset.split(",") if existing_offset else []
        existing_parts += [None] * (3 - len(existing_parts))
        resolved = [
            new if new is not None else existing
            for new, existing in zip((x_off, y_off, z_off), existing_parts)
        ]
        if all(part is not None for part in resolved):
            offset_updated = update_existing_header(
                lines, ["Offset_m"], ",".join(resolved), data_header_idx, nl
            )

    latency_updated = False
    if latency is not None:
        latency_updated = update_existing_header(
            lines, ["Latency_s", "Latency"], latency, data_header_idx, nl
        )

    path.write_text("".join(lines), encoding="utf-8")
    return offset_updated, latency_updated


def edit_gp2_headers(
    paths: Iterable[Path],
    x_off: str | None,
    y_off: str | None,
    z_off: str | None,
    latency: str | None,
) -> None:
    """Edit GP2 headers in place for multiple files and print a one-line summary."""
    paths = list(paths)
    offset_desc = ",".join(v if v is not None else "unchanged" for v in (x_off, y_off, z_off))
    latency_desc = latency if latency is not None else "unchanged"
    print(f"  Offset_m={offset_desc} | Latency={latency_desc}")

    missing_offset = 0
    missing_latency = 0
    for path in paths:
        has_offset, has_latency = edit_gp2_headers_in_place(path, x_off, y_off, z_off, latency)
        if (x_off is not None or y_off is not None or z_off is not None) and not has_offset:
            missing_offset += 1
        if latency is not None and not has_latency:
            missing_latency += 1

    if latency is not None:
        print(f"  Latency updated in {len(paths) - missing_latency}/{len(paths)} files")
    if x_off is not None or y_off is not None or z_off is not None:
        print(f"  Offset_m updated in {len(paths) - missing_offset}/{len(paths)} files")


def main() -> None:
    selected = choose_gp2_files("Select GP2 files to edit")
    x_off, y_off, z_off, latency = prompt_header_values()

    if x_off is None and y_off is None and z_off is None and latency is None:
        print("No values entered, nothing to change")
        return

    gp2_files = copy_selected_to_subfolder(selected, "edit_headers")

    print(f"Copied {len(gp2_files)} selected file(s) to edit_headers folder(s)")
    edit_gp2_headers(gp2_files, x_off, y_off, z_off, latency)
    print("Done")


if __name__ == "__main__":
    main()

