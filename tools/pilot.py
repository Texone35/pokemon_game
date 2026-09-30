"""Pilote automatique du Pokémon du joueur (tests) : se déplace comme une IA et utilise ses attaques
comme un joueur (appui puis relâchement de la touche, visée « à la souris » sur la cible), achète
des objets et se transforme."""
import random

from game import config as C
from game.pokemon.units import BotBrain, PlayerBrain


class Pilot(PlayerBrain):
    """Joue à la place du joueur : se déplace comme une IA et utilise ses attaques comme un joueur
    (appui puis relâchement de la touche, visée à la souris)."""

    def __init__(self, unit, match):
        super().__init__(unit, match)
        self.bot = BotBrain(unit, match)
        self.bot.use_moves = lambda *a: False      # les attaques passent par les touches du joueur
        if not match.authority:                    # invité : pas de tir local sans passer par le réseau
            unit.basic_attack = lambda *a, **k: False
        self.t = 0.0

    def update(self, dt):
        if self.dash_t > 0:
            return super().update(dt)
        self.dash_cd -= dt
        u, m = self.u, self.m
        self.target = m.find_target(u, C.TARGET_RANGE)
        moving = self.bot.update(dt)
        if not m.authority and self.target is not None and u.in_attack_range(self.target):
            self.use_auto()                         # invité : l'auto-attaque passe par la touche J (réseau)
        self.t -= dt
        if self.t <= 0:
            self.t = random.uniform(.4, 1.0)
            ready = [mv for mv in u.moves if not mv['locked'] and u.cd.get(mv['slot'], 0) <= 0]
            if ready and self.target is not None:
                mv = random.choice(ready)
                self.input(mv['key'])
                if self.aiming is not None:
                    self.indicator.show(u, mv, self.target.position)
                    self.cursor = lambda: self.target.position if self.target is not None else u.position
                    self.input(mv['key'] + ' up')
            if random.random() < .1:
                self.dash()
            if self.target is not None and u.can_transform():
                self.input(C.TRANSFORM_KEY)
            if m.can_shop(u) and len(u.items) < C.ITEM_SLOTS:          # achète ce qu'il peut
                for key, it in C.ITEMS.items():
                    if key not in u.items and u.gold >= it['price']:
                        m.request_buy(key)
                        break
        return moving
