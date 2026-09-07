# DeltaGPR

[![License: MIT](https://img.shields.io/pypi/l/imod)](https://choosealicense.com/licenses/mit)
[![Lifecycle: experimental](https://lifecycle.r-lib.org/articles/figures/lifecycle-experimental.svg)](https://lifecycle.r-lib.org/articles/stages.html)
[![Formatting: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

<img src="docs/assets/deltagpr_logo.png" alt="DeltaGPR Logo" width="100" align="left">

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
pixi run apply_offsets
```

What happens:
- A file dialog opens to select one or more GP2 files.
- Selected files are copied to an `offset_corrected` subfolder.
- For each selected file, the `;Offset_m=` header value is applied to GPS coordinates in that file.
- After applying the correction, `;Offset_m=` is reset to `0.00,0.00,0.00` in the copied file.
- This offset application outside of software is a temporary workaround for a known Ekko_Project v6 bug (currently being fixed): 

Example 2: Edit GP2 header values

```powershell
pixi run edit_headers
```

What happens:
- A file dialog opens to select one or more GP2 files.
- Selected files are copied to an `edit_headers` subfolder.
- A small form asks for X/Y/Z offset and latency values.
- Existing header lines are updated in place in GP2 files in the copied folder.

When to use this after `pixi run apply_offsets`:
- You only need `pixi run edit_headers` if you want to set new header values (for example, a different planned `Offset_m` or latency) for later processing.
- You do not need it just to zero offsets after `pixi run apply_offsets`; that already happens automatically.

Example 3: Clean repeated GP2 coordinates

```powershell
pixi run clean_coordinates
```

A file dialog opens to select one or more GP2 files. Selected files are copied
to a `clean_coordinates` subfolder. A second dialog offers three methods:

- `Inner endpoints` (default) uses the last position in a starting repeated-trace
	group and the first position in an ending group.
- `Outer endpoints` uses the first position in a starting group and the last
	position in an ending group.
- `Median` uses the median position for every repeated-trace group.

Both endpoint methods use the median for repeated-trace groups in the middle of
a line and when one group spans the whole file. Latitude, longitude, and
ellipsoidal height are cleaned together. Rows, timestamps, and other NMEA fields
are retained.

Example 4: Export GP2 navigation as tracklines

```powershell
pixi run tracklines
```

A file dialog opens to select one or more GP2 files, followed by an output CRS
prompt. The shapefile is written to a `shapefile` subfolder with the selected file
range and CRS in its name, for example
`Line4-ch2_to_Line6-ch6_EPSG28992.shp`.

The same functionality can be called from Python:

```python
from deltagpr import tracklines_to_shape

tracklines_to_shape("examples/gp2", output_crs=28992)
```

Each GP2 file becomes one line feature. GP2 coordinates are read as WGS 84 and
can be transformed to any CRS understood by `pyproj`, such as Dutch RD New above.

## Repository layout

- `src/deltagpr/` contains all installed library and command code.
- `tests/` contains the automated test suite.
- `examples/gp2/` contains original GP2 example inputs. Generated outputs are
	ignored and should not be committed.
- `optional/gfp_from_excel/` contains a separate experimental GFP/XML geometry
	utility and its example inputs.
- `docs/assets/` contains documentation images.

## Development

Run the complete test and lint checks with:

```powershell
pixi run test
pixi run lint
```

## License

MIT License. See [LICENSE](LICENSE).
