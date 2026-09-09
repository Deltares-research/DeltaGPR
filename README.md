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

### 2. Use the individual tools

```bash
pixi run apply_offsets
pixi run clean_coordinates
pixi run edit_headers
pixi run tracklines
pixi run convert_to_nap
```

These commands open a file picker and work on a copy of the selected GP2 files so the originals stay untouched.

### 3. Download the NLGEO2018 grid for NAP conversion

```bash
pixi run download_nap_grid
```

The conversion to NAP requires the Dutch geoid grid. If it is missing, the tool will tell you and can download it for you.

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
