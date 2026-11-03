import unittest
from unittest.mock import patch
from datetime import datetime, timezone

from tracker import (
    athlete_matches, find_player_statistics, game_is_final, normalized,
    parse_result, team_matches, notification_text, dates_to_check, collect_results,
)

SAMPLE_PLAYER = {"name": "Dusty Stromer", "league": "d1", "team": "San Diego", "gcu_years": "2025–26"}

SAMPLE_EVENT = {
    "id": "401999555",
    "date": "2026-11-02T23:00Z",
    "status": {"type": {"completed": True}},
    "competitions": [{"competitors": [
        {"homeAway": "home", "team": {"id": "301", "location": "San Diego", "displayName": "San Diego Toreros"}, "score": "77"},
        {"homeAway": "away", "team": {"id": "249", "location": "Pepperdine", "displayName": "Pepperdine Waves"}, "score": "70"},
    ]}]
}

SAMPLE_SUMMARY = {
    "boxscore": {"players": [
        {"team": {"id": "301"}, "statistics": [{
            "labels": ["MIN", "FG", "3PT", "FT", "OREB", "DREB", "REB", "AST", "STL", "BLK", "TO", "PF", "PTS"],
            "athletes": [
                {"athlete": {"id": "100", "displayName": "Some Teammate"}, "stats": ["20", "3-7", "0-1", "1-1", "0", "4", "4", "2", "0", "0", "2", "2", "7"]},
                {"athlete": {"id": "222", "displayName": "Dusty Stromer"}, "stats": ["29", "5-10", "2-5", "0-0", "1", "5", "6", "3", "1", "0", "2", "1", "12"]},
            ],
        }]},
        {"team": {"id": "249"}, "statistics": []},
    ]}
}


class TrackerTests(unittest.TestCase):
    def test_matches_exact_team_not_similar_school(self):
        self.assertTrue(team_matches({"location": "San Diego"}, SAMPLE_PLAYER))
        self.assertFalse(team_matches({"location": "San Diego State"}, SAMPLE_PLAYER))

    def test_accent_matching(self):
        self.assertEqual(normalized("José Núñez"), normalized("Jose Nunez"))

    def test_name_or_id_matching(self):
        self.assertTrue(athlete_matches({"id": "123", "displayName": "Dusty Stromer"}, SAMPLE_PLAYER))
        self.assertFalse(athlete_matches({"id": "321", "displayName": "Dusty Stromer"}, {**SAMPLE_PLAYER, "athlete_id":"123"}))

    def test_full_boxscore_extracted_and_scores(self):
        result = parse_result("d1", SAMPLE_EVENT, SAMPLE_PLAYER, SAMPLE_SUMMARY)
        self.assertIsNotNone(result)
        self.assertEqual(result["outcome"], "W")
        self.assertEqual((result["pts"],result["reb"],result["ast"]), ("12", "6", "3"))
        self.assertEqual(len(result["stats"]), 13)
        self.assertEqual(result["stats"][1], {"label":"FG", "value":"5-10"})
        self.assertEqual(result["opponent"], "Pepperdine")
        self.assertIn("5-10", notification_text(result))

    def test_dnp_not_reported(self):
        dnp = {"boxscore":{"players":[{"team":{"id":"301"}, "statistics":[{
            "labels":["MIN","PTS"], "athletes":[{"athlete":{"displayName":"Dusty Stromer"}, "didNotPlay":True, "stats":["0","0"]}]
        }]}]}}
        self.assertIsNone(find_player_statistics(dnp, SAMPLE_PLAYER, "301"))
        self.assertIsNone(parse_result("d1", SAMPLE_EVENT, SAMPLE_PLAYER, dnp))

    def test_not_matching_player_on_opposing_team(self):
        wrong_school = {**SAMPLE_PLAYER, "team":"Pepperdine"}
        self.assertIsNone(parse_result("d1", SAMPLE_EVENT, wrong_school, SAMPLE_SUMMARY))

    def test_only_final(self):
        self.assertTrue(game_is_final(SAMPLE_EVENT))
        self.assertFalse(game_is_final({"status":{"type":{"name":"STATUS_IN_PROGRESS","completed":False}}}))

    def test_integration_queries_all_di_and_reads_only_relevant_boxscore(self):
        events = [SAMPLE_EVENT, {
            "id": "401999666", "date": "2026-11-02T23:00Z",
            "status": {"type": {"completed": True}},
            "competitions": [{"competitors": [
                {"team": {"id": "500", "location": "San Diego State"}},
                {"team": {"id": "501", "location": "Arizona"}}
            ]}]
        }]
        calls = []

        def fake_get_json(session, endpoint, params):
            calls.append((endpoint, params))
            if endpoint.endswith("/scoreboard"):
                return {"events": events}
            if endpoint.endswith("/summary"):
                self.assertEqual(params["event"], "401999555")
                return SAMPLE_SUMMARY
            self.fail("Unexpected endpoint")

        with patch("tracker.get_json", side_effect=fake_get_json), patch("tracker.dates_to_check", return_value=["20261102"]), patch("tracker.time.sleep"):
            got = collect_results(None, [SAMPLE_PLAYER], 1)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["name"], "Dusty Stromer")
        self.assertEqual(calls[0][1]["groups"], 50)
        self.assertEqual(len(calls), 2)

    def test_az_dates(self):
        # 2026-11-03 03:00Z is still Nov 2 in Phoenix.
        now = datetime(2026,11,3,3,0,tzinfo=timezone.utc)
        self.assertEqual(dates_to_check(2,now), ["20261102","20261101"])


if __name__ == "__main__":
    unittest.main()
