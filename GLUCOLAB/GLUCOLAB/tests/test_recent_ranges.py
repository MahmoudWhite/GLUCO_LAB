"""Regression tests for recent-data window and rate-range extraction. Synthetic CSVs only."""
import io
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import analyze_files


def libre(rows):
    return ('Device export\nDevice Timestamp,Record Type,Historic Glucose (mg/dL)\n'
            + '\n'.join(f'{stamp},0,{bg}' for stamp,bg in rows) + '\n').encode()


def pump(rows, marker=None):
    data=['header', 'Date,Time,Basal Rate (U/h),Event Marker']
    data.extend(f'{stamp.split()[0]},{stamp.split()[1]},{rate},' for stamp,rate in rows)
    if marker:
        data.append(f'{marker.split()[0]},{marker.split()[1]},,Basal profile changed')
    return ('\n'.join(data)+'\n').encode()


class RecentWindowTests(unittest.TestCase):
    def test_old_history_is_excluded_everywhere(self):
        lib=libre([
            ('05/09/2022 07:52:00',500),
            ('01/10/2026 08:00:00',490),
            ('31/10/2026 11:00:00',320),
            ('05/11/2026 13:00:00',110),
            ('06/11/2026 09:50:00',125),
        ])
        pump_csv=pump([('2026/11/05 00:00:00',0.7),('2026/11/05 06:00:00',0.8),
                       ('2026/11/05 22:00:00',0.6)])
        r=analyze_files(lib,pump_csv)
        self.assertEqual(r['libre']['summary']['readings'],3)
        self.assertEqual(r['libre']['summary']['highest'],320)
        self.assertEqual(r['pattern']['glucose_readings'],3)
        self.assertEqual(r['filters']['days'],14)
        self.assertEqual([x['start'] for x in r['pattern']['segments']], ['00:00','06:00','22:00'])
        self.assertEqual(r['pattern']['segments'][-1]['end'],'24:00')
        self.assertEqual(r['pattern']['profile_day'],'2026-11-05')

    def test_one_recent_rate_is_not_a_whole_day_schedule(self):
        lib=libre([('15/11/2026 07:00:00',210), ('16/11/2026 07:00:00',220),
                   ('17/11/2026 12:00:00',150)])
        r=analyze_files(lib,pump([('2026/11/16 12:40:00',1.75)]))
        self.assertEqual(r['pattern']['status'],'no_profile')
        self.assertEqual(r['pattern']['segments'],[])
        self.assertEqual(r['pattern']['recent_rate_entries'],1)
        self.assertIn('One recorded rate',r['pattern']['range_note'])

    def test_pick_older_sufficient_day_when_latest_day_sparse(self):
        lib=libre([('16/11/2026 12:00:00',155),('17/11/2026 12:00:00',135)])
        r=analyze_files(lib,pump([
            ('2026/11/16 00:00:00',0.55),('2026/11/16 06:00:00',0.65),
            ('2026/11/16 18:00:00',0.75),('2026/11/17 12:00:00',0.80),
        ]))
        self.assertEqual(r['pattern']['profile_day'],'2026-11-16')
        self.assertEqual(len(r['pattern']['segments']),3)
        self.assertTrue(r['pattern']['profile_complete'])

    def test_partial_intervals_display_without_simulated_final_schedule(self):
        lib=libre([('16/11/2026 12:00:00',155),('17/11/2026 12:00:00',135)])
        r=analyze_files(lib,pump([
            ('2026/11/16 06:00:00',0.55),('2026/11/16 13:00:00',0.65),
        ]))
        self.assertEqual(r['pattern']['status'],'partial_profile')
        self.assertEqual(r['pattern']['segments'],[])
        self.assertEqual(r['pattern']['partial_ranges'][0]['start'],'06:00')
        self.assertEqual(r['pattern']['partial_ranges'][0]['end'],'13:00')

    def test_explicit_marker_shortens_already_recent_period(self):
        lib=libre([('15/11/2026 07:00:00',210),('16/11/2026 07:00:00',220),
                   ('17/11/2026 08:00:00',120)])
        r=analyze_files(lib,pump([('2026/11/17 00:00:00',0.8),
                                  ('2026/11/17 08:00:00',0.9)],
                                 marker='2026/11/16 12:00:00'))
        self.assertEqual(r['libre']['summary']['readings'],1)
        self.assertEqual(r['libre']['summary']['from'],'2026-11-17 08:00')
        self.assertEqual(r['pattern']['last_edit'],'2026-11-16 12:00')


if __name__=='__main__': unittest.main()
