# DeltaGPR

[![License: MIT](https://img.shields.io/pypi/l/imod)](https://choosealicense.com/licenses/mit)
[![Lifecycle: experimental](https://lifecycle.r-lib.org/articles/figures/lifecycle-experimental.svg)](https://lifecycle.r-lib.org/articles/stages.html)
[![Formatting: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

<img src="deltagpr_logo.png" alt="DeltaGPR Logo" width="100" align="left">

The Deltares Ground Penetrating Radar (DeltaGPR) package provides practical tooling to prepare GPR survey files. It focuses on a straightforward workflow for copying raw survey data into a working subfolder and applying consistent edits there, so original files remain untouched. Current utilities support GP2 header editing and GPS offset correction.

<br clear="left"/>

## Installation

The installation uses package manager pixi, for installation options see
https://pixi.sh/latest/

To install pixi on Windows, in PowerShell type:

```powershell
winget install prefix-dev.pixi
```

Now clone DeltaGPR to your local drive using:

```powershell
git clone https://github.com/Deltares-research/DeltaGPR.git
```

Then navigate into that folder with:

```powershell
cd DeltaGPR
```

To create the environment and install DeltaGPR in it, type:

```powershell
pixi run install
```

## Update DeltaGPR

To update DeltaGPR with the latest version from GitHub, open a shell in the DeltaGPR folder and run:

```powershell
git pull
pixi run install
```

## Usage

Example 1: Apply GPS offsets to GP2 data

```powershell
pixi run offsets
```

What happens:
- A folder dialog opens.
- The selected folder is copied to a subfolder named offset corrected.
- For each GP2 file, the `;Offset_m=` header value is applied to GPS coordinates in that same file.
- After applying the correction, `;Offset_m=` is reset to `0.00,0.00,0.00` in the copied file.
- This offset application outside of software is a temporary workaround for a known Ekko_Project v6 bug (currently being fixed): 

Example 2: Edit GP2 header values

```powershell
pixi run edit_headers
```

What happens:
- A folder dialog opens.
- The selected folder is copied to a subfolder named edit_headers.
- A small form asks for X/Y/Z offset and latency values.
- Existing header lines are updated in place in GP2 files in the copied folder.

When to use this after `pixi run offsets`:
- You only need `pixi run edit_headers` if you want to set new header values (for example, a different planned `Offset_m` or latency) for later processing.
- You do not need it just to zero offsets after `pixi run offsets`; that already happens automatically.

Example 3: Export GP2 navigation as tracklines

```powershell
pixi run tracklines
```

A file dialog opens to select one or more GP2 files, followed by an output CRS
prompt. The shapefile is written to a `shapefile` subfolder with the selected file
range and CRS in its name, for example
`Line4-ch2_to_Line6-ch6_EPSG28992.shp`.

The same functionality can be called from Python:

```python
from deltagpr.tools import tracklines_to_shape

tracklines_to_shape("data", output_crs=28992)
```

Each GP2 file becomes one line feature. GP2 coordinates are read as WGS 84 and
can be transformed to any CRS understood by `pyproj`, such as Dutch RD New above.

## License

MIT License. See [LICENSE](LICENSE).
