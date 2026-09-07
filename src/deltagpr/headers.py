from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from .dialogs import choose_gp2_files, copy_selected_to_subfolder
from .gp2 import find_data_header, update_existing_header


def prompt_header_values() -> tuple[str, str, str, str]:
    root = tk.Tk()
    root.title("Edit GP2 Headers")
    root.attributes("-topmost", True)
    root.resizable(False, False)

    fields = [
        ("X offset", "0.00"),
        ("Y offset", "0.00"),
        ("Z offset", "0.00"),
        ("Latency", "0.00"),
    ]

    entries: list[tk.Entry] = []
    for i, (label, default) in enumerate(fields):
        tk.Label(root, text=label, anchor="w", width=12).grid(
            row=i, column=0, padx=8, pady=5, sticky="w"
        )
        e = tk.Entry(root, width=18)
        e.insert(0, default)
        e.grid(row=i, column=1, padx=8, pady=5)
        entries.append(e)

    result: dict[str, tuple[str, str, str, str] | None] = {"values": None}

    def on_ok() -> None:
        vals = [e.get().strip() for e in entries]
        try:
            float(vals[0])
            float(vals[1])
            float(vals[2])
            float(vals[3])
        except ValueError:
            messagebox.showerror(
                "Invalid value",
                "Please enter numeric values for all fields.",
                parent=root,
            )
            return
        result["values"] = (vals[0], vals[1], vals[2], vals[3])
        root.destroy()

    def on_cancel() -> None:
        root.destroy()

    btn_frame = tk.Frame(root)
    btn_frame.grid(row=len(fields), column=0, columnspan=2, pady=(6, 10))
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
    path: Path, x_off: str, y_off: str, z_off: str, latency: str
) -> tuple[bool, bool]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    if not lines:
        return False, False

    nl = "\r\n" if any(line.endswith("\r\n") for line in lines[:10]) else "\n"
    data_header_idx = find_data_header(lines)
    if data_header_idx is None:
        data_header_idx = len(lines)

    offset_updated = update_existing_header(
        lines, ["Offset_m"], f"{x_off},{y_off},{z_off}", data_header_idx, nl
    )
    latency_updated = update_existing_header(
        lines, ["Latency_s", "Latency"], latency, data_header_idx, nl
    )

    path.write_text("".join(lines), encoding="utf-8")
    return offset_updated, latency_updated


def main() -> None:
    selected = choose_gp2_files("Select GP2 files to edit")
    x_off, y_off, z_off, latency = prompt_header_values()

    gp2_files = copy_selected_to_subfolder(selected, "edit_headers")

    print(f"Copied {len(gp2_files)} selected file(s) to edit_headers folder(s)")
    print(
        f"Applying header edits: Offset_m={x_off},{y_off},{z_off} | Latency={latency}"
    )

    missing_offset = 0
    missing_latency = 0
    for file_path in gp2_files:
        has_offset, has_latency = edit_gp2_headers_in_place(
            file_path, x_off, y_off, z_off, latency
        )
        if not has_offset:
            missing_offset += 1
        if not has_latency:
            missing_latency += 1
        print(f"  edited: {file_path.name}")

    if missing_offset:
        print(
            f"Warning: Offset_m header not found in {missing_offset} file(s), "
            "so it was not changed there."
        )
    if missing_latency:
        print(
            f"Warning: Latency_s/Latency header not found in {missing_latency} "
            "file(s), so it was not changed there."
        )

    print("Done")


if __name__ == "__main__":
    main()
