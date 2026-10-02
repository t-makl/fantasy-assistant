import unittest, tempfile, sys, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server as app
from unittest.mock import patch
import httpx

class WorkspaceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old_db=app.DB;self.old_data=app.DATA
  app.DATA=Path(self.tmp.name);app.DB=app.DATA/'test.sqlite3';app.init()
  app.put('league',{'budget':200,'slots':12,'teams':[{'id':12},{'id':4}]})
  with app.conn() as c:
   for pid in [1,2,3]:c.execute('INSERT INTO players VALUES(?,?)',(pid,json.dumps({'id':pid})))
 def tearDown(self):app.DB=self.old_db;app.DATA=self.old_data;self.tmp.cleanup()
 def test_correct_categories_and_season_source(self):
  p={'stats':[{'seasonId':2026,'statSourceId':1,'statSplitTypeId':0,'stats':{'0':999}}, {'seasonId':2026,'statSourceId':0,'statSplitTypeId':0,'stats':{'0':100,'6':50,'3':30,'2':10,'1':5,'42':10,'19':.52,'20':.8}}]}
  s=app.parse_stats(p,2026,0);self.assertEqual(s['per']['reb'],5);self.assertEqual(s['per']['ast'],3);self.assertEqual(s['per']['stl'],1);self.assertEqual(s['per']['blk'],.5);self.assertEqual(s['per']['fg'],.52);self.assertEqual(s['total']['pts'],100);self.assertIsNone(app.parse_stats(p,2027,1))
 def test_placeholder_and_missing_prices_ignored(self):
  self.assertEqual(app.reconcile({},[{'playerId':-1,'teamId':-1,'bidAmount':0},{'playerId':1,'teamId':12}]),{})
 def test_conflict_and_deduplication(self):
  m={'1':{'playerId':1,'teamId':12,'price':30,'source':'Manual'}};p=[{'playerId':1,'teamId':4,'bidAmount':31,'id':8}]
  result=app.reconcile(m,p);self.assertEqual(result['1']['price'],30);self.assertEqual(result['1']['conflict']['price'],31);self.assertEqual(len(app.reconcile(result,p)),1)
 def test_matching_manual_becomes_confirmed(self):
  m={'1':{'playerId':1,'teamId':12,'price':30,'source':'Manual'}}
  self.assertEqual(app.reconcile(m,[{'playerId':1,'teamId':12,'bidAmount':30}])['1']['source'],'ESPN')
 def test_budget_validation_and_undo_preserves_new_espn_pick(self):
  with self.assertRaises(ValueError):app.mutate('/api/purchase',{'playerId':1,'teamId':12,'price':200})
  self.assertEqual(app.get('undo'),[])
  app.mutate('/api/purchase',{'playerId':1,'teamId':12,'price':70})
  app.put('purchases',app.reconcile(app.get('purchases'),[{'playerId':2,'teamId':4,'bidAmount':45}]))
  app.mutate('/api/undo',{});self.assertNotIn('1',app.get('purchases'));self.assertIn('2',app.get('purchases'))
 def test_research_survives_data_refresh(self):
  app.mutate('/api/research',{'id':1,'notes':'My view','target':55,'tags':'assists, star'})
  app.ingest([{'player':{'id':1,'fullName':'Test player'}}],2027)
  self.assertEqual(app.get('research')['1']['notes'],'My view')
 def test_overlapping_collections_and_import(self):
  for n in ['Assists','Stars']:app.mutate('/api/collections',{'action':'create','name':n})
  for c in app.get('collections'):app.mutate('/api/collections',{'action':'toggle','id':c['id'],'playerId':1})
  self.assertTrue(all(1 in c['players'] for c in app.get('collections')))
  app.mutate('/api/purchase',{'playerId':1,'teamId':12,'price':20})
  app.mutate('/api/import',{'version':1,'research':{},'collections':[]})
  self.assertIn('1',app.get('purchases'))
 def test_invalid_import_does_not_overwrite(self):
  app.put('research',{'1':{'notes':'keep'}})
  with self.assertRaises(ValueError):app.mutate('/api/import',{'version':1,'research':{},'collections':[{'id':'bad"id','name':'x','players':[]}]})
  self.assertEqual(app.get('research')['1']['notes'],'keep')
 def test_connection_failure_preserves_workspace_and_recovers(self):
  app.put('research',{'1':{'notes':'keep'}})
  with patch.object(app,'api_request',side_effect=httpx.ConnectError('offline')):app.sync()
  self.assertFalse(app.get('sync')['ok']);self.assertIn('Cannot reach ESPN',app.get('sync')['error'])
  self.assertEqual(app.get('research')['1']['notes'],'keep')
  with patch.object(app,'config',return_value={'league_id':1,'year':2027}),patch.object(app,'api_request',return_value={'settings':{},'draftDetail':{},'teams':[]}):app.sync()
  self.assertTrue(app.get('sync')['ok']);self.assertIsNone(app.get('sync')['error'])
 def test_expired_cookie_has_actionable_error(self):
  response=httpx.Response(401,request=httpx.Request('GET','https://example.test'))
  with patch.object(app,'api_request',side_effect=httpx.HTTPStatusError('unauthorized',request=response.request,response=response)):app.sync()
  self.assertIn('Update your ESPN cookies',app.get('sync')['error'])
 def test_failed_player_refresh_remains_pending_for_retry(self):
  with patch.object(app,'api_request',side_effect=httpx.ConnectError('offline')):app.sync(True)
  self.assertTrue(app.get('sync')['playerRefreshPending'])
 def test_draft_totals_weighted_shooting_and_other_team_average(self):
  def p(pid,pts,fgm,fga,ftm,fta):return {'id':pid,'actual':{'per':{'pts':pts,'fgm':fgm,'fga':fga,'ftm':ftm,'fta':fta},'total':{'pts':pts*10,'fgm':fgm*10,'fga':fga*10,'ftm':ftm*10,'fta':fta*10}}}
  players=[p(1,20,8,10,2,4),p(2,10,2,10,6,6),p(3,30,6,10,8,10)]
  buys={str(i):{'playerId':i,'teamId':12 if i<3 else 4} for i in [1,2,3]}
  league={'myTeam':12,'teams':[{'id':12},{'id':4},{'id':9}]}
  c=app.draft_comparison(players,buys,league)
  self.assertEqual(c['mine']['values']['pts'],30)
  self.assertEqual(c['mine']['values']['fg'],.5)
  self.assertEqual(c['mine']['values']['ft'],.8)
  self.assertEqual(c['mine']['values']['fga'],20)
  self.assertEqual(c['opponents']['values']['pts'],15) # Empty team participates in counting averages.
  self.assertEqual(c['opponents']['values']['fg'],.6) # Empty shooting sample does not.
  self.assertEqual(c['opponents']['sample']['fg'],1)
  self.assertEqual(app.draft_comparison(players,buys,league,mode='total')['mine']['values']['pts'],300)
 def test_opponents_are_averaged_by_team_not_pooled_attempts(self):
  players=[{'id':1,'projected':{'per':{'fgm':1,'fga':2}}},{'id':2,'projected':{'per':{'fgm':9,'fga':10}}}]
  buys={'1':{'playerId':1,'teamId':4},'2':{'playerId':2,'teamId':9}}
  c=app.draft_comparison(players,buys,{'myTeam':12,'teams':[{'id':12},{'id':4},{'id':9}]},'projected')
  self.assertAlmostEqual(c['opponents']['values']['fg'],.7)
 def test_missing_player_stats_are_not_fabricated(self):
  c=app.draft_comparison([{'id':1}],{'1':{'playerId':1,'teamId':12}},{'myTeam':12,'teams':[{'id':12},{'id':4}]})
  self.assertIsNone(c['mine']['values']['pts']);self.assertEqual(c['mine']['covered'],0)
  self.assertEqual(c['opponents']['values']['pts'],0);self.assertIsNone(c['opponents']['values']['fg'])
 def test_checkpoint_restores_all_research_without_touching_purchases(self):
  app.put('research',{'1':{'tier':'Tier 2','tags':'assists','notes':'keep','target':40,'max':45,'rank':12,'confidence':4,'discuss':True}})
  app.put('collections',[{'id':'stars','name':'Stars','players':[1]}])
  app.put('prefs',{'filters':{'nbaTeam':'DEN','excluded':{'tags':['injury']}}})
  saved=app.mutate('/api/saves',{'name':'First pass'})['save']
  app.mutate('/api/research',{'id':1,'tier':'Tier 5'})
  app.mutate('/api/purchase',{'playerId':1,'teamId':12,'price':20})
  app.mutate('/api/saves/restore',{'id':saved['id']})
  self.assertEqual(app.get('research')['1']['tier'],'Tier 2')
  self.assertEqual(app.get('prefs')['filters']['nbaTeam'],'DEN')
  self.assertEqual(app.get('collections')[0]['players'],[1]);self.assertIn('1',app.get('purchases'))
  safety=next(x for x in app.list_saves() if x['name']=='Automatic safety save before restore')
  self.assertEqual(app.saved_research(safety['id'])['research']['1']['tier'],'Tier 5')
  payload=app.saved_research(saved['id']);self.assertEqual(payload['version'],1)
  self.assertNotIn('purchases',payload);self.assertNotIn('connection',payload)
 def test_tier_only_update_preserves_notes_and_prices(self):
  app.mutate('/api/research',{'id':1,'notes':'Keep me','target':40,'tags':'star'})
  app.mutate('/api/research',{'id':1,'tier':'Tier 1'})
  self.assertEqual(app.get('research')['1']['notes'],'Keep me');self.assertEqual(app.get('research')['1']['target'],40)

if __name__=='__main__':unittest.main()
