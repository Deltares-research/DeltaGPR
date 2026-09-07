# GFP geometry utility

This optional script applies line start and end coordinates from an Excel table
to a Sensors & Software GFP XML export. It is separate from the supported GP2
commands.

Run it from the repository root:

```powershell
pixi run python optional/gfp_from_excel/apply_gfp_from_excel.py
```

By default it reads the bundled `water_soil_flume.xml` and
`gfp_lines_template.xlsx`, then writes `water_soil_flume.updated.xml` beside the
input XML. Override the paths with `--gfp`, `--excel`, and `--out`.
