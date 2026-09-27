import io
import tempfile
import unittest
import zipfile

from core.patch_sanitize import sanitize_patch_html
from core.security import is_https_host, safe_filename, validate_instance_id
from core.updater import _safe_extract_zip


class SecurityTests(unittest.TestCase):
    def test_patch_html_is_sanitized(self):
        html = (
            '<p>Hello <strong>world</strong></p>'
            '<script>alert(1)</script>'
            '<img src="https://launchercontent.mojang.com/v2/x.png" onerror="alert(2)">'
            '<img src="https://evil.example/x.png">'
        )
        result = sanitize_patch_html(html, 'https://launchercontent.mojang.com')
        self.assertIn('<strong>world</strong>', result)
        self.assertNotIn('<script', result)
        self.assertNotIn('onerror', result)
        self.assertNotIn('evil.example', result)

    def test_filename_and_instance_validation(self):
        self.assertEqual(safe_filename('test.jar'), 'test.jar')
        for value in ('../evil.jar', 'a/b.jar', r'..\evil.jar', '/evil.jar', 'C:evil.jar', '', '..'):
            with self.assertRaises(ValueError):
                safe_filename(value)
        for value in ('../x', 'ABC', 'a/b', ''):
            with self.assertRaises(ValueError):
                validate_instance_id(value)

    def test_modrinth_download_host_policy(self):
        self.assertTrue(is_https_host('https://cdn.modrinth.com/data/x/y.jar', {'cdn.modrinth.com'}))
        self.assertFalse(is_https_host('http://cdn.modrinth.com/data/x/y.jar', {'cdn.modrinth.com'}))
        self.assertFalse(is_https_host('https://evil.example/y.jar', {'cdn.modrinth.com'}))

    def test_zip_slip_is_rejected(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as zf:
            zf.writestr('../../evil.txt', 'owned')
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                _safe_extract_zip(archive.getvalue(), tmp)


if __name__ == '__main__':
    unittest.main()
