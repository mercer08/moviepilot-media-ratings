import importlib.util
from pathlib import Path
import unittest


CLIENT_PATH = (
    Path(__file__).parents[1] / "plugins.v2/mediaratings/client.py"
)
SPEC = importlib.util.spec_from_file_location("media_ratings_client", CLIENT_PATH)
CLIENT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(CLIENT)


class MediaRatingsClientTest(unittest.TestCase):
    def test_normalize_score_accepts_ten_and_hundred_point_scales(self):
        self.assertEqual(CLIENT.normalize_score("8.4"), 8.4)
        self.assertEqual(CLIENT.normalize_score("84/100"), 8.4)
        self.assertEqual(CLIENT.normalize_score("84%", 100), 8.4)
        self.assertIsNone(CLIENT.normalize_score("N/A"))
        self.assertIsNone(CLIENT.normalize_score(101, 10))

    def test_select_bangumi_subject_prefers_matching_title_and_year(self):
        candidates = [
            {"id": 1, "name": "Sousou no Frieren", "name_cn": "葬送的芙莉莲", "date": "2023-09-29", "rating": {"score": 9.1, "total": 30000}},
            {"id": 2, "name": "Frieren Special", "name_cn": "芙莉莲 特别篇", "date": "2025-01-01", "rating": {"score": 7.0, "total": 200}},
        ]
        result = CLIENT.select_bangumi_subject(candidates, ["葬送的芙莉莲"], 2023)
        self.assertEqual(result["id"], 1)

    def test_select_bangumi_subject_rejects_unrelated_result(self):
        result = CLIENT.select_bangumi_subject(
            [{"id": 1, "name": "Completely Different", "date": "2023-01-01"}],
            ["葬送的芙莉莲"],
            2023,
        )
        self.assertIsNone(result)

    def test_select_imdb_title_uses_type_title_and_year(self):
        result = CLIENT.select_imdb_title([
            {"id": "tt-old", "type": "tvSeries", "primary_title": "Top Boy", "start_year": 2011},
            {"id": "tt-new", "type": "tvSeries", "primary_title": "Top Boy", "start_year": 2019},
            {"id": "tt-movie", "type": "movie", "primary_title": "Top Boy", "start_year": 2019},
        ], "Top Boy", 2019, "tv")
        self.assertEqual(result["id"], "tt-new")

    def test_omdb_extracts_imdb_rotten_tomatoes_and_metacritic(self):
        ratings = CLIENT.omdb_ratings({
            "Response": "True",
            "imdbRating": "8.2",
            "imdbVotes": "12,345",
            "Metascore": "77",
            "Ratings": [
                {"Source": "Rotten Tomatoes", "Value": "91%"},
                {"Source": "Metacritic", "Value": "77/100"},
            ],
        })
        self.assertEqual(ratings["imdb"], {"score": 8.2, "votes": 12345})
        self.assertEqual(ratings["rotten_tomatoes"]["score"], 9.1)
        self.assertEqual(ratings["metacritic"]["score"], 7.7)

    def test_matches_episode_by_airdate_when_imdb_season_number_differs(self):
        anchors = [
            {"episode_number": 1, "name": "Bruk Up", "air_date": "2019-09-13"},
            {"episode_number": 2, "name": "Building Bridges", "air_date": "2019-09-13"},
        ]
        candidates = [
            {
                "id": "tt-old",
                "title": "Episode #1.1",
                "season": "1",
                "episodeNumber": 1,
                "releaseDate": {"year": 2011, "month": 10, "day": 31},
            },
            {
                "id": "tt-new-1",
                "title": "Bruk Up",
                "season": "3",
                "episodeNumber": 1,
                "releaseDate": {"year": 2019, "month": 9, "day": 13},
            },
            {
                "id": "tt-new-2",
                "title": "Building Bridges",
                "season": "3",
                "episodeNumber": 2,
                "releaseDate": {"year": 2019, "month": 9, "day": 13},
            },
        ]
        matches = CLIENT.match_episode_candidates(anchors, candidates)
        self.assertEqual(matches[1]["id"], "tt-new-1")
        self.assertEqual(matches[2]["id"], "tt-new-2")

    def test_aggregates_season_score_with_vote_weighting(self):
        result = CLIENT.aggregate_episode_source(
            "imdb",
            "IMDb",
            [
                {"score": 8.0, "votes": 100},
                {"score": 9.0, "votes": 300},
            ],
            "https://example.test/episodes",
        )
        self.assertEqual(result["score"], 8.8)
        self.assertEqual(result["votes"], 400)
        self.assertEqual(result["episodes"], 2)


if __name__ == "__main__":
    unittest.main()
