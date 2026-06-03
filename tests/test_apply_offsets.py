import math
import unittest

from apply_offsets import (
    Offset,
    apply_offset,
    estimate_heading_series,
    format_gpgga_with_checksum,
    parse_gpgga,
    parse_offset_line,
    project_latlon_to_xy,
    inverse_project_xy_to_latlon,
    _make_projector,
)


class TestApplyOffsetsHelpers(unittest.TestCase):
    def test_parse_offset_line(self):
        off = parse_offset_line(";Offset_m=0.00,-0.87,0.10")
        self.assertAlmostEqual(off.offset_x, 0.0)
        self.assertAlmostEqual(off.offset_y, -0.87)
        self.assertAlmostEqual(off.offset_z, 0.10)

    def test_parse_and_format_gpgga(self):
        s = "$GPGGA,100710.00,5140.6771919,N,00423.6409497,E,4,25,0.59,2.4535,M,47.1945,M,1.0,4095*7F"
        gga = parse_gpgga(s)
        out = format_gpgga_with_checksum(gga, gga.latitude + 1e-6, gga.longitude - 1e-6, gga.altitude_msl_m + 0.1)
        self.assertTrue(out.startswith("$GPGGA,"))
        self.assertIn("*", out)

    def test_projection_roundtrip(self):
        lat, lon = 51.6771919, 4.39409497
        projector = _make_projector(lat, lon)
        x, y = project_latlon_to_xy(lat, lon, projector)
        lat2, lon2 = inverse_project_xy_to_latlon(x, y, projector)
        self.assertAlmostEqual(lat, lat2, places=6)
        self.assertAlmostEqual(lon, lon2, places=6)

    def test_estimate_heading_series(self):
        xs = [0.0, 1.0, 2.0, 3.0, 4.0]
        ys = [0.0, 0.0, 0.0, 0.0, 0.0]
        hs = estimate_heading_series(xs, ys, min_baseline_m=0.5, window_max=3)
        for h in hs:
            if not math.isnan(h):
                self.assertAlmostEqual(h, 0.0, places=3)

    def test_apply_offset(self):
        off = Offset(offset_x=1.0, offset_y=2.0, offset_z=0.5)
        x2, y2, z2 = apply_offset(10.0, 20.0, 3.0, 0.0, off)
        self.assertAlmostEqual(x2, 12.0)
        self.assertAlmostEqual(y2, 19.0)
        self.assertAlmostEqual(z2, 3.5)


if __name__ == "__main__":
    unittest.main()
