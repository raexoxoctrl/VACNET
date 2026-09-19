import unittest

from app.tunnel import QUICK_TUNNEL_PATTERN


class TestTunnel(unittest.TestCase):
    def test_quick_tunnel_url_is_detected(self):
        line = "INF | Your quick Tunnel has been created! https://violet-sun.trycloudflare.com"
        match = QUICK_TUNNEL_PATTERN.search(line)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(0), "https://violet-sun.trycloudflare.com")

    def test_unrelated_url_is_ignored(self):
        self.assertIsNone(QUICK_TUNNEL_PATTERN.search("https://example.com"))


if __name__ == "__main__":
    unittest.main()
