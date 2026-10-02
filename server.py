"""Local fantasy research workspace. Run with the NBA stats Python environment."""
import json, sqlite3, threading, time, uuid, traceback, sys, os
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from datetime import datetime, timezone
import httpx

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'; DATA.mkdir(exist_ok=True)
DB=DATA/'workspace.sqlite3'
APP_VERSION='1.1.0'
RESEARCH_KEYS=('research','collections','prefs')
LOCK=threading.RLock(); SYNC_LOCK=threading.Lock()
STAT_IDS={'pts':'0','reb':'6','ast':'3','stl':'2','blk':'1','tov':'11','threes':'17','fg':'19','ft':'20','fgm':'13','fga':'14','ftm':'15','fta':'16','min':'40'}
POSITIONS={1:'PG',2:'SG',3:'SF',4:'PF',5:'C'}
TEAMS={1:'ATL',2:'BOS',3:'NOP',4:'CHI',5:'CLE',6:'DAL',7:'DEN',8:'DET',9:'GSW',10:'HOU',11:'IND',12:'LAC',13:'LAL',14:'MIA',15:'MIL',16:'MIN',17:'BKN',18:'NYK',19:'ORL',20:'PHI',21:'PHX',22:'POR',23:'SAC',24:'SAS',25:'OKC',26:'UTA',27:'WAS',28:'TOR',29:'MEM',30:'CHA'}

def now(): return datetime.now(timezone.utc).isoformat()
def conn():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init():
 with conn() as c:
  c.executescript('CREATE TABLE IF NOT EXISTS players(id INTEGER PRIMARY KEY, data TEXT NOT NULL); CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY,value TEXT NOT NULL);')
  c.execute('CREATE TABLE IF NOT EXISTS research_saves(id TEXT PRIMARY KEY,name TEXT NOT NULL,created TEXT NOT NULL,payload TEXT NOT NULL)')
  for k,v in {'research':{},'collections':[],'purchases':{},'undo':[],'sync':{},'league':{},'prefs':{}}.items():
   c.execute('INSERT OR IGNORE INTO kv VALUES(?,?)',(k,json.dumps(v)))
def get(k,default=None):
 with conn() as c: r=c.execute('SELECT value FROM kv WHERE key=?',(k,)).fetchone()
 return json.loads(r[0]) if r else default
def put(k,v):
 with conn() as c: c.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',(k,json.dumps(v)))
def config(): return json.loads((DATA/'connection.json').read_text())
def backup():
 folder=DATA/'backups'; folder.mkdir(exist_ok=True)
 target=folder/(datetime.now().strftime('%Y-%m-%d')+'.sqlite3')
 with conn() as source, sqlite3.connect(target) as dest: source.backup(dest)
def export_research():
 with LOCK:
  return {'version':1,'appVersion':APP_VERSION,'exported':now(),**{k:get(k) for k in RESEARCH_KEYS}}
def save_research(name):
 name=str(name).strip()[:100]
 if not name:raise ValueError('Enter a save name')
 entry={'id':uuid.uuid4().hex,'name':name,'created':now()}
 with conn() as c:c.execute('INSERT INTO research_saves VALUES(?,?,?,?)',(entry['id'],name,entry['created'],json.dumps(export_research())))
 return entry
def saved_research(save_id):
 with conn() as c:r=c.execute('SELECT payload FROM research_saves WHERE id=?',(save_id,)).fetchone()
 if not r:raise ValueError('Research save not found')
 return json.loads(r[0])
def list_saves():
 with conn() as c:return [dict(r) for r in c.execute('SELECT id,name,created FROM research_saves ORDER BY created DESC')]
def draft_comparison(players,purchases,league,source='actual',mode='per'):
 lookup={p['id']:p for p in players}; keys=['pts','reb','ast','threes','stl','blk','fg','ft','tov','fga','fta']
 def team_profile(team_id):
  roster=[p for p in purchases.values() if p['teamId']==team_id]
  stats=[lookup.get(p['playerId'],{}).get(source) for p in roster]
  rows=[s[mode] for s in stats if s and isinstance(s.get(mode),dict)]
  values={}; coverage={}
  for key in keys:
   if key in ('fg','ft'):
    made,attempt=('fgm','fga') if key=='fg' else ('ftm','fta')
    valid=[r for r in rows if r.get(made) is not None and r.get(attempt) is not None]
    denominator=sum(r[attempt] for r in valid)
    values[key]=sum(r[made] for r in valid)/denominator if denominator else None
   else:
    valid=[r for r in rows if r.get(key) is not None]
    values[key]=sum(r[key] for r in valid) if valid or not roster else None
   coverage[key]=len(valid)
  return {'values':values,'players':len(roster),'covered':len(rows),'coverage':coverage}
 mine=team_profile(league.get('myTeam'))
 opponents=[team_profile(t['id']) for t in league.get('teams',[]) if t['id']!=league.get('myTeam')]
 averages={}; sample={}
 for key in keys:
  vals=[t['values'][key] for t in opponents if t['values'][key] is not None]
  averages[key]=sum(vals)/len(vals) if vals else None;sample[key]=len(vals)
 return {'mine':mine,'opponents':{'values':averages,'teams':len(opponents),'sample':sample,'players':sum(t['players'] for t in opponents),'covered':sum(t['covered'] for t in opponents)}}
def parse_stats(player,year,source):
 rows=[r for r in player.get('stats',[]) if r.get('seasonId')==year and r.get('statSourceId')==source and r.get('statSplitTypeId')==0 and r.get('stats')]
 if not rows:return None
 row=next((r for r in rows if r.get('proTeamId',0)==0),rows[0]); raw=row['stats']; avg=row.get('averageStats',{})
 gp=raw.get('42',raw.get('41'))
 totals={key:raw.get(sid) for key,sid in STAT_IDS.items()}
 per={key:avg.get(sid,raw.get(sid) if key in ('fg','ft') else (raw[sid]/gp if gp and sid in raw else None)) for key,sid in STAT_IDS.items()}
 return {'gp':gp,'per':per,'total':totals}
def parse_player(entry,year):
 p=entry['player']; rank=p.get('draftRanksByRankType',{}).get('ROTO',{})
 return {'id':p['id'],'name':p.get('fullName','Unknown'),'position':POSITIONS.get(p.get('defaultPositionId'),'—'),'team':TEAMS.get(p.get('proTeamId'),'FA'),'injury':p.get('injuryStatus','ACTIVE'),'active':p.get('active',True),'espnPrice':rank.get('auctionValue'),'leaguePrice':entry.get('draftAuctionValue'),'espnRank':rank.get('rank'),'published':rank.get('published',False),'actual':parse_stats(p,year-1,0),'projected':parse_stats(p,year,1),'source':'ESPN','updated':now()}
def ingest(entries,year):
 with conn() as c:
  for e in entries:
   p=parse_player(e,year)
   c.execute('INSERT OR REPLACE INTO players VALUES(?,?)',(p['id'],json.dumps(p)))
def api_request(views,players=False):
 cfg=config(); url=f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{cfg['year']}/segments/0/leagues/{cfg['league_id']}"
 headers={}; rows=[]
 with httpx.Client(timeout=35,cookies={'espn_s2':cfg.get('espn_s2',''),'SWID':cfg.get('swid','')}) as client:
  for offset in range(0,10000,1000) if players else [0]:
   if players: headers['x-fantasy-filter']=json.dumps({'players':{'limit':1000,'offset':offset,'sortPercOwned':{'sortPriority':1,'sortAsc':False}}})
   r=client.get(url,params=[('view',v) for v in views],headers=headers); r.raise_for_status(); data=r.json()
   if not players:return data
   page=data.get('players',[]); rows.extend(page)
   if len(page)<1000:break
  return {'players':rows}
def reconcile(purchases,picks):
 result=dict(purchases)
 for pick in picks:
  pid=pick.get('playerId',-1); tid=pick.get('teamId',-1); price=pick.get('bidAmount')
  if pid<=0 or tid<=0 or price is None:continue
  key=str(pid); incoming={'playerId':pid,'teamId':tid,'price':price,'source':'ESPN','pickId':pick.get('id'),'updated':now()}
  existing=result.get(key)
  if existing and existing.get('source')=='Manual' and (existing['teamId']!=tid or existing['price']!=price):
   existing=dict(existing); existing['conflict']=incoming; result[key]=existing
  else:result[key]=incoming
 return result
def sync(full=False):
 if not SYNC_LOCK.acquire(False):return
 status=get('sync',{}); status.update(busy=True,attempt=now())
 if full:status['playerRefreshPending']=True
 put('sync',status)
 try:
  data=api_request(['mSettings','mTeam','mDraftDetail']); cfg=config(); s=data.get('settings',{}); ds=s.get('draftSettings',{}); draft=data.get('draftDetail',{})
  league={'name':s.get('name','Ball Don’t Lie'),'id':cfg['league_id'],'year':cfg['year'],'myTeam':cfg.get('team_id',12),'budget':ds.get('auctionBudget',200),'draftDate':ds.get('date'),'slots':sum(v for k,v in s.get('rosterSettings',{}).get('lineupSlotCounts',{}).items() if k not in ['13','14']),'teams':[{'id':t['id'],'name':t.get('name') or (t.get('location','')+' '+t.get('nickname','')).strip(),'abbrev':t.get('abbrev','')} for t in data.get('teams',[])],'inProgress':draft.get('inProgress',False),'drafted':data.get('status',{}).get('isActive',False) and draft.get('drafted',False)}
  with LOCK:
   put('league',league); put('purchases',reconcile(get('purchases',{}),draft.get('picks',[])))
  if full:
   entries=api_request(['kona_player_info'],True)['players']
   if not entries:raise ValueError('ESPN returned an empty player pool. Saved player data was retained.')
   ingest(entries,cfg['year']); status['playersUpdated']=now(); status['playerCount']=len(entries); status['playerRefreshPending']=False
  status.update(ok=True,error=None,lastSuccess=now(),failures=0)
 except Exception as exc:
  if isinstance(exc,httpx.HTTPStatusError) and exc.response.status_code in (401,403): message='ESPN rejected the session. Update your ESPN cookies in Connection, then reconnect.'
  elif isinstance(exc,httpx.HTTPStatusError): message=f'ESPN returned HTTP {exc.response.status_code}. Your saved workspace remains available.'
  elif isinstance(exc,httpx.RequestError): message='Cannot reach ESPN. Check your internet connection; automatic retries are enabled.'
  else:message=str(exc)[:250]
  status.update(ok=False,error=message,failures=status.get('failures',0)+1)
 finally:
  status['busy']=False; status['nextRetrySeconds']=min(120,15*2**min(status.get('failures',0),3)); put('sync',status); SYNC_LOCK.release()
def loop():
 sync(True); last_full=time.monotonic()
 while True:
  time.sleep(get('sync',{}).get('nextRetrySeconds',15))
  full=time.monotonic()-last_full>21600 or get('sync',{}).get('playerRefreshPending',False); sync(full)
  if full:last_full=time.monotonic(); backup()
def state():
 with LOCK, conn() as c:
  data={'players':[json.loads(r[0]) for r in c.execute('SELECT data FROM players')],**{k:get(k) for k in ['research','collections','purchases','league','sync','prefs']},'canUndo':bool(get('undo')),'appVersion':APP_VERSION}
  data['draftComparison']={s:{m:draft_comparison(data['players'],data['purchases'],data['league'],s,m) for m in ('per','total')} for s in ('actual','projected')}
  return data
def undo_snapshot(pid):
 history=get('undo',[]); history.append({'playerId':pid,'before':get('purchases',{}).get(pid)}); put('undo',history[-30:])
def number(value,low=0,high=10000):
 if value in (None,''):return None
 val=float(value)
 if not low<=val<=high:raise ValueError('Number is outside the allowed range')
 return val
def mutate(path,b):
 with LOCK:
  if path=='/api/research':
   pid=str(int(b['id'])); r=get('research',{}); old=r.get(pid,{})
   old.update({k:str(b[k])[:10000] for k in ['notes','tier','tags'] if k in b})
   for k in ['target','max','rank','confidence']:
    if k in b:old[k]=number(b[k],0,5 if k=='confidence' else 10000)
   if 'discuss' in b:old['discuss']=bool(b['discuss'])
   old['updated']=now(); r[pid]=old; put('research',r)
  elif path=='/api/collections':
   cs=get('collections',[]); action=b['action']
   if action=='create':
    name=str(b.get('name','')).strip()[:60]
    if not name:raise ValueError('Enter a collection name')
    cs.append({'id':uuid.uuid4().hex,'name':name,'players':[]})
   else:
    col=next((x for x in cs if x['id']==b['id']),None)
    if not col:raise ValueError('Collection not found')
    if action=='delete':cs.remove(col)
    elif action=='rename':
     name=str(b['name']).strip()[:60]
     if not name:raise ValueError('Enter a collection name')
     col['name']=name
    elif action=='toggle':
     pid=int(b['playerId'])
     if pid in col['players']:col['players'].remove(pid)
     else:col['players'].append(pid)
    else:raise ValueError('Unknown collection action')
   put('collections',cs)
  elif path=='/api/purchase':
   pid=str(int(b['playerId'])); purchases=get('purchases',{})
   with conn() as c:
    if not c.execute('SELECT 1 FROM players WHERE id=?',(int(pid),)).fetchone():raise ValueError('Player not found')
   if b.get('remove'):
    if purchases.get(pid,{}).get('source')=='ESPN':raise ValueError('ESPN purchases cannot be deleted locally; correct the purchase instead')
    undo_snapshot(pid); purchases.pop(pid,None)
   elif b.get('acceptEspn'):
    if purchases.get(pid,{}).get('conflict'):undo_snapshot(pid); purchases[pid]=purchases[pid]['conflict']
   else:
    price=number(b.get('price')); tid=int(b['teamId'])
    if price is None or price<1 or price!=int(price):raise ValueError('Enter a whole-dollar purchase price of at least $1')
    league=get('league',{}); teams={t['id'] for t in league.get('teams',[])}
    if tid not in teams:raise ValueError('Select a league team')
    others=[p for key,p in purchases.items() if key!=pid and p['teamId']==tid]
    slots=league.get('slots',12); remaining=league.get('budget',200)-sum(p['price'] for p in others)
    if len(others)>=slots or price>remaining-max(0,slots-len(others)-1):raise ValueError('Purchase exceeds the team’s budget or remaining roster slots')
    undo_snapshot(pid); purchases[pid]={'playerId':int(pid),'teamId':tid,'price':price,'source':'Manual','updated':now()}
   put('purchases',purchases)
  elif path=='/api/undo':
   h=get('undo',[])
   if h:
    last=h.pop(); pid=last['playerId']; purchases=get('purchases',{})
    if purchases.get(pid,{}).get('source')=='ESPN':raise ValueError('This purchase is now confirmed by ESPN. Use Correct purchase for an explicit override.')
    if last['before'] is None:purchases.pop(pid,None)
    else:purchases[pid]=last['before']
    put('purchases',purchases); put('undo',h)
  elif path=='/api/prefs':put('prefs',b)
  elif path=='/api/connection':
   c=config()
   for k in ['espn_s2','swid']:
    if b.get(k):c[k]=str(b[k]).strip()
   (DATA/'connection.json').write_text(json.dumps(c)); threading.Thread(target=sync,args=(True,),daemon=True).start()
  elif path=='/api/sync':threading.Thread(target=sync,args=(b.get('full',False),),daemon=True).start()
  elif path=='/api/saves':return {'ok':True,'save':save_research(b.get('name',''))}
  elif path=='/api/saves/restore':return mutate('/api/import',saved_research(str(b['id'])))
  elif path=='/api/import':
   if b.get('version')!=1 or not isinstance(b.get('research'),dict) or not isinstance(b.get('collections'),list):raise ValueError('Not a valid workspace backup')
   for pid,r in b['research'].items():
    if not pid.isdigit() or not isinstance(r,dict):raise ValueError('Invalid player research')
    for key in ['notes','tags','tier']:
     if key in r and not isinstance(r[key],str):raise ValueError('Invalid research field')
    for key in ['target','max','rank','confidence']:
     if key in r:r[key]=number(r[key],0,5 if key=='confidence' else 10000)
   seen=set()
   for col in b['collections']:
    if not isinstance(col,dict) or not isinstance(col.get('id'),str) or not col['id'].isalnum() or col['id'] in seen:raise ValueError('Invalid collection ID')
    seen.add(col['id'])
    if not isinstance(col.get('name'),str) or not col['name'].strip() or len(col['name'])>60:raise ValueError('Invalid collection name')
    if not isinstance(col.get('players'),list) or not all(isinstance(p,int) and p>0 for p in col['players']):raise ValueError('Invalid collection members')
   if 'prefs' in b and not isinstance(b['prefs'],dict):raise ValueError('Invalid preferences')
   backup(); save_research('Automatic safety save before restore')
   # Research-only import deliberately does not overwrite live ESPN purchases.
   with conn() as c:
    for k in RESEARCH_KEYS:
     if k in b:c.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',(k,json.dumps(b[k])))
  else:raise ValueError('Unknown operation')
 return {'ok':True}

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def send(self,obj,status=200,ctype='application/json'):
  payload=json.dumps(obj,allow_nan=False).encode() if ctype=='application/json' else obj
  self.send_response(status); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(payload))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(payload)
 def do_GET(self):
  path=urlparse(self.path).path
  if path=='/api/state':return self.send(state())
  if path=='/api/health':return self.send({'ok':True,'version':APP_VERSION})
  if path=='/api/export':return self.send(export_research())
  if path=='/api/saves':return self.send(list_saves())
  if path.startswith('/api/saves/'):
   try:return self.send(saved_research(path.rsplit('/',1)[-1]))
   except ValueError as e:return self.send({'error':str(e)},404)
  files={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/board-utils.js':('board-utils.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
  if path in files:
   name,typ=files[path]; return self.send((ROOT/'static'/name).read_bytes(),ctype=typ)
  self.send({'error':'Not found'},404)
 def do_POST(self):
  origin=self.headers.get('Origin'); host=self.headers.get('Host')
  if origin and origin!=f'http://{host}':return self.send({'error':'Origin rejected'},403)
  try:
   length=int(self.headers.get('Content-Length',0))
   if length>4_000_000:raise ValueError('Request too large')
   b=json.loads(self.rfile.read(length)); self.send(mutate(urlparse(self.path).path,b))
  except (ValueError,KeyError,TypeError) as e:self.send({'error':str(e)},400)
  except Exception:self.send({'error':'Unable to save. Your previously saved data is retained.'},500); traceback.print_exc()

if __name__=='__main__':
 init()
 with LOCK:save_research('Automatic save before launch '+APP_VERSION)
 raw=DATA/'raw_players.json'
 with conn() as c:empty=c.execute('SELECT count(*) FROM players').fetchone()[0]==0
 if empty and raw.exists():ingest(json.loads(raw.read_text()).get('players',[]),config()['year'])
 backup(); threading.Thread(target=loop,daemon=True).start()
 print('Fantasy workspace running at http://127.0.0.1:8765',flush=True)
 ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()
