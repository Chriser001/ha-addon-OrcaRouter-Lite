import re
import unittest
from pathlib import Path

APP_JS = Path('design/app.js').read_text(encoding='utf-8')

REQUIRED_KEYS = {
    'auth.tagline','auth.welcome','auth.subtitle','auth.api_key','auth.continue','nav.search',
    'nav.overview','nav.providers','nav.routing','nav.analytics','nav.api_keys','nav.help_docs','nav.sign_out',
    'status.connected','status.disconnected','auth.checking','auth.welcome_aboard','auth.key_invalid',
}

class I18NTests(unittest.TestCase):
    def test_supported_locales_present(self):
        m = re.search(r'SUPPORTED_LOCALES\s*=\s*\[(.*?)\];', APP_JS, re.S)
        self.assertIsNotNone(m)
        locales = {s.strip().strip('"') for s in m.group(1).split(',') if s.strip()}
        self.assertEqual(locales, {'en','zh','hi','es','pt','ru','ja','de','fr','it','ar','ko'})

    def test_each_locale_has_required_keys(self):
        block = re.search(r'const I18N = \{(.*?)\n\};', APP_JS, re.S)
        self.assertIsNotNone(block)
        text = block.group(1)
        locale_blocks = re.findall(r'\n\s{2}([a-z]{2}):\s*\{(.*?)\},', text, re.S)
        self.assertEqual(len(locale_blocks), 12)
        for locale, body in locale_blocks:
            keys = set(re.findall(r'"([a-z0-9_.]+)"\s*:', body))
            missing = REQUIRED_KEYS - keys
            self.assertFalse(missing, f"{locale} missing keys: {sorted(missing)}")

    def test_required_keys_are_not_english_for_non_english_locales(self):
        block = re.search(r'const I18N = \{(.*?)\n\};', APP_JS, re.S)
        self.assertIsNotNone(block)
        text = block.group(1)
        locale_blocks = dict(re.findall(r'\n\s{2}([a-z]{2}):\s*\{(.*?)\},', text, re.S))
        en_values = dict(re.findall(r'"([a-z0-9_.]+)"\s*:\s*"([^"]*)"', locale_blocks["en"]))
        for locale, body in locale_blocks.items():
            if locale == "en":
                continue
            values = dict(re.findall(r'"([a-z0-9_.]+)"\s*:\s*"((?:[^"\\]|\\.)*)"', body))
            for key in REQUIRED_KEYS:
                self.assertIn(key, values)
                self.assertNotEqual(values[key], en_values.get(key), f"{locale} uses English fallback for {key}")

    def test_zh_covers_every_en_key(self):
        """zh is the only locale kept fully in sync with en — every en key must
        have a zh translation (the other 10 locales intentionally ship the
        small base set and fall back via t())."""
        block = re.search(r'const I18N = \{(.*?)\n\};', APP_JS, re.S)
        self.assertIsNotNone(block)
        text = block.group(1)
        locale_blocks = dict(re.findall(r'\n\s{2}([a-z]{2}):\s*\{(.*?)\},', text, re.S))
        en_keys = set(re.findall(r'"([a-z0-9_.]+)"\s*:', locale_blocks["en"]))
        zh_keys = set(re.findall(r'"([a-z0-9_.]+)"\s*:', locale_blocks["zh"]))
        self.assertEqual(en_keys, zh_keys, f"en/zh key drift: en-only={sorted(en_keys-zh_keys)} zh-only={sorted(zh_keys-en_keys)}")
        # zh values must not be verbatim English (spot obvious fallbacks)
        zh_vals = dict(re.findall(r'"([a-z0-9_.]+)"\s*:\s*"((?:[^"\\]|\\.)*)"', locale_blocks["zh"]))
        # keys whose zh value is legitimately identical ASCII (pure code/product terms)
        ascii_exceptions = {"ui.routing.map_litellm"}
        for k, v in zh_vals.items():
            if k in ascii_exceptions:
                continue
            self.assertFalse(v and re.fullmatch(r'[\x20-\x7e]+', v), f"zh value still pure ASCII (untranslated?): {k}={v!r}")

if __name__ == '__main__':
    unittest.main()
