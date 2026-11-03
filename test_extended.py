import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from extended_sources import key_name, parse_ncaa_result, ncaa_player_stats, name_matches, collect_ncaa_results, collect_naia_results
from tracker import validate_players, parse_result, notification_text, send_alerts, collect_results, LEAGUES

PLAYER = {"name":"Former Lope", "league":"d2", "team":"West Texas A&M", "gcu_years":"2024-25"}
NCAA_ENTRY = {"game": {
    "gameID":"7771111", "gameState":"final", "startDate":"2026-11-02", "startTimeEpoch":"1793656800",
    "home":{"names":{"full":"West Texas A&M", "short":"West Texas A&M"}, "score":"85"},
    "away":{"names":{"full":"Texas A&M-Kingsville", "short":"TAMUK"}, "score":"73"}
}}
NCAA_GAMEINFO = {"gameinfo":{"teams":[{"teamId":"123","isHome":True},{"teamId":"456","isHome":False}]}}
NCAA_BOX = {"teamBoxscore":[
    {"teamId":"456", "playerStats":[{"fullName":"Former Lope","minutesPlayed":"22", "points":"42"}]},
    {"teamId":"123", "playerStats":[{"fullName":"Former Lope","minutesPlayed":"31", "fieldGoalsMade":"4", "fieldGoalsAttempted":"9", "totalRebounds":"8", "assists":"6", "points":"13"}]}
]}

class ExtendedTests(unittest.TestCase):
    def test_all_six_leagues_allowed(self):
        for key in ('d1','d2','d3','naia','gleague','nba'):
            self.assertIn(key, LEAGUES)
            self.assertEqual(validate_players([{**PLAYER, "league":key}])[0]['league'], key)
        with self.assertRaises(ValueError):
            validate_players([{**PLAYER,"league":"international"}])

    def test_ncaa_boxscore_uses_team_id_not_same_name_on_away(self):
        game = parse_ncaa_result('d2', NCAA_ENTRY, PLAYER, NCAA_BOX, NCAA_GAMEINFO)
        self.assertIsNotNone(game)
        self.assertEqual(game['opponent'], 'Texas A&M-Kingsville')
        self.assertEqual(game['outcome'], 'W')
        self.assertEqual((game['pts'], game['reb'], game['ast']), ('13','8','6'))
        self.assertEqual(game['score_for'], '85')
        self.assertEqual(len(game['stats']), 6)
        self.assertEqual(game['league'], 'd2')
        self.assertIn('game/7771111', game['boxscore_url'])

    def test_ncaa_dnp_and_ambiguous_team_ignored(self):
        import copy
        box = copy.deepcopy(NCAA_BOX)
        box['teamBoxscore'][1]['playerStats'][0]['minutesPlayed'] = '0'
        self.assertIsNone(parse_ncaa_result('d2', NCAA_ENTRY, PLAYER, box, NCAA_GAMEINFO))
        self.assertIsNone(parse_ncaa_result('d2', NCAA_ENTRY, {**PLAYER,'team':'Unknown'}, NCAA_BOX, NCAA_GAMEINFO))

    def test_ncaa_collector_two_leagues_only_relevant_games(self):
        player = {**PLAYER}
        calls = []
        def fake(session, url, params=None, headers=None):
            calls.append(url)
            if url.endswith('/scoreboard/basketball-men/d2/2026/11/02/all-conf'):
                return {'games':[NCAA_ENTRY]}
            if url.endswith('/game/7771111'):
                return NCAA_GAMEINFO
            if url.endswith('/game/7771111/boxscore'):
                return NCAA_BOX
            raise AssertionError(url)
        with patch('extended_sources.get_json',side_effect=fake),patch('extended_sources.time',create=True),patch('time.sleep'):
            results = collect_ncaa_results(None,[player],1,['20261102'])
        self.assertEqual(len(results),1)
        self.assertEqual(len(calls),3)

    def test_gleague_espm_summary_pipeline(self):
        p = {"name":"Former Lope", "team":"South Bay", "league":"gleague", "gcu_years":"2023-24"}
        event = {"id":"999500", "date":"2026-11-02T23:00:00Z", "status":{"type":{"completed":True}},
            "competitions":[{"competitors":[
                {"homeAway":"home","team":{"id":"51","location":"South Bay","displayName":"South Bay Lakers"}, "score":"104"},
                {"homeAway":"away","team":{"id":"52","location":"Santa Cruz","displayName":"Santa Cruz Warriors"},"score":"100"}
            ]}]}
        summary={"boxscore":{"players":[{"team":{"id":"51"},"statistics":[{
            "labels":["MIN","REB","AST","PTS"],
            "athletes":[{"athlete":{"displayName":"Former Lope"},"stats":["26","4","2","19"]}]
        }]}]}}
        calls=[]
        def fake(s, endpoint, params):
            calls.append(endpoint)
            return {"events":[event]} if endpoint.endswith('/scoreboard') else summary
        with patch('tracker.get_json',side_effect=fake), patch('tracker.dates_to_check',return_value=['20261102']), patch('tracker.time.sleep'):
            got=collect_results(None,[p],1)
        self.assertEqual(len(got),1)
        self.assertEqual(got[0]['league'],'gleague')
        self.assertIn('/nba-development/scoreboard', calls[0])
        self.assertIn('/nba-development/summary', calls[1])

    def test_naia_missing_key_does_not_invent_results(self):
        with patch.dict('os.environ',{'MONTEHALL_API_KEY':''}):
            self.assertEqual(collect_naia_results(None,[{**PLAYER,'league':'naia'}],1,['20261102']),[])

    def test_per_player_per_game_telegram_and_dedupe(self):
        s=Mock()
        s.post.return_value.raise_for_status.return_value=None
        now=datetime.now(timezone.utc)
        games=[]
        for idx, who in enumerate(['Player A','Player B']):
            games.append({
                'id':f'nba:777:{who}', 'date':now.isoformat(), 'name':who,
                'league':'nba', 'team':'Team', 'opponent':'Other', 'home':True,
                'outcome':'W','score_for':'80','score_against':'72',
                'pts':'10','reb':'5','ast':'3',
                'stats':[{'label':'PTS','value':'10'}],
                'boxscore_url':'https://www.espn.com/nba/boxscore/_/gameId/777'
            })
        sent={}
        with patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN':'unit-test-token','TELEGRAM_CHAT_ID':'unit-test-chat','DISCORD_WEBHOOK_URL':''}):
            self.assertEqual(send_alerts(s, games, sent, 60), 2)
            self.assertEqual(send_alerts(s, games, sent, 60), 0)
        self.assertEqual(s.post.call_count,2)
        sent_texts=[c.kwargs['json']['text'] for c in s.post.call_args_list]
        self.assertTrue(any('Player A' in m for m in sent_texts))
        self.assertTrue(any('Player B' in m for m in sent_texts))

if __name__=='__main__':
    unittest.main()
