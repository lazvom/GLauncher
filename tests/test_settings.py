import json
import os
import tempfile
import unittest

from core.settings import DEFAULT_THEME, THEMES, Settings


class SettingsThemeTests(unittest.TestCase):
    def test_defaults_to_default_theme(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(Settings(tmp).theme, DEFAULT_THEME)

    def test_round_trips_a_valid_theme(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Settings(tmp)
            s.theme = THEMES[-1]
            s.save()
            self.assertEqual(Settings(tmp).theme, THEMES[-1])

    def test_rejects_unknown_theme_from_disk(self):
        # A hand-edited (or tampered) settings.json shouldn't be able to put
        # an arbitrary string into what api.get_settings() hands back to the
        # page - it ends up on the <html> element's data-theme attribute.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "settings.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"theme": "<script>alert(1)</script>"}, f)
            self.assertEqual(Settings(tmp).theme, DEFAULT_THEME)

    def test_brand_new_install_is_not_onboarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(Settings(tmp).onboarded)

    def test_completing_onboarding_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Settings(tmp)
            s.onboarded = True
            s.save()
            self.assertTrue(Settings(tmp).onboarded)

    def test_pre_existing_settings_file_is_not_re_onboarded(self):
        # An update from a version that predates onboarding shouldn't make an
        # existing player sit through the first-run intro screen.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "settings.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"ram_min_mb": 2048}, f)  # no "onboarded" key at all
            self.assertTrue(Settings(tmp).onboarded)


if __name__ == "__main__":
    unittest.main()
