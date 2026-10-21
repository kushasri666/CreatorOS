"""Prevent visible UTF-8/Windows-1252 corruption in shipped UI assets; no AI."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FrontendEncodingTests(unittest.TestCase):
    def test_served_ui_assets_are_utf8_without_known_mojibake_sequences(self):
        # Match sequences, not individual accented characters or valid Unicode.
        symbols = "\u00b7\u00d7\u2013\u2014\u2019\u2026\u2197\u21b3\u26f6\u2713\u2192\u2212\u2161\u25b7\u2194"
        corrupted = [symbol.encode("utf-8").decode("cp1252") for symbol in symbols]
        for path in [ROOT / "studio.html", *sorted((ROOT / "static").glob("*.js"))]:
            with self.subTest(asset=path.name):
                text = path.read_text(encoding="utf-8", errors="strict")
                self.assertNotIn("\ufffd", text, "Unicode replacement character in shipped UI")
                for sequence in corrupted:
                    self.assertNotIn(sequence, text, "Double-decoded punctuation: " + ascii(sequence))

    def test_html_declares_utf8_for_user_facing_unicode_labels(self):
        html = (ROOT / "studio.html").read_text(encoding="utf-8")
        self.assertIn('<meta charset="utf-8">', html.lower())


if __name__ == "__main__":
    unittest.main()
