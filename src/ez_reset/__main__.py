"""Polish maintenance UI for EZ-Reset. Run with: python -m ez_reset"""
from __future__ import annotations

import json
import logging
import re
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import messagebox, ttk

from ez_reset.d4 import D4ControlBackend
from ez_reset.devices import Device, by_model
from ez_reset.level_panel import StatusLevelsPanel
from ez_reset.maintenance import (
    get_print_queues, open_printer_preferences, print_test_page,
    print_raw_nozzle_check, recommend_queue,
)
from ez_reset.printer import Printer
from ez_reset.utils import parse_identifier
from ez_reset.win_usbprint import USBPRINTTransport, enumerate_printers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
SETTINGS_FILE = Path.home() / ".ez_reset" / "settings.json"


def short_usb_path(path: str) -> str:
    """Human-friendly label, not a substitute for actual IEEE 1284 identification."""
    vid = re.search(r"vid_([a-fA-F0-9]{4})", path, re.I)
    pid = re.search(r"pid_([a-fA-F0-9]{4})", path, re.I)
    bits = re.split(r"[#\\]", path)
    candidate = next((b for b in bits if "epson" in b.casefold()), "USBPRINT")
    candidate = re.sub(r"[_]+", " ", candidate)
    candidate = candidate[-55:]
    usb = f"[{vid.group(1).upper()}:{pid.group(1).upper()}] " if vid and pid else ""
    return usb + candidate


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(data: dict) -> None:
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as err:
        logger.warning("Could not save preferences: %s", err)


class EzResetApp(ttk.Frame):
    def __init__(self, master: tk.Tk) -> None:
        super().__init__(master, padding=12)
        self.root = master
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="epson-usb")
        self.settings = load_settings()
        self._busy = False
        self._closing = False
        self.transport = None
        self.backend = None
        self.printer = None
        self.device = None
        self.identifier = {}
        self.paths: list[str] = []
        self.queues = []
        self.status_text = tk.StringVar(value="Gotowy. Wybierz drukarkę USB.")
        self.model_text = tk.StringVar(value="Brak połączenia")
        self.queue_text = tk.StringVar()
        self.buttons: list[ttk.Button] = []

        master.title("EZ-Reset — Serwis drukarek Epson")
        master.geometry(self.settings.get("geometry", "850x630"))
        master.minsize(740, 520)
        self.pack(fill="both", expand=True)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(header, text="EZ-Reset", font=("Segoe UI", 19, "bold")).pack(side="left")
        ttk.Label(header, text="USB • diagnostyka • konserwacja", foreground="#606060").pack(side="left", padx=16)

        self.tabs = ttk.Notebook(self)
        self.tabs.grid(row=1, column=0, sticky="nsew")
        self.tab_usb = ttk.Frame(self.tabs, padding=12)
        self.tab_status = ttk.Frame(self.tabs, padding=12)
        self.tab_maintenance = ttk.Frame(self.tabs, padding=12)
        self.tab_print = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(self.tab_usb, text="Połączenie USB")
        self.tabs.add(self.tab_status, text="Liczniki")
        self.tabs.add(self.tab_maintenance, text="Konserwacja")
        self.tabs.add(self.tab_print, text="Wydruki testowe")

        self._build_usb()
        self._build_status()
        self._build_maintenance()
        self._build_print()
        bottom = ttk.Frame(self)
        bottom.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Separator(bottom).pack(fill="x", pady=(0, 8))
        ttk.Label(bottom, textvariable=self.status_text, foreground="#345b7e").pack(side="left")
        self.progress = ttk.Progressbar(bottom, mode="indeterminate", length=110)
        self.progress.pack(side="right")
        self.progress.pack_forget()

        self.refresh_usb()
        self.refresh_queues()
        master.protocol("WM_DELETE_WINDOW", self.close)

    def _button(self, frame, label, callback, **kwargs):
        b = ttk.Button(frame, text=label, command=callback, **kwargs)
        self.buttons.append(b)
        return b

    def _build_usb(self):
        self.tab_usb.columnconfigure(0, weight=1)
        self.tab_usb.rowconfigure(2, weight=1)
        ttk.Label(self.tab_usb, text="Podłączone drukarki USB", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, sticky="w")
        ttk.Label(self.tab_usb, text="Wybierz interfejs urządzenia. Szczegóły USB widoczne poniżej.",
                  foreground="#666666").grid(row=1, column=0, sticky="w", pady=(3, 10))
        wrapper = ttk.Frame(self.tab_usb)
        wrapper.grid(row=2, column=0, sticky="nsew")
        wrapper.columnconfigure(0, weight=1)
        wrapper.rowconfigure(0, weight=1)
        self.usb_list = ttk.Treeview(wrapper, columns=("device", "usb"), show="headings", selectmode="browse")
        self.usb_list.heading("device", text="Urządzenie")
        self.usb_list.heading("usb", text="Interfejs / port USBPRINT")
        self.usb_list.column("device", width=250, stretch=False)
        self.usb_list.column("usb", width=480, stretch=True)
        self.usb_list.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(wrapper, orient="vertical", command=self.usb_list.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.usb_list.configure(yscrollcommand=scrollbar.set)
        self.usb_list.bind("<Double-1>", lambda _e: self.connect())
        actions = ttk.Frame(self.tab_usb)
        actions.grid(row=3, column=0, sticky="ew", pady=(12, 4))
        self._button(actions, "⟳  Odśwież USB", self.refresh_usb).pack(side="left")
        self._button(actions, "Połącz z wybraną drukarką", self.connect).pack(side="left", padx=(10, 0))
        self._button(actions, "Rozłącz", self.disconnect).pack(side="left", padx=(10, 0))
        ttk.Label(self.tab_usb, textvariable=self.model_text, font=("Segoe UI", 11, "bold")).grid(
            row=4, column=0, sticky="w", pady=(12, 0))

    def _build_status(self):
        self.tab_status.columnconfigure(0, weight=1)
        self.tab_status.rowconfigure(1, weight=1)
        bar = ttk.Frame(self.tab_status)
        bar.grid(row=0, column=0, sticky="ew")
        ttk.Label(bar, text="Stan drukarki i pochłaniacza", font=("Segoe UI", 12, "bold")).pack(side="left")
        self._button(bar, "Odśwież liczniki", self.refresh_status).pack(side="right")
        self.level_panel = StatusLevelsPanel(self.tab_status)
        self.level_panel.grid(row=1, column=0, sticky="nsew", pady=12)
        actions = ttk.Frame(self.tab_status)
        actions.grid(row=2, column=0, sticky="ew")
        self._button(actions, "Reset licznika pampersa (EEPROM)", self.reset_waste).pack(side="left")
        ttk.Label(self.tab_status,
                  text="Uwaga: reset nie wymienia ani nie czyści fizycznego pochłaniacza atramentu.",
                  foreground="#8a5220").grid(row=3, column=0, sticky="w", pady=(12, 0))

    def _build_maintenance(self):
        self.tab_maintenance.columnconfigure(0, weight=1)
        ttk.Label(self.tab_maintenance, text="Konserwacja głowicy", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 12))
        ttk.Label(self.tab_maintenance, wraplength=700, justify="left",
                  text="Test dysz: otwiera narzędzia producenta w preferencjach wskazanej kolejki Windows. "
                       "W oknie sterownika Epson wybierz zakładkę Konserwacja → Test dysz. "
                       "Obsługa zależy od zainstalowanego sterownika.").grid(row=1, column=0, sticky="w")
        row = ttk.Frame(self.tab_maintenance)
        row.grid(row=2, column=0, sticky="w", pady=(12, 22))
        self._button(row, "Test dysz (sterownik Epson)",
                     self.open_nozzle_utility).pack(side="left")
        self._button(row, "Test dysz bezpośredni (ESC/P2, eksperymentalny)",
                     self.direct_nozzle_check).pack(side="left", padx=(12, 0))
        ttk.Separator(self.tab_maintenance).grid(row=3, column=0, sticky="ew")
        ttk.Label(self.tab_maintenance,
                  text="Standardowe czyszczenie: wysyła istniejącą komendę serwisową USB (0x84, poziom 0). "
                       "Nie wszystkie modele muszą ją obsługiwać.",
                  wraplength=700, justify="left").grid(row=4, column=0, sticky="w", pady=(14, 8))
        self._button(self.tab_maintenance, "Wykonaj standardowe czyszczenie USB",
                     self.clean_head).grid(row=5, column=0, sticky="w", pady=6)
        ttk.Label(self.tab_maintenance, text="Brak funkcji głębokiego/power cleaning: to wymaga potwierdzenia dla modelu.",
                  foreground="#8a5220").grid(row=6, column=0, sticky="w", pady=(16, 0))

    def _build_print(self):
        self.tab_print.columnconfigure(0, weight=1)
        ttk.Label(self.tab_print, text="Kolejka Windows dla wydruków",
                  font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w")
        bar = ttk.Frame(self.tab_print)
        bar.grid(row=1, column=0, sticky="ew", pady=(14, 8))
        bar.columnconfigure(0, weight=1)
        self.queue_picker = ttk.Combobox(bar, textvariable=self.queue_text, state="readonly")
        self.queue_picker.grid(row=0, column=0, sticky="ew")
        self._button(bar, "⟳  Odśwież", self.refresh_queues).grid(row=0, column=1, padx=(8, 0))
        ttk.Label(self.tab_print,
                  text="Wybór kolejki jest niezależny od portu USBPRINT. Potwierdź, że odpowiada tej samej drukarce.",
                  wraplength=710, foreground="#8a5220").grid(row=2, column=0, sticky="w", pady=(5, 22))
        row = ttk.Frame(self.tab_print)
        row.grid(row=3, column=0, sticky="w")
        self._button(row, "Drukuj test CZARNO-BIAŁY", lambda: self.do_test_print(False)).pack(side="left")
        self._button(row, "Drukuj test KOLOROWY", lambda: self.do_test_print(True)).pack(side="left", padx=12)
        ttk.Label(self.tab_print,
                  text="Testy używają zwykłego sterownika Windows (GDI). Nie są testem dysz ani kalibracją drukarki.",
                  wraplength=710).grid(row=4, column=0, sticky="w", pady=18)

    def _write_readout(self, lines):
        self.level_panel.show_message(lines)

    def _set_busy(self, is_busy: bool):
        self._busy = is_busy
        for button in self.buttons:
            button.configure(state="disabled" if is_busy else "normal")
        if is_busy:
            self.progress.pack(side="right")
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.pack_forget()

    def _submit(self, label, operation, success=None):
        if self._busy or self._closing:
            return
        self._set_busy(True)
        self.status_text.set(label + "…")
        future = self.executor.submit(operation)

        def completed(fut):
            try:
                self.root.after(0, lambda: self._resolve(fut, label, success))
            except (RuntimeError, tk.TclError):
                pass  # UI was already destroyed

        future.add_done_callback(completed)

    def _resolve(self, fut, label, success):
        if self._closing:
            return
        self._set_busy(False)
        try:
            result = fut.result()
            self.status_text.set(label + " — gotowe.")
            if success is not None:
                success(result)
        except Exception as err:
            logger.exception("%s", label)
            self.status_text.set("Błąd: " + str(err)[:130])
            messagebox.showerror("EZ-Reset", f"{label}\n\n{err}", parent=self.root)

    def refresh_usb(self):
        def on_success(paths):
            self.paths = paths
            self.usb_list.delete(*self.usb_list.get_children())
            for idx, path in enumerate(paths):
                self.usb_list.insert("", "end", iid=str(idx), values=(short_usb_path(path), path))
            previous = self.settings.get("usb_path")
            if previous in paths:
                self.usb_list.selection_set(str(paths.index(previous)))
            elif len(paths) == 1:
                self.usb_list.selection_set("0")
            if not paths:
                self.status_text.set("Nie wykryto drukarki USBPRINT. Sprawdź kabel i sterownik Epson.")
        self._submit("Skanowanie interfejsów USB", lambda: list(enumerate_printers()), on_success)

    def refresh_queues(self):
        try:
            self.queues = get_print_queues()
            names = [q.label for q in self.queues]
            self.queue_picker["values"] = names
            selected = self.settings.get("queue_name")
            idx = next((i for i, q in enumerate(self.queues) if q.name == selected), None)
            if idx is not None:
                self.queue_picker.current(idx)
            elif not names:
                self.queue_text.set("")
            elif len(names) == 1:
                self.queue_picker.current(0)
            else:
                self.queue_text.set("")
        except Exception as err:
            self.status_text.set("Brak dostępu do kolejek drukowania: " + str(err))

    def selected_path(self):
        selection = self.usb_list.selection()
        if not selection:
            raise ValueError("Najpierw wybierz drukarkę USB z listy.")
        return self.paths[int(selection[0])]

    def selected_queue(self):
        idx = self.queue_picker.current()
        if not (0 <= idx < len(self.queues)):
            raise ValueError("Wybierz konkretną kolejkę drukarki z listy Windows.")
        self.settings["queue_name"] = self.queues[idx].name
        save_settings(self.settings)
        return self.queues[idx].name

    def _disconnect_worker(self):
        try:
            if self.backend:
                self.backend.__exit__(None, None, None)
        finally:
            self.backend = None
            try:
                if self.transport:
                    self.transport.__exit__(None, None, None)
            finally:
                self.transport = self.printer = self.device = None
                self.identifier = {}

    def connect(self):
        try:
            path = self.selected_path()
        except ValueError as err:
            messagebox.showwarning("USB", str(err), parent=self.root)
            return

        def operation():
            self._disconnect_worker()
            transport = USBPRINTTransport(path)
            try:
                transport.__enter__()
                backend = D4ControlBackend(transport)
                try:
                    backend.__enter__()
                    identifier = parse_identifier(backend.identify())
                    model = identifier.get("MDL", "").strip()
                    try:
                        device = by_model(model)
                        profile_found = True
                    except (AttributeError, LookupError, ValueError):
                        device = Device(model=b"", key=b"", counters=[], reset={})
                        profile_found = False
                    self.transport, self.backend = transport, backend
                    self.device = device
                    self.identifier = identifier
                    self.printer = Printer(backend, device)
                    return identifier, profile_found
                except Exception:
                    # The backend might not have opened a channel: best-effort cleanup.
                    if backend.channel is not None:
                        backend.__exit__(None, None, None)
                    raise
            except Exception:
                if transport.handle is not None:
                    transport.__exit__(None, None, None)
                raise

        def success(result):
            ident, known = result
            self.model_text.set(f"Połączono: {ident.get('DES') or ident.get('MDL') or 'Epson'}"
                                + ("  |  profil EZ-Reset znaleziony" if known else
                                   "  |  brak potwierdzonego profilu EEPROM"))
            self.settings["usb_path"] = path
            save_settings(self.settings)
            self.refresh_queues()
            # Ink levels are readable even if the model has no EEPROM reset profile.
            self.tabs.select(self.tab_status)
            self.refresh_status()
            suggested = recommend_queue(self.queues, ident.get("MDL", ""))
            if suggested is not None and not self.settings.get("queue_name"):
                self.queue_picker.current(suggested)

        self._submit("Łączenie przez USB", operation, success)

    def disconnect(self):
        def success(_):
            self.model_text.set("Rozłączono")
            self._write_readout(["Brak połączenia z drukarką."])
        self._submit("Rozłączanie USB", self._disconnect_worker, success)

    def refresh_status(self):
        if self.printer is None:
            self.status_text.set("Najpierw połącz drukarkę USB.")
            return

        def operation():
            state, waste, state_error, waste_error = None, [], "", ""
            try:
                state = self.printer.get_status()
            except Exception as exc:
                logger.warning("Odczyt poziomów tuszu nieudany: %s", exc)
                state_error = str(exc)
            if self.device and self.device.counters and self.device.model:
                try:
                    waste = self.printer.get_waste()
                except Exception as exc:
                    logger.warning("Odczyt pochłaniacza nieudany: %s", exc)
                    waste_error = str(exc)
            return state, waste, state_error, waste_error

        def success(data):
            state, waste, state_error, waste_error = data
            self.level_panel.show_levels(
                self.identifier.get("MDL", "?"), state, waste,
                status_error=state_error, waste_error=waste_error,
                profile_available=bool(self.device and self.device.model),
            )
            if state_error and waste_error:
                self.status_text.set("Nie udało się odczytać stanu ani liczników; sprawdź połączenie.")
        self._submit("Odczyt stanu drukarki", operation, success)

    def reset_waste(self):
        if not self.printer or not self.device or not self.device.reset or not self.device.model:
            messagebox.showwarning("Reset", "Brak potwierdzonej konfiguracji resetu dla tej drukarki.",
                                   parent=self.root)
            return
        text = ("ZRESETOWAĆ licznik EEPROM?\n\nNajpierw wymień lub wyczyść pochłaniacz. "
                "Operacja zapisuje pamięć drukarki i może być nieodwracalna. "
                "Program zapisze kopię zmienianych komórek EEPROM i zweryfikuje każdy zapis.")
        if not messagebox.askyesno("Potwierdzenie resetu EEPROM", text, parent=self.root):
            return

        def operation():
            import datetime
            old = {addr: self.printer.read_eeprom(addr) for addr in self.device.reset}
            backup = Path.home() / ".ez_reset" / "backups"
            backup.mkdir(parents=True, exist_ok=True)
            serial = re.sub(r"[^A-Za-z0-9_-]", "_", self.identifier.get("SN", "unknown"))[:50]
            date = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            path = backup / f"backup_{serial}_{date}.json"
            path.write_text(json.dumps({"device": self.identifier,
                                        "before": {hex(k): v for k, v in old.items()}},
                                       indent=2, ensure_ascii=False), encoding="utf-8")
            for addr, value in self.device.reset.items():
                self.printer.write_eeprom(addr, value)
                actual = self.printer.read_eeprom(addr)
                if actual != value:
                    raise RuntimeError(f"Błąd weryfikacji EEPROM na {addr:#06x}: "
                                       f"oczekiwano {value:#04x}, otrzymano {actual:#04x}. "
                                       f"Przerwano kolejne zapisy! Kopia: {path}")
            return path

        def success(path):
            messagebox.showinfo("Reset zakończony", "Potwierdzono zapisy EEPROM. "
                                "Wyłącz i włącz drukarkę.\nKopia danych: " + str(path), parent=self.root)
            self.refresh_status()
        self._submit("Reset i weryfikacja EEPROM", operation, success)

    def clean_head(self):
        if not self.printer or not self.device or not self.device.model:
            messagebox.showwarning("Czyszczenie", "Połącz drukarkę z rozpoznanym profilem serwisowym.",
                                   parent=self.root)
            return
        if not messagebox.askyesno("Czyszczenie głowicy",
                                   "Uruchomić STANDARDOWE czyszczenie przez USB?\n"
                                   "Komenda serwisowa może nie działać na wszystkich modelach. "
                                   "Operacja zużywa tusz i zwiększa poziom licznika pampersa.",
                                   parent=self.root):
            return
        self._submit("Wysyłanie polecenia czyszczenia", lambda: self.printer.clean(0),
                     lambda _result: messagebox.showinfo("Czyszczenie", "Polecenie wysłano. "
                                                       "Sprawdź na drukarce, czy cykl rzeczywiście ruszył.",
                                                       parent=self.root))

    def open_nozzle_utility(self):
        try:
            queue_name = self.selected_queue()
        except ValueError as err:
            messagebox.showwarning("Drukarka Windows", str(err), parent=self.root)
            self.tabs.select(self.tab_print)
            return
        def operation():
            if self.printer:
                self._disconnect_worker()
            open_printer_preferences(queue_name)

        def success(_):
            self.model_text.set("Odłączono USB. W sterowniku uruchom test dysz.")
            messagebox.showinfo("Test dysz", "Otwarto preferencje sterownika. "
                                "Wybierz Konserwacja → Test dysz. "
                                "Przycisk nie wykonuje wydruku automatycznie.", parent=self.root)
        self._submit("Otwieranie konserwacji Epson", operation, success)

    def direct_nozzle_check(self):
        try:
            queue_name = self.selected_queue()
        except ValueError as err:
            messagebox.showwarning("Test dysz", str(err), parent=self.root)
            return
        if not messagebox.askyesno("Test dysz ESC/P2",
                                   "Eksperymentalna funkcja dla drukarek Epson obsługujących "
                                   "polecenia ESC/P2 Remote Mode.\n\n"
                                   "Nie każda drukarka/sterownik przekaże RAW bez zmian. "
                                   "Wysłanie danych do kolejki NIE potwierdza wydruku. "
                                   f"\n\nDrukarka Windows: {queue_name}\n\nKontynuować?",
                                   parent=self.root):
            return

        def operation():
            if self.printer:
                self._disconnect_worker()
            return print_raw_nozzle_check(queue_name)

        def success(job_id):
            self.model_text.set("Rozłączono USB podczas wysyłania testu RAW.")
            messagebox.showinfo("Test dysz ESC/P2", f"Zadanie nr {job_id} dodano do kolejki. "
                                "Sprawdź na drukarce, czy test się wydrukował.", parent=self.root)
        self._submit("Wysyłanie testu dysz ESC/P2", operation, success)

    def do_test_print(self, color):
        try:
            queue_name = self.selected_queue()
        except ValueError as err:
            messagebox.showwarning("Wydruk", str(err), parent=self.root)
            return
        if not messagebox.askyesno("Wydruk testowy", f"Wydrukować test "
                                   f"{'kolorowy' if color else 'czarno-biały'} na:\n{queue_name}?",
                                   parent=self.root):
            return
        if self.printer:
            # Release USBPRINT before Windows spooler tries to print on the device.
            def action():
                self._disconnect_worker()
                print_test_page(queue_name, color=color)
            self._submit("Wydruk testowy (USB odłączone)", action, lambda _:
                         self.model_text.set("USB rozłączono na czas wydruku. Połącz ponownie."))
        else:
            self._submit("Wydruk testowy", lambda: print_test_page(queue_name, color=color))

    def close(self):
        if self._closing:
            return
        self.settings["geometry"] = self.root.geometry()
        save_settings(self.settings)
        self._closing = True
        self.executor.submit(self._disconnect_worker)
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def main():
    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    EzResetApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
