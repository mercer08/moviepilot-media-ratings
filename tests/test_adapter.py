import importlib.util
from pathlib import Path
import unittest


BUILD_PATH = Path(__file__).parents[1] / "adapters/reverse-proxy/build_index.py"
SPEC = importlib.util.spec_from_file_location("media_ratings_build_index", BUILD_PATH)
BUILD = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(BUILD)


class AdapterBuilderTest(unittest.TestCase):
    def test_injects_versioned_script_and_dedicated_api_path(self):
        output = BUILD.inject("<!doctype html><html><head></head><body></body></html>")
        self.assertIn('/moviepilot-ratings/ratings.js?v=1.5.0', output)
        self.assertIn('data-api="/moviepilot-ratings/api/detail"', output)
        self.assertIn('data-episodes-api="/moviepilot-ratings/api/episodes"', output)
        self.assertIn('data-card-api="/moviepilot-ratings/api/card"', output)
        script = (BUILD_PATH.parent / "ratings.js").read_text()
        self.assertIn("['电影', 'movie', 'film']", script)
        self.assertIn("const CARD_SELECTOR = '.media-card'", script)
        self.assertIn("new IntersectionObserver", script)
        self.assertIn("CARD_CONCURRENCY = 2", script)
        plugin = (BUILD_PATH.parents[2] / "plugins.v2/mediaratings/__init__.py").read_text()
        self.assertIn('"path": "/card"', plugin)
        self.assertIn("asyncio.Semaphore(3)", plugin)
        self.assertLess(output.index("ratings.js"), output.index("</head>"))

    def test_rejects_duplicate_injection(self):
        with self.assertRaises(ValueError):
            BUILD.inject('<head><script src="/moviepilot-ratings/ratings.js"></script></head>')

    def test_rejects_invalid_index(self):
        with self.assertRaises(ValueError):
            BUILD.inject("<html><body></body></html>")


if __name__ == "__main__":
    unittest.main()
