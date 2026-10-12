"""Guard against displaying unknown Epson readings as 0%."""
import unittest

from ez_reset.level_panel import ink_reading, waste_reading


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


if __name__ == "__main__":
    unittest.main()
