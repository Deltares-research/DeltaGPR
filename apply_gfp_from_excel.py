from __future__ import annotations

import argparse
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd


def load_excel_table(xlsx_path: Path) -> dict[str, dict[str, float | bool]]:
    df = pd.read_excel(xlsx_path)
    cols = {str(c).lower(): c for c in df.columns}
    required = ["linename", "x_start", "y_start", "x_end", "y_end"]
    missing = [c for c in required if c not in cols]
    if missing:
        raise ValueError(
            f"Excel missing required columns: {missing}. Present: {list(df.columns)}"
        )

    reverse_col = next(
        (c for c in ["reverse", "flip", "direction_flip"] if c in cols), None
    )
    out: dict[str, dict[str, float | bool]] = {}

    for _, row in df.iterrows():
        name = row[cols["linename"]]
        if pd.isna(name):
            continue
        name = str(name).strip()

        reverse = False
        if reverse_col is not None:
            val = row[cols[reverse_col]]
            if isinstance(val, str):
                reverse = val.strip().lower() in {"1", "true", "yes", "y", "t"}
            elif pd.notna(val):
                try:
                    reverse = bool(int(val))
                except Exception:
                    reverse = bool(val)

        out[name] = {
            "x0": float(row[cols["x_start"]]),
            "y0": float(row[cols["y_start"]]),
            "x1": float(row[cols["x_end"]]),
            "y1": float(row[cols["y_end"]]),
            "reverse": reverse,
        }
    return out


def update_line_geometry(
    line_elem: ET.Element, x0: float, y0: float, x1: float, y1: float
) -> tuple[bool, str]:
    data_file = line_elem.find("./DataFile") or line_elem.find(".//DataFile")
    if data_file is None:
        return False, "No DataFile node"

    pos0 = pos1 = None
    for pos in data_file.findall("./Position"):
        npos = pos.attrib.get("normalized_file_pos")
        if npos == "0":
            pos0 = pos
        elif npos == "1":
            pos1 = pos
    if pos0 is None or pos1 is None:
        return False, "Missing Position nodes"

    pos0.set("X", f"{x0:.6f}")
    pos0.set("Y", f"{y0:.6f}")
    pos1.set("X", f"{x1:.6f}")
    pos1.set("Y", f"{y1:.6f}")

    length = math.hypot(x1 - x0, y1 - y0)
    ntraces = None

    dsc = data_file.find("./DataSampleCnt")
    if dsc is not None:
        dim2 = dsc.attrib.get("dim2")
        if dim2 and dim2 != "NA":
            try:
                ntraces = int(dim2)
            except Exception:
                ntraces = None

    odom = data_file.find("./Odometer")
    odom_start = 0.0
    if odom is not None:
        try:
            odom_start = float(odom.attrib.get("start", "0"))
        except Exception:
            odom_start = 0.0

    step = None
    if ntraces and ntraces > 1:
        step = length / (ntraces - 1)
    elif odom is not None and "step" in odom.attrib:
        try:
            step = float(odom.attrib["step"])
        except Exception:
            step = None
    if step is None:
        step = length

    if odom is not None:
        odom.set("end", f"{odom_start + length:.6f}")
        odom.set("step", f"{step:.6f}")

    for settings in list(data_file.findall("./Settings")) + list(
        line_elem.findall("./Settings")
    ):
        step_size = settings.find("./StepSize")
        if step_size is not None:
            step_size.text = f"{step:.6f}"

    if "X" in line_elem.attrib and "Y" in line_elem.attrib:
        line_elem.set("X", f"{x0:.6f}")
        line_elem.set("Y", f"{y0:.6f}")

    return True, f"length={length:.3f} m, step={step:.6f} m"


def apply_updates(
    gfp_path: Path, xlsx_path: Path, out_path: Path | None
) -> tuple[list[tuple[str, bool, str]], list[str], Path]:
    tree = ET.parse(gfp_path)
    root = tree.getroot()

    excel = load_excel_table(xlsx_path)
    lines = {
        line.attrib.get("name"): line
        for line in root.findall(".//Line")
        if line.attrib.get("name")
    }

    report: list[tuple[str, bool, str]] = []
    missing: list[str] = []

    for name, rec in excel.items():
        line = lines.get(name)
        if line is None:
            missing.append(name)
            continue

        x0, y0, x1, y1 = rec["x0"], rec["y0"], rec["x1"], rec["y1"]
        if bool(rec["reverse"]):
            x0, y0, x1, y1 = x1, y1, x0, y0

        ok, msg = update_line_geometry(line, x0, y0, x1, y1)
        report.append((name, ok, msg))

    out = out_path or gfp_path.with_suffix(".updated.xml")
    tree.write(out, encoding="utf-8", xml_declaration=True)
    return report, missing, out


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Apply line geometry updates to Sensors & Software GFP XML from Excel"
        )
    )
    parser.add_argument(
        "--gfp", default="water_soil_flume.xml", help="Path to .gfp/.xml file"
    )
    parser.add_argument(
        "--excel", default="gfp_lines_template.xlsx", help="Path to Excel table"
    )
    parser.add_argument(
        "--out", default="", help="Output XML path (default: <gfp>.updated.xml)"
    )
    args = parser.parse_args()

    report, missing, out = apply_updates(
        gfp_path=Path(args.gfp),
        xlsx_path=Path(args.excel),
        out_path=Path(args.out) if args.out else None,
    )

    print(f"Updated {len(report)} lines. Missing in GFP: {len(missing)}. Output: {out}")
    if missing:
        print("Missing lines:", ", ".join(missing))
    for name, ok, msg in report[:20]:
        print(f"{name}: {'OK' if ok else 'FAIL'} - {msg}")


if __name__ == "__main__":
    main()
