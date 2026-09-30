"""Tableau d'équilibrage : stats des lignées par niveau et temps pour mettre K.O. (sans objets ni buffs).

Lancer :  python tools/balance_table.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from game import config as C  # noqa: E402
from game.pokemon import kit  # noqa: E402

LEVELS = (1, 3, 5, 7, 10, 15)


def unit(line, level, build=None):
    form = C.form_for(line, level)
    st = kit.team_stats(line, form, level, build)
    return form, st


def main():
    print(f"{'lignée':11s} {'Nv':>3s} {'forme':12s} " + ' '.join(f'{C.STAT_SHORT[k]:>5s}' for k in C.STATS)
          + '   auto/s  skill%  ult%  TTK-auto')
    avg = {}
    for lv in LEVELS:                        # cible moyenne de ce niveau
        sts = [unit(l, lv)[1] for l in C.LINES]
        avg[lv] = {k: sum(s[k] for s in sts) / len(sts) for k in C.STATS}
    for line in C.LINES:
        for lv in LEVELS:
            form, st = unit(line, lv)
            tgt = avg[lv]
            auto = kit.auto_for(line, form)
            dps = kit.raw_damage(auto['power'], st['atk']) * kit.mitigation(tgt['def']) \
                * kit.attack_speed(st['spe']) / auto['cooldown']
            mv = kit.moves_for(line, form, lv)
            sk = [m for m in mv if m['aim'] == 'skill' and m['kind'] != 'heal' and m['slot'] != 'ult']
            s = sk[1] if len(sk) > 1 else sk[0]
            off = st['atk' if s['cat'] == 'phys' else 'spa']
            dmg = kit.raw_damage(s['power'], off, 'skill') * kit.mitigation(tgt['def' if s['cat'] == 'phys' else 'spd'])
            u = mv[-1]
            udmg = kit.raw_damage(u['power'], st['atk' if u['cat'] == 'phys' else 'spa'], 'skill') \
                * kit.mitigation(tgt['def' if u['cat'] == 'phys' else 'spd'])
            print(f"{line:11s} {lv:3d} {form:12s} " + ' '.join(f'{st[k]:5.0f}' for k in C.STATS)
                  + f"   {dps:6.0f}  {100 * dmg / tgt['hp']:5.1f}  {100 * udmg / tgt['hp']:4.0f}  {tgt['hp'] / dps:6.1f}s"
                  + f"   vit {kit.move_speed(st['spe']):.2f}")
        print()


if __name__ == '__main__':
    main()
