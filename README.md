# DeltaGPR

DeltaGPR is the generic toolbox for preparing and QC-ing GPR survey data. It handles GP2 header editing, GPS offset correction, coordinate cleaning, height conversion to NAP, and the generic `.gpz` processing pipeline.

## Setup

1. Install Pixi: https://pixi.sh/
2. Clone the repo:
   ```bash
   git clone https://github.com/Deltares-research/DeltaGPR.git
   cd DeltaGPR
   ```
3. Create the environment and install the package:
   ```bash
   pixi run install
   ```

## Main usage

### 1. Run the generic pipeline on `.gpz` files

```bash
pixi shell
cd path/to/folder-with-gpz-files
deltagpr_pipeline
```

This scans the current folder for `.gpz` files and creates one output folder per file, including QC tracklines and a processing log.

The default antenna height for the executable is `1.0 m`. Override it if needed:

```bash
deltagpr_pipeline --antenna-height 1.25
```

### 2. Use the individual tools

```bash
pixi run apply_offsets
pixi run clean_coordinates
pixi run edit_headers
pixi run tracklines
pixi run convert_to_nap
```

These commands open a file picker and work on a copy of the selected GP2 files so the originals stay untouched.

### 3. Convert AHN rasters to GeoLitix grids

```bash
pixi run ahn_to_geolitix
```

Converts every AHN GeoTIFF in a folder (a folder picker opens if no path is given) to a Surfer binary `.grd` next to the source raster, which GeoLitix can import. Rasters that already have a `.grd` are skipped, so it is safe to re-run.

### 4. Convert EM models to GeoLitix depth grids

```bash
pixi run em_to_geolitix
pixi run em_to_geolitix "path/to/model.xyz" --depth 1.5
pixi run em_to_geolitix "path/to/xyz-folder" --cell-size 0.5 --doi standard
```

Reads Seequent layered XYZ exports with `X`, `Y`, `RHO_n`, `DEP_TOP_n`, and
`DEP_BOT_n` columns. With no path, a folder picker opens. By default, every
native layer is exported as a separate resistivity grid (ohm m), sampled at its
midpoint. `--depth` instead selects the containing layer at that depth in metres
below **local ground**, not at a constant NAP elevation. At an internal boundary
the deeper layer is used; the final model bottom is included. Models with varying
layer boundaries require an explicit `--depth` to avoid misleading layer labels.

Use `--recursive` to search subfolders and `--name-contains MOD_inv` to select
inversion-model filenames case-insensitively. These options are also available
as `recursive` and `name_contains` in the `em_xyzs_to_grd` Python API.

Uses the same Surfer 7 binary writer as the AHN tool; `--format surfer6` is also
available. A Surfer grid is a 2D scalar map, not a volume: its values here are
resistivity, not height. The depth/layer interval is in the filename. Import these
as scalar maps in GeoLitix, not terrain surfaces. This conversion does not establish
whether GeoLitix supports volumes through some other import format.

The default gridding is linear interpolation at 0.5 coordinate-unit spacing,
appropriate as a starting point for metre-based survey coordinates. This is display
sampling, not a claim of 0.5 m EM resolution. Nodes outside the soundings' convex
hull or farther than 1 m from a sounding are blanked to limit extrapolation and
gap filling. Adjust `--max-distance` to survey-line spacing; its default is twice
`--cell-size`. `--method nearest` avoids interpolating values and supports straight
survey lines, using the distance mask where no 2D hull exists. X/Y coordinates are
preserved without CRS conversion; select the source CRS when importing.

All model depths are exported by default, including values below the depth of
investigation. Use `--doi standard` or `--doi conservative` to blank soundings
where the slice depth exceeds the corresponding DOI column. For all-layer exports,
DOI is evaluated at each layer midpoint, not its bottom. Linear interpolation also
blanks triangles touching missing/masked values, so masked coverage is conservative.
Non-positive/missing resistivity is blanked; duplicate locations are averaged.

Outputs are written beside each XYZ, or to `--output-dir`. Existing outputs are
skipped; use `--overwrite` when changing gridding settings, which are not encoded
in the filenames. Source files are never modified.

### 5. The NLGEO2018 grid for NAP conversion

The conversion to NAP needs the Dutch geoid grid `nl_nsgi_nlgeo2018.tif`. It is downloaded automatically into the PROJ user data folder the first time it is needed, so normally you do not have to do anything. To fetch it up front (for example before going offline):

```bash
pixi run download_nap_grid
```

Without the grid PROJ silently falls back to a "ballpark" vertical transformation that leaves heights unchanged, so the tools refuse to run rather than return wrong heights.

## Standalone executable

Build a Windows executable:

```bash
pixi run build_exe
```

This writes `dist/deltagpr_pipeline.exe`. Copy it next to one or more `.gpz` files and run it there.

For Linux, build on Linux:

```bash
pixi run build_linux_executable
```

## Repository layout

- `src/deltagpr/`: library code and CLI entry points
- `tests/`: automated tests
- `examples/`: example GP2 inputs
- `docs/`: images and the executable icon

## Relationship to deltagpr-projects

Use `DeltaGPR` for the generic tools and the project-specific scripts in `deltagpr-projects` for survey-specific processing choices such as antenna height, latency, and project naming.
