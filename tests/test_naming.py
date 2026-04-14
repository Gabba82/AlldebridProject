import unittest

from app.utils.naming import build_strm_path, classify_media, clean_release_name


class NamingTests(unittest.TestCase):
    def test_clean_release_name_removes_noise(self) -> None:
        cleaned = clean_release_name("The.Matrix.1999.1080p.BluRay.x264-TEST.mkv")
        self.assertEqual(cleaned, "The Matrix 1999 TEST")

    def test_classify_series(self) -> None:
        result = classify_media("Severance.S02E03.1080p.WEB-DL.mkv")
        self.assertEqual(result.media_type, "series")
        self.assertEqual(result.title, "Severance")
        self.assertEqual(result.season, 2)
        self.assertEqual(result.episode, 3)

    def test_classify_movie(self) -> None:
        result = classify_media("Dune Part Two 2024 2160p WEB-DL.mkv")
        self.assertEqual(result.media_type, "movie")
        self.assertEqual(result.title, "Dune Part Two")
        self.assertEqual(result.year, 2024)

    def test_build_strm_path_for_series(self) -> None:
        result = classify_media("Show.S01E02.mkv")
        path = build_strm_path(result)
        self.assertEqual(path.as_posix(), "Series/Show/Season 01/Show - s01e02.strm")


if __name__ == "__main__":
    unittest.main()
