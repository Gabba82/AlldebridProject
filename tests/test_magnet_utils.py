import unittest

from app.utils.magnet import extract_magnet_hash, magnet_display_name


class MagnetUtilsTests(unittest.TestCase):
    def test_extract_magnet_hash(self) -> None:
        magnet = "magnet:?xt=urn:btih:1234567890ABCDEF1234567890ABCDEF12345678&dn=Example"
        self.assertEqual(extract_magnet_hash(magnet), "1234567890abcdef1234567890abcdef12345678")

    def test_magnet_display_name(self) -> None:
        magnet = "magnet:?xt=urn:btih:1234567890ABCDEF1234567890ABCDEF12345678&dn=My%20Release"
        self.assertEqual(magnet_display_name(magnet), "My Release")


if __name__ == "__main__":
    unittest.main()
