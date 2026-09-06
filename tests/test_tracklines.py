import tempfile
import unittest
from pathlib import Path

import geopandas as gpd

from deltagpr.tools import tracklines_to_shape
from deltagpr.tools.tracklines import _default_output_path


def _write_gp2(path: Path, coordinates: list[tuple[str, str, str, str]]) -> None:
    lines = [";GPS@@@", "traces,GPS"]
    for index, (latitude, north_south, longitude, east_west) in enumerate(coordinates):
        sentence = (
            f"$GPGGA,10070{index}.00,{latitude},{north_south},{longitude},"
            f"{east_west},4,25,0.59,2.4,M,47.1,M,1.0,4095*00"
        )
        lines.append(f'{index},"{sentence}"')
    path.write_text("\n".join(lines), encoding="utf-8")


class TestTracklinesToShape(unittest.TestCase):
    def test_default_output_path_shows_file_range_and_crs(self):
        files = [Path("survey/Line4-ch2.GP2"), Path("survey/Line6-ch6.gp2")]

        output = _default_output_path(files, 28992)

        self.assertEqual(
            output, Path("survey/shapefile/Line4-ch2_to_Line6-ch6_EPSG28992.shp")
        )

    def test_writes_one_projected_line_per_gp2(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            _write_gp2(
                tmp_path / "line_a.GP2",
                [
                    ("5140.0000", "N", "00423.0000", "E"),
                    ("5140.0060", "N", "00423.0060", "E"),
                ],
            )
            _write_gp2(
                tmp_path / "line_b.gp2",
                [
                    ("5141.0000", "N", "00424.0000", "E"),
                    ("5141.0060", "N", "00424.0060", "E"),
                ],
            )

            output = tracklines_to_shape(tmp_path, output_crs=28992)

            result = (
                gpd.read_file(output).sort_values("linename").reset_index(drop=True)
            )
            self.assertEqual(output.name, "line_a_to_line_b_EPSG28992.shp")
            self.assertEqual(output.parent.name, "shapefile")
            self.assertEqual(result.crs.to_epsg(), 28992)
            self.assertEqual(result["linename"].tolist(), ["line_a", "line_b"])
            self.assertEqual(result["n_points"].tolist(), [2, 2])
            self.assertEqual(
                result.geometry.geom_type.tolist(), ["LineString", "LineString"]
            )

    def test_rejects_file_without_a_line(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            path = tmp_path / "single.GP2"
            _write_gp2(path, [("5140.0000", "N", "00423.0000", "E")])

            with self.assertRaisesRegex(ValueError, "fewer than two"):
                tracklines_to_shape(path, tmp_path / "tracks.shp")


if __name__ == "__main__":
    unittest.main()
