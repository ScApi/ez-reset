"""Visual ink and waste-counter indicators for EZ-Reset.

Values are obtained from Printer.get_status() and Printer.get_waste().
An unavailable value is never interpreted as zero.
"""
from __future__ import annotations

import re
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk

INK_COLORS = {
    "BLACK": ("Czarny · BK", "#313942"),
    "CYAN": ("Cyjan · C", "#06a7c9"),
    "MAGENTA": ("Magenta · M", "#c73c93"),
    "YELLOW": ("Żółty · Y", "#dfa900"),
    "LIGHT_CYAN": ("Jasny cyjan · LC", "#68c9e1"),
    "LIGHT_MAGENTA": ("Jasna magenta · LM", "#e58bc1"),
    "DARK_YELLOW": ("Ciemny żółty", "#b88b08"),
    "GRAY": ("Szary", "#7a8592"),
    "LIGHT_BLACK": ("Jasny czarny", "#68717a"),
    "RED": ("Czerwony", "#cf4141"),
    "BLUE": ("Niebieski", "#3974c2"),
    "GLOSS_OPTIMIZER": ("Optymalizator połysku", "#73818f"),
    "LIGHT_GRAY": ("Jasny szary", "#a4aeb6"),
    "ORANGE": ("Pomarańczowy", "#db781d"),
}



# Epson L3150 / EcoTank: no reliable ink percentages in the reported status
# when EPSON Status Monitor instructs users to check the physical reservoirs.
# Extend only with verified models; a missing percentage must not become 0%.
MANUAL_TANK_MODELS = frozenset({"L3150"})
BASIC_INKS = ("BLACK", "CYAN", "MAGENTA", "YELLOW")


@dataclass(frozen=True)
class InkCard:
    """Data to display for one cartridge or tank, independent of Tk."""
    name: str
    percent: float | None
    amount: str
    color: str
    manual: bool = False


def requires_manual_tank_check(model: str) -> bool:
    """Match the actual model token (e.g. 'EPSON L3150 Series'), not L31500."""
    return any(re.search(rf"(?<![A-Z0-9]){re.escape(token)}(?![A-Z0-9])",
                         model or "", re.IGNORECASE) for token in MANUAL_TANK_MODELS)


def build_ink_cards(model: str, status: object | None) -> list[InkCard]:
    """Preserve reported values and mark unavailable EcoTank levels as manual.

    Called only for successfully parsed status responses. If status could not be
    fetched, return no cards so the caller can display a communication error.
    """
    if status is None:
        return []
    reported: list[InkCard] = []
    for ink in getattr(status, "levels", None) or ():
        name = getattr(getattr(ink, "color", None), "name", "UNKNOWN")
        _, color = INK_COLORS.get(name, (name, "#73818f"))
        percent, amount = ink_reading(getattr(ink, "level", None))
        reported.append(InkCard(name, percent, amount, color))

    if not requires_manual_tank_check(model):
        return reported

    result: list[InkCard] = []
    for name in BASIC_INKS:
        current = next((card for card in reported if card.name == name), None)
        if current is not None and current.percent is not None:
            result.append(current)
        else:
            result.append(InkCard(name, None, "Sprawdź w zbiorniku",
                                  INK_COLORS[name][1], manual=True))
    result.extend(card for card in reported if card.name not in BASIC_INKS)
    return result

def ink_reading(level: object) -> tuple[float | None, str]:
    """Return percentage and label; out-of-range readings are unknown."""
    if isinstance(level, bool) or not isinstance(level, (int, float)) or not 0 <= level <= 100:
        return None, "Brak danych"
    return float(level), f"{level:g}%"


def waste_reading(count: object, maximum: object) -> tuple[float | None, str, str]:
    """Return percent (possibly above 100), detail, and state."""
    if (isinstance(count, bool) or not isinstance(count, int) or count < 0 or
            isinstance(maximum, bool) or not isinstance(maximum, int) or maximum <= 0):
        detail = f"Odczyt: {count}" if isinstance(count, int) and count >= 0 else "Brak odczytu"
        return None, f"{detail} · nieznany limit", "Brak danych"
    percent = 100 * count / maximum
    state = "Krytyczny" if percent >= 90 else "Uwaga" if percent >= 70 else "W normie"
    return percent, f"{count:,} / {maximum:,}".replace(",", " "), state


class _Meter(ttk.LabelFrame):
    """Resize-aware canvas bar whose color works across Windows ttk themes."""

    def __init__(self, parent, title: str, percent: float | None, amount: str,
                 color: str, detail: str = ""):
        super().__init__(parent, text=title, padding=(12, 9))
        self.columnconfigure(0, weight=1)
        upper = ttk.Frame(self)
        upper.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        upper.columnconfigure(0, weight=1)
        ttk.Label(upper, text=detail, foreground="#626b73").grid(row=0, column=0, sticky="w")
        ttk.Label(upper, text=amount, font=("Segoe UI", 11, "bold")).grid(row=0, column=1, sticky="e")
        self.bar = tk.Canvas(self, height=15, bg="#e1e5e9", highlightthickness=0, bd=0)
        self.bar.grid(row=1, column=0, sticky="ew")
        self.percent = percent
        self.color = color
        self.bar.bind("<Configure>", self._redraw)

    def _redraw(self, _event=None):
        width = self.bar.winfo_width()
        height = self.bar.winfo_height()
        self.bar.delete("all")
        self.bar.create_rectangle(0, 0, width, height, fill="#e1e5e9", outline="")
        if self.percent is not None:
            progress = max(0.0, min(100.0, self.percent))
            if progress > 0:
                self.bar.create_rectangle(0, 0, round(width * progress / 100), height,
                                          fill=self.color, outline="")



class _ManualTank(ttk.LabelFrame):
    """Colored swatch, never a filled meter that implies measured percentage."""

    def __init__(self, parent, title: str, color: str):
        super().__init__(parent, text=title, padding=(12, 12))
        row = ttk.Frame(self)
        row.pack(fill="x")
        swatch = tk.Canvas(row, width=29, height=34, highlightthickness=0, bd=0)
        swatch.pack(side="left", padx=(0, 12))
        swatch.create_rectangle(4, 2, 25, 31, fill=color, outline="#727b84", width=1)
        ttk.Label(row, text="Sprawdź w zbiorniku",
                  foreground="#8a5220", font=("Segoe UI", 10, "bold")).pack(
                      side="left", fill="x")


class StatusLevelsPanel(ttk.Frame):
    """Scrollable dashboard for any number of ink channels or waste counters."""

    def __init__(self, parent):
        super().__init__(parent)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.content = ttk.Frame(self.canvas, padding=(2, 8))
        self.content.columnconfigure(0, weight=1)
        self.window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", self._update_scroll)
        self.canvas.bind("<Configure>", self._update_width)
        self.show_message(["Połącz drukarkę USB, aby odczytać jej stan."])

    def _update_scroll(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _update_width(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _clear(self):
        for widget in self.content.winfo_children():
            widget.destroy()

    def show_message(self, lines):
        self._clear()
        ttk.Label(self.content, text="\n".join(lines), justify="left", wraplength=660,
                  font=("Segoe UI", 10)).grid(row=0, column=0, sticky="nw", pady=12)

    def show_levels(self, model: str, status: object | None,
                    waste: list[tuple[int, int]], status_error: str = "",
                    waste_error: str = "", profile_available: bool = True):
        self._clear()
        content = self.content
        row = 0
        ttk.Label(content, text=f"Model: {model or 'Nieznany'}", font=("Segoe UI", 11, "bold")).grid(
            row=row, column=0, sticky="w", pady=(0, 10))
        row += 1

        waste_group = ttk.LabelFrame(content, text="Zapełnienie pochłaniacza (pampersa)", padding=10)
        waste_group.grid(row=row, column=0, sticky="ew", pady=(0, 13))
        waste_group.columnconfigure(0, weight=1)
        row += 1
        if waste:
            for idx, (count, maximum) in enumerate(waste, 1):
                pct, detail, label = waste_reading(count, maximum)
                shade = "#c13d3d" if label == "Krytyczny" else "#dd980c" if label == "Uwaga" else "#39905a"
                if pct is None:
                    shade = "#98a1ab"
                amount = f"{pct:.1f}%" if pct is not None else "—"
                meter = _Meter(waste_group, f"Licznik {idx}", pct, amount, shade,
                               f"{detail} · {label}")
                meter.grid(row=idx-1, column=0, sticky="ew", pady=4)
        else:
            txt = ("Błąd odczytu licznika: " + waste_error if waste_error else
                   "Brak profilu EEPROM dla tego modelu." if not profile_available else
                   "Brak zdefiniowanych liczników dla tego modelu.")
            ttk.Label(waste_group, text=txt, wraplength=640).grid(row=0, column=0, sticky="w")
        ttk.Label(waste_group, text="Wskaźnik obliczany z EEPROM — nie jest pomiarem fizycznym.",
                  foreground="#6b7075").grid(row=len(waste) + 1, column=0, sticky="w", pady=(9, 0))

        inks_group = ttk.LabelFrame(content, text="Poziomy tuszu", padding=10)
        inks_group.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        inks_group.columnconfigure(0, weight=1)
        inks_group.columnconfigure(1, weight=1)
        row += 1
        # Display a communication error instead of hypothetical tank readings.
        cards = build_ink_cards(model, status) if not status_error else []
        if cards:
            for idx, ink in enumerate(cards):
                title, shade = INK_COLORS.get(
                    ink.name, (ink.name.replace("_", " ").title(), ink.color))
                if ink.manual:
                    card = _ManualTank(inks_group, title, shade)
                else:
                    card = _Meter(inks_group, title, ink.percent, ink.amount, shade)
                card.grid(row=idx // 2, column=idx % 2, sticky="ew", padx=4, pady=5)
            foot_row = (len(cards) + 1) // 2
        else:
            if status_error:
                message = "Błąd odczytu tuszu: " + status_error
            elif status is None:
                message = "Nie udało się uzyskać stanu drukarki."
            else:
                message = "Drukarka nie udostępniła poziomów tuszu."
            ttk.Label(inks_group, text=message, wraplength=620).grid(
                row=0, column=0, columnspan=2, sticky="w")
            foot_row = 1

        manual_cards = any(card.manual for card in cards)
        if manual_cards:
            note = ("W tym modelu brak wiarygodnego odczytu wybranych zbiorników. "
                    "Sprawdź ich poziomy wzrokowo; program nie szacuje procentów.")
        else:
            note = "Poziomy raportowane przez drukarkę (mogą być szacunkowe)."
        ttk.Label(inks_group, text=note, wraplength=620,
                  foreground="#6b7075").grid(
                      row=foot_row, column=0, columnspan=2, sticky="w", pady=(11, 0))

        if status is not None:
            state = getattr(getattr(status, "state", None), "name", "?")
            serial = getattr(status, "serial", "")
            ttk.Label(content, text=f"Stan: {state}     Numer seryjny: {serial or 'brak danych'}",
                      foreground="#626b73").grid(row=row, column=0, sticky="w")
        self.canvas.yview_moveto(0)
