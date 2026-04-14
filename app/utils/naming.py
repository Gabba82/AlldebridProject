from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from app.models import ClassificationResult

YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2}|21\d{2})\b")
SEASON_EPISODE_RE = re.compile(r"(?i)\bS(\d{1,2})E(\d{1,3})\b")
X_RE = re.compile(r"(?i)\b(\d{1,2})x(\d{1,3})\b")
SEASON_WORD_RE = re.compile(r"(?i)\b(?:season|temporada)[ ._-]?(\d{1,2})\b")
EPISODE_WORD_RE = re.compile(r"(?i)\b(?:episode|episodio|ep)[ ._-]?(\d{1,3})\b")
TAG_RE = re.compile(
    r"(?i)\b("
    r"2160p|1080p|720p|480p|x264|x265|h\.?264|h\.?265|hevc|hdr|dv|ddp\d\.\d|"
    r"bluray|brrip|bdrip|webrip|web-dl|webdl|remux|proper|repack|multi|dubbed|"
    r"subs?|yts|rarbg|amzn|nf|dsnp|aac\d\.\d|dts|ac3|10bit"
    r")\b"
)
BRACKET_RE = re.compile(r"[\[\(\{].*?[\]\)\}]")
SEPARATORS_RE = re.compile(r"[._]+")
MULTISPACE_RE = re.compile(r"\s+")


def _ascii_clean(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def clean_release_name(raw_name: str) -> str:
    stem = Path(raw_name).stem
    stem = _ascii_clean(stem)
    stem = SEPARATORS_RE.sub(" ", stem)
    stem = stem.replace("-", " ")
    stem = BRACKET_RE.sub(" ", stem)
    stem = TAG_RE.sub(" ", stem)
    stem = MULTISPACE_RE.sub(" ", stem).strip(" -._")
    return stem.strip()


def classify_media(filename: str) -> ClassificationResult:
    cleaned = clean_release_name(filename)
    reasons: list[str] = []

    if match := SEASON_EPISODE_RE.search(cleaned):
        title = cleaned[: match.start()].strip(" -")
        reasons.append("matched_sxxexx")
        return ClassificationResult(
            media_type="series",
            title=title or "Unknown Series",
            season=int(match.group(1)),
            episode=int(match.group(2)),
            confidence=0.95,
            reasons=reasons,
        )

    if match := X_RE.search(cleaned):
        title = cleaned[: match.start()].strip(" -")
        reasons.append("matched_nxnn")
        return ClassificationResult(
            media_type="series",
            title=title or "Unknown Series",
            season=int(match.group(1)),
            episode=int(match.group(2)),
            confidence=0.92,
            reasons=reasons,
        )

    season_match = SEASON_WORD_RE.search(cleaned)
    episode_match = EPISODE_WORD_RE.search(cleaned)
    if season_match and episode_match:
        reasons.append("matched_words")
        return ClassificationResult(
            media_type="series",
            title=cleaned[: season_match.start()].strip(" -") or "Unknown Series",
            season=int(season_match.group(1)),
            episode=int(episode_match.group(1)),
            confidence=0.8,
            reasons=reasons,
        )

    if match := YEAR_RE.search(cleaned):
        title = cleaned[: match.start()].strip(" -")
        reasons.append("matched_year")
        return ClassificationResult(
            media_type="movie",
            title=title or cleaned,
            year=int(match.group(1)),
            confidence=0.8,
            reasons=reasons,
        )

    reasons.append("fallback_movie")
    review_needed = len(cleaned.split()) < 2
    return ClassificationResult(
        media_type="movie",
        title=cleaned or "Unknown Title",
        confidence=0.5,
        review_needed=review_needed,
        reasons=reasons,
    )


def build_strm_path(result: ClassificationResult) -> Path:
    title = sanitize_path_component(result.title)
    if result.media_type == "series":
        season = result.season or 1
        episode = result.episode or 1
        folder = Path("Series") / title / f"Season {season:02d}"
        filename = f"{title} - s{season:02d}e{episode:02d}.strm"
        return folder / filename
    year_suffix = f" ({result.year})" if result.year else ""
    movie_dir = Path("Peliculas") / f"{title}{year_suffix}"
    movie_file = f"{title}{year_suffix}.strm"
    return movie_dir / movie_file


def sanitize_path_component(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*]', " ", value)
    value = MULTISPACE_RE.sub(" ", value).strip(" .")
    return value or "Unknown"
