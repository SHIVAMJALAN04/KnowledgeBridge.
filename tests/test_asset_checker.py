import unittest
from pathlib import Path

from utils.asset_checker import (
    ASSET_SIMILARITY_THRESHOLD,
    compare_images,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSETS = PROJECT_ROOT / "assets"


class AssetCheckerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.approved = (ASSETS / "demo_approved_logo.png").read_bytes()
        cls.modified = (ASSETS / "demo_modified_logo.png").read_bytes()

    def test_identical_asset_has_100_percent_similarity(self):
        result = compare_images(self.approved, self.approved)
        self.assertEqual(result["similarity_score"], 100.0)
        self.assertTrue(result["exact_match"])
        self.assertTrue(result["is_match"])

    def test_modified_demo_asset_is_flagged(self):
        result = compare_images(self.approved, self.modified)
        self.assertLess(result["similarity_score"], ASSET_SIMILARITY_THRESHOLD)
        self.assertFalse(result["is_match"])

    def test_invalid_image_bytes_raise_value_error(self):
        with self.assertRaises(ValueError):
            compare_images(b"not an image", self.approved)


if __name__ == "__main__":
    unittest.main()
