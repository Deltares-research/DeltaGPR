import tempfile
import unittest
from pathlib import Path

from deltagpr.workspace import sort_gp2_by_channel


class TestSortGp2ByChannel(unittest.TestCase):
    def test_sorts_with_frequency(self):
        with tempfile.TemporaryDirectory() as directory:
            deltagpr_dir = Path(directory)
            gp2_file = deltagpr_dir / "Line1-ch2.gp2"
            hd_file = deltagpr_dir / "Line1-ch2.hd"
            dt1_file = deltagpr_dir / "Line1-ch2.dt1"

            gp2_file.write_text("gp2 content", encoding="utf-8")
            hd_file.write_text(
                "NUMBER OF TRACES   = 100\nNominal Frequency = 250\n",
                encoding="utf-8",
            )
            dt1_file.write_text("dt1 content", encoding="utf-8")

            sort_gp2_by_channel(deltagpr_dir, [gp2_file])

            target_dir = deltagpr_dir / "ch2-250mhz"
            self.assertTrue(target_dir.is_dir())
            self.assertTrue((target_dir / "Line1-ch2.gp2").is_file())
            self.assertTrue((target_dir / "Line1-ch2.hd").is_file())
            self.assertTrue((target_dir / "Line1-ch2.dt1").is_file())

    def test_sorts_single_channel_without_suffix(self):
        with tempfile.TemporaryDirectory() as directory:
            deltagpr_dir = Path(directory)
            gp2_file = deltagpr_dir / "Line1.gp2"
            hd_file = deltagpr_dir / "Line1.hd"

            gp2_file.write_text("gp2 content", encoding="utf-8")
            hd_file.write_text("Nominal Frequency (MHz) : 500\n", encoding="utf-8")

            sort_gp2_by_channel(deltagpr_dir, [gp2_file])

            target_dir = deltagpr_dir / "ch1-500mhz"
            self.assertTrue(target_dir.is_dir())
            self.assertTrue((target_dir / "Line1.gp2").is_file())
            self.assertTrue((target_dir / "Line1.hd").is_file())


if __name__ == "__main__":
    unittest.main()
