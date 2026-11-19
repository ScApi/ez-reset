import sys
import tempfile
import types
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from ez_reset.maintenance import (PrintQueue, fit_logo_size, normalize_model, recommend_queue, print_test_page)
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
                print_test_page('EPSON Test', color=color, model_name='L3150')
                self.assertIn('start', calls)
                self.assertIn('end', calls)
                self.assertIn('finish', calls)
                self.assertIn('delete', calls)
                self.assertIn(('text', 'RAPORT JAKOŚCI WYDRUKU'), calls)
                self.assertIn(('text', 'Drukarka: L3150'), calls)
                self.assertTrue(any(item[0] == 'text' and item[1].startswith('Data: ')
                                    for item in calls if isinstance(item, tuple)))
                self.assertEqual(sum(c[0] == 'fill' for c in calls if isinstance(c, tuple)), 12 if color else 8)
        finally:
            for k, v in old.items():
                if v is None: sys.modules.pop(k, None)
                else: sys.modules[k] = v



class ReportLogoTests(unittest.TestCase):
    def test_fit_logo_size_preserves_aspect_and_does_not_enlarge(self):
        self.assertEqual(fit_logo_size((1000, 500), (100, 100)), (100, 50))
        self.assertEqual(fit_logo_size((500, 1000), (100, 100)), (50, 100))
        self.assertEqual(fit_logo_size((20, 10), (100, 100)), (20, 10))
        with self.assertRaises(ValueError):
            fit_logo_size((0, 10), (100, 100))

    def test_optional_logo_is_drawn_in_report_header(self):
        calls = []

        class FakeImage:
            def __init__(self, size=(800, 400)):
                self.size = size
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def convert(self, _mode): return self
            def resize(self, size, _resample):
                self.size = size
                return self

        image_module = types.ModuleType('PIL.Image')
        image_module.open = lambda _path: FakeImage()
        image_module.new = lambda _mode, size, _fill: FakeImage(size)
        image_module.alpha_composite = lambda background, _image: FakeImage(background.size)
        image_module.Resampling = types.SimpleNamespace(LANCZOS=1)

        class FakeDib:
            def __init__(self, image): self.size = image.size
            def draw(self, _hdc, rect): calls.append(('logo', rect))

        image_win_module = types.ModuleType('PIL.ImageWin')
        image_win_module.Dib = FakeDib
        pil_module = types.ModuleType('PIL')
        pil_module.Image = image_module
        pil_module.ImageWin = image_win_module

        class FakeDC:
            def CreatePrinterDC(self, _queue): pass
            def GetDeviceCaps(self, idx): return 1200 if idx == 1 else 1600
            def GetHandleOutput(self): return 'HDC'
            def StartDoc(self, _name): pass
            def StartPage(self): pass
            def TextOut(self, *_args): pass
            def FillSolidRect(self, *_args): pass
            def EndPage(self): pass
            def EndDoc(self): pass
            def DeleteDC(self): pass

        fakeprint = types.SimpleNamespace(OpenPrinter=lambda q: q, ClosePrinter=lambda _h: None,
                                          GetPrinter=lambda h, _level: {'pPrinterName': h})
        fakeui = types.SimpleNamespace(CreateDC=lambda: FakeDC())
        fakecon = types.SimpleNamespace(HORZRES=1, VERTRES=2)
        names = ('PIL', 'PIL.Image', 'PIL.ImageWin', 'win32print', 'win32ui', 'win32con')
        old = {name: sys.modules.get(name) for name in names}
        sys.modules.update({
            'PIL': pil_module, 'PIL.Image': image_module, 'PIL.ImageWin': image_win_module,
            'win32print': fakeprint, 'win32ui': fakeui, 'win32con': fakecon,
        })
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp:
                temp_path = temp.name
            print_test_page('EPSON Test', color=False, model_name='L3150', logo_path=temp_path)
            self.assertEqual(calls, [('logo', (90, 90, 273, 182))])
        finally:
            if temp_path:
                from pathlib import Path
                Path(temp_path).unlink(missing_ok=True)
            for name, module in old.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module



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
