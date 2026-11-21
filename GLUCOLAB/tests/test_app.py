"""Run from project folder with: python -m unittest discover -s tests -v"""
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import InputError, LibreAnalyzer, PumpAnalyzer, TimeWindow, analyze_files


def libre_csv():
    # Note: the text starts with a metadata row (as real LibreView exports often do).
    return ("Patient export info\n"
            "Device Timestamp,Record Type,Historic Glucose (mg/dL),Scan Glucose (mg/dL)\n"
            "19/11/2026 01:00,0,65,\n"
            "19/11/2026 01:15,0,62,\n"
            "19/11/2026 01:30,0,81,\n"
            "19/11/2026 02:00,0,69,\n"
            "19/11/2026 02:15,0,75,\n"
            "19/11/2026 03:00,1,,110\n"
            "19/11/2026 23:00,0,150,\n").encode()


def pump_csv():
    return ("Medical Data Export\nHeader 2\nHeader 3\nHeader 4\nHeader 5\nHeader 6\n"
            "Date,Time,Basal Rate (U/h),Bolus Volume Delivered (U)\n"
            "2026/11/19,01:00:00,0.7,\n"
            "2026/11/19,01:15:00,0.9,\n"
            "2026/11/19,02:00:00,1.1,\n"
            "2026/11/19,23:00:00,1.0,\n").encode()


class GlucoseDashboardTests(unittest.TestCase):
    def test_libre_record_type_and_episodes(self):
        analyzer = LibreAnalyzer(libre_csv(), day_first=True)
        result = analyzer.analyze(TimeWindow("00:00", "00:00", "", ""))
        self.assertEqual(result["summary"]["readings"], 6)
        self.assertEqual(result["summary"]["hypo_episodes"], 2)
        self.assertEqual(result["hypo_events_per_hour"][1], 1)
        self.assertEqual(result["hypo_events_per_hour"][2], 1)
        self.assertEqual(result["hourlybg"][1], round((65+62+81)/3, 2))
        self.assertEqual(result["summary"]["lowest"], 62.0)

    def test_clock_time_overnight(self):
        result = LibreAnalyzer(libre_csv()).analyze(TimeWindow("22:00", "02:00", "", ""))
        self.assertEqual(result["summary"]["readings"], 4)
        self.assertEqual(result["summary"]["hypo_episodes"], 1)

    def test_pump_metadata_header(self):
        pump = PumpAnalyzer(pump_csv())
        out = pump.analyze(TimeWindow("01:00", "02:00", "", ""))
        self.assertEqual(out["summary"]["entries"], 2)
        self.assertEqual(out["summary"]["mean"], 0.8)
        self.assertEqual(out["hourly"][1]["entries"], 2)

    def test_all_data_combined(self):
        result = analyze_files(libre_csv(), pump_csv(),
                               {"start_time":"00:00", "end_time":"00:00",
                                "libre_day_first":"true", "pump_day_first":"false"})
        self.assertIn("FORMATTED", "FORMATTED")
        self.assertEqual(len(result["libre"]["hourly"]), 24)
        self.assertEqual(len(result["pump"]["hourly"]), 24)
        self.assertIn("MEDTRONIC / OBSERVED RATE", result["report"])

    def test_invalid_files_show_friendly_error(self):
        with self.assertRaises(InputError):
            LibreAnalyzer(b"any,columns\na,b\n")

    def test_empty_pump_period_is_nonfatal(self):
        output = PumpAnalyzer(pump_csv()).analyze(TimeWindow("18:00", "19:00", "", ""))
        self.assertEqual(output["summary"]["entries"], 0)

    def test_date_filters(self):
        w = TimeWindow("00:00", "00:00", "2026-11-19", "2026-11-19")
        self.assertEqual(LibreAnalyzer(libre_csv()).analyze(w)["summary"]["readings"], 6)
        with self.assertRaises(InputError):
            TimeWindow("00:00", "00:00", "2026-11-20", "2026-11-19")


if __name__ == "__main__":
    unittest.main()
