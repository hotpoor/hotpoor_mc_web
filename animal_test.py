"""Animal combat, trust, taming, shared food and persistent companions."""
import math
import tempfile
import time
from pathlib import Path
from db import Database
from game import Game, Player
import animal_system as animals
from world import collides


def main():
    with tempfile.TemporaryDirectory() as directory:
        db = Database(str(Path(directory) / 'animal.db'))
        g = Game(db)
        now = time.monotonic()
        dog = next(o for o in g.objects if o['kind'] == 'animal' and o['animal'] == 'dog')
        wolf = next(o for o in g.objects if o['kind'] == 'animal' and o['animal'] == 'wolf')
        tiger = next(o for o in g.objects if o['kind'] == 'animal' and o['animal'] == 'tiger')
        for beast in [o for o in g.objects if o['kind'] == 'animal' and o['animal'] != 'dog']: beast['last_attack'] = now + 1000
        p = Player('a', '主人甲', 'red', None, dog['x'], dog['z'] + 1)
        q = Player('b', '路人乙', 'blue', None, dog['x'] + 2, dog['z'])
        g.players = {p.id: p, q.id: q}
        # Every weapon can hit animals, including melee and arrows; no duplicate loot.
        assert dog in g.targets(p)
        g.damage_object(p, dog, 1, now)
        assert dog['favor'][p.name] == -35 and dog['angry_at'] == p.name
        g.advance_animals(.05, now + 1)
        assert p.hp == 90 and q.hp == 100
        assert dog['favor'].get(q.name, 0) == 0
        # Feeding calms the dog; cooldown prevents consuming the whole inventory at once.
        animals.feed(g, p, now + 2)
        assert p.food == 2 and dog['favor'][p.name] == 0 and not dog['angry_at']
        animals.feed(g, p, now + 2.1)
        assert p.food == 2
        p.food = 10
        for i in range(3): animals.feed(g, p, now + 3 + i)
        assert dog['owner'] == p.name and dog['favor'][p.name] == 100
        animals.feed(g, q, now + 7)
        assert dog['owner'] == p.name  # Other players cannot steal a companion.
        # A trusted dog tolerates one hit but repeated abuse triggers betrayal.
        g.damage_object(p, dog, 1, now + 8)
        assert dog['owner'] == p.name and dog['favor'][p.name] == 65
        # Hungry and full dogs react differently to poop; neither grants positive trust.
        p.poop = 4
        dog['favor'][p.name] = 0; dog['owner'] = ''; dog['hunger'] = 10
        animals.feed(g, p, now + 10, poop=True)
        assert dog['favor'][p.name] == -5 and dog['hunger'] == 18 and not dog['angry_at']
        dog['hunger'] = 90
        animals.feed(g, p, now + 11, poop=True)
        assert dog['favor'][p.name] == -45 and dog['angry_at'] == p.name and dog['hunger'] == 90
        # Full inventory leaves shared excess food on the ground; normal food and poop stay separate.
        item = next(o for o in g.objects if o['kind'] == 'food_pickup' and 'expires' in o)
        p.x, p.z = -22, 4
        item.update(x=p.x, z=p.z, amount=3)
        p.food = 19
        g.interact(p, now + 12)
        assert p.food == 20 and item['amount'] == 2
        poop = next(o for o in g.objects if o['kind'] == 'poop_pickup')
        p.x, p.z = -22, 5; poop.update(x=p.x, z=p.z)
        before = p.poop
        g.interact(p, now + 13)
        assert p.poop == before + 1 and poop not in g.objects
        # Wolf and tiger attacks respect armor, jump height, wall collision and respawn protection.
        dog.update(angry_at='', angry_until=0, owner='')
        for beast, damage in [(wolf, 10), (tiger, 24)]:
            p.x, p.z = beast['x'], beast['z'] + 1
            q.x, q.z = 24, 0
            p.hp = 100; p.invuln_until = 0
            beast['last_attack'] = 0
            g.advance_animals(.05, now + 20)
            assert p.hp == 100 - damage, (beast['animal'], p.hp)
            p.invuln_until = now + 100
            g.advance_animals(.05, now + 22)
            assert p.hp == 100 - damage
        # Real projectile path, jump immunity and walls use the same animal hit rules.
        old_wolf = {key: wolf[key] for key in ('x', 'z', 'home_x', 'home_z')}
        wolf.update(x=-24, z=2, home_x=-24, home_z=2, last_attack=0)
        p.x, p.z, p.hp, p.invuln_until = -24, 3.5, 100, 0
        wall = {'x': -24, 'z': 3, 'h': 3, 'type': 'brick'}
        g.blocks.append(wall)
        g.advance_animals(.05, now + 23)
        assert p.hp == 100
        g.blocks.remove(wall)
        p.jump = 2
        g.advance_animals(.05, now + 25)
        assert p.hp == 100
        p.jump = 0
        p.x, p.z = -24, 4.5
        before = wolf['hp']
        g.shoot(p, math.pi, 0, now + 26, 1)
        for i in range(8): g.advance_arrows(.025, now + 26 + i * .025)
        assert wolf['hp'] < before
        wolf.update(old_wolf)
        # Defeated wild animals drop meat and armor exactly once and respawn later.
        count = len(g.objects)
        g.damage_object(p, tiger, 1000, now + 24)
        assert tiger['hp'] == 0 and tiger['ready'] == now + 84
        assert len(g.objects) == count + 2
        g.damage_object(p, tiger, 1000, now + 25)
        assert len(g.objects) == count + 2
        assert any(o['id'].startswith('meat-') and o['amount'] == 4 for o in g.objects)
        # Companion catch-up crosses a chapter trip safely; dogs fight guards and guards retaliate.
        p.invuln_until = 0; p.hp = 100
        dog.update(owner=p.name, hp=100, angry_at='', angry_until=0, favor={p.name:100}, hunger=80)
        p.x, p.z = 0, -43
        g.advance_animals(.05, now + 26)
        assert math.hypot(dog['x'] - p.x, dog['z'] - p.z) < 3
        assert not collides(dog['x'], dog['z'], g.blocks, radius=.3)
        guard = next(o for o in g.objects if o['kind'] == 'enemy' and o['x'] == 0 and o['city'] == 'yellow')
        dog.update(x=guard['x'], z=guard['z'] + 1, last_attack=0)
        p.x, p.z = guard['x'] + 2, guard['z'] + 1
        before = guard['hp']
        g.advance_animals(.05, now + 28)
        assert guard['hp'] == before - 12
        before = dog['hp']
        guard['last_attack'] = 0
        g.advance_enemies(.05, now + 29)
        assert dog['hp'] < before
        # Saved ownership and affection survive server restart; hunger decays over time.
        before = dog['hunger']; g.advance_animals(.1, now + 30)
        assert dog['hunger'] < before
        animals.save(g)
        restored = Game(db)
        saved = next(o for o in restored.objects if o['id'] == dog['id'])
        assert saved['owner'] == p.name and round(saved['favor'][p.name]) == 100
        assert all(not collides(o['x'], o['z'], g.blocks, radius=.25) for o in g.objects
                   if o['kind'] in ('food_pickup', 'poop_pickup') and o['id'].startswith('random-'))
        print('ANIMALS PASSED: individual trust, bites, feeding cooldown, taming, no theft, hunger/poop reactions, shared inventory, predators, loot, follow, guard combat, persistence, safe random drops')


if __name__ == '__main__':
    main()
