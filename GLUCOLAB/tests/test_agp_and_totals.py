"""New AGP-style profile and duration-weighted daily candidate basal totals."""
import io
import math
import sys
import unittest
from datetime import datetime,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import analyze_libre_only, analyze_files, integrated_daily_basal

ROOT=Path(__file__).resolve().parents[1]

class ProfileAndTotalsTests(unittest.TestCase):
    def make_libre(self,days=14):
        lines=['Export','Device Timestamp,Record Type,Historic Glucose (mg/dL)']
        start=datetime(2026,11,6)
        for day in range(days):
            for index in range(288):
                t=start+timedelta(days=day,minutes=index*5)
                minute=t.hour*60+t.minute
                val=round(145+28*math.sin(2*math.pi*(minute-270)/1440)+day*0.9,2)
                lines.append(f'{t:%d/%m/%Y %H:%M:%S},0,{val}')
        return ('\n'.join(lines)+'\n').encode()

    def test_agp_bins_have_correct_percentile_order_and_counts(self):
        output=analyze_libre_only(io.BytesIO(self.make_libre()))
        bins=output['libre']['agp']['bins']
        self.assertEqual(len(bins),48)
        self.assertEqual([x['minute'] for x in bins],list(range(0,1440,30)))
        self.assertTrue(all(b['days']==14 for b in bins))
        self.assertTrue(all(b['readings']==84 for b in bins))
        for b in bins:
            self.assertLessEqual(b['p05'],b['p25'])
            self.assertLessEqual(b['p25'],b['p50'])
            self.assertLessEqual(b['p50'],b['p75'])
            self.assertLessEqual(b['p75'],b['p95'])

    def test_agp_sparse_bins_are_null(self):
        output=analyze_libre_only(io.BytesIO(self.make_libre(days=1)))
        self.assertTrue(all(b['p50'] is None for b in output['libre']['agp']['bins']))

    def test_duration_weighted_total_not_sum_of_rates(self):
        rows=[
            {'start':'00:00','end':'03:00','original_rate':1.75,'illustrative_rate':1.80},
            {'start':'03:00','end':'07:00','original_rate':1.90,'illustrative_rate':1.95},
            {'start':'07:00','end':'10:00','original_rate':2.30,'illustrative_rate':2.35},
            {'start':'10:00','end':'16:30','original_rate':2.10,'illustrative_rate':2.15},
            {'start':'16:30','end':'20:00','original_rate':2.20,'illustrative_rate':2.25},
            {'start':'20:00','end':'24:00','original_rate':2.35,'illustrative_rate':2.40},
        ]
        expected=sum((end-start)*r['original_rate'] for start,end,r in
            [(0,3,rows[0]),(3,7,rows[1]),(7,10,rows[2]),(10,16.5,rows[3]),(16.5,20,rows[4]),(20,24,rows[5])])
        self.assertAlmostEqual(integrated_daily_basal(rows,'original_rate'),expected,places=3)
        self.assertAlmostEqual(integrated_daily_basal(rows,'illustrative_rate'),expected+1.2,places=3)

    def test_missing_interval_or_end_is_not_an_estimated_total(self):
        self.assertIsNone(integrated_daily_basal([{'start':'00:00','end':'03:00','original_rate':1.7}], 'original_rate'))
        self.assertIsNone(integrated_daily_basal([{'start':'00:00','end':'03:00','original_rate':1.7},
            {'start':'04:00','end':'24:00','original_rate':1.8}],'original_rate'))

    def test_combined_analysis_contains_totals_and_agp(self):
        a=(ROOT/'samples/example_libreview.csv').read_bytes()
        b=(ROOT/'samples/example_medtronic.csv').read_bytes()
        result=analyze_files(a,b)
        p=result['pattern']
        self.assertAlmostEqual(p['observed_daily_basal_u'],18.1,places=3)
        self.assertAlmostEqual(p['illustrative_daily_basal_u'],17.8,places=3)
        self.assertAlmostEqual(p['illustrative_daily_difference_u'],-.3,places=3)
        self.assertEqual(len(result['libre']['agp']['bins']),48)
        self.assertIn('Estimated 24-hour candidate total',result['report'])
        self.assertIn('Illustrative 24-hour total',result['report'])

    def test_html_column_order_and_chart_panel(self):
        html=(ROOT/'index.html').read_text()
        self.assertIn('<th>Observed U/h</th><th>Illustrative U/h</th><th>Simulated step</th>',html)
        self.assertIn('Glucose patterns · 24-hour profile (AGP-style)',html)
        self.assertIn('candidateTotal',html)
        self.assertIn('illustrativeTotal',html)

if __name__=='__main__':
    unittest.main()
