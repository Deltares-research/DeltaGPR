from __future__ import annotations

import shutil
from pathlib import Path
import tkinter as tk
from tkinter import filedialog


def choose_folder(title: str, fallback_dirs: tuple[Path, ...] = ()) -> Path:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected = filedialog.askdirectory(title=title)
    root.destroy()

    if selected:
        return Path(selected)

    for fallback in fallback_dirs:
        if fallback.is_dir():
            print(f"No folder selected, using fallback: {fallback}")
            return fallback
    raise SystemExit("No folder selected")


def copy_to_subfolder(source: Path, subfolder_name: str) -> Path:
    target = source / subfolder_name
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    for item in source.iterdir():
        if item.name.lower() == subfolder_name.lower():
            continue
        dest = target / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    return target


def find_gp2_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".gp2")


def detect_data_header_idx(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        if not line.strip().startswith(";") and "gps" in line.lower():
            return i
    return len(lines)


def update_existing_header(lines: list[str], keys: list[str], value: str, data_header_idx: int, nl: str) -> bool:
    prefixes = [f";{key}=".lower() for key in keys]
    for i in range(data_header_idx):
        stripped = lines[i].strip()
        lowered = stripped.lower()
        if not any(lowered.startswith(prefix) for prefix in prefixes):
            continue
        existing_key = stripped.split("=", 1)[0]
        lines[i] = f"{existing_key}={value}{nl}"
        return True
    return False
