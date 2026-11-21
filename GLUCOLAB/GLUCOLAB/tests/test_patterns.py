"""Synthetic, non-patient data for GLUCOLAB pattern tests."""
import io
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import InputError, LibreAnalyzer, PumpAnalyzer, analyze_files, app
from fastapi.testclient import TestClient


def pump_csv(with_marker=False):
    rows = [
        'Device export',
        'Date,Time,Basal Rate (U/h),Event Marker',
        '2026/11/17,00:00:00,0.60,',
        '2026/11/17,06:00:00,0.75,',
        '2026/11/17,10:00:00,0.85,',
        '2026/11/17,22:00:00,0.65,',
    ]
    if with_marker:
        rows.append('2026/11/14,08:30:00,,Basal profile changed')
    return ('\n'.join(rows)+'\n').encode()


def libre_csv(hypo=True, high=True, conflict=False):
    rows = ['LibreView export', 'Device Timestamp,Record Type,Historic Glucose (mg/dL)']
    for day in (15,16):
        if high:
            rows.extend([f'{day}/11/2026 06:00,0,210', f'{day}/11/2026 06:15,0,220',
                         f'{day}/11/2026 07:00,0,215', f'{day}/11/2026 07:15,0,220'])
        if conflict:
            rows.extend([f'{day}/11/2026 06:35,0,60', f'{day}/11/2026 06:50,0,90'])
        if hypo:
            rows.extend([f'{day}/11/2026 12:00,0,55', f'{day}/11/2026 12:15,0,59',
                         f'{day}/11/2026 12:30,0,115'])
        rows.extend([f'{day}/11/2026 14:00,0,125', f'{day}/11/2026 14:15,0,128'])
    rows.append('17/11/2026 23:00,0,205')
    return ('\n'.join(rows)+'\n').encode()


class PatternTests(unittest.TestCase):
    def analyze(self, **kwargs):
        return analyze_files(libre_csv(**kwargs),pump_csv(with_marker=True))['pattern']

    def test_one_step_per_basalsegment_for_multiple_hours(self):
        p=self.analyze()
        self.assertEqual(p['status'],'review_only')
        seg=next(s for s in p['segments'] if s['start']=='06:00')
        self.assertEqual(seg['end'],'10:00')
        self.assertEqual(seg['action'],'high')
        self.assertEqual(seg['change'],0.05) # not 0.10 for 06 and 07
        self.assertEqual(seg['illustrative_rate'],0.80)
        self.assertIn('06:00',seg['high_hours'])
        self.assertIn('07:00',seg['high_hours'])

    def test_low_on_adjacent_dates_yields_one_decrease(self):
        p=self.analyze()
        seg=next(s for s in p['segments'] if s['start']=='10:00')
        self.assertEqual(seg['action'],'low')
        self.assertEqual(seg['change'],-0.05)
        self.assertEqual(seg['illustrative_rate'],0.80)
        hour=p['hourly_evidence'][12]
        self.assertEqual(len(hour['low_consecutive_pairs']),1)

    def test_one_day_hourly_average_can_trigger(self):
        p=self.analyze()
        hour=p['hourly_evidence'][23]
        self.assertFalse(hour['two_high_days'])
        self.assertTrue(hour['overall_average_high'])
        seg=next(s for s in p['segments'] if s['start']=='22:00')
        self.assertEqual(seg['action'],'high')
        self.assertEqual(seg['change'],0.05)

    def test_conflicting_patterns_are_not_changed(self):
        p=self.analyze(conflict=True)
        seg=next(s for s in p['segments'] if s['start']=='06:00')
        self.assertEqual(seg['action'],'conflict')
        self.assertEqual(seg['change'],0.0)
        self.assertEqual(seg['illustrative_rate'],seg['original_rate'])

    def test_missing_edit_time_uses_all_libre_history_and_warns(self):
        result=analyze_files(libre_csv(),pump_csv())
        p=result['pattern']
        self.assertEqual(p['status'],'review_only_unknown_edit')
        self.assertIsNone(p['last_edit'])
        self.assertEqual(p['glucose_readings'],result['libre']['summary']['readings'])
        self.assertGreater(len(p['segments']),0)
        self.assertTrue(any('NOT verified' in w for w in p['warnings']))

    def test_explicit_export_event_anchors_analysis(self):
        p=self.analyze()
        self.assertEqual(p['anchor_source'],'explicit pump event')
        self.assertEqual(p['last_edit'],'2026-11-14 08:30')
        self.assertGreater(len(p['segments']),0)

    def test_no_manual_timestamp_input_field(self):
        html=(Path(__file__).resolve().parents[1]/'index.html').read_text()
        self.assertNotIn('id="basalEdit"',html)
        self.assertNotIn('Last basal profile edit</h2>',html)
        self.assertNotIn('form.append("last_basal_edit"',html)
        self.assertIn('checkConnection()',html)

    def test_streamed_files_and_upload_endpoint_two_files_only(self):
        p=analyze_files(io.BytesIO(libre_csv()),io.BytesIO(pump_csv()))
        self.assertEqual(p['pattern']['status'],'review_only_unknown_edit')
        with TestClient(app) as client:
            health=client.get('/api/health')
            self.assertEqual(health.status_code,200)
            homepage=client.get('/')
            self.assertEqual(homepage.status_code,200)
            self.assertNotIn('basalEdit',homepage.text)
            result=client.post('/api/analyze', files={
                'libre_file':('any_name.csv',libre_csv(),'text/csv'),
                'pump_file':('other_name.csv',pump_csv(),'text/csv')})
            self.assertEqual(result.status_code,200, result.text)
            self.assertEqual(result.json()['pattern']['segments_changed'],3)
            self.assertIsNone(result.json()['pattern']['last_edit'])


if __name__ == '__main__':
    unittest.main()
