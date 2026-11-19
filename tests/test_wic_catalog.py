import os
import sys
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from aktualizuj_katalog_wic import (
    parse_html,title_aliases,canonical,rows_compare,seed_models,get_ez_rows
)

class AuditTests(unittest.TestCase):
    @staticmethod
    def _xml_path():
        path = Path(os.environ.get("EZ_DEVICES_XML", Path(__file__).resolve().parents[1] / "src/ez_reset/devices.xml"))
        if not path.is_file():
            raise unittest.SkipTest("Repozytorium docelowe powinno zawierać oryginalny devices.xml")
        return path

    def test_aliased_models(self):
        aliases=title_aliases('Epson ET-2850/2851/2853/2855')
        self.assertTrue({'ET2850','ET2851','ET2853','ET2855'}<=aliases)
        self.assertTrue({'L3250','L3251','L3253','L3255'}<=title_aliases('Epson L3250/L3251/L3253/L3255'))

    def test_section_and_status_separation(self):
        html='''<h2>Canon printers</h2><p><a>TS5100 Series</a></p>
          <h2>Epson printers</h2><p>ET: <a href="/x">ET-2850</a>, <a>XP-2200</a></p>
          <h3>The reset and read counters function are NOT available for these models (adjustment functions only):</h3>
          <p><a>ET-2830</a></p><h3>The Reset function is NOT available. Reading counters and adjustments are available in these models:</h3>
          <p><a>WP-4010</a></p><h4>Company</h4><a href="/about">About WIC</a>'''
        self.assertEqual(parse_html(html), [('ET-2850','reset_wic'),('XP-2200','reset_wic'),
             ('ET-2830','bez_odczytu_reset'),('WP-4010','tylko_odczyt')])

    def test_nothing_invents_reset(self):
        r=ET.parse(self._xml_path()).getroot()
        rows=rows_compare(r,[('ET-2850','reset_wic'),('ET-2830','bez_odczytu_reset'),
                             ('L999999','reset_wic')],'test')
        by_name={r['wic_model']:r for r in rows}
        self.assertEqual(by_name['ET-2850']['ez_wynik'],'EZ_MA_RESET_I_ODCZYT')
        self.assertEqual(by_name['ET-2830']['ez_wynik'],'EZ_BRAK_KOMEND')
        self.assertEqual(by_name['L999999']['ez_wynik'],'BRAK_W_EZ')
        self.assertEqual(by_name['L999999']['do_weryfikacji'],'TAK')

    def test_ez_schema(self):
        r=ET.parse(self._xml_path()).getroot()
        entries=get_ez_rows(r)
        self.assertEqual(len(entries),1124)
        self.assertGreater(sum(1 for x in entries if x['reset'] and x['read']),700)

if __name__=='__main__':
    unittest.main(verbosity=2)
