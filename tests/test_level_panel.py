"""Guard against displaying unknown Epson readings as 0%."""
import unittest
from types import SimpleNamespace

from ez_reset.level_panel import (
    build_ink_cards, ink_reading, requires_manual_tank_check, waste_reading,
)


class TestLevelReadings(unittest.TestCase):
    def test_ink_levels(self):
        self.assertEqual(ink_reading(0), (0.0, "0%"))
        self.assertEqual(ink_reading(42), (42.0, "42%"))
        self.assertEqual(ink_reading(100), (100.0, "100%"))
        for value in (-1, 101, 105, 110, None, True):
            self.assertEqual(ink_reading(value), (None, "Brak danych"))

    def test_waste_levels(self):
        self.assertEqual(waste_reading(0, 100), (0.0, "0 / 100", "W normie"))
        self.assertEqual(waste_reading(69, 100)[2], "W normie")
        self.assertEqual(waste_reading(70, 100)[2], "Uwaga")
        self.assertEqual(waste_reading(90, 100)[2], "Krytyczny")
        self.assertEqual(waste_reading(115, 100)[0], 115.0)
        self.assertEqual(waste_reading(5, 0)[0], None)
        self.assertEqual(waste_reading(-1, 100)[0], None)
        self.assertEqual(waste_reading(5, None)[0], None)



class TestTankDisplay(unittest.TestCase):
    @staticmethod
    def status(**levels):
        return SimpleNamespace(levels=[
            SimpleNamespace(color=SimpleNamespace(name=name), level=level)
            for name, level in levels.items()
        ])

    def test_model_identification(self):
        for name in ("L3150", "EPSON L3150 Series", "Epson L3150", "Epson L3150 series"):
            self.assertTrue(requires_manual_tank_check(name))
        for name in ("L31500", "L3151", "L3250", "EPSON ET-3150", ""):
            self.assertFalse(requires_manual_tank_check(name))

    def test_l3150_without_ink_telemetry_shows_four_manual_tanks(self):
        cards = build_ink_cards("EPSON L3150 Series", self.status())
        self.assertEqual([c.name for c in cards], ["BLACK", "CYAN", "MAGENTA", "YELLOW"])
        self.assertTrue(all(c.manual and c.percent is None for c in cards))
        self.assertTrue(all(c.amount == "Sprawdź w zbiorniku" for c in cards))

    def test_l3150_unknown_values_are_not_zero(self):
        cards = build_ink_cards("L3150", self.status(BLACK=-1, CYAN=105, MAGENTA=110))
        self.assertTrue(all(c.percent is None and c.manual for c in cards))

    def test_valid_reported_values_are_preserved(self):
        cards = build_ink_cards("L3150", self.status(BLACK=42, CYAN=0))
        self.assertEqual([c.percent for c in cards], [42.0, 0.0, None, None])
        self.assertEqual([c.manual for c in cards], [False, False, True, True])
        self.assertEqual([c.amount for c in cards[:2]], ["42%", "0%"])

    def test_other_models_do_not_get_synthetic_ink_cards(self):
        self.assertEqual(build_ink_cards("L3250", self.status()), [])
        cards = build_ink_cards("L3250", self.status(BLACK=105, CYAN=35))
        self.assertEqual(len(cards), 2)
        self.assertFalse(any(c.manual for c in cards))
        self.assertEqual(cards[0].amount, "Brak danych")
        self.assertEqual(cards[1].percent, 35.0)

    def test_communication_error_does_not_create_manual_cards(self):
        self.assertEqual(build_ink_cards("L3150", None), [])



if __name__ == "__main__":
    unittest.main()
