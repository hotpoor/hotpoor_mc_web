"""Geometry contracts for authoritative conquest and city rendering."""
import math
import unittest
from collections import deque
from open_world import build_open_world
from world import collides

class OpenWorldMapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w=build_open_world();cls.cities=cls.w['cities'];cls.blocks=cls.w['blocks']

    def test_population_bounds_and_budget(self):
        self.assertEqual(len(self.cities),24)
        self.assertEqual(len(self.w['factions']),8)
        names=[n for c in self.cities for n in c['bosses']]
        self.assertEqual(len(names),len(set(names)))
        self.assertLess(len(self.blocks),25000)
        for a in self.cities:
            for b in self.cities:
                if a is not b:self.assertGreater(math.hypot(a['x']-b['x'],a['z']-b['z']),110)
        self.assertTrue(all(abs(b['x'])<self.w['half']-2 and abs(b['z'])<self.w['half']-2 for b in self.blocks))

    def test_spawns_are_clear(self):
        for c in self.cities:
            for p in [c['capture'],c['safe_spawn'],*c['general_spawns'],*c['guard_spawns']]:
                self.assertFalse(collides(*p,self.blocks),(c['name'],p))
        for t in self.w['teams'].values():self.assertFalse(collides(*t['spawn'],self.blocks))
        for v in self.w['villages']:
            for dx,dz in [(0,0),(-5.5,-4),(5.5,-4),(-5.5,-6),(5.5,-6)]:
                self.assertFalse(collides(v['x']+dx,v['z']+dz,self.blocks))

    def test_gate_passage(self):
        for c in self.cities:
            x,z=c['x'],c['z'];targets={(0,-36),(0,36),(-36,0),(36,0),(4,52)}
            seen={(0,-15)};q=deque(seen)
            while q and not targets.issubset(seen):
                px,pz=q.popleft()
                for dx,dz in [(1,0),(-1,0),(0,1),(0,-1)]:
                    p=(px+dx,pz+dz)
                    if p in seen or not(-40<=p[0]<=40 and -40<=p[1]<=54):continue
                    if not collides(x+p[0],z+p[1],self.blocks):seen.add(p);q.append(p)
            self.assertTrue(targets.issubset(seen),c['name'])
            self.assertTrue(collides(x+10,z+42,self.blocks))
            self.assertTrue(collides(x-5,z+48,self.blocks))
            self.assertFalse(collides(x+4,z+48,self.blocks))

    def test_road_network(self):
        roads=self.w['roads'];seen={self.cities[0]['id']}
        self.assertEqual(len(roads),len(self.cities)-1)
        for _ in self.cities:
            for r in roads:
                if r['from'] in seen or r['to'] in seen:seen.update([r['from'],r['to']])
        self.assertEqual(len(seen),len(self.cities))

if __name__=='__main__':unittest.main()
