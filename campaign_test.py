"""Isolated campaign regression checks: combat, AI, city gates and scoped reset."""
import math
import tempfile
import time
from pathlib import Path
from db import Database
from game import Game, Player, ARMOR_TYPES
from world import collides


def main():
    with tempfile.TemporaryDirectory() as directory:
        game = Game(Database(str(Path(directory) / 'campaign.db')))
        now = time.monotonic()
        p = Player('campaign-player', '测试将军', 'red', None, 0, -43)
        game.players[p.id] = p
        enemies = [o for o in game.objects if o['kind'] == 'enemy']
        yellow = [o for o in enemies if o['city'] == 'yellow']
        assert len(game.world['cities']) == 10 and sum(bool(o.get('boss')) for o in yellow) == 3
        for city in game.world['cities']:
            for r in (18, 8):
                for side, dx, dz in [('north', 0, -r), ('south', 0, r), ('east', r, 0), ('west', -r, 0)]:
                    assert collides(city['x'] + dx, city['z'] + dz, game.blocks) == (side not in city['gates'])
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
        assert not game.city_unlocked('hulao')
        game.damage_object(p, other, 10000, now)
        assert other['hp'] == 80  # Later chapters cannot be attacked early.
        for enemy in yellow: game.damage_object(p, enemy, 10000, now)
        assert game.city_unlocked('hulao')
        game.damage_object(p, other, 10000, now)
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
        test_loot_progress_armor(game, p, now, directory)
        print('CAMPAIGN PASSED: ten chapters, thirty bosses, walkable gates, melee/slam/ranged, pursuit, NPC kill, scoped revival, stone cooldown, snapshots')


def test_loot_progress_armor(game, p, now, directory):
    from unittest.mock import patch
    enemy = next(o for o in game.objects if o['kind'] == 'enemy' and o['city'] == 'yellow' and not o.get('boss'))
    boss = next(o for o in game.objects if o['kind'] == 'enemy' and o['city'] == 'yellow' and o.get('boss'))
    # Guarantee the probabilistic armor path; damage_object must not drop twice.
    with patch('game.random.random', return_value=0):
        game.damage_object(p, enemy, 10000, now)
    game.damage_object(p, boss, 10000, now)
    weapons = [o for o in game.objects if o['id'].startswith('loot-')]
    assert any(o['uses'] == 10 and o['rarity'] == 'normal' for o in weapons)
    assert any(o['uses'] == 40 and o['rarity'] == 'boss' for o in weapons)
    count = len(game.objects)
    game.damage_object(p, boss, 10000, now)
    assert len(game.objects) == count
    # Another player can claim a shared drop exactly once.
    q = Player('loot-player', '拾取将军', 'blue', None, -22, 3)
    game.players[q.id] = q
    drop = next(o for o in weapons if o['rarity'] == 'boss')
    drop['x'], drop['z'] = q.x, q.z
    game.interact(q, now)
    assert q.weapon == drop['weapon'] and q.weapons[q.weapon] == 40 and drop not in game.objects
    game.interact(p, now)
    assert drop not in game.objects
    # Equip a single armor slot, absorb damage, break and return to full damage.
    armor_drop = next(o for o in game.objects if o['kind'] == 'armor_pickup' and o['armor_kind'] == 'iron')
    q.x, q.z = -22, 6
    armor_drop['x'], armor_drop['z'] = q.x, q.z
    game.interact(q, now)
    assert q.armor['kind'] == 'iron' and q.armor['durability'] == 80
    q.invuln_until = 0
    game.damage(p, q, 20, now)
    assert q.hp == 88 and q.armor['durability'] == 72
    q.armor['durability'] = 2
    game.damage(p, q, 20, now)
    assert q.hp == 70 and not q.armor
    assert any(e['k'] == 'armor_break' and e['id'] == q.id for e in game.events)
    game.damage(p, q, 20, now)
    assert q.hp == 50
    # Better armor replaces the old piece without stacking; the old durability drops.
    q.armor = {**ARMOR_TYPES['iron'], 'kind': 'iron', 'durability': 30}
    elite = next(o for o in game.objects if o['kind'] == 'armor_pickup' and o['armor_kind'] == 'elite')
    q.x, q.z = -22, 5
    elite['x'], elite['z'] = q.x, q.z
    game.interact(q, now)
    assert q.armor['kind'] == 'elite' and q.armor['durability'] == 160
    assert any(o['kind'] == 'armor_pickup' and o['armor_kind'] == 'iron' and o['durability'] == 30 for o in game.objects)
    game.damage(p, q, 20, now)
    assert q.hp == 42 and q.armor['durability'] == 148
    # The connected road centre is walkable; water cannot be crossed even by jumping.
    from world import ROUTES, CITIES
    for i, city in enumerate(CITIES):
        prev = CITIES[i - 1] if i else {'x': 0, 'z': 0}
        for step in range(111):
            t = step / 110
            assert not collides(prev['x'] + (city['x'] - prev['x']) * t,
                                prev['z'] + (city['z'] - prev['z']) * t, game.blocks)
    for moat in game.world['moats']:
        assert collides((moat['x0'] + moat['x1']) / 2, (moat['z0'] + moat['z1']) / 2, game.blocks, feet=5)
    assert len(game.world['villages']) == 10 and len([o for o in game.objects if o['kind'] == 'animal']) == 20
    animals = [o for o in game.objects if o['kind'] == 'animal']
    before = [(o['x'], o['z']) for o in animals]
    game.advance_animals(.1, now)
    assert any((o['x'], o['z']) != old for o, old in zip(animals, before))
    assert all(not collides(o['x'], o['z'], game.blocks, radius=.3) for o in animals)
    # Village fountains heal players under the existing crystal rule.
    village = game.world['villages'][1]
    p.x, p.z, p.hp, p.last_input = village['x'], village['z'], 50, time.monotonic()
    game.last_tick = time.monotonic() - .05
    game.tick()
    assert p.hp > 50 and p.heal_rate == 16
    # Complete all chapters and use the actual E interaction to travel to each next city.
    for i, city in enumerate(game.world['cities']):
        assert game.city_unlocked(city['id'])
        for obj in game.objects[:]:
            if obj['kind'] == 'enemy' and obj['city'] == city['id']:
                game.damage_object(p, obj, 10000, now)
        assert city['id'] in game.cleared_cities
        if i < 9:
            portal = next(o for o in game.objects if o['id'] == 'portal-' + city['id'] + '-next')
            p.x, p.z = portal['x'], portal['z']
            game.interact(p, now)
            dest = game.world['cities'][i + 1]
            assert (p.x, p.z) == (dest['x'], dest['z'] + 16)
    assert len(game.cleared_cities) == 10
    restored = Game(Database(str(Path(directory) / 'campaign.db')))
    assert restored.cleared_cities == game.cleared_cities
    assert all(o['hp'] == 0 for o in restored.objects if o['kind'] == 'enemy')
    # Armor state is shared in snapshots and drops with its remaining durability on death.
    assert next(o for o in game.snapshot()['players'] if o['id'] == q.id)['armor']['durability'] == 148
    game.damage(p, q, 1000, now)
    assert not q.alive and not q.armor
    print('  [ok] shared one-time drops, 10/40 uses, E equip, white-bar state, 40/60% armor, breakage, single slot, 10 gates, persisted progression')


if __name__ == '__main__':
    main()
