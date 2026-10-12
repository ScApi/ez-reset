import sys
import types
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from ez_reset.maintenance import PrintQueue, normalize_model, recommend_queue, print_test_page
from ez_reset.wic_catalog import candidate_info


class MaintenanceTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_model('Epson ET-2850 Series'), 'ET2850SERIES')
        self.assertEqual(normalize_model('EPSON L3250'), 'L3250')

    def test_only_unambiguous_queue(self):
        queues = [PrintQueue('EPSON L3250 Series', 'USB001', 'EPSON ESC/P-R'),
                  PrintQueue('EPSON ET-2850', 'USB002', 'EPSON ESC/P-R')]
        self.assertEqual(recommend_queue(queues, 'L3250 Series'), 0)
        self.assertIsNone(recommend_queue(queues, 'L3251'))
        self.assertIsNone(recommend_queue(queues + [queues[0]], 'L3250 Series'))

    def test_wic_is_not_a_reset_profile(self):
        item = candidate_info('Epson EP-774A')
        self.assertIsNotNone(item)
        self.assertEqual(item['eeprom_verified'], 'false')
        self.assertEqual(item['ez_reset_enabled'], 'false')
        self.assertIsNone(candidate_info('Not a printer 4444'))

    def test_print_requires_selected_queue(self):
        with self.assertRaises(ValueError):
            print_test_page('', color=False)

    def test_gdi_render_mono_and_color(self):
        calls = []
        class FakeDC:
            def CreatePrinterDC(self, q): calls.append(('printer', q))
            def GetDeviceCaps(self, idx): return 1200 if idx == 1 else 1600
            def StartDoc(self, name): calls.append(('doc', name))
            def StartPage(self): calls.append('start')
            def TextOut(self, x, y, s): calls.append(('text', s))
            def FillSolidRect(self, rect, rgb): calls.append(('fill', rgb))
            def EndPage(self): calls.append('end')
            def EndDoc(self): calls.append('finish')
            def DeleteDC(self): calls.append('delete')
        fakeprint = types.SimpleNamespace(OpenPrinter=lambda q: q, ClosePrinter=lambda h: None,
                 GetPrinter=lambda h, level: {'pPrinterName': h})
        fakeui = types.SimpleNamespace(CreateDC=lambda: FakeDC())
        fakecon = types.SimpleNamespace(HORZRES=1, VERTRES=2)
        old = {k: sys.modules.get(k) for k in ('win32print', 'win32ui', 'win32con')}
        sys.modules.update({'win32print': fakeprint, 'win32ui': fakeui, 'win32con': fakecon})
        try:
            for color in (False, True):
                calls.clear()
                print_test_page('EPSON Test', color=color)
                self.assertIn('start', calls)
                self.assertIn('end', calls)
                self.assertIn('finish', calls)
                self.assertIn('delete', calls)
                self.assertEqual(sum(c[0] == 'fill' for c in calls if isinstance(c, tuple)), 12 if color else 8)
        finally:
            for k, v in old.items():
                if v is None: sys.modules.pop(k, None)
                else: sys.modules[k] = v


if __name__ == '__main__':
    unittest.main()

class NozzleTests(unittest.TestCase):
    def test_nozzle_payload(self):
        from ez_reset.maintenance import nozzle_check_payload
        data = nozzle_check_payload()
        self.assertIn(b'\x1b(R\x08\x00\x00REMOTE1', data)
        self.assertIn(b'NC\x02\x00\x00\x00', data)
        self.assertTrue(data.endswith(b'JE\x01\x00\x00'))

    def test_raw_spooler_job(self):
        from ez_reset.maintenance import nozzle_check_payload, print_raw_nozzle_check
        calls = []
        printer = types.SimpleNamespace(OpenPrinter=lambda q: q,
                                        StartDocPrinter=lambda h, l, doc: (calls.append(doc), 22)[1],
                                        StartPagePrinter=lambda h: calls.append('start'),
                                        WritePrinter=lambda h, data: (calls.append(data), len(data))[1],
                                        EndPagePrinter=lambda h: calls.append('end'),
                                        EndDocPrinter=lambda h: calls.append('finish'),
                                        ClosePrinter=lambda h: calls.append('close'))
        old = sys.modules.get('win32print')
        sys.modules['win32print'] = printer
        try:
            self.assertEqual(print_raw_nozzle_check('Epson Queue'), 22)
            self.assertIn(nozzle_check_payload(), calls)
            self.assertEqual(calls[-3:], ['end', 'finish', 'close'])
        finally:
            if old is None: sys.modules.pop('win32print', None)
            else: sys.modules['win32print'] = old
