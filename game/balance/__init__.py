"""Valeurs d'équilibrage de Pokémon Dominion : c'est ici qu'on règle le jeu, sans toucher au code.

  rules.py     la partie : durée, score, réapparition, base, esquive, visée, vision
  combat.py    dégâts : table des types, statuts (brûlure, ralentissement), talents
  arenas.py    arènes : capture, points, bonus d'équipe, météo, tour défensive, rivière
  economy.py   progression : expérience, niveaux, Poké Dollars gagnés
  items.py     objets de la boutique
  stats.py     stats des Pokémon : rôles, courbes early/late, lignées, formule de dégâts
  moves.py     attaques : kits (4 attaques + ultime), déblocage, visée, builds
  jungle.py    jungle : buffs, camps, petits sauvages, boss du Boss Pit, zones de soin
  lanes.py     vagues de sbires sur les voies entre les arènes

Toutes ces valeurs sont aussi accessibles depuis game.config (C.RESPAWN_TIME, C.CAMPS...).
"""
