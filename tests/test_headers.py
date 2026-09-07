import tempfile
import unittest
from pathlib import Path

from deltagpr.headers import edit_gp2_headers_in_place


class TestEditHeaders(unittest.TestCase):
    def test_updates_existing_headers_and_preserves_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "line.GP2"
            path.write_text(
                ";GPS@@@\n"
                ";Offset_m=0.00,-0.87,0.00\n"
                ";Latency_s=0.00\n"
                "traces,GPS\n"
                '1,"$GPGGA,100000.00,5140.0,N,00423.0,E,4,20,0.7,1,M,47,M,1,1*00"\n',
                encoding="utf-8",
            )

            result = edit_gp2_headers_in_place(path, "1.0", "2.0", "3.0", "0.5")

            output = path.read_text(encoding="utf-8")
            self.assertEqual(result, (True, True))
            self.assertIn(";Offset_m=1.0,2.0,3.0\n", output)
            self.assertIn(";Latency_s=0.5\n", output)
            self.assertIn("traces,GPS\n", output)

    def test_reports_missing_headers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "line.GP2"
            original = ";GPS@@@\ntraces,GPS\n"
            path.write_text(original, encoding="utf-8")

            result = edit_gp2_headers_in_place(path, "1", "2", "3", "0.5")

            self.assertEqual(result, (False, False))
            self.assertEqual(path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
