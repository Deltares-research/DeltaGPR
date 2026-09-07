from __future__ import annotations

import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog


def choose_gp2_files(title: str) -> list[Path]:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askopenfilenames(
            parent=root,
            title=title,
            filetypes=(("GP2 files", "*.gp2 *.GP2"), ("All files", "*.*")),
        )
    finally:
        root.destroy()

    files = [Path(path) for path in selected]
    if not files:
        raise SystemExit("No GP2 files selected")
    return files


def copy_selected_to_subfolder(files: list[Path], subfolder_name: str) -> list[Path]:
    copied = []
    for source in files:
        target_dir = source.parent / subfolder_name
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        shutil.copy2(source, target)
        copied.append(target)
    return copied
