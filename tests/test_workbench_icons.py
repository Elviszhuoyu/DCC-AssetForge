"""Geometry and matte regressions for the small workbench icons."""

import unittest

from PIL import Image, ImageDraw

from scripts.extract_workbench_icons import DESTINATION, ICON_NAMES, remove_matte


class WorkbenchIconTests(unittest.TestCase):
    def test_unmatte_keeps_holes_and_recovers_edge_color(self):
        matte = (28, 29, 33)
        ink = (196, 199, 203)
        cell = Image.new("RGB", (64, 64), matte)
        draw = ImageDraw.Draw(cell)
        draw.rectangle((14, 16, 49, 47), outline=ink, width=4)
        half_covered = tuple((a + b) // 2 for a, b in zip(matte, ink))
        cell.putpixel((13, 31), half_covered)
        glyph = remove_matte(cell)
        self.assertEqual(glyph.size, (37, 32))
        self.assertEqual(glyph.getpixel((18, 16))[3], 0)
        edge = glyph.getpixel((0, 15))
        self.assertEqual(edge[:3], ink)
        self.assertAlmostEqual(edge[3], 128, delta=2)

    def test_each_shipped_png_has_centered_padded_coverage(self):
        for name in ICON_NAMES:
            with self.subTest(icon=name), Image.open(DESTINATION / (name + ".png")) as icon:
                self.assertEqual((icon.mode, icon.size), ("RGBA", (64, 64)))
                alpha = icon.getchannel("A")
                left, top, right, bottom = alpha.getbbox()
                self.assertGreaterEqual(min(left, top, 64 - right, 64 - bottom), 8)
                self.assertLessEqual(abs(left - (64 - right)), 1)
                self.assertLessEqual(abs(top - (64 - bottom)), 1)
                self.assertEqual(alpha.getextrema(), (0, 255))
                self.assertTrue(any(0 < coverage < 255 for coverage in alpha.getdata()))


if __name__ == "__main__":
    unittest.main()
