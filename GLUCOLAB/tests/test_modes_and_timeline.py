"""Tests added for dual-device modes, 24-hour timeline and graph continuity."""
import io
import unittest
from datetime import datetime, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import analyze_libre_only, analyze_files, app, LibreAnalyzer, build_meal_timeline
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]

def libre_csv(rows):
    header="LibreView export\nDevice Timestamp,Record Type,Historic Glucose (mg/dL)\n"
    return (header+'\n'.join(f"{stamp.strftime('%d/%m/%Y %H:%M:%S')},0,{value}" for stamp,value in rows)).encode()

class ModeAndTimelineTests(unittest.TestCase):
    def test_libre_only_endpoint_single_csv(self):
        client=TestClient(app)
        payload=(ROOT/'samples/example_libreview.csv').read_bytes()
        r=client.post('/api/analyze',data={'mode':'libre'},files={'libre_file':('libre.csv',payload,'text/csv')})
        self.assertEqual(r.status_code,200,r.text)
        result=r.json()
        self.assertEqual(result['mode'],'libre')
        self.assertIsNone(result['pump'])
        self.assertIsNone(result['pattern'])
        meals=result['meal_timeline']
        self.assertEqual([x['meal'] for x in meals['periods']],
                         ['Breakfast', 'Morning snack', 'Lunch', 'Afternoon snack', 'Dinner', 'Evening snack'])
        self.assertEqual(len(meals['half_hourly']), 48)
        self.assertEqual(meals['threshold_mgdl'], 230)
        self.assertTrue(any(x['end_hour']-x['start_hour']>=5 for x in meals['periods']))
        self.assertIn('Do not delay meals',meals['notice'])

    def test_both_mode_preserves_response(self):
        client=TestClient(app)
        a=(ROOT/'samples/example_libreview.csv').read_bytes()
        b=(ROOT/'samples/example_medtronic.csv').read_bytes()
        r=client.post('/api/analyze',data={'mode':'both'},files={
            'libre_file':('libre.csv',a,'text/csv'),
            'pump_file':('medtronic.csv',b,'text/csv')})
        self.assertEqual(r.status_code,200,r.text)
        response=r.json()
        self.assertEqual(response['mode'],'both')
        self.assertIsNotNone(response['pump'])
        self.assertIsNotNone(response['pattern'])
        self.assertIsNone(response['meal_timeline'])

    def test_pump_mode_requires_pump_csv(self):
        client=TestClient(app)
        payload=(ROOT/'samples/example_libreview.csv').read_bytes()
        response=client.post('/api/analyze',data={'mode':'both'},files={'libre_file':('libre.csv',payload,'text/csv')})
        self.assertEqual(response.status_code,422)
        self.assertIn('requires both',response.json()['error'])

    def test_5_minute_readings_are_connected_and_gap_is_preserved(self):
        start=datetime(2026,11,6,0,0)
        rows=[(start+timedelta(minutes=i*5), 115+i%20) for i in range(24*12*14)]
        # The missing hour should create exactly one line break.
        rows=[r for r in rows if not (start+timedelta(days=2,hours=4)<=r[0]<start+timedelta(days=2,hours=5))]
        result=analyze_libre_only(io.BytesIO(libre_csv(rows)))
        trend=result['libre']['trend']
        self.assertGreater(len(trend),3000)
        self.assertEqual(sum(r['break_before'] for r in trend),2)
        self.assertLess(len(trend),12001)

    def test_no_data_does_not_claim_meal_is_safe(self):
        payload=(ROOT/'samples/example_libreview.csv').read_bytes()
        output=analyze_libre_only(io.BytesIO(payload))
        meals=output['meal_timeline']
        labels=[r['status'] for r in meals['half_hourly']]
        self.assertIn('insufficient',labels)
        self.assertIn('a list of times when eating is safe or forbidden',meals['notice'])
        for period in meals['periods']:
            self.assertGreater(len(period['ranges']),0)

    def test_ui_removes_requested_sections_and_has_explanation_dialog(self):
        html=(ROOT/'index.html').read_text()
        for heading in ('Pump basal-rate entries</h3>','Medtronic rate ranges / source records','Why these hours were flagged'):
            self.assertNotIn(heading,html)
        for expected in ('sensorOptions','pumpOptions','continueSetup','mealTrack','Explain modifications','modDialog','pumpUpload'):
            self.assertIn(expected,html)

if __name__ == '__main__':
    unittest.main()
