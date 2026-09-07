import csv
import tempfile
import unittest
from pathlib import Path

from deltagpr.clean_coordinates import clean_gp2_coordinates_in_place
from deltagpr.dialogs import copy_selected_to_subfolder
from deltagpr.gp2 import parse_gpgga


def _gga(time: str, latitude: str, longitude: str, altitude: str) -> str:
    return (
        f"$GPGGA,{time},{latitude},N,{longitude},E,4,20,0.70,{altitude},"
        "M,47.0000,M,1.0,4095*00"
    )


def _checksum_is_valid(sentence: str) -> bool:
    body, expected = sentence.split("*")
    checksum = 0
    for character in body[1:]:
        checksum ^= ord(character)
    return expected == f"{checksum:02X}"


def _write_rows(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow([";GPS@@@"])
        writer.writerow(["traces", "GPS"])
        writer.writerows(rows)


def _read_fixes(path: Path):
    output = list(csv.reader(path.read_text(encoding="utf-8").splitlines()))
    return [parse_gpgga(row[1]) for row in output[2:]]


class TestCleanCoordinates(unittest.TestCase):
    def test_replaces_repeated_trace_with_coordinate_and_height_medians(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "line.GP2"
            rows = [
                ["10", _gga("100000.00", "5140.0000000", "00423.0000000", "1.0")],
                ["10", _gga("100001.00", "5140.0003000", "00423.0006000", "9.0")],
                ["10", _gga("100002.00", "5140.0006000", "00423.0003000", "5.0")],
            ]
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow([";GPS@@@"])
                writer.writerow(["traces", "GPS"])
                writer.writerows(rows)

            cleaned = clean_gp2_coordinates_in_place(path)

            output = list(csv.reader(path.read_text(encoding="utf-8").splitlines()))
            sentences = [row[1] for row in output[2:]]
            fixes = [parse_gpgga(sentence) for sentence in sentences]
            self.assertEqual(cleaned, 3)
            self.assertEqual(len(fixes), 3)
            self.assertEqual([fix.fields[1] for fix in fixes], [
                "100000.00",
                "100001.00",
                "100002.00",
            ])
            for fix, sentence in zip(fixes, sentences):
                self.assertAlmostEqual(fix.latitude, fixes[0].latitude)
                self.assertAlmostEqual(fix.longitude, fixes[0].longitude)
                self.assertAlmostEqual(fix.z_m, 52.0)
                self.assertTrue(_checksum_is_valid(sentence))

    def test_does_not_merge_nonconsecutive_equal_traces(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "line.GP2"
            content = "\n".join(
                [
                    ";GPS@@@",
                    "traces,GPS",
                    f'1,"{_gga("100000.00", "5140.0000000", "00423.0000000", "1.0")}"',
                    f'2,"{_gga("100001.00", "5140.0010000", "00423.0010000", "2.0")}"',
                    f'1,"{_gga("100002.00", "5140.0020000", "00423.0020000", "3.0")}"',
                ]
            )
            path.write_text(content, encoding="utf-8")

            cleaned = clean_gp2_coordinates_in_place(path)

            self.assertEqual(cleaned, 0)
            self.assertEqual(path.read_text(encoding="utf-8"), content)

    def test_inner_and_outer_endpoints_use_median_for_middle_groups(self):
        rows = [
            ["1", _gga("100000.00", "5140.0000000", "00423.0000000", "1.0")],
            ["1", _gga("100001.00", "5140.0001000", "00423.0001000", "2.0")],
            ["2", _gga("100002.00", "5140.0010000", "00423.0010000", "3.0")],
            ["3", _gga("100003.00", "5140.0020000", "00423.0020000", "4.0")],
            ["3", _gga("100004.00", "5140.0090000", "00423.0090000", "9.0")],
            ["3", _gga("100005.00", "5140.0030000", "00423.0030000", "5.0")],
            ["4", _gga("100006.00", "5140.0040000", "00423.0040000", "6.0")],
            ["4", _gga("100007.00", "5140.0041000", "00423.0041000", "7.0")],
        ]
        with tempfile.TemporaryDirectory() as directory:
            inner_path = Path(directory) / "inner.GP2"
            outer_path = Path(directory) / "outer.GP2"
            _write_rows(inner_path, rows)
            _write_rows(outer_path, rows)

            clean_gp2_coordinates_in_place(inner_path)
            clean_gp2_coordinates_in_place(outer_path, "outer_endpoints")

            inner = _read_fixes(inner_path)
            outer = _read_fixes(outer_path)
            self.assertEqual(inner[0].fields[2], "5140.0001000")
            self.assertEqual(inner[-1].fields[2], "5140.0040000")
            self.assertEqual(outer[0].fields[2], "5140.0000000")
            self.assertEqual(outer[-1].fields[2], "5140.0041000")
            for fixes in (inner, outer):
                for fix in fixes[3:6]:
                    self.assertEqual(fix.fields[2], "5140.0030000")
                    self.assertAlmostEqual(fix.altitude_msl_m, 5.0)

    def test_rejects_removed_average_method(self):
        with self.assertRaisesRegex(ValueError, "Unknown cleaning method"):
            clean_gp2_coordinates_in_place(Path("unused.GP2"), "average")

    def test_copies_only_selected_files_to_one_named_subfolder(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            first = source / "first.GP2"
            second = source / "second.gp2"
            unselected = source / "other.txt"
            first.write_text("first", encoding="utf-8")
            second.write_text("second", encoding="utf-8")
            unselected.write_text("other", encoding="utf-8")

            copied = copy_selected_to_subfolder(
                [first, second], "clean_coordinates"
            )

            self.assertEqual(
                copied,
                [
                    source / "clean_coordinates" / "first.GP2",
                    source / "clean_coordinates" / "second.gp2",
                ],
            )
            self.assertFalse((source / "clean_coordinates" / "other.txt").exists())


if __name__ == "__main__":
    unittest.main()
