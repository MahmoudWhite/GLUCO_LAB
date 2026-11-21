"""Guard against treating an incomplete last pump day as a 24-hour profile."""
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import analyze_files


def make_libre():
    return ("Export\nDevice Timestamp,Record Type,Historic Glucose (mg/dL)\n"
            "04/11/2026 09:00:00,0,190\n"
            "05/11/2026 09:00:00,0,205\n"
            "05/11/2026 19:00:00,0,160\n"
            "06/11/2026 09:50:00,0,195\n").encode()


def make_pump(rows):
    return ("Export\nDate,Time,Basal Rate (U/h)\n" +
            "\n".join(f"{day},{clock},{rate}" for day,clock,rate in rows) + "\n").encode()


class SixRangeTests(unittest.TestCase):
    def setUp(self):
        self.full_day=[('2026/11/05','00:00:00',1.75),('2026/11/05','03:00:00',1.90),
                       ('2026/11/05','07:00:00',2.30),('2026/11/05','10:00:00',2.10),
                       ('2026/11/05','16:30:00',2.20),('2026/11/05','20:00:00',2.35)]
        self.short_day=[('2026/11/06','00:00:00',1.75),('2026/11/06','03:00:00',1.95),
                        ('2026/11/06','07:00:00',2.30)]

    def test_six_ranges_on_previous_full_day_not_three_on_truncated_latest_day(self):
        result=analyze_files(make_libre(),make_pump(self.full_day+self.short_day))
        p=result['pattern']
        self.assertEqual(p['profile_day'],'2026-11-05')
        self.assertEqual(len(p['segments']),6)
        self.assertEqual([(s['start'],s['end']) for s in p['segments']], [
            ('00:00','03:00'), ('03:00','07:00'), ('07:00','10:00'),
            ('10:00','16:30'), ('16:30','20:00'), ('20:00','24:00')])
        self.assertEqual([s['original_rate'] for s in p['segments']],
                         [1.75,1.90,2.30,2.10,2.20,2.35])
        self.assertIn('CANDIDATE RECORDED TIME RANGES',result['report'])
        self.assertIn('20:00 - 24:00',result['report'])
        self.assertIn('Other dates contain DIFFERENT rates',p['range_note'])
        self.assertEqual(p['profile_discrepancies'][0]['time'],'03:00')

    def test_does_not_make_all_day_schedule_using_morning_only(self):
        result=analyze_files(make_libre(),make_pump(self.short_day))
        p=result['pattern']
        self.assertEqual(p['segments'],[])
        self.assertEqual(p['status'],'partial_profile')
        self.assertEqual(len(p['partial_ranges']),2)
        self.assertEqual(p['partial_ranges'][-1]['end'],'07:00')
        self.assertNotIn('07:00–24:00',p['range_note'])

    def test_most_detailed_day_selected_not_just_latest_prior_date(self):
        less_complete=[('2026/11/06','00:00:00',1.75),('2026/11/06','07:00:00',2.30)]
        # Here Libre latest is 09:50, so the Nov 6 pump rates are still a partial day.
        result=analyze_files(make_libre(),make_pump(self.full_day+less_complete))
        self.assertEqual(result['pattern']['profile_day'],'2026-11-05')

    def test_frontend_shows_separate_unverified_6_range_table(self):
        html=(Path(__file__).resolve().parents[1]/'index.html').read_text()
        self.assertIn('id="candidateTable"',html)
        self.assertIn('Recorded time ranges · candidate only',html)
        self.assertIn('Export candidate ranges',html)

if __name__=='__main__':
    unittest.main()
