import unittest
import urllib.error
from email.message import Message
from unittest.mock import patch

from core import updater


def _http_error(code, rate_limit_remaining=None):
    hdrs = Message()
    if rate_limit_remaining is not None:
        hdrs["X-RateLimit-Remaining"] = rate_limit_remaining
    return urllib.error.HTTPError(updater.API_LATEST_RELEASE_URL, code, "err", hdrs, None)


class UpdaterErrorTests(unittest.TestCase):
    def test_404_means_no_releases_published(self):
        with patch.object(updater, "_get_json", side_effect=_http_error(404)):
            self.assertIsNone(updater.get_remote_release())

    def test_403_with_exhausted_quota_is_a_clear_rate_limit_message(self):
        with patch.object(updater, "_get_json", side_effect=_http_error(403, rate_limit_remaining="0")):
            with self.assertRaises(RuntimeError) as ctx:
                updater.get_remote_release()
            self.assertIn("rate limit", str(ctx.exception).lower())

    def test_403_without_rate_limit_headers_is_not_swallowed(self):
        # A plain 403 that isn't a rate limit (e.g. abuse detection) shouldn't
        # be mislabeled - it should surface as the original HTTPError.
        with patch.object(updater, "_get_json", side_effect=_http_error(403)):
            with self.assertRaises(urllib.error.HTTPError):
                updater.get_remote_release()

    def test_check_for_update_surfaces_rate_limit_as_error_dict(self):
        with patch.object(updater, "is_frozen", return_value=False), \
             patch.object(updater, "get_remote_release", side_effect=RuntimeError("GitHub API rate limit exceeded for your network - try again later.")):
            result = updater.check_for_update()
            self.assertIn("rate limit", result.get("error", "").lower())


if __name__ == "__main__":
    unittest.main()
