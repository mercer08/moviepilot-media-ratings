"""Pure helpers for the MoviePilot multi-source detail ratings plugin."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional


def normalize_score(value: Any, scale: float = 10.0) -> Optional[float]:
    """Return a finite 0-10 score, accepting common percent/100 point scales."""

    if value in (None, "", "N/A", "null"):
        return None
    try:
        text = str(value).strip()
        if "/" in text:
            numerator, denominator = text.split("/", 1)
            score = float(numerator.strip())
            parsed_scale = float(denominator.strip())
            if parsed_scale > 0:
                scale = parsed_scale
        else:
            score = float(text.rstrip("%"))
    except (TypeError, ValueError):
        return None
    if scale <= 0:
        return None
    score = score * 10.0 / scale
    if not 0 < score <= 10:
        return None
    return round(score, 1)


def normalize_votes(value: Any) -> Optional[int]:
    if value in (None, "", "N/A"):
        return None
    try:
        votes = int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None
    return votes if votes >= 0 else None


def normalized_title(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^\w\u3040-\u30ff\u3400-\u9fff]+", "", text)


def card_lookup_title(value: Any) -> str:
    """Remove an explicit trailing season label without changing real titles."""

    title = unicodedata.normalize("NFKC", str(value or "")).strip()
    season_suffix = re.compile(
        r"\s*(?:第\s*[零〇一二三四五六七八九十百两0-9]+\s*季|season\s*[0-9]+|s[0-9]{1,3})\s*$",
        re.IGNORECASE,
    )
    stripped = season_suffix.sub("", title).strip()
    return stripped or title


def year_from_date(value: Any) -> Optional[int]:
    match = re.search(r"\b(19|20)\d{2}\b", str(value or ""))
    return int(match.group(0)) if match else None


def select_bangumi_subject(
    candidates: Iterable[Dict[str, Any]],
    titles: Iterable[str],
    year: Any,
) -> Optional[Dict[str, Any]]:
    """Choose a Bangumi subject conservatively by title similarity and year."""

    wanted_titles = [normalized_title(item) for item in titles if normalized_title(item)]
    wanted_year = year_from_date(year)
    best = None
    best_score = 0.0
    for candidate in candidates or []:
        candidate_titles = [
            normalized_title(candidate.get("name")),
            normalized_title(candidate.get("name_cn")),
        ]
        candidate_titles = [item for item in candidate_titles if item]
        if not candidate_titles or not wanted_titles:
            continue
        similarity = max(
            SequenceMatcher(None, wanted, actual).ratio()
            for wanted in wanted_titles
            for actual in candidate_titles
        )
        candidate_year = year_from_date(candidate.get("date"))
        if wanted_year and candidate_year:
            difference = abs(wanted_year - candidate_year)
            if difference > 1:
                similarity -= min(0.45, difference * 0.08)
            elif difference == 0:
                similarity += 0.08
        rating = candidate.get("rating") or {}
        if normalize_votes(rating.get("total")):
            similarity += 0.02
        if similarity > best_score:
            best = candidate
            best_score = similarity
    return best if best_score >= 0.72 else None


def select_imdb_title(
    candidates: Iterable[Dict[str, Any]], title: str, year: Any, media_type: str
) -> Optional[Dict[str, Any]]:
    """Select an IMDbAPI search result without accepting loose title matches."""

    wanted = normalized_title(title)
    wanted_year = year_from_date(year)
    allowed_types = (
        {"movie", "tvMovie", "short"}
        if media_type == "movie"
        else {"tvSeries", "tvMiniSeries", "tvShort"}
    )
    best = None
    best_score = 0.0
    for candidate in candidates or []:
        candidate_type = str(candidate.get("type") or "")
        if candidate_type and candidate_type not in allowed_types:
            continue
        titles = [
            normalized_title(candidate.get("primary_title") or candidate.get("primaryTitle")),
            normalized_title(candidate.get("original_title") or candidate.get("originalTitle")),
        ]
        titles = [item for item in titles if item]
        if not wanted or not titles:
            continue
        similarity = max(SequenceMatcher(None, wanted, item).ratio() for item in titles)
        candidate_year = candidate.get("start_year") or candidate.get("startYear")
        try:
            candidate_year = int(candidate_year) if candidate_year else None
        except (TypeError, ValueError):
            candidate_year = None
        if wanted_year and candidate_year:
            difference = abs(wanted_year - candidate_year)
            if difference == 0:
                similarity += 0.08
            elif media_type == "tv":
                # Some databases keep a revival under the original series' first year.
                similarity -= min(0.15, difference * 0.03)
            else:
                similarity -= min(0.4, difference * 0.08)
        if similarity > best_score:
            best = candidate
            best_score = similarity
    return best if best_score >= 0.8 else None


def omdb_ratings(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Extract IMDb, Rotten Tomatoes, and Metacritic values from OMDb."""

    if not payload or payload.get("Response") == "False":
        return {}
    values: Dict[str, Dict[str, Any]] = {}
    imdb = normalize_score(payload.get("imdbRating"))
    if imdb is not None:
        values["imdb"] = {"score": imdb, "votes": normalize_votes(payload.get("imdbVotes"))}
    for item in payload.get("Ratings") or []:
        source = str(item.get("Source") or "")
        raw_value = item.get("Value")
        if source == "Rotten Tomatoes":
            score = normalize_score(raw_value, 100)
            if score is not None:
                values["rotten_tomatoes"] = {"score": score, "display": str(raw_value)}
        elif source == "Metacritic":
            raw_score = str(raw_value or "").split("/", 1)[0]
            score = normalize_score(raw_score, 100)
            if score is not None:
                values["metacritic"] = {"score": score, "display": str(raw_value)}
    metascore = normalize_score(payload.get("Metascore"), 100)
    if metascore is not None and "metacritic" not in values:
        values["metacritic"] = {
            "score": metascore,
            "display": f"{int(metascore * 10)}/100",
        }
    return values


def precision_date(value: Any) -> str:
    """Normalize an ISO date or an IMDb precision-date object to YYYY-MM-DD."""

    if isinstance(value, dict):
        try:
            year = int(value.get("year"))
            month = int(value.get("month"))
            day = int(value.get("day"))
            return f"{year:04d}-{month:02d}-{day:02d}"
        except (TypeError, ValueError):
            return ""
    match = re.search(r"\b(19|20)\d{2}-\d{2}-\d{2}\b", str(value or ""))
    return match.group(0) if match else ""


def match_episode_candidates(
    anchors: Iterable[Dict[str, Any]],
    candidates: Iterable[Dict[str, Any]],
) -> Dict[int, Dict[str, Any]]:
    """Match external episodes to TMDB anchors without trusting season numbering."""

    available: List[Dict[str, Any]] = list(candidates or [])
    matches: Dict[int, Dict[str, Any]] = {}
    used: set[int] = set()
    for anchor in anchors or []:
        try:
            episode_number = int(anchor.get("episode_number"))
        except (TypeError, ValueError):
            continue
        anchor_title = normalized_title(anchor.get("name") or anchor.get("title"))
        anchor_date = precision_date(anchor.get("air_date") or anchor.get("release_date"))
        best_index = -1
        best_score = 0.0
        for index, candidate in enumerate(available):
            if index in used:
                continue
            candidate_title = normalized_title(candidate.get("title") or candidate.get("name"))
            candidate_date = precision_date(
                candidate.get("air_date")
                or candidate.get("airdate")
                or candidate.get("release_date")
                or candidate.get("releaseDate")
            )
            similarity = (
                SequenceMatcher(None, anchor_title, candidate_title).ratio()
                if anchor_title and candidate_title
                else 0.0
            )
            score = similarity * 0.72
            if anchor_date and candidate_date and anchor_date == candidate_date:
                score += 0.72
            try:
                candidate_number = int(
                    candidate.get("episode_number")
                    or candidate.get("episodeNumber")
                    or candidate.get("number")
                )
            except (TypeError, ValueError):
                candidate_number = None
            if candidate_number == episode_number:
                score += 0.16
            if score > best_score:
                best_index = index
                best_score = score
        if best_index >= 0 and best_score >= 0.72:
            used.add(best_index)
            matches[episode_number] = available[best_index]
    return matches


def aggregate_episode_source(
    source_id: str,
    name: str,
    episodes: Iterable[Dict[str, Any]],
    url: str,
) -> Optional[Dict[str, Any]]:
    """Build a season score from episode scores, weighting sources with votes."""

    scored = [item for item in episodes or [] if normalize_score(item.get("score")) is not None]
    if not scored:
        return None
    weighted = [item for item in scored if normalize_votes(item.get("votes"))]
    if weighted:
        total_votes = sum(normalize_votes(item.get("votes")) or 0 for item in weighted)
        score = sum(
            (normalize_score(item.get("score")) or 0) * (normalize_votes(item.get("votes")) or 0)
            for item in weighted
        ) / total_votes
        votes: Optional[int] = total_votes
    else:
        score = sum(normalize_score(item.get("score")) or 0 for item in scored) / len(scored)
        votes = None
    return {
        "id": source_id,
        "name": name,
        "score": round(score, 1),
        "display": f"{score:.1f}",
        "votes": votes,
        "episodes": len(scored),
        "url": url,
    }
