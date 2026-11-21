"""Simplified movement probe on the real map, NOT an official simulator."""
import sys,json,gzip,random,math,copy,time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bot import Bot
from collections import deque
root=str(ROOT)
with gzip.open(root+'/check/stream.jsonl.gz','rt') as f: msgs=[json.loads(l) for l in f]
h=msgs[0];h['map']['dir']=root+'/arena';b=Bot(h);rng=random.Random(2112)
initial=next(m for m in msgs if m['type']=='obs')
largest=max(range(len(b.nav.component_sizes)),key=b.nav.component_sizes.__getitem__);opened=[i for i,v in enumerate(b.nav.open) if v and b.nav.components[i]==largest]
results=[]
for trial in range(12):
 start=b.nav.point(rng.choice(opened));goal=b.nav.point(rng.choice(opened))
 while not 100<math.dist(start,goal)<350: goal=b.nav.point(rng.choice(opened))
 o=copy.deepcopy(initial);me=o['self'];me['pos']=[*start,b.world.ground(*start)]
 o['zone'].update(center=[0,0],radius=2000,next_center=[0,0],next_radius=1800)
 b.mode='explore';b.nav.path=[];b.nav.goal=None;b.nav.planned=-100;b.history.clear()
 distance=math.dist(start,goal);travel=0
 for i in range(1000):
  o['t']=i*.1;o['tick']=i*2
  p=me['pos'];wp=b.nav.waypoint(p,goal,o['t'],o['zone'],[],2.8,9)
  move,boost,jump=b.steer(o,wp,[],None)
  speed=19.5 if boost else 11.7
  nextp=[p[0]+move[0]*speed*.1,p[1]+move[1]*speed*.1]
  if b.world.travel_clear(p,nextp,2.5,9):
   travel+=math.dist(p[:2],nextp);me['pos']=[*nextp,b.world.ground(*nextp)]
  if math.dist(me['pos'][:2],goal)<7: break
 result={'trial':trial,'start':start,'goal':goal,'direct_m':round(distance),'travel_m':round(travel),'steps':i+1,'remaining_m':round(math.dist(me['pos'][:2],goal),1)}
 results.append(result);print(json.dumps(result),flush=True)
print('Reached',sum(r['remaining_m']<7 for r in results),'of',len(results),flush=True)

if any(r["remaining_m"]>=7 for r in results):
 sys.exit(1)
