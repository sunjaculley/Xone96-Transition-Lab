#!/usr/bin/env python3
"""Plan a whole-set performance preview for the lab, from the set builder's sheet and the track prep data.

  python3 scripts/plan-performance.py SHEET.md REKORDBOX.xml WORKDIR OUT.json [--playlist NAME]

SHEET.md     4-deck set sheet from the set builder (order, decks, Play at, B / C / H, Bass in / out, Start next, notes)
REKORDBOX.xml  rekordbox collection export; the playlist (default: the sheet's title) sets the final order, pads come from here
WORKDIR      ~/.local/share/rekordbox-tools/work (analysis.json = bar-by-bar kick / bass / level, harmony.json, mik.json)
OUT.json     the performance plan the lab opens with its Set sheet button. It holds titles and timings only, never audio.
             Keep it private: it is your set.

One scene per change (and per sheet layer). The sheet is the backbone: its order, decks, Play at tempo, Start next and change type.
On top of that, every scene gets a recommendation from the data, with its reason:
  - swap on the breakdown: when the outgoing track breaks down within 16 bars of the planned swap, move the swap onto it
  - hold on H: when the outgoing track reaches its Mix out 8 loop (Active Loop) before the change is done
  - texture tail: in compatible keys, keep the outgoing track's loop under the new one (LO cut, filter rising) for 16 bars
  - layers from the sheet (mashups), with their Key Shift and LOW cut, carried into the next change when they still play
Phase budgets keep texture where her arc wants it (none in the Micro Reset). Anything the analysis can't hear is flagged
'check by ear'. Assumptions are listed in the plan so the lab can show them.
"""
import sys, re, json, argparse, unicodedata, xml.etree.ElementTree as ET
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('sheet'); ap.add_argument('xml'); ap.add_argument('work'); ap.add_argument('out'); ap.add_argument('--playlist')
a = ap.parse_args()

N = lambda s: re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', str(s).lower()).encode('ascii', 'ignore').decode())
tsec = lambda s: (lambda m: int(m[1]) * 60 + int(m[2]) if m else None)(re.search(r'(\d+):(\d{2})', s or ''))
fmt = lambda s: '–' if s is None else f'{int(max(0, s) // 60)}:{int(max(0, s) % 60):02d}'
DBY = {1: 'C', 2: 'A', 3: 'B', 4: 'D'}; DNUM = {'C': 1, 'A': 2, 'B': 3, 'D': 4}; DCH = {d: 'c%d' % n for d, n in DNUM.items()}

# ---------- sheet ----------
md = open(a.sheet, encoding='utf-8').read().splitlines()
title = next((l[2:] for l in md if l.startswith('# ')), 'Set').split(' · ')[0].strip()
rows, layers, phase, hdr = [], {}, '', None
for l in md:
    if not l.startswith('|'): continue
    c = [x.strip() for x in l.strip().split('|')[1:-1]]
    if not c or re.fullmatch(r':?-+:?', c[0]): continue
    if c[0] == 'Clock': hdr = 'set'; continue
    if c[0] == 'Lead' and c[1] == 'Layer': hdr = 'lay'; continue
    if c[0] == 'Phase': hdr = None; continue
    if hdr == 'set':
        m = re.match(r'^\*\*([\d:]+)\s+(.+?)\*\*$', c[0])
        if m: p = m[2].split(' · ')[0].lower(); phase = p[0].upper() + p[1:]; continue
        if len(c) < 15 or not c[2].isdigit(): continue
        rows.append(dict(clock=tsec(c[0]), layer='layer' in c[1], deck=int(c[2]), key=c[3], playAt=float(c[4]) if re.fullmatch(r'[\d.]+', c[4]) else None,
                         title=c[5], artist=c[6], E=int(c[7]) if c[7].isdigit() else 0, B=tsec(c[8]), C=tsec(c[9]), bi=tsec(c[10]), bo=tsec(c[11]),
                         sn=tsec(c[12]), H=tsec(c[13]), note=c[14], phase=phase))
    elif hdr == 'lay' and len(c) >= 7:
        m = re.search(r'in at lead bar (\d+) \(([\d:]+) on the lead\)', c[2]); ks = re.search(r'Key Shift ([+\-−]?\d+) on the layer', c[6])
        layers[N(c[1])] = dict(lead=c[0], inSec=tsec(m[2]) if m else None, thin='keep the layer thin' in c[2], adds=c[4],
                               ks=int(ks[1].replace('−', '-')) if ks else 0)

# ---------- rekordbox: final order + pads ----------
root = ET.parse(a.xml).getroot()
TR = {t.get('TrackID'): t for t in root.iter('TRACK') if t.get('Name') is not None}
pl = next((n for n in root.find('PLAYLISTS').iter('NODE') if n.get('Type') == '1' and n.get('Name') == (a.playlist or title)), None)
if pl is None: sys.exit(f'playlist "{a.playlist or title}" not in the xml')
order = [x.get('Key') for x in pl if x.tag == 'TRACK']
bytitle = {}
for r in rows: bytitle.setdefault(N(r['title']), r)
seq, changed = [], []
for i, cid in enumerate(order):
    t = TR[cid]; r = bytitle.get(N(t.get('Name')))
    if r is None: sys.exit('not on the sheet: ' + t.get('Name'))
    tempos = [x for x in t if x.tag == 'TEMPO']; t0 = tempos[0] if tempos else None
    pads, mem = {}, {}
    for pm in t:
        if pm.tag != 'POSITION_MARK': continue
        n = int(pm.get('Num')); st = float(pm.get('Start'))
        if 0 <= n < 8: pads['ABCDEFGH'[n]] = dict(name=pm.get('Name') or '', sec=st, end=float(pm.get('End')) if pm.get('End') else None)
        elif n == -1: mem[pm.get('Name') or ''] = st
    r = dict(r, cid=cid, bpm=float(t0.get('Bpm')) if t0 is not None else float(t.get('AverageBpm') or 0) or 125.0,
             fb=float(t0.get('Inizio')) if t0 is not None else 0.0, dur=float(t.get('TotalTime') or 0), pads=pads, mem=mem, xkey=t.get('Tonality') or r['key'])
    seq.append(r)
leads = [r for r in seq if not r['layer']]
sheet_leads = [r for r in rows if not r['layer']]
moved = [r['title'] for i, r in enumerate(leads) if N(r['title']) != N(sheet_leads[i]['title'])]
for i, r in enumerate(leads): r['clock'] = sheet_leads[i]['clock']  # slot times stay with the slot, so a swap keeps the clock running forward

# ---------- bar analysis ----------
AN = json.load(open(a.work + '/analysis.json')); HA = json.load(open(a.work + '/harmony.json'))
try: MK = json.load(open(a.work + '/mik.json'))['tracks']
except Exception: MK = {}


def profile(r):
    """Per grid bar: kick, bass, level, tops. Breaks in time order (her pads first, then measured)."""
    bars = AN.get(r['cid'], {}).get('bars') or []
    nb = max([(b['i'] - 1) // 4 for b in bars] + [0]) + 1
    g = lambda k: np.array([np.nan] * nb)
    tot, kv, bass, hi, mid = g(0), g(0), g(0), g(0), g(0)
    for b in bars:
        k = (b['i'] - 1) // 4
        tot[k], kv[k], bass[k], hi[k], mid[k] = b['tot'], b['kick'], b.get('bass', 0), b.get('hi', 0), b.get('mid', 0)
    ok = ~np.isnan(tot)
    if ok.sum() < 16: return dict(nb=nb, breaks=[], kick=np.zeros(nb, bool), tot=np.zeros(nb), hi=np.zeros(nb), mid=np.zeros(nb), body=0)
    for arr in (tot, kv, bass, hi, mid): arr[~ok] = np.nanmedian(arr)
    kick = kv > max(3.0, 0.6 * np.median(kv)); has_kick = np.percentile(kv, 80) > 5 and kick.mean() > .3
    body = np.percentile(tot[kick] if has_kick else tot, 60)
    quiet = np.array([(has_kick and not kick[k]) or tot[k] < body - 3 for k in range(nb)])
    bar = lambda s: (s - r['fb']) * r['bpm'] / 240
    a0 = int(round(bar(r['pads']['A']['sec']))) if 'A' in r['pads'] else 0
    breaks = []
    for L in 'DEFG':  # her own pads, by name
        p = r['pads'].get(L)
        if p and re.match(r'break', p['name'], re.I): breaks.append((bar(p['sec']), 'her pad ' + L + ' "' + p['name'] + '"'))
    if not breaks:
        k = a0 + 24
        while k + 8 < nb * .9:
            if quiet[k:k + 8].sum() >= 3 and (not has_kick or kick[k + 8:k + 16].mean() >= .75):
                breaks.append((k, 'measured breakdown')); k += 32
            else: k += 8
    return dict(nb=nb, breaks=breaks, kick=kick, tot=tot, hi=hi, mid=mid, body=body, bar=bar)


P = {r['cid']: profile(r) for r in seq}

# ---------- keys ----------
def cam(k):
    m = re.match(r'(\d{1,2})([AB])', k or ''); return (int(m[1]), m[2]) if m else None
def keyrel(k1, k2):
    a_, b_ = cam(k1), cam(k2)
    if not a_ or not b_: return 'unknown'
    if a_ == b_: return 'same'
    if a_[0] == b_[0]: return 'relative'
    d = (b_[0] - a_[0]) % 12
    if a_[1] == b_[1] and d in (1, 11): return 'adjacent'
    return 'far'

BUDGET = {'Locked opening': 1, 'Orientation': 2, 'Groove formation': 3, 'First pressure wave': 5, 'Micro reset': 0,
          'Second pressure wave': 5, 'Handoff': 2}
ASSUME = [
    'Order from your rekordbox playlist "%s" (sheet order with %s).' % (pl.get('Name'), ' and '.join(moved) + ' swapped' if moved else 'no changes'),
    'The sheet is the backbone: decks, Play at tempo, Start next, change type and trims. Recommendations sit on top and are marked.',
    'Textures come from the set\'s own tracks (their loops), not the loop deck. At most 3 decks sound at once.',
    'Tools: EQ, the two filters, GAIN and faders. No CRUNCH, no crossfader.',
    'Layer and texture choices are made from measured level, kick, bass and key. Vocals and melodic clashes are not detected: check by ear.',
    'Condensed: each change plays in full, the stretches in between are skipped.',
]

# ---------- scenes ----------
scenes, carry = [], None
used = {}
def secbar(r, s): return (s - r['fb']) * r['bpm'] / 240


def tail_score(x, y):
    """How well the outgoing track's loop can sit under the next one as texture."""
    rel = keyrel(x['key'], y['key'])
    if rel not in ('same', 'relative', 'adjacent'): return None, rel
    p = P[x['cid']]; H = x['pads'].get('H')
    if not H or p['body'] == 0: return None, rel
    k = int(secbar(x, H['sec']))
    if k + 8 > p['nb']: return None, rel
    tops = float(np.mean(p['hi'][k:k + 8]) - np.median(p['hi'])); mids = float(np.mean(p['mid'][k:k + 8]) - np.median(p['mid']))
    s = {'same': 2.0, 'relative': 1.2, 'adjacent': 1.0}[rel] + .25 * max(-4, min(6, tops)) + .1 * max(-4, min(6, mids))
    # Mixed In Key energy: a texture should sit at or under the new track's energy, not fight it
    mx, my = MK.get(x['cid']), MK.get(y['cid'])
    if mx and my:
        eH = next((e for st_, ln, e in mx.get('segs', []) if st_ <= H['sec'] < st_ + ln), mx.get('e_out'))
        if eH is not None and my.get('e_in') is not None: s += .4 if eH <= my['e_in'] else -.4 * (eH - my['e_in'])
    return s, rel


# choose texture tails per phase budget (best scores, never two changes in a row)
cands = []
for i in range(len(leads) - 1):
    x, y = leads[i], leads[i + 1]
    if re.search(r'\b(SWAP|CUT):', y['note']) or x['playAt'] is None or y['playAt'] is None: continue
    s, rel = tail_score(x, y)
    if s is not None: cands.append((s, i, rel))
tails = set()
for ph, bud in BUDGET.items():
    cs = sorted([c for c in cands if leads[c[1] + 1]['phase'].lower() == ph.lower()], reverse=True)
    for s, i, rel in cs:
        if len([t for t in tails if leads[t + 1]['phase'].lower() == ph.lower()]) >= bud: break
        if i - 1 in tails or i + 1 in tails or s < 1.6: continue
        tails.add(i)

layer_of = {}  # lead index -> layer row
for r in seq:
    if r['layer']:
        info = layers.get(N(r['title']), {}); lead = next((x for x in leads if N(x['title']) == N(info.get('lead', ''))), None)
        if lead: layer_of[leads.index(lead)] = (r, info)

def kf(): return {}

for i in range(len(leads) - 1):
    x, y = leads[i], leads[i + 1]
    X, Y = DBY[x['deck']], DBY[y['deck']]; cX, cY = DCH[X], DCH[Y]; nX, nY = DNUM[X], DNUM[Y]
    play = x['playAt'] or y['playAt'] or 125.0
    bx, by = 240 / x['bpm'], 240 / y['bpm']                      # track seconds per bar
    note = y['note']; typ = 'swap' if re.search(r'\bSWAP:', note) else 'cut' if re.search(r'\bCUT:', note) else 'blend'
    late = 'cut its lows late' in note; hold = bool(re.search(r'= hold|YOUR PAIR|long blend', note))
    reasons, ears = [], []
    # incoming: bars from B to Bass in (prefer the xml markers)
    yB = y['pads'].get('B', {}).get('sec', y['B']); ybi = y['mem'].get('Bass in', y['bi'])
    xbo = x['mem'].get('Bass out', x['bo']); xH = x['pads'].get('H', {}).get('sec', x['H'])
    Nb = int(round((ybi - yB) / by)) if ybi is not None and yB is not None else None
    est = False
    if Nb is None or Nb < 4 or Nb > 96: Nb = 8
    if xbo is not None: sn = xbo - Nb * bx
    elif xH is not None: sn = xH - Nb * bx; est = True
    else: sn = x['sn'] or (x['dur'] * .7); est = True
    if x['sn'] is not None and abs(x['sn'] - sn) > 2.5 and not moved: reasons.append(f'Start next recomputed from your rekordbox markers: {fmt(sn)} (sheet {fmt(x["sn"])}).')
    sw = 8 + Nb
    # recommendation: swap on the outgoing breakdown
    rec = None
    if typ != 'cut' and i not in layer_of:
        for bk, src in P[x['cid']]['breaks']:
            kb = 8 + ((x['fb'] + bk * bx) - sn) / bx
            if -32 <= kb - sw <= 16 and abs(kb - sw) >= 2:
                d = round(kb - sw); sn += d * bx; rec = ('breakdown', src, d); break
            if abs(kb - sw) < 2: rec = ('already', src, 0); break
    if rec and rec[0] == 'breakdown':
        reasons.append(f'Recommendation: CDJ {nX} breaks down at {fmt(sn + Nb * bx)} ({rec[1]}). Its bass drops out there, so start CDJ {nY} {abs(rec[2])} bars {"later" if rec[2] > 0 else "earlier"} (Start next {fmt(sn)}) and land the swap in the gap.' + (f' This plays {x["title"]} {abs(rec[2])} bars shorter.' if rec[2] < 0 else ''))
    elif rec: reasons.append(f'The planned swap already lands on CDJ {nX}\'s breakdown ({rec[1]}).')
    s_ = sw + (4 if late else 0)
    # does the outgoing reach H (its Active Loop) inside the scene?
    kH = 8 + (xH - sn) / bx if xH is not None else None
    tail = i in tails and typ == 'blend'
    fe = 8 if hold else 4
    endb = s_ + 2 + fe + 1
    if tail: endb = s_ + 2 + 16 + 4 + 1
    loopAt = None
    if kH is not None and kH < endb - 1:
        loopAt = max(0.0, round(kH * 4) / 4)
        reasons.append(f'CDJ {nX} reaches its Mix out 8 loop (H, {fmt(xH)}) at bar {int(loopAt) + 1}: the Active Loop holds its groove for the rest of the change.')
    if tail and loopAt is None:
        loopAt = float(s_ + 2)
        reasons.append(f'Texture: at bar {s_ + 3} put an 8-beat loop on CDJ {nX} (or press H early) to hold it under the new track.')
    trim = 0
    m = re.search(r'([+\-−]\d+) dB vs previous: trim (down|up)', note)
    if m: trim = max(-12, min(10, -int(m[1].replace('−', '-'))))
    elif re.search(r'clips \(', note): trim = -3
    # ---------- keyframes ----------
    setup = {f'{d}.play': 0 for d in 'ABCD'}; setup.update({f'c{n}.fader': 0 for n in (1, 2, 3, 4)})
    setup[X + '.play'] = 1; setup[cX + '.fader'] = .8
    T = {Y + '.play': [[0, 0], [8, 1]]}
    if trim: T[cY + '.gain'] = [[2, 0], [4, trim]]
    steps = [[0, f'CDJ {nX} plays {x["title"]} ({fmt(sn - 8 * bx)}). {y["title"]} is cued on pad B on CDJ {nY}.' + (f' Set CH {nY} GAIN to {"+" if trim > 0 else "−"}{abs(trim)} dB.' if trim else '')]]
    if loopAt is not None and kH is not None and abs(loopAt - kH) < .5:
        steps.append([loopAt, f'CDJ {nX} reaches H (Mix out 8, {fmt(xH)}): its Active Loop catches the groove and holds it, so the change has no deadline.'])
    if loopAt is not None:
        T[X + '.loop'] = [[0, 0], [loopAt, 8 if kH is not None and abs(loopAt - kH) < .5 else 2]]
    if typ == 'cut':
        setup.update({cY + '.lo': 0}); T[cX + '.fader'] = [[s_, .8], [s_ + .03, 0]]; T[cY + '.fader'] = [[s_, 0], [s_ + .03, .8]]
        steps += [[8, f'Start next ({fmt(sn)}): press B on CDJ {nY}, channel closed, headphones only.'],
                  [s_, f'Cut on the 1: CH {nX} down, CH {nY} up in one move. (Key Shift ±1 on CDJ {nY} is the blend alternative.)']]
        endb = s_ + 4
        ears.append('Semitone or key-jump cut: check that the new track lands cleanly after the cut.')
    elif typ == 'swap':
        setup.update({cY + '.hi': -40, cY + '.hm': -27, cY + '.lm': -27, cY + '.lo': -40})
        T.update({cY + '.fader': [[8, 0], [9, .8]], cY + '.hi': [[9, -40], [sw - 2, 0]], cY + '.hm': [[9, -27], [sw - 2, 0]],
                  cX + '.hm': [[sw - 4, 0], [sw - 1, -27]], cX + '.lm': [[sw - 4, 0], [sw - 1, -27]],
                  cX + '.lo': [[sw, 0], [sw + .03, -40]], cY + '.lo': [[sw, -40], [sw + .03, 0]], cY + '.lm': [[sw, -27], [sw + .03, 0]],
                  cX + '.fader': [[sw, .8], [sw + 2, 0]]})
        steps += [[8, f'Start next ({fmt(sn)}): press B on CDJ {nY}, every band down.'], [9, f'Bring CH {nY} HI and HI MID up.'],
                  [sw - 4, f'Strip CH {nX} to drums (mids down).'], [sw, f'Swap on the 1: CH {nX} LO out, CH {nY} LO and LO MID in, close CH {nX} over 2 bars.']]
        endb = sw + 4
    else:
        setup.update({cY + '.hi': -40, cY + '.lo': -40})
        hiEnd = max(12, min(sw - 1, 10 + Nb // 2))
        T.update({cY + '.fader': [[8, 0], [10, .8]], cY + '.hi': [[10, -40], [hiEnd, 0]], cX + '.lo': [[s_, 0], [s_ + .03, -40]], cY + '.lo': [[s_, -40], [s_ + .03, 0]]})
        steps += [[8, f'Start next ({fmt(sn)}): press B on CDJ {nY}, LO killed.'], [10, f'Raise CH {nY} HI over {hiEnd - 10} bars.' + (' Same key: let them sit together.' if hold else '')]]
        if late: steps.append([sw, f'Energy drops here: keep CDJ {nX}\'s low end 4 more bars.'])
        steps.append([s_, f'Bass swap on the 1: CH {nX} LO out, CH {nY} LO in.'])
        if tail:
            f0 = s_ + 2; f1 = f0 + 16
            T.update({cX + '.fa': [[0, 0], [f0, 1]], 'f1.on': [[0, 0], [f0, 1]], 'f1.mode': [[0, 'HPF']], 'f1.freq': [[f0, .22], [f1, .5]], 'f1.res': [[f0, .25], [f1, .45]],
                      cX + '.hm': [[f0, 0], [f0 + 2, -8]], cX + '.fader': [[f0, .8], [f0 + 4, .5], [f1, .5], [f1 + 4, 0]]})
            sc, rel = tail_score(x, y)
            steps.append([f0, f'Texture: CDJ {nX} keeps looping under {y["title"]}: Filter 1 on CH {nX} (HPF rising slowly), fader to half, HI MID down a touch.'])
            steps.append([f1, f'Fade the texture out over 4 bars, exit the loop, load the next track on CDJ {nX}.'])
            reasons.append(f'Recommendation (texture): {x["key"]} → {y["key"]} ({rel} key) and CDJ {nX}\'s outro loop is rich in tops, so it can ride under the new track for 16 bars with its LO cut.')
            ears.append('Texture tail: listen for clashing melodies or vocals between the loop and the new track.')
            endb = f1 + 5
        else:
            T[cX + '.fader'] = [[s_ + 2, .8], [s_ + 2 + fe, 0]]
            steps.append([s_ + 2, f'Fade CH {nX} out over {fe} bars.'])
    # a layer still playing from the previous scene fades out on this change
    decks = [dict(d=X, title=x['title'], sec=sn - 8 * bx, bpm=x['bpm'], loopAt=loopAt, loopSec=xH, loopLen=8 if (kH is not None and loopAt is not None and abs(loopAt - kH) < .5) else 2),
             dict(d=Y, title=y['title'], sec=yB, bpm=y['bpm'], startBar=8)]
    if carry and carry['d'] not in (X, Y):
        Z = carry['d']; cZ = DCH[Z]
        setup.update({Z + '.play': 1, cZ + '.fader': .55, cZ + '.lo': -40, cZ + '.hm': -8, cZ + '.gain': carry['gain']})
        T[cZ + '.fader'] = [[0, .55], [min(s_, endb - 4), .55], [min(s_, endb - 4) + 4, 0]]
        lead_sec0 = sn - 8 * bx; zsec = carry['B'] + (lead_sec0 - carry['leadIn']) * (x['bpm'] / carry['bpm'])
        decks.append(dict(d=Z, title=carry['title'], sec=zsec, bpm=carry['bpm']))
        steps.append([min(s_, endb - 4), f'The layer on CDJ {DNUM[Z]} ({carry["title"]}) goes out with the old lead: CH {DNUM[Z]} down over 4 bars.'])
        reasons.append(f'Three decks: the layer on CDJ {DNUM[Z]} is still under {x["title"]} when the change starts.')
        carry = None
    steps.sort(key=lambda s: s[0])
    real_from_B = (sn - 8 * bx - (x['pads'].get('B', {}).get('sec', x['B']) or 0)) * x['bpm'] / play
    scenes.append(dict(id=f'f{len(scenes) + 1}', kind='loop' if loopAt is not None and typ != 'cut' else typ, tail=tail, title=f'{x["title"]} → {y["title"]}',
                       phase=y['phase'], pair=[X, Y], playAt=play, bars=int(np.ceil(endb)), setup=setup, tracks=T, steps=steps,
                       why=f'{y["phase"]}. {x["key"]} → {y["key"]} · {x["playAt"] or "free"} → {y["playAt"] or "free"} BPM · energy {x["E"]} → {y["E"]}. '
                           + ' · '.join(p for p in note.split(' · ') if not p.startswith('MIK:')),
                       reasons=reasons, ears=ears, decks=decks, clock=(x['clock'] or 0) + max(0, real_from_B), est=est,
                       cues=[[8, f'B on CDJ {nY}'], [s_, 'the cut' if typ == 'cut' else 'the bass swap']] + ([[loopAt, f'H loop on CDJ {nX}']] if loopAt is not None else [])))
    # the sheet layer that comes in under the new lead
    if (i + 1) in layer_of:
        ly, info = layer_of[i + 1]; L = y; Z = DBY[ly['deck']]; cZ = DCH[Z]; nZ = DNUM[Z]
        inS = info.get('inSec') or (L['pads'].get('C', {}).get('sec') or 60); g = -6 if info.get('thin') else -3; ks = info.get('ks') or 0
        lB = ly['pads'].get('B', {}).get('sec', ly['B']) or 0; bl = 240 / L['bpm']
        su = {f'{d}.play': 0 for d in 'ABCD'}; su.update({f'c{n}.fader': 0 for n in (1, 2, 3, 4)}); su.update({DBY[L['deck']] + '.play': 1, DCH[DBY[L['deck']]] + '.fader': .8, cZ + '.lo': -40})
        TT = {Z + '.play': [[0, 0], [8, 1]], cZ + '.gain': [[2, 0], [4, g]], cZ + '.fader': [[8, 0], [12, .55]], cZ + '.hm': [[12, 0], [16, -8]]}
        st = [[0, f'CDJ {DNUM[DBY[L["deck"]]]} leads with {L["title"]} ({fmt(inS - 8 * bl)}). {ly["title"]} is cued on B on CDJ {nZ}, CH {nZ} LO killed.'],
              [2, f'Set CH {nZ} GAIN to −{abs(g)} dB.'], [8, f'On the lead\'s phrase ({fmt(inS)}): press B on CDJ {nZ}, bring CH {nZ} to about half over 4 bars.'],
              [12, f'Scoop CH {nZ} HI MID so the lead stays in front. The layer adds {info.get("adds") or "texture"}.'], [24, 'Hold the layer: it stays in until the lead goes out.']]
        if ks: TT[Z + '.ks'] = [[5, 0], [6, ks]]; st.append([5, f'Key Shift {"+" if ks > 0 else "−"}{abs(ks)} on CDJ {nZ}.'])
        st.sort(key=lambda s: s[0])
        scenes.append(dict(id=f'f{len(scenes) + 1}', kind='layer', tail=False, title=f'Layer: {ly["title"]} under {L["title"]}', phase=ly['phase'],
                           pair=[DBY[L['deck']], Z], playAt=L['playAt'] or 140, bars=28, setup=su, tracks=TT, steps=st,
                           why=f'{ly["phase"]}. Mashup from your sheet: {ly["note"]}', reasons=['Your pick (sheet layer).'],
                           ears=['Layer: check the two tracks together by ear (vocals, melodies).'],
                           decks=[dict(d=DBY[L['deck']], title=L['title'], sec=inS - 8 * bl, bpm=L['bpm']), dict(d=Z, title=ly['title'], sec=lB, bpm=ly['bpm'], startBar=8)],
                           clock=(L['clock'] or 0) + max(0, (inS - (L['pads'].get('B', {}).get('sec', L['B']) or 0)) * L['bpm'] / (L['playAt'] or 140)),
                           cues=[[8, f'B on CDJ {nZ}']]))
        carry = dict(d=Z, title=ly['title'], B=lB, leadIn=inS, bpm=ly['bpm'], gain=g)

KEYMOVE = [('⇈', 'a key lift (whole tone or minor third)'), ('⇊', 'a key drop (whole tone or minor third)'), ('⤴', 'a semitone lift'), ('⤵', 'a semitone drop'),
           ('!!', 'a key jump'), ('↔', 'a move to the relative key'), ('↕', 'a mood change (minor/major)'), ('↑', 'a lift one step up'), ('↓', 'a release one step down'), ('= hold', 'the same key')]
FLAG = {'blend': 'Blend', 'long': 'Long blend', 'swap': 'Quick swap', 'cut': 'Cut', 'hloop': 'H loop', 'tail': 'Texture tail', 'brk': 'Breakdown swap',
        'late': 'Late lows', 'layer': 'Layer', 'three': '3 decks', 'trim': 'Gain trim'}
TAGS = [(r'^CDJ \d+ (plays|leads)', 'Prep'), (r'Set CH \d+ GAIN', 'Trim'), (r'Key Shift', 'Key Shift'), (r'Start next|press B', 'Cue in'),
        (r'reaches H|H loop', 'H loop'), (r'Strip', 'Strip'), (r'Energy drops', 'Hold lows'), (r'Bass swap|Swap on the 1', 'Bass swap'), (r'Cut on the 1', 'Cut'),
        (r'^Texture:', 'Texture'), (r'Fade the texture', 'Texture out'), (r'goes out with the old lead', 'Layer out'), (r'Raise|Bring CH|bring CH', 'Blend in'),
        (r'Scoop', 'Shape'), (r'Hold the layer', 'Layer'), (r'Fade CH|Close', 'Out')]
for sc in scenes:
    note = sc['why']; fl = []
    if sc['kind'] == 'layer': fl.append('layer')
    elif sc['kind'] == 'cut': fl.append('cut')
    elif sc['kind'] == 'swap': fl.append('swap')
    else: fl.append('long' if re.search(r'= hold|YOUR PAIR', note) else 'blend')
    if any('Mix out 8 loop' in r for r in sc['reasons']): fl.append('hloop')
    if sc['tail']: fl.append('tail')
    if any('breaks down' in r for r in sc['reasons']): fl.append('brk')
    if 'cut its lows late' in note: fl.append('late')
    if any('Three decks' in r for r in sc['reasons']): fl.append('three')
    if any(k.endswith('.gain') for k in sc['tracks']) and sc['kind'] != 'layer': fl.append('trim')
    km = next((t for sym, t in KEYMOVE if sym in note), 'a key change')
    X, Y = sc['pair']; nX, nY = DNUM[X], DNUM[Y]
    base = {'long': f'Hand the floor over without a seam: {km}, so let both tracks play as one and swap the low end on the phrase.',
            'blend': f'{km[0].upper() + km[1:]}: bring CDJ {nY} in under CDJ {nX}, one low end at a time, and swap the bass on the phrase.',
            'swap': f'{km[0].upper() + km[1:]}: keys that clash if they overlap long, so keep it short, strip CDJ {nX} to drums and swap on the 1.',
            'cut': f'{km[0].upper() + km[1:]}: no blend, a clean cut on the 1 (on a breakdown if you can).',
            'layer': f'Build a third thing: CDJ {nY} rides under CDJ {nX} as a layer, its lows cut, the lead stays in front.'}[fl[0]]
    extra = []
    if 'hloop' in fl: extra.append(f'CDJ {nX} sits on its H loop, so there is no deadline')
    if 'brk' in fl: extra.append(f'land the swap in CDJ {nX}\'s breakdown, where its bass drops out anyway')
    if 'tail' in fl: extra.append(f'after the swap CDJ {nX}\'s loop stays underneath as background texture (LO cut, filter rising)')
    if 'late' in fl: extra.append('the energy steps down, so hold the old low end a little longer')
    if 'three' in fl: extra.append('the layer from the last scene is still in and goes out with the old lead')
    sc['flags'] = [dict(k=f, label=FLAG[f]) for f in fl]
    sc['intent'] = base + (' Then: ' + '; '.join(extra) + '.' if extra else '')
    for st in sc['steps']:
        st.append(next((tg for rx, tg in TAGS if re.search(rx, st[1])), ''))

phases = []
for r in leads:
    if not phases or phases[-1]['name'] != r['phase']: phases.append(dict(name=r['phase'], clock=r['clock'] or 0))
end = (leads[-1]['clock'] or 0) + (((leads[-1]['H'] or leads[-1]['dur']) - (leads[-1]['B'] or 0)) * leads[-1]['bpm'] / (leads[-1]['playAt'] or 140))
out = dict(kind='xone96-performance', version=1, name=title, playlist=pl.get('Name'), assumptions=ASSUME, phases=phases, end=end,
           tracks=[dict(title=r['title'], artist=r['artist'], deck=r['deck'], key=r['key'], playAt=r['playAt'], clock=r['clock'], layer=r['layer']) for r in seq],
           scenes=scenes)
json.dump(out, open(a.out, 'w'), ensure_ascii=False, indent=0)
k = {}
for s in scenes: k[s['kind']] = k.get(s['kind'], 0) + 1
print(f'{len(scenes)} scenes · {k} · texture tails {sum(s["tail"] for s in scenes)} · breakdown swaps {sum(any("breaks down" in r for r in s["reasons"]) for s in scenes)} · moved {moved}')

