"""Add cached multi-source ratings to MoviePilot media pages and list cards."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Query

from app.chain.media import MediaChain
from app.core.plugin import PluginManager
from app.log import logger
from app.modules.themoviedb.tmdbapi import TmdbApi
from app.plugins import _PluginBase
from app.schemas.types import MediaType
from app.utils.http import AsyncRequestUtils

from .client import (
    aggregate_episode_source,
    card_lookup_title,
    match_episode_candidates,
    normalize_score,
    normalize_votes,
    normalized_title,
    omdb_ratings,
    select_bangumi_subject,
    select_imdb_title,
)


class MediaRatings(_PluginBase):
    plugin_name = "全站多源评分"
    plugin_desc = "在详情页、推荐与榜单卡片聚合 TMDB、IMDb、烂番茄、Metacritic、豆瓣评分；动漫追加 Bangumi。"
    plugin_icon = "mdi-star-box-multiple-outline"
    plugin_version = "1.5.2"
    plugin_author = "mercer08"
    author_url = "https://github.com/mercer08"
    plugin_config_prefix = "mediaratings_"
    plugin_order = 24
    auth_level = 1

    _enabled = True
    _cache_hours = 12
    _omdb_api_key = ""

    def __init__(self):
        super().__init__()
        self._tmdb = TmdbApi()
        self._media_chain = MediaChain()
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._card_lookup_semaphore = asyncio.Semaphore(3)

    def init_plugin(self, config: dict = None) -> None:
        config = config or {}
        self._enabled = bool(config.get("enabled", True))
        try:
            self._cache_hours = max(1, min(168, int(config.get("cache_hours") or 12)))
        except (TypeError, ValueError):
            self._cache_hours = 12
        self._omdb_api_key = str(
            config.get("omdb_api_key") or os.environ.get("OMDB_API_KEY") or ""
        ).strip()

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/detail",
                "endpoint": self.detail,
                "methods": ["GET"],
                "summary": "获取媒体详情页多源评分",
                "allow_anonymous": True,
            },
            {
                "path": "/episodes",
                "endpoint": self.episodes,
                "methods": ["GET"],
                "summary": "获取指定季及单集的多源评分",
                "allow_anonymous": True,
            },
            {
                "path": "/card",
                "endpoint": self.card,
                "methods": ["GET"],
                "summary": "按标题、年份和类型获取榜单卡片多源评分",
                "allow_anonymous": True,
            },
        ]

    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        """Return a native MoviePilot configuration form and safe defaults."""

        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用评分聚合 API",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "cache_hours",
                                            "label": "缓存时长（小时）",
                                            "type": "number",
                                            "min": 1,
                                            "max": 168,
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "omdb_api_key",
                                            "label": "OMDb API Key（可选）",
                                            "type": "password",
                                            "hint": "配置后可追加 Rotten Tomatoes 与 Metacritic。",
                                            "persistentHint": True,
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VAlert",
                        "props": {
                            "type": "info",
                            "variant": "tonal",
                            "text": "MoviePilot V2 暂无原生媒体页面插件插槽；详情页与榜单卡片评分需要仓库中可选的反向代理适配器。",
                        },
                    },
                ],
            }
        ], {
            "enabled": True,
            "cache_hours": 12,
            "omdb_api_key": "",
        }

    def get_page(self) -> Optional[List[dict]]:
        return None

    def stop_service(self) -> None:
        self._memory_cache.clear()

    async def detail(
        self,
        tmdb_id: int = Query(..., ge=1),
        media_type: str = Query("tv"),
        title: str = Query("", max_length=200),
        year: Optional[int] = Query(None, ge=1800, le=2200),
    ) -> Dict[str, Any]:
        if not self._enabled:
            return {"tmdb_id": tmdb_id, "sources": [], "message": "plugin disabled"}
        normalized_type = "movie" if str(media_type).lower() in {"movie", "电影"} else "tv"
        cache_key = f"detail:v2:{normalized_type}:{tmdb_id}"
        cached = self._memory_cache.get(cache_key) or self.get_data(cache_key)
        if self._fresh(cached):
            self._memory_cache[cache_key] = cached
            return cached

        result = await self._collect(tmdb_id, normalized_type, title, year)
        if result.get("sources"):
            self._memory_cache[cache_key] = result
            self.save_data(cache_key, result)
        return result

    async def episodes(
        self,
        tmdb_id: int = Query(..., ge=1),
        season: int = Query(..., ge=0, le=200),
    ) -> Dict[str, Any]:
        """Return a lazily loaded season and episode rating projection."""

        if not self._enabled:
            return {"tmdb_id": tmdb_id, "season": season, "sources": [], "episodes": []}
        cache_key = f"episodes:v1:{tmdb_id}:{season}"
        cached = self._memory_cache.get(cache_key) or self.get_data(cache_key)
        if self._fresh(cached):
            self._memory_cache[cache_key] = cached
            return cached
        result = await self._collect_episodes(tmdb_id, season)
        if result.get("episodes"):
            self._memory_cache[cache_key] = result
            self.save_data(cache_key, result)
        return result

    async def card(
        self,
        title: str = Query(..., min_length=1, max_length=200),
        media_type: str = Query("tv"),
        year: Optional[int] = Query(None, ge=1800, le=2200),
    ) -> Dict[str, Any]:
        """Resolve list-card metadata to TMDB once, then reuse detail caches."""

        normalized_type = "movie" if str(media_type).lower() in {"movie", "电影"} else "tv"
        lookup_title = card_lookup_title(title)
        lookup_key = (
            f"card:v2:{normalized_type}:{normalized_title(lookup_title)}:{year or ''}"
        )
        cached = self._memory_cache.get(lookup_key) or self.get_data(lookup_key)
        if self._fresh(cached):
            self._memory_cache[lookup_key] = cached
            return cached
        if not self._enabled:
            return {
                "title": title,
                "media_type": normalized_type,
                "sources": [],
                "message": "plugin disabled",
            }

        async with self._card_lookup_semaphore:
            # Another request for the same card may have populated the cache
            # while this request waited for a lookup slot.
            cached = self._memory_cache.get(lookup_key) or self.get_data(lookup_key)
            if self._fresh(cached):
                self._memory_cache[lookup_key] = cached
                return cached
            mtype = MediaType.MOVIE if normalized_type == "movie" else MediaType.TV
            try:
                matched = await self._tmdb.async_match(
                    name=lookup_title,
                    mtype=mtype,
                    year=str(year) if year else None,
                ) or {}
                if not matched and normalized_type == "tv" and year:
                    # Douban season pages expose the season year, while TMDB
                    # searches TV records by the series' original first-air year.
                    matched = await self._tmdb.async_match(
                        name=lookup_title,
                        mtype=mtype,
                        year=None,
                    ) or {}
                tmdb_id = int(matched.get("id") or 0)
            except Exception as error:
                logger.info(
                    f"MediaRatings card lookup unavailable for {title} ({year or '-'}): {error}"
                )
                tmdb_id = 0

            if tmdb_id:
                result = await self.detail(
                    tmdb_id=tmdb_id,
                    media_type=normalized_type,
                    title=lookup_title,
                    year=year,
                )
            else:
                result = {
                    "tmdb_id": None,
                    "media_type": normalized_type,
                    "title": title,
                    "fetched_at": int(time.time()),
                    "sources": [],
                }
        self._memory_cache[lookup_key] = result
        self.save_data(lookup_key, result)
        return result

    async def _collect(
        self, tmdb_id: int, media_type: str, title: str, year: Optional[int]
    ) -> Dict[str, Any]:
        mtype = MediaType.MOVIE if media_type == "movie" else MediaType.TV
        try:
            tmdb = await self._tmdb.async_get_info(mtype=mtype, tmdbid=tmdb_id) or {}
        except Exception as error:
            logger.warning(f"MediaRatings TMDB lookup failed for {tmdb_id}: {error}")
            tmdb = {}

        external_ids = tmdb.get("external_ids") or {}
        imdb_id = str(tmdb.get("imdb_id") or external_ids.get("imdb_id") or "").strip()
        tvdb_id = tmdb.get("tvdb_id") or external_ids.get("tvdb_id")
        resolved_title = str(tmdb.get("title") or tmdb.get("name") or title or "").strip()
        original_title = str(
            tmdb.get("original_title") or tmdb.get("original_name") or ""
        ).strip()
        release_date = tmdb.get("release_date") or tmdb.get("first_air_date") or ""
        resolved_year = year or self._year(release_date)
        foreign_title = original_title or resolved_title or title
        sources: Dict[str, Dict[str, Any]] = {}

        tmdb_score = normalize_score(tmdb.get("vote_average"))
        if tmdb_score is not None:
            sources["tmdb"] = self._source(
                "tmdb", "TMDB", tmdb_score, tmdb.get("vote_count"),
                f"https://www.themoviedb.org/{media_type}/{tmdb_id}",
            )

        tasks = [self._douban(tmdb_id, mtype)]
        is_anime = self._is_anime(tmdb)
        if is_anime:
            tasks.append(self._bangumi([original_title, resolved_title, title], resolved_year))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for item in results:
            if isinstance(item, dict) and item.get("id") and item.get("score") is not None:
                sources[item["id"]] = item

        imdb_source = await self._imdb(
            imdb_id, foreign_title, resolved_year, media_type
        )
        if imdb_source:
            sources["imdb"] = imdb_source
            metacritic_score = normalize_score(
                imdb_source.pop("metacritic_score", None), 100
            )
            if metacritic_score is not None:
                sources["metacritic"] = self._source(
                    "metacritic",
                    "Metacritic",
                    metacritic_score,
                    imdb_source.pop("metacritic_reviews", None),
                    "https://www.metacritic.com/search/" + (resolved_title or title) + "/",
                    display=f"{int(metacritic_score * 10)}/100",
                )

        if self._omdb_api_key and imdb_id:
            try:
                omdb = await AsyncRequestUtils(timeout=10).get_json(
                    "https://www.omdbapi.com/",
                    params={"i": imdb_id, "apikey": self._omdb_api_key},
                )
                for source_id, item in omdb_ratings(omdb or {}).items():
                    if source_id == "imdb" and source_id in sources:
                        continue
                    label = {
                        "imdb": "IMDb",
                        "rotten_tomatoes": "Rotten Tomatoes",
                        "metacritic": "Metacritic",
                    }[source_id]
                    link = {
                        "imdb": f"https://www.imdb.com/title/{imdb_id}",
                        "rotten_tomatoes": "https://www.rottentomatoes.com/search?search=" + resolved_title,
                        "metacritic": "https://www.metacritic.com/search/" + resolved_title + "/",
                    }[source_id]
                    sources[source_id] = self._source(
                        source_id, label, item["score"], item.get("votes"), link,
                        display=item.get("display"),
                    )
            except Exception as error:
                logger.warning(f"MediaRatings OMDb lookup failed for {imdb_id}: {error}")

        order = [
            "tmdb", "imdb", "rotten_tomatoes", "metacritic", "douban", "bangumi"
        ]
        return {
            "tmdb_id": tmdb_id,
            "media_type": media_type,
            "title": resolved_title or title,
            "anime": is_anime,
            "seasons": self._season_numbers(tmdb) if media_type == "tv" else [],
            "fetched_at": int(time.time()),
            "sources": [sources[key] for key in order if key in sources],
        }

    async def _collect_episodes(self, tmdb_id: int, season: int) -> Dict[str, Any]:
        """Use TMDB episodes as anchors, then merge IMDb by date/title."""

        try:
            tmdb = await self._tmdb.async_get_info(
                mtype=MediaType.TV, tmdbid=tmdb_id
            ) or {}
            season_info = await self._tmdb.async_get_tv_season_detail(
                tmdbid=tmdb_id, season=season
            ) or {}
        except Exception as error:
            logger.warning(
                f"MediaRatings TMDB season lookup failed for {tmdb_id} S{season}: {error}"
            )
            tmdb, season_info = {}, {}

        anchors = sorted(
            [item for item in season_info.get("episodes") or [] if isinstance(item, dict)],
            key=lambda item: int(item.get("episode_number") or 0),
        )
        external_ids = tmdb.get("external_ids") or {}
        imdb_id = str(tmdb.get("imdb_id") or external_ids.get("imdb_id") or "").strip()
        imdb_matches = await self._imdb_episode_matches(imdb_id, anchors, season)
        source_rows: Dict[str, List[Dict[str, Any]]] = {
            "tmdb": [], "imdb": []
        }
        episodes: List[Dict[str, Any]] = []
        for anchor in anchors:
            number = int(anchor.get("episode_number") or 0)
            row_sources: List[Dict[str, Any]] = []
            tmdb_score = normalize_score(anchor.get("vote_average"))
            if tmdb_score is not None:
                item = self._source(
                    "tmdb", "TMDB", tmdb_score, anchor.get("vote_count"),
                    f"https://www.themoviedb.org/tv/{tmdb_id}/season/{season}/episode/{number}",
                )
                row_sources.append(item)
                source_rows["tmdb"].append(item)

            imdb = imdb_matches.get(number)
            imdb_rating = (imdb or {}).get("rating") or {}
            imdb_score = normalize_score(
                imdb_rating.get("aggregateRating")
                if isinstance(imdb_rating, dict) else None
            )
            if imdb_score is not None:
                imdb_episode_id = str((imdb or {}).get("id") or "")
                item = self._source(
                    "imdb", "IMDb", imdb_score,
                    imdb_rating.get("voteCount") if isinstance(imdb_rating, dict) else None,
                    f"https://www.imdb.com/title/{imdb_episode_id}/",
                )
                row_sources.append(item)
                source_rows["imdb"].append(item)

            episodes.append({
                "season": season,
                "episode": number,
                "title": anchor.get("name") or f"第 {number} 集",
                "air_date": anchor.get("air_date") or "",
                "sources": row_sources,
            })

        season_sources = []
        source_meta = {
            "tmdb": ("TMDB", f"https://www.themoviedb.org/tv/{tmdb_id}/season/{season}"),
            "imdb": ("IMDb", f"https://www.imdb.com/title/{imdb_id}/episodes/"),
        }
        for source_id in ("tmdb", "imdb"):
            name, url = source_meta[source_id]
            aggregate = aggregate_episode_source(
                source_id, name, source_rows[source_id], url
            )
            if aggregate:
                season_sources.append(aggregate)
        return {
            "tmdb_id": tmdb_id,
            "season": season,
            "title": season_info.get("name") or f"第 {season} 季",
            "fetched_at": int(time.time()),
            "sources": season_sources,
            "episodes": episodes,
        }

    async def _imdb_episode_matches(
        self, imdb_id: str, anchors: List[Dict[str, Any]], requested_season: int
    ) -> Dict[int, Dict[str, Any]]:
        """Search likely IMDb seasons and stop after the TMDB anchors match."""

        if not imdb_id or not anchors:
            return {}
        client = AsyncRequestUtils(timeout=12)
        try:
            season_payload = await client.get_json(
                f"https://api.tiffara.com/titles/{imdb_id}/seasons"
            ) or {}
            raw_seasons = season_payload.get("seasons") or []
            seasons = []
            for item in raw_seasons:
                value = item.get("season") if isinstance(item, dict) else item
                try:
                    seasons.append(int(value))
                except (TypeError, ValueError):
                    continue
            seasons = sorted(set(seasons), key=lambda value: (abs(value - requested_season), value))
            if requested_season not in seasons:
                seasons.insert(0, requested_season)
            candidates: List[Dict[str, Any]] = []
            for imdb_season in seasons[:8]:
                payload = await client.get_json(
                    f"https://api.tiffara.com/titles/{imdb_id}/episodes",
                    params={"season": imdb_season, "pageSize": 50},
                ) or {}
                candidates.extend(payload.get("episodes") or [])
                matches = match_episode_candidates(anchors, candidates)
                if len(matches) >= max(1, int(len(anchors) * 0.7)):
                    return matches
            return match_episode_candidates(anchors, candidates)
        except Exception as error:
            logger.info(f"MediaRatings IMDb episode lookup unavailable for {imdb_id}: {error}")
            return {}

    async def _imdb(
        self, imdb_id: str, title: str, year: Optional[int], media_type: str
    ) -> Optional[Dict[str, Any]]:
        info: Any = None
        try:
            if imdb_id:
                payload = await AsyncRequestUtils(timeout=10).get_json(
                    f"https://api.tiffara.com/titles/{imdb_id}"
                )
                info = (payload or {}).get("title") if isinstance(payload, dict) else None
                info = info or payload
            elif title:
                payload = await AsyncRequestUtils(timeout=10).get_json(
                    "https://api.tiffara.com/search/titles", params={"query": title}
                )
                candidates = (
                    (payload or {}).get("titles")
                    or (payload or {}).get("results")
                    or (payload or {}).get("data")
                    or []
                )
                info = select_imdb_title(candidates, title, year, media_type)
                imdb_id = str(self._value(info, "id") or "")
        except Exception as error:
            logger.info(f"MediaRatings direct IMDb lookup unavailable: {error}")

        target = PluginManager().running_plugins.get("ImdbSource")
        helper = getattr(target, "_imdb_helper", None) if target else None
        try:
            if info is None and imdb_id and helper:
                info = await helper.async_get_info_by_imdbid(imdb_id)
            if info is None:
                return None
            rating = self._value(info, "rating", "ratings_summary", "ratingsSummary")
            score = self._value(info, "vote_average", "aggregate_rating", "aggregateRating")
            if score is None:
                score = self._value(
                    rating, "aggregate_rating", "aggregateRating", "value", "score"
                )
            if score is None and isinstance(rating, (int, float, str)):
                score = rating
            score = normalize_score(score)
            if score is None:
                return None
            votes = self._value(info, "vote_count", "votes", "rating_count")
            if votes is None:
                votes = self._value(rating, "vote_count", "voteCount", "votes", "count")
            source = self._source(
                "imdb", "IMDb", score, votes, f"https://www.imdb.com/title/{imdb_id}"
            )
            critic = self._value(info, "critic_review", "criticReview", "metacritic")
            source["metacritic_score"] = self._value(critic, "score")
            source["metacritic_reviews"] = self._value(
                critic, "review_count", "reviewCount", "count"
            )
            return source
        except Exception as error:
            logger.warning(f"MediaRatings IMDb lookup failed for {imdb_id}: {error}")
            return None

    async def _douban(self, tmdb_id: int, mtype: MediaType) -> Optional[Dict[str, Any]]:
        try:
            info = await self._media_chain.async_get_doubaninfo_by_tmdbid(
                tmdbid=tmdb_id, mtype=mtype
            )
            douban_id = str((info or {}).get("id") or "").strip()
            if douban_id:
                detail = await self._media_chain.async_douban_info(
                    doubanid=douban_id, mtype=mtype, raise_exception=False
                )
                if detail:
                    info = detail
            rating = (info or {}).get("rating") or {}
            score = normalize_score(
                rating.get("value") if isinstance(rating, dict) else rating
            )
            if score is None:
                return None
            votes = rating.get("count") if isinstance(rating, dict) else None
            return self._source(
                "douban", "豆瓣", score, votes,
                f"https://movie.douban.com/subject/{douban_id}/" if douban_id else "https://movie.douban.com/",
            )
        except Exception as error:
            logger.info(f"MediaRatings Douban lookup unavailable for TMDB {tmdb_id}: {error}")
            return None

    async def _bangumi(
        self, titles: List[str], year: Optional[int]
    ) -> Optional[Dict[str, Any]]:
        keyword = next((item for item in titles if item), "")
        if not keyword:
            return None
        try:
            data = await AsyncRequestUtils(
                headers={
                    "User-Agent": "MoviePilot-MediaRatings/1.2 (+https://github.com/mercer08/moviepilot-media-ratings)",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=10,
            ).post_json(
                "https://api.bgm.tv/v0/search/subjects",
                params={"limit": 10, "offset": 0},
                json={"keyword": keyword, "filter": {"type": [2]}},
            )
            subject = select_bangumi_subject((data or {}).get("data") or [], titles, year)
            if not subject:
                return None
            rating = subject.get("rating") or {}
            score = normalize_score(rating.get("score"))
            if score is None:
                return None
            subject_id = subject.get("id")
            return self._source(
                "bangumi", "Bangumi", score, rating.get("total"),
                f"https://bgm.tv/subject/{subject_id}",
            )
        except Exception as error:
            logger.info(f"MediaRatings Bangumi lookup unavailable for {keyword}: {error}")
            return None

    @staticmethod
    def _source(
        source_id: str,
        name: str,
        score: float,
        votes: Any,
        url: str,
        display: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "id": source_id,
            "name": name,
            "score": score,
            "display": display or f"{score:.1f}",
            "votes": normalize_votes(votes),
            "url": url,
        }

    @staticmethod
    def _value(value: Any, *names: str) -> Any:
        for name in names:
            if isinstance(value, dict) and value.get(name) is not None:
                return value.get(name)
            candidate = getattr(value, name, None)
            if candidate is not None:
                return candidate
        return None

    @staticmethod
    def _year(value: Any) -> Optional[int]:
        try:
            return int(str(value)[:4])
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _season_numbers(tmdb: Dict[str, Any]) -> List[int]:
        numbers = set()
        for item in tmdb.get("seasons") or []:
            value = item.get("season_number") if isinstance(item, dict) else None
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            if 0 <= number <= 200:
                numbers.add(number)
        return sorted(numbers)

    @staticmethod
    def _is_anime(tmdb: Dict[str, Any]) -> bool:
        language = str(tmdb.get("original_language") or "").lower()
        countries = {str(item.get("iso_3166_1") or "").upper() for item in tmdb.get("origin_country") or [] if isinstance(item, dict)}
        countries.update(str(item).upper() for item in tmdb.get("origin_country") or [] if isinstance(item, str))
        genres = {
            str(item.get("name") if isinstance(item, dict) else item).lower()
            for item in tmdb.get("genres") or []
        }
        return language == "ja" and ("animation" in genres or "动画" in genres or "JP" in countries)

    def _fresh(self, record: Any) -> bool:
        if not isinstance(record, dict) or not isinstance(record.get("sources"), list):
            return False
        try:
            fetched_at = float(record.get("fetched_at") or 0)
        except (TypeError, ValueError):
            return False
        return fetched_at > 0 and time.time() - fetched_at < self._cache_hours * 3600
