import json, httpx
from pathlib import Path
c=json.loads((Path(__file__).parent/'data/connection.json').read_text())
url=f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{c['year']}/segments/0/leagues/{c['league_id']}"
f={'players':{'limit':1000,'sortPercOwned':{'sortPriority':1,'sortAsc':False}}}
with httpx.Client(timeout=40,cookies={'espn_s2':c['espn_s2'],'SWID':c['swid']}) as client:
 r=client.get(url,params={'view':'kona_player_info'},headers={'x-fantasy-filter':json.dumps(f)})
 print('status',r.status_code)
 d=r.json(); ps=d.get('players',[])
 print('players',len(ps),'keys',list(d))
 if ps:
  p=next((x for x in ps if x.get('player',{}).get('fullName')=='Nikola Jokic'),ps[0])
  print(json.dumps(p)[:22000])
 (Path(__file__).parent/'data/raw_players.json').write_text(json.dumps(d))
