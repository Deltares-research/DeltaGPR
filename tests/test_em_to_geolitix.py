import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

from deltagpr.ahn_to_geolitix import SURFER_BLANK
from deltagpr.em_to_geolitix import (
    em_xyzs_to_grd,
    grid_em_slice,
    read_em_xyz,
    values_at_depth,
)


def _write_xyz(path: Path) -> None:
    path.write_text(
        "/ Seequent model export\n"
        "/ X Y RHO_1 RHO_2 DEP_TOP_1 DEP_TOP_2 DEP_BOT_1 DEP_BOT_2 "
        "DOI_STANDARD\n"
        "0 0 10 100 0 1 1 3 2\n"
        "1 0 20 200 0 1 1 3 2\n"
        "0 1 30 300 0 1 1 3 0.5\n"
        "1 1 40 400 0 1 1 3 0.5\n",
        encoding="utf-8",
    )


class TestEMToGeolitix(unittest.TestCase):
    def test_parser_depth_boundaries_and_doi(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.xyz"
            _write_xyz(path)
            model = read_em_xyz(path)
            np.testing.assert_array_equal(values_at_depth(model, 0), [10, 20, 30, 40])
            np.testing.assert_array_equal(
                values_at_depth(model, 1), [100, 200, 300, 400],
            )
            np.testing.assert_array_equal(
                values_at_depth(model, 3), [100, 200, 300, 400],
            )
            self.assertTrue(np.isnan(values_at_depth(model, 4)).all())
            np.testing.assert_allclose(
                values_at_depth(model, 1, "standard"),
                [100, 200, np.nan, np.nan], equal_nan=True,
            )
            with self.assertRaisesRegex(ValueError, "DOI_CONSERVATIVE"):
                values_at_depth(model, 1, "conservative")

    def test_linear_grid_orientation_interpolation_and_mask(self):
        points = np.array([[0, 0], [1, 0], [0, 1]])
        grid, *bounds = grid_em_slice(points, np.array([10, 20, 30]), 0.5)
        self.assertEqual(bounds, [0, 1, 0, 1])
        np.testing.assert_allclose(grid[0], [10, 15, 20])
        self.assertEqual(grid[1, 1], 25)
        self.assertEqual(grid[2, 0], 30)
        self.assertTrue(np.isnan(grid[2, 2]))
        masked, *_ = grid_em_slice(
            points, np.array([10, 20, 30]), 0.5, max_distance=0.1,
        )
        self.assertTrue(np.isnan(masked[1, 1]))

    def test_duplicate_points_are_averaged(self):
        points = np.array([[0, 0], [0, 0], [1, 0], [0, 1]])
        grid, *_ = grid_em_slice(points, np.array([10, 30, 40, 50]))
        self.assertEqual(grid[0, 0], 20)

    def test_collinear_survey_requires_nearest(self):
        points = np.array([[0, 0], [1, 0], [2, 0]])
        with self.assertRaisesRegex(ValueError, "non-collinear"):
            grid_em_slice(points, np.array([10, 20, 30]))
        grid, *_ = grid_em_slice(points, np.array([10, 20, 30]), method="nearest")
        np.testing.assert_array_equal(grid[0, ::2], [10, 20, 30])

    def test_writes_all_layers_and_skips_existing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.xyz"
            _write_xyz(path)
            outputs = em_xyzs_to_grd(path, cell_size=1)
            self.assertEqual(len(outputs), 2)
            self.assertIn("layer01_0-1m", outputs[0].name)
            binary = outputs[0].read_bytes()
            self.assertEqual(binary[:4], b"DSRB")
            self.assertEqual(struct.unpack_from("<ll", binary, 20), (2, 2))
            np.testing.assert_array_equal(
                np.frombuffer(binary, dtype="<f8", offset=100), [10, 20, 30, 40],
            )
            self.assertEqual(em_xyzs_to_grd(path, cell_size=1), [])

    def test_specific_depth_surfer6_and_blank(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.xyz"
            _write_xyz(path)
            output = em_xyzs_to_grd(
                path.parent, depth=1, cell_size=1,
                grid_format="surfer6", method="nearest", doi="standard",
            )[0]
            binary = output.read_bytes()
            self.assertEqual(binary[:4], b"DSBB")
            values = np.frombuffer(binary, dtype="<f4", offset=56)
            np.testing.assert_array_equal(values[:2], [100, 200])
            np.testing.assert_array_equal(values[2:], np.float32(SURFER_BLANK))

    def test_recursive_search_and_case_insensitive_name_filter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "data" / "EM" / "results"
            nested.mkdir(parents=True)
            _write_xyz(root / "root_MOD_inv.xyz")
            _write_xyz(nested / "survey_mod_INV.XYZ")
            (nested / "raw.xyz").write_text("not an inversion model")
            (nested / "survey_MOD_inv.txt").write_text("not an XYZ")
            outputs = em_xyzs_to_grd(root, depth=1, name_contains="MOD_inv")
            self.assertEqual(len(outputs), 1)
            self.assertEqual(outputs[0].parent, root)
            outputs = em_xyzs_to_grd(
                root, depth=1, recursive=True, name_contains="MOD_inv",
            )
            self.assertEqual(len(outputs), 1)
            self.assertEqual(outputs[0].parent, nested)
            with self.assertRaisesRegex(ValueError, "No XYZ files"):
                em_xyzs_to_grd(root, recursive=True, name_contains="absent")

    def test_variable_layer_depths_need_explicit_depth(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.xyz"
            _write_xyz(path)
            path.write_text(path.read_text().replace("0 1 1 3 2", "0 2 2 3 2"))
            with self.assertRaisesRegex(ValueError, "layer depths vary"):
                em_xyzs_to_grd(path)
            model = read_em_xyz(path)
            np.testing.assert_array_equal(
                values_at_depth(model, 1.5), [10, 20, 300, 400],
            )

    def test_rejects_invalid_depth_spacing_and_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.xyz"
            _write_xyz(path)
            model = read_em_xyz(path)
            for depth in (-1, np.nan, np.inf):
                with self.assertRaises(ValueError):
                    values_at_depth(model, depth)
            for spacing in (0, -1, np.nan):
                with self.assertRaises(ValueError):
                    grid_em_slice(model.points, model.resistivity[:, 0], spacing)
            path.write_text(path.read_text().replace("DEP_BOT_2", "OTHER"))
            with self.assertRaisesRegex(ValueError, "missing columns"):
                read_em_xyz(path)


if __name__ == "__main__":
    unittest.main()
