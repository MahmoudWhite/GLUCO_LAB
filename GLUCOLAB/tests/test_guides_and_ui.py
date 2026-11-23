"""Regressions for the file-download help pages and navigation changes."""
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from app import app

ROOT = Path(__file__).resolve().parents[1]

class GuideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_guides_return_documented_download_steps(self):
        libre = self.client.get('/how-to/libre')
        pump = self.client.get('/how-to/pump')
        self.assertEqual(libre.status_code, 200)
        self.assertEqual(pump.status_code, 200)
        self.assertIn('Download Glucose Data', libre.text)
        self.assertIn('Data Export (CSV)', pump.text)
        self.assertIn('href="/"', libre.text)
        self.assertIn('href="/"', pump.text)

    def test_method_links_and_simplified_file_copy(self):
        html = (ROOT / 'index.html').read_text(encoding='utf-8')
        self.assertEqual(html.count('Show Method</a>'), 2)
        self.assertIn('href="/?guide=libre"', html)
        self.assertIn('href="/?guide=pump"', html)
        self.assertIn('Choose a raw, timestamped glucose data file', html)
        self.assertIn('Choose a timestamped pump basal-rate export', html)
        self.assertNotIn('The app automatically locates the header and uses Record Type 0.', html)
        self.assertNotIn('Basal Rate (U/h) columns.', html)
        # The guide URL is handled by the same root page; no new backend routes,
        # popup permissions, or extra browser tabs are needed.
        for which in ('libre', 'pump'):
            page = self.client.get('/?guide='+which)
            self.assertEqual(page.status_code, 200)
            self.assertIn('id="'+which+'Guide"', page.text)
        self.assertNotIn('target="_blank" rel="noopener noreferrer" aria-label="Show method', html)

    def test_navigation_and_footer(self):
        html = (ROOT / 'index.html').read_text(encoding='utf-8')
        self.assertEqual(html.count('id="changeMode"'), 1)
        self.assertGreater(html.index('id="changeMode"'), html.index('id="connectionStatus"'))
        self.assertIn('$("changeMode").hidden=false;', html)
        self.assertIn('$("changeMode").hidden=true;', html)
        self.assertIn('© 2026 GLUCOLAB.', html)
        self.assertIn('BY MAHMOUD ABIAD', html)
        self.assertNotIn('GLUCOLAB — Exploratory pattern software only.', html)
        self.assertIn('class="footer" aria-label="GLUCOLAB legal and attribution"', html)
        self.assertEqual(html.count('class="footer-line"'), 4)

if __name__ == '__main__':
    unittest.main()
