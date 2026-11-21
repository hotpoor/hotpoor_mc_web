"""Isolated campaign regression checks: combat, AI, city gates and scoped reset."""
import math
import tempfile
import time
from pathlib import Path
from db import Database
from game import Game, Player
from world import collides


def main():
    with tempfile.TemporaryDirectory() as directory:
        game = Game(Database(str(Path(directory) / 'campaign.db')))
        now = time.monotonic()
        p = Player('campaign-player', '测试将军', 'red', None, 0, -43)
        game.players[p.id] = p
        enemies = [o for o in game.objects if o['kind'] == 'enemy']
        yellow = [o for o in enemies if o['city'] == 'yellow']
        assert len(game.world['cities']) == 4 and sum(bool(o.get('boss')) for o in yellow) == 3
        for city in game.world['cities']:
            for r in (18, 8) if city['id'] == 'yellow' else (18,):
                assert not collides(city['x'], city['z'] + r, game.blocks)
                assert collides(city['x'] + 5, city['z'] + r, game.blocks)
        assert all(not collides(o['x'], o['z'], game.blocks) for o in enemies)
        guard = next(o for o in yellow if o['x'] == 0)
        p.x, p.z = guard['x'], guard['z'] + 2
        p.weapon = 'hammer'
        game.attack(p, math.pi, now)
        assert guard['hp'] == 25
        game.hammer_slam(p, now + 2)
        assert guard['hp'] == 0 and guard['ready'] is None
        game.tick()
        assert guard['hp'] == 0
        # Each existing ranged path reaches campaign targets.
        guard.update(hp=80, x=0, z=-44)
        p.x, p.z = 0, -42
        p.wave_ready = p.beam_ready = 0
        game.wave(p, math.pi, now + 3, gun=True)
        assert guard['hp'] == 75
        game.wave(p, math.pi, now + 4, beam=True)
        assert guard['hp'] == 25
        game.shoot(p, math.pi, 0, now + 5, 1)
        for i in range(8): game.advance_arrows(.025, now + 5 + i * .025)
        assert guard['hp'] < 25
        # Pursuit, damage, collision and lethal NPC attack use server rules.
        guard.update(hp=80, x=0, z=-44, last_attack=0)
        p.x, p.z, p.hp = 0, -40, 100
        before = guard['z']
        game.advance_enemies(.1, now + 7)
        assert guard['z'] > before and not collides(guard['x'], guard['z'], game.blocks)
        p.z = guard['z'] + 1
        game.advance_enemies(.05, now + 9)
        assert p.hp == 92
        p.hp = 1
        game.advance_enemies(.05, now + 12)
        assert not p.alive and p.respawn_at > now + 12
        p.alive, p.hp = True, 100
        # Dead enemies remain dead even after future ticks; reset is city scoped.
        other = next(o for o in enemies if o['city'] == 'hulao')
        for enemy in yellow + [other]: game.damage_object(p, enemy, 10000, now)
        assert all(o['hp'] == 0 and o['ready'] is None for o in yellow + [other])
        stone = next(o for o in game.objects if o['id'] == 'time-yellow')
        p.x, p.z, p.weapon, p.last_attack = stone['x'], stone['z'] - 2, 'hammer', 0
        game.attack(p, 0, now + 15)
        assert stone['hp'] == 45
        game.attack(p, 0, now + 17)
        assert stone['hp'] == 0 and stone['ready'] == now + 27
        assert all(o['hp'] == o['max_hp'] and o['x'] == o['home_x'] and o['z'] == o['home_z'] for o in yellow)
        assert other['hp'] == 0
        stone['ready'] = time.monotonic() - 1
        game.tick()
        assert stone['hp'] == 100 and other['hp'] == 0
        snapshot = game.snapshot()
        assert any(o['kind'] == 'enemy' and 'attacking' in o for o in snapshot['objects'])
        print('CAMPAIGN PASSED: four cities, three bosses, walkable gates, melee/slam/ranged, pursuit, NPC kill, scoped revival, stone cooldown, snapshots')


if __name__ == '__main__':
    main()
