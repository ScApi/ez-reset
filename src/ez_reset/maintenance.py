"""Windows spooler integration for EZ-Reset maintenance test pages.

The selected Windows queue is separate from a USBPRINT interface. Never use the
system default printer implicitly: the caller must pass the exact queue name.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


def normalize_model(label: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", label.upper().removeprefix("EPSON "))


@dataclass(frozen=True)
class PrintQueue:
    name: str
    port: str
    driver: str

    @property
    def label(self) -> str:
        return f"{self.name}  ·  {self.port}"


def get_print_queues() -> list[PrintQueue]:
    """Return Epson queues installed in Windows (no USBPRINT guessing)."""
    import win32print  # imported lazily so model utilities can be unit-tested anywhere

    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    queues = []
    for item in win32print.EnumPrinters(flags, None, 2):
        name = item.get("pPrinterName", "")
        driver = item.get("pDriverName", "")
        if "epson" in (name + " " + driver).lower():
            queues.append(PrintQueue(name, item.get("pPortName", ""), driver))
    return sorted(queues, key=lambda item: item.name.casefold())


def recommend_queue(queues: list[PrintQueue], usb_model: str) -> int | None:
    """Only return an automatic match when it is unambiguous.

    Does not determine physical USB identity: the operator confirms the queue.
    """
    needle = normalize_model(usb_model).removesuffix("SERIES")
    if not needle or len(needle) < 3:
        return None
    matches = [idx for idx, q in enumerate(queues) if needle in normalize_model(q.name)]
    return matches[0] if len(matches) == 1 else None


def open_printer_preferences(queue_name: str) -> None:
    """Open the Epson driver GUI. Nozzle Check is on its Maintenance tab.

    This deliberately does not claim that a driver UI operation was executed.
    """
    import subprocess

    if not queue_name or '\x00' in queue_name:
        raise ValueError("Nie wybrano kolejki drukarki.")
    # Running PrintUIEntry as arguments avoids shell quoting/injection problems.
    subprocess.Popen(["rundll32.exe", "printui.dll,PrintUIEntry", "/e", "/n", queue_name])


def fit_logo_size(image_size: tuple[int, int], max_size: tuple[int, int]) -> tuple[int, int]:
    """Fit a logo inside a bounding box without distorting or enlarging it."""
    image_width, image_height = image_size
    max_width, max_height = max_size
    if min(image_width, image_height, max_width, max_height) <= 0:
        raise ValueError("Nieprawidłowy rozmiar logo.")
    scale = min(max_width / image_width, max_height / image_height, 1.0)
    return max(1, round(image_width * scale)), max(1, round(image_height * scale))


def _prepare_logo(logo_path: str | None, max_size: tuple[int, int]):
    """Load PNG/JPEG/BMP and prepare a white-backed, aspect-safe Windows DIB."""
    if not logo_path:
        return None
    path = Path(logo_path)
    if not path.is_file():
        raise FileNotFoundError(f"Nie znaleziono pliku logo: {path}")
    try:
        from PIL import Image, ImageWin

        with Image.open(path) as source:
            rgba = source.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        image = Image.alpha_composite(background, rgba).convert("RGB")
        size = fit_logo_size(image.size, max_size)
        if image.size != size:
            image = image.resize(size, Image.Resampling.LANCZOS)
        return ImageWin.Dib(image), size
    except Exception as exc:
        raise ValueError(f"Nie można wczytać logo '{path}'. Użyj poprawnego pliku PNG, JPG lub BMP. {exc}") from exc


def print_test_page(
    queue_name: str,
    *,
    color: bool,
    model_name: str = "",
    logo_path: str | None = None,
) -> None:
    """Print a branded print-quality report using the selected Windows GDI queue.

    The optional logo is embedded in the report header. This is a normal Windows
    print job, not a nozzle check or calibration operation.
    """
    if not queue_name:
        raise ValueError("Wybierz kolejkę drukarki Windows.")
    import win32ui
    import win32con
    import win32print

    handle = win32print.OpenPrinter(queue_name)
    try:
        info = win32print.GetPrinter(handle, 2)
        if info.get("pPrinterName") != queue_name:
            raise RuntimeError("Nazwa kolejki drukarki nie zgadza się z wybraną.")
    finally:
        win32print.ClosePrinter(handle)

    dc = win32ui.CreateDC()
    try:
        dc.CreatePrinterDC(queue_name)
        width = dc.GetDeviceCaps(win32con.HORZRES)
        height = dc.GetDeviceCaps(win32con.VERTRES)
        if width <= 0 or height <= 0:
            raise RuntimeError("Sterownik nie zwrócił poprawnego rozmiaru strony.")
        margin = int(min(width, height) * 0.075)
        left, right = margin, width - margin
        top = margin
        logo_limit = (max(1, int((right - left) * 0.18)), max(1, int(height * 0.08)))
        prepared_logo = _prepare_logo(logo_path, logo_limit)

        dc.StartDoc("EZ-Reset - Raport jakosci wydruku")
        try:
            dc.StartPage()
            title_x = left
            if prepared_logo:
                logo, (logo_width, logo_height) = prepared_logo
                logo.draw(dc.GetHandleOutput(), (left, top, left + logo_width, top + logo_height))
                title_x = left + logo_width + max(12, int(height * 0.012))

            dc.TextOut(title_x, top, "RAPORT JAKOŚCI WYDRUKU")
            dc.TextOut(title_x, top + int(height * 0.035),
                       "Drukarka: " + (model_name.strip()[:90] if model_name.strip() else "Nie wykryto modelu"))
            dc.TextOut(title_x, top + int(height * 0.060),
                       "Data: " + datetime.now().strftime("%d.%m.%Y  %H:%M"))
            dc.TextOut(left, top + int(height * 0.095),
                       "Rodzaj testu: " + ("KOLOROWY" if color else "CZARNO-BIAŁY"))
            dc.TextOut(left, top + int(height * 0.125), "-" * 72)
            dc.TextOut(left, top + int(height * 0.145),
                       "WZORZEC KONTROLNY — " + ("CMYK / RGB" if color else "SKALA SZAROŚCI"))

            y = top + int(height * 0.18)
            size = max(18, int((right - left) / 8))
            # win32api RGB = 0x00BBGGRR
            def rgb(r, g, b):
                return r | (g << 8) | (b << 16)

            shades = [(v, v, v) for v in range(0, 256, 32)]
            swatches = ([(0, 0, 0), (0, 255, 255), (255, 0, 255),
                         (255, 255, 0), (255, 0, 0), (0, 255, 0),
                         (0, 0, 255), (255, 255, 255)] if color else shades)
            for i, (r, g, b) in enumerate(swatches):
                x0 = left + i * (right - left) // 8
                x1 = left + (i + 1) * (right - left) // 8
                dc.FillSolidRect((x0, y, x1, y + size), rgb(r, g, b))
            for i in range(13):
                yy = y + size + int(height * (0.045 + i * 0.032))
                dc.TextOut(left, yy, f"{i + 1:02d}  ABCDEFGHIJKLMNOPQRSTUVWXYZ  1234567890")
            if color:
                for row, (r, g, b) in enumerate(((0, 255, 255), (255, 0, 255), (255, 255, 0), (0, 0, 0))):
                    yy = int(height * 0.72) + row * int(height * 0.046)
                    dc.FillSolidRect((left, yy, right, yy + int(height * 0.032)), rgb(r, g, b))
            dc.TextOut(left, height - margin * 2,
                       "EZ-Reset  |  Kolejka: " + queue_name[:55] + "  |  Raport jakości wydruku")
            dc.EndPage()
        finally:
            dc.EndDoc()
    finally:
        dc.DeleteDC()


def nozzle_check_payload() -> bytes:
    """Documented legacy Epson ESC/P2 Remote Mode nozzle-check command.

    References: Ircama/epson_escp2, check_nozzles(type=0). This is NOT a
    universal Epson command and is not equivalent to a printer's USB D4 service
    channel. Users must opt in for a legacy ESC/P2-capable queue.
    """
    exit_packet_mode = b"\x00\x00\x00\x1b\x01@EJL 1284.4\n@EJL     \n"
    enter_remote = b"\x1b@\x1b@\x1b(R\x08\x00\x00REMOTE1"
    nozzle = b"NC\x02\x00\x00\x00"
    exit_remote = b"\x1b\x00\x00\x00"
    job_end = b"JE\x01\x00\x00"
    return exit_packet_mode + enter_remote + nozzle + exit_remote + job_end


def print_raw_nozzle_check(queue_name: str) -> int:
    """Enqueue a legacy ESC/P2 nozzle check via Windows RAW spooler.

    Returns a spooler job ID, NOT confirmation from the printer that it ran.
    Caller must perform model suitability check/confirmation before calling.
    """
    if not queue_name:
        raise ValueError("Nie wybrano kolejki drukarki.")
    import win32print
    handle = win32print.OpenPrinter(queue_name)
    try:
        job_id = win32print.StartDocPrinter(handle, 1, ("EZ-Reset / ESC-P2 Nozzle Check", None, "RAW"))
        try:
            win32print.StartPagePrinter(handle)
            try:
                payload = nozzle_check_payload()
                written = win32print.WritePrinter(handle, payload)
                if written != len(payload):
                    raise OSError(f"Niepełny zapis RAW: {written} / {len(payload)} bajtów")
            finally:
                win32print.EndPagePrinter(handle)
        finally:
            win32print.EndDocPrinter(handle)
        return job_id
    finally:
        win32print.ClosePrinter(handle)
