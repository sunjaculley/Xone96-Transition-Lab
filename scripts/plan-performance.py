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

def pick_tails(budget):
    tails = set()
    for ph, bud in budget.items():
        cs = sorted([c for c in cands if leads[c[1] + 1]['phase'].lower() == ph.lower()], reverse=True)
        for s, i, rel in cs:
            if len([t for t in tails if leads[t + 1]['phase'].lower() == ph.lower()]) >= bud: break
            if i - 1 in tails or i + 1 in tails or s < 1.6: continue
            tails.add(i)
    return tails

layer_of = {}  # lead index -> layer row
for r in seq:
    if r['layer']:
        info = layers.get(N(r['title']), {}); lead = next((x for x in leads if N(x['title']) == N(info.get('lead', ''))), None)
        if lead: layer_of[leads.index(lead)] = (r, info)


def stability(r):
    p = P[r['cid']]
    if p['body'] == 0: return 0
    k = p['kick'].astype(float); n = len(k)
    a0 = int(max(0, secbar(r, r['pads'].get('B', {}).get('sec', r['B'] or 0) or 0))); h = int(min(n, secbar(r, r['pads'].get('H', {}).get('sec', r['H'] or r['dur']) or r['dur'])))
    body = k[a0:h] if h > a0 + 8 else k
    e = (MK.get(r['cid']) or {}).get('e_play') or r['E'] or 3
    return float(body.mean()) * e
core = set()
for ph in {r['phase'] for r in leads}:
    rs = [r for r in leads if r['phase'] == ph and r['playAt']]
    if len(rs) >= 3: core.add(max(rs, key=stability)['cid'])

# third-deck textures (DVS1 hopscotch): the track two changes ahead, its breakdown, on its own free deck
aux_c = []
for i in range(len(leads) - 2):
    x, y, z = leads[i], leads[i + 1], leads[i + 2]
    if re.search(r'\b(CUT):', y['note']) or not (x['playAt'] and y['playAt'] and z['playAt']): continue
    if DBY[z['deck']] in (DBY[x['deck']], DBY[y['deck']]) or not P[z['cid']]['breaks']: continue  # (clips use the Drop pad when there is one)
    rel = keyrel(y['key'], z['key'])
    if rel not in ('same', 'relative', 'adjacent'): continue
    s = {'same': 2.0, 'relative': 1.3, 'adjacent': 1.0}[rel] + (.5 if re.search(r'= hold', y['note']) else 0)
    aux_c.append((s, i))
def pick_aux(budget):
    out = set()
    for ph, bud in budget.items():
        cs = sorted([c for c in aux_c if leads[c[1] + 1]['phase'].lower() == ph.lower()], reverse=True)
        for s, i in cs:
            if len([t for t in out if leads[t + 1]['phase'].lower() == ph.lower()]) >= bud: break
            if i - 1 in out or i + 1 in out or (i + 1) in layer_of or i in layer_of: continue
            out.add(i)
    return out

# ---------- mashups: her pairs file (Ableton rows + Mixed In Key favourites) ----------
MASH = {}
try:
    PAIRS = json.load(open(a.work.rstrip('/').rsplit('/', 1)[0] + '/pairs.json'))['pairs']
except Exception:
    PAIRS = []
pos = {r['cid']: i for i, r in enumerate(leads)}
def xrow(cid, lead):
    t = TR.get(cid)
    if t is None: return None
    tempos = [x for x in t if x.tag == 'TEMPO']; t0 = tempos[0] if tempos else None
    pads, mem = {}, {}
    for pm in t:
        if pm.tag != 'POSITION_MARK': continue
        n_ = int(pm.get('Num')); st_ = float(pm.get('Start'))
        if 0 <= n_ < 8: pads['ABCDEFGH'[n_]] = dict(name=pm.get('Name') or '', sec=st_)
        elif n_ == -1: mem[pm.get('Name') or ''] = st_
    bpm = float(t0.get('Bpm')) if t0 is not None else float(t.get('AverageBpm') or 0) or 130.0
    return dict(cid=cid, title=t.get('Name'), artist=t.get('Artist') or '', key=t.get('Tonality') or '', bpm=bpm, fb=float(t0.get('Inizio')) if t0 is not None else 0.0,
                pads=pads, mem=mem, B=pads.get('B', {}).get('sec', 0), playAt=lead['playAt'], phase=lead['phase'], note='', deck=None)
for q in PAIRS:
    a_, b_ = q['a'], q['b']
    if a_ in pos and b_ in pos: continue                    # pairs inside the set are played as long blends ('Your pair')
    if (a_ in pos) == (b_ in pos) or not any('MIK' in s_ for s_ in q['src']): continue
    lc, mc = (a_, b_) if a_ in pos else (b_, a_); i = pos[lc]; L_ = leads[i]
    if i == 0 or i >= len(leads) - 1 or not L_['playAt']: continue
    M = xrow(mc, L_)
    if not M or keyrel(L_['key'], M['key']) not in ('same', 'relative', 'adjacent') and not q.get('pitch'): continue
    ks = int(q.get('pitch', {}).get(mc, 0)) - int(q.get('pitch', {}).get(lc, 0))
    sc_ = q.get('rating', 0) + (1 if any('Ableton' in s_ for s_ in q['src']) else 0) + (1 if keyrel(L_['key'], M['key']) == 'same' else 0)
    if i not in MASH or sc_ > MASH[i][0]: MASH[i] = (sc_, M, dict(label=q['label'], ks=ks, rating=q.get('rating', 0)))
MASHB = {'Locked opening': 0, 'Orientation': 1, 'Groove formation': 1, 'First pressure wave': 2, 'Micro reset': 0, 'Second pressure wave': 2, 'Handoff': 1}
mash_of = {}
for ph, bud in MASHB.items():
    cs = sorted([(v[0], i) for i, v in MASH.items() if leads[i]['phase'].lower() == ph.lower() and i not in layer_of and v[0] >= 2], reverse=True)
    for sc_, i in cs[:bud]: mash_of[i] = MASH[i]

def mash_scene(L, M, info, i, scenes_len, carry_deck):
    # the partner rides on the deck the previous track just left
    prev = leads[i - 1]; Z = DBY[prev['deck']]
    if Z == DBY[L['deck']] or Z == carry_deck: Z = next(d for d in 'CABD' if d not in (DBY[L['deck']], DBY[leads[i + 1]['deck']], carry_deck))
    cZ = DCH[Z]; nZ = DNUM[Z]; nL = DNUM[DBY[L['deck']]]; bl = 240 / L['bpm']
    C = L['pads'].get('C', {}).get('sec') or (L['B'] or 0) + 32 * bl; bo = L['mem'].get('Bass out', L['bo']) or (L['dur'] * .8)
    inS = max((L['B'] or 0) + 16 * bl, min(C + 16 * bl, bo - 56 * bl)); g = -4; ks = info['ks']
    su = {f'{d}.play': 0 for d in 'ABCD'}; su.update({f'c{n}.fader': 0 for n in (1, 2, 3, 4)}); su.update({DBY[L['deck']] + '.play': 1, DCH[DBY[L['deck']]] + '.fader': .8, cZ + '.lo': -40})
    TT = {Z + '.play': [[0, 0], [8, 1]], cZ + '.gain': [[2, 0], [4, g]], cZ + '.fader': [[8, 0], [12, .6], [28, .6], [32, 0]], cZ + '.hm': [[12, 0], [16, -6]]}
    st = [[0, f'CDJ {nL} leads with {L["title"]} ({fmt(inS - 8 * bl)}). Load {M["title"]} on CDJ {nZ} (your mashup partner, not in this set), cued on B, CH {nZ} LO killed.'],
          [2, f'Set CH {nZ} GAIN to −{abs(g)} dB.'], [8, f'Mashup in on the lead\'s phrase ({fmt(inS)}): press B on CDJ {nZ}, bring CH {nZ} to about 6/10 over 4 bars.'],
          [12, f'Scoop CH {nZ} HI MID a little: {L["title"]} keeps the melody in front, {M["title"]} adds its own parts on top.'],
          [28, f'Mashup out over 4 bars; CDJ {nZ} is free again before the next change.']]
    if ks: TT[Z + '.ks'] = [[5, 0], [6, ks]]; st.append([5, f'Key Shift {"+" if ks > 0 else "−"}{abs(ks)} on CDJ {nZ} (from your Mixed In Key mashup).'])
    st.sort(key=lambda s_: s_[0])
    return dict(id=f'f{scenes_len + 1}', kind='layer', tail=False, xf=['mik'], title=f'Mashup: {M["title"]} over {L["title"]}', phase=L['phase'],
                pair=[DBY[L['deck']], Z], playAt=L['playAt'] or 140, bars=34, setup=su, tracks=TT, steps=st,
                why=f'{L["phase"]}. Mashup from your pairs: {info["label"]}. {L["key"]} + {M["key"]}' + (f', Key Shift {ks:+d} on the partner' if ks else '') + '.',
                reasons=[f'Your mashup ({info["label"]}): Mixed In Key marked these two as a mashup' + (' and you played them together in Ableton.' if 'Ableton' in info['label'] else '.') + f' {M["title"]} is not in this set: it rides on the free CDJ {nZ} for 24 bars.'],
                ears=['Mashup: check vocals and melodies together by ear.'],
                decks=[dict(d=DBY[L['deck']], title=L['title'], sec=inS - 8 * bl, bpm=L['bpm']), dict(d=Z, title=M['title'], sec=M['B'] or 0, bpm=M['bpm'], startBar=8)],
                clock=(L['clock'] or 0) + max(0, (inS - 8 * bl - (L['B'] or 0)) * L['bpm'] / (L['playAt'] or 140)), cues=[[8, f'B on CDJ {nZ}'], [28, 'the mashup out']])

def build(ST):
    scenes, carry = [], None
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
        tail = i in ST['tails'] and typ == 'blend'
        xf = []
        if ST.get('core') and x['cid'] in core and typ == 'blend': xf.append('core')
        if 'YOUR PAIR' in note and typ == 'blend': xf.append('pair')
        fe = 16 if ('core' in xf or 'pair' in xf) else 8 if hold else 4
        parts = ST.get('parts') and typ == 'blend' and keyrel(x['key'], y['key']) in ('same', 'relative', 'adjacent')
        bridge = ST.get('bridge') and typ in ('swap', 'cut') and sw >= 13
        endb = s_ + 2 + fe + 1
        if parts: endb = s_ + 6 + fe + 1
        if tail: endb = (s_ + 6 if parts else s_ + 2) + 16 + 4 + 1
        if bridge: endb = sw + 11
        if ST.get('avoidH') and kH is not None and 8 < kH < endb - 1 and typ != 'cut' and not bridge:
            dd = int(np.ceil(endb - kH + 1))
            if dd <= 24:
                sn -= dd * bx; kH += dd; xf.append('early')
                reasons.append(f'DVS1 rule: no loop on a track that is about to end. CDJ {nX} would reach its H loop inside the change, so start CDJ {nY} {dd} bars earlier (Start next {fmt(sn)}) instead.')
        loopAt = None
        if kH is not None and kH < endb - 1 and not bridge:
            loopAt = max(0.0, round(kH * 4) / 4)
            reasons.append(f'CDJ {nX} reaches its Mix out 8 loop (H, {fmt(xH)}) at bar {int(loopAt) + 1}: the Active Loop holds its groove for the rest of the change.')
        if tail and loopAt is None:
            loopAt = float(s_ + 6 if parts else s_ + 2)
            reasons.append(f'Texture: at bar {int(loopAt) + 1} put an 8-beat loop on CDJ {nX} (or press H early) to hold it under the new track.')
        loopSec = xH; loopLen = 8 if (kH is not None and loopAt is not None and abs(loopAt - kH) < .5) else 2
        if bridge:
            lp = max(11, sw - 4); loopAt = float(lp); loopSec = sn + (lp - 8) * bx; loopLen = 2
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
            T[X + '.loop'] = [[0, 0], [loopAt, loopLen]]
        if bridge:
            xf.append('bridge'); bh = 4 if ST.get('fast') else 8
            setup.update({cY + '.hi': -40, cY + '.hm': -27, cY + '.lm': -27, cY + '.lo': -40})
            T.update({cX + '.hm': [[lp - 2, 0], [lp, -27]], cX + '.lm': [[lp - 2, 0], [lp, -27]], cY + '.fader': [[8, 0], [9, .8]], cY + '.hi': [[9, -40], [lp, 0]],
                      cY + '.hm': [[lp, -27], [sw, 0]], cX + '.lo': [[sw, 0], [sw + .03, -40]], cY + '.lo': [[sw, -40], [sw + .03, 0]], cY + '.lm': [[sw, -27], [sw + .03, 0]],
                      cX + '.fader': [[sw, .8], [sw + 2, .55], [sw + bh, .55], [sw + bh + 2, 0]]})
            steps += [[8, f'Start next ({fmt(sn)}): press B on CDJ {nY}, every band down.'], [9, f'Bring CH {nY} HI up: hats and air first.'],
                      [lp - 2, f'Strip CH {nX} to drums (mids out) and loop 8 beats on CDJ {nX}: drums have no key, so they can carry the floor across the key change.'],
                      [lp, f'Bring CH {nY} HI MID up: its melody arrives over CDJ {nX}\'s drums only, so the two keys never overlap.'],
                      [sw, f'Low end on the 1: CH {nX} LO out, CH {nY} LO and LO MID in. CDJ {nX}\'s drum loop stays under with its LO cut.'],
                      [sw + bh, f'Close CH {nX} over 2 bars and exit its loop.']]
            reasons.append(f'Drum bridge: {x["key"]} → {y["key"]} clash if their melodies overlap, but drums don\'t. CDJ {nX} loops its drums with the mids out while CDJ {nY}\'s melody comes in.')
            endb = sw + bh + 3
        elif typ == 'cut':
            xf.append('xfade')
            setup.update({cY + '.lo': 0, cX + '.x': 'X', cY + '.x': 'Y', 'curve': 'sharp', 'xf': 0})
            T[cY + '.fader'] = [[8, 0], [9, .8]]; T['xf'] = [[s_, 0], [s_ + .03, 1]]; T[cX + '.fader'] = [[s_ + 1, .8], [s_ + 2, 0]]
            steps += [[2, f'Crossfader: assign CH {nX} to X and CH {nY} to Y, curve sharp, crossfader full X.'],
                      [8, f'Start next ({fmt(sn)}): press B on CDJ {nY} and open CH {nY}: the crossfader keeps it silent, check it in the headphones.'],
                      [s_, f'Cut on the 1: slam the crossfader to Y. (Key Shift ±1 on CDJ {nY} is the blend alternative.)'],
                      [s_ + 1, f'Close CH {nX}, exit its loop, set both crossfader assigns back to off.']]
            if loopAt is None and s_ >= 11:
                xf.append('roll')
                T[X + '.loop'] = [[0, 0], [s_ - 2, 1], [s_ - 1.5, .5], [s_ - 1, .25], [s_ - .5, .125], [s_ - .25, .0625], [s_ + .02, 0]]
                steps.append([s_ - 2, f'Loop roll on CDJ {nX}: a 4-beat loop, halved every half bar (2, 1, 1/2, 1/4 beat) so it tightens into the cut.'])
            endb = s_ + 4
            ears.append('Semitone or key-jump cut: check that the new track lands cleanly after the cut.')
        elif typ == 'swap':
            setup.update({cY + '.hi': -40, cY + '.hm': -27, cY + '.lm': -27, cY + '.lo': -40})
            T.update({cY + '.fader': [[8, 0], [9, .8]], cY + '.hi': [[9, -40], [sw - 2, 0]], cY + '.hm': [[9, -27], [sw - 2, 0]],
                      cX + '.fa': [[0, 0], [sw - 4, 1]], 'f1.on': [[0, 0], [sw - 4, 1], [sw + 2, 0]], 'f1.mode': [[0, 'HPF']], 'f1.freq': [[sw - 4, .08], [sw, .42]], 'f1.res': [[sw - 4, .3], [sw, .6]],
                      cX + '.lo': [[sw, 0], [sw + .03, -40]], cY + '.lo': [[sw, -40], [sw + .03, 0]], cY + '.lm': [[sw, -27], [sw + .03, 0]],
                      cX + '.fader': [[sw, .8], [sw + 2, 0]]})
            xf.append('hpf')
            steps += [[8, f'Start next ({fmt(sn)}): press B on CDJ {nY}, every band down.'], [9, f'Bring CH {nY} HI and HI MID up.'],
                      [sw - 4, f'Filter 1 on CH {nX}, HPF: sweep FREQ up with RES rising over 4 bars. It strips the old track to its tops before the swap.'],
                      [sw, f'Swap on the 1: CH {nX} LO out, CH {nY} LO and LO MID in, close CH {nX} over 2 bars, Filter 1 off.']]
            endb = sw + 4
        else:
            setup.update({cY + '.hi': -40, cY + '.lo': -40})
            if parts: setup.update({cY + '.hm': -27, cY + '.lm': -27})
            lmA = 2 if ST.get('fast') else 4
            hiEnd = max(12, min(sw - 1, 10 + Nb // 2))
            lpf = ST.get('lpf') and not parts and i % 2 == 0
            T.update({cY + '.fader': [[8, 0], [10, .8]], cY + '.hi': [[10, -40], [hiEnd, 0]], cX + '.lo': [[s_, 0], [s_ + .03, -40]], cY + '.lo': [[s_, -40], [s_ + .03, 0]]})
            if lpf:
                xf.append('lpf'); setup.update({cY + '.hi': 0, cY + '.fa': 2, 'f2.on': 1, 'f2.mode': 'LPF', 'f2.freq': .3, 'f2.res': .25})
                del T[cY + '.hi']; T.update({'f2.freq': [[10, .3], [hiEnd, 1]], 'f2.on': [[0, 1], [hiEnd + .5, 0]]})
                steps += [[8, f'Start next ({fmt(sn)}): press B on CDJ {nY}, LO killed, Filter 2 (LPF) already on CH {nY}, FREQ low.'],
                          [10, f'Open Filter 2 on CH {nY} over {hiEnd - 10} bars: the new track arrives muffled and brightens into the mix, then switch the filter off.' + (' Same key: let them sit together.' if hold else '')]]
            else:
                steps += [[8, f'Start next ({fmt(sn)}): press B on CDJ {nY}, LO killed.'], [10, f'Raise CH {nY} HI over {hiEnd - 10} bars.' + (' Same key: let them sit together.' if hold else '')]]
            if late: steps.append([sw, f'Energy drops here: keep CDJ {nX}\'s low end 4 more bars.'])
            steps.append([s_, f'Bass swap on the 1: CH {nX} LO out, CH {nY} LO in.'])
            if parts:
                xf.append('parts'); hE = hiEnd; hmAt = max(hE + 1, s_ - (4 if ST.get('fast') else 8))
                if hmAt + 2 >= s_: hmAt = max(hE, s_ - 3)
                T.update({cY + '.hm': [[hmAt, -27], [hmAt + 2, 0]], cX + '.hm': [[hmAt, 0], [hmAt + 2, -27]], cX + '.hi': [[hE, 0], [hE + 2, -6]],
                          cY + '.lm': [[s_ + lmA, -27], [s_ + lmA + 2, 0]], cX + '.lm': [[s_ + lmA, 0], [s_ + lmA + 2, -27]]})
                steps.append([hmAt, f'Hand over the mids: CH {nX} HI MID down, CH {nY} HI MID up. The chords and melody change hands before the low end does.'])
                steps.append([s_ + lmA, f'Last part: LO MID (bass tone, kick knock) changes hands. CDJ {nX} is now only its highs.'])
                reasons.append('Part by part (Hawtin): the tracks trade one band at a time: highs, mids, low end, low mids, each on its own line, instead of one swap.')
            if tail:
                f0 = (s_ + 6) if parts else s_ + 2; f1 = f0 + 16
                T.update({cX + '.fa': [[0, 0], [f0, 1]], 'f1.on': [[0, 0], [f0, 1]], 'f1.mode': [[0, 'HPF']], 'f1.freq': [[f0, .22], [f1, .5]], 'f1.res': [[f0, .25], [f1, .45]],
                          cX + '.hm': [[f0, 0], [f0 + 2, -8]], cX + '.fader': [[f0, .8], [f0 + 4, .5], [f1, .5], [f1 + 4, 0]]})
                sc, rel = tail_score(x, y)
                if ST.get('crunch'):
                    xf.append('crunch'); T.update({'f1.crunch': [[f0, 0], [f1, .35]], 'f1.res': [[f0, .3], [f1, .6]]})
                steps.append([f0, f'Texture: CDJ {nX} keeps looping under {y["title"]}: Filter 1 on CH {nX} (HPF rising slowly), fader to half, HI MID down a touch.' + (' Add CRUNCH on Filter 1 as it rises: the loop turns to grit and resonance as it leaves.' if ST.get('crunch') else '')])
                steps.append([f1, f'Fade the texture out over 4 bars, exit the loop, load the next track on CDJ {nX}.'])
                reasons.append(f'Recommendation (texture): {x["key"]} → {y["key"]} ({rel} key) and CDJ {nX}\'s outro loop is rich in tops, so it can ride under the new track for 16 bars with its LO cut.')
                ears.append('Texture tail: listen for clashing melodies or vocals between the loop and the new track.')
                endb = f1 + 5
            elif ST.get('edit') and (not parts or ST.get('fast')) and loopAt is None and s_ >= 12 and 'core' not in xf:
                xf += ['edit', 'roll', 'crunch']; ed = s_ + 5 if parts else s_
                T.update({X + '.loop': [[0, 0], [ed - 2, 1], [ed - 1.5, .5], [ed - 1, .25], [ed - .5, .125], [ed - .25, .0625], [ed + .02, 0]],
                          cX + '.fa': [[0, 0], [ed - 2, 1]], 'f1.on': [[0, 0], [ed - 2, 1], [ed + .03, 0]], 'f1.mode': [[0, 'HPF']], 'f1.freq': [[ed - 2, .05], [ed, .35]],
                          'f1.res': [[ed - 2, .3], [ed, .6]], 'f1.crunch': [[ed - 2, 0], [ed, .5]], cX + '.fader': [[ed, .8], [ed + .03, 0]]})
                steps.append([ed - 2, f'Edit: loop roll on CDJ {nX} (4 beats, halving every half bar) with Filter 1 HPF and CRUNCH rising: a 2-bar build.'])
                steps.append([ed + .03, f'Land it on the 1: CH {nX} fader shut' + (' as CH ' + str(nY) + ' takes the low end' if not parts else ', CDJ ' + str(nY) + ' now plays every band') + '. The change sounds like an edit, not a fade.'])
                reasons.append(f'Edit on the fly (Temple): instead of a slow fade, CDJ {nX} rolls and crunches into the 1' + (' once the parts have traded' if parts else '') + '.')
                endb = ed + 4
            else:
                f0 = (s_ + 6) if parts else s_ + 2
                T[cX + '.fader'] = [[f0, .8], [f0 + fe, 0]]
                steps.append([f0, f'Fade CH {nX} out over {fe} bars.' + (' It is the core rhythm of this phase: let it leave slowly.' if 'core' in xf else '')])
            if 'core' in xf: reasons.append(f'Core rhythm (DVS1): {x["title"]} carries this phase\'s groove, so the change is built around it and it leaves slowly.')
        # a layer still playing from the previous scene fades out on this change
        decks = [dict(d=X, title=x['title'], sec=sn - 8 * bx, bpm=x['bpm'], loopAt=loopAt, loopSec=loopSec, loopLen=loopLen),
                 dict(d=Y, title=y['title'], sec=yB, bpm=y['bpm'], startBar=8)]
        if i in ST['aux'] and not (carry and carry['d'] not in (X, Y)):
            z = leads[i + 2]; Z = DBY[z['deck']]; cZ = DCH[Z]; nZ = DNUM[Z]; bz = 240 / z['bpm']
            bk = P[z['cid']]['breaks'][0][0]; zsec = z['fb'] + bk * bz; a0 = (s_ + 2) if typ != 'swap' else sw + 2
            clip = ST.get('clip') and (ST['clip'] is True or i % 2 == 1) and z['pads'].get('E')
            if clip: zsec = z['pads']['E']['sec']
            setup.update({cZ + '.lo': -40, cZ + '.hm': -6, cZ + '.gain': -4})
            T.update({Z + '.play': [[0, 0], [a0, 1], [a0 + 16, 0]], cZ + '.fader': [[a0, 0], [a0 + 4, .45], [a0 + 12, .45], [a0 + 16, 0]]})
            if clip: T[Z + '.loop'] = [[0, 0], [a0, 1], [a0 + 16, 0]]
            if clip:
                steps.append([a0 - 1, f'Third deck clip: cue CDJ {nZ} ({z["title"]}, two changes from now) on its Drop pad ({fmt(zsec)}). CH {nZ} LO killed, GAIN −4 dB.'])
                steps.append([a0, f'Third deck in as a clip: a 4-beat loop of {z["title"]}\'s drop, CH {nZ} up to about half. It adds percussion and grit on top, like a sample.'])
            else:
                steps.append([a0 - 1, f'Third deck: cue CDJ {nZ} ({z["title"]}, its real slot is two changes from now) at its breakdown ({fmt(zsec)}). CH {nZ} LO killed, GAIN −4 dB.'])
                steps.append([a0, f'Third deck in: the blend is stable, so bring CH {nZ} up to about half. {z["title"]}\'s breakdown adds atmosphere over the new groove.'])
            steps.append([a0 + 12, f'Third deck out over 4 bars, then re-cue CDJ {nZ} to pad B for its own entry.'])
            decks.append(dict(d=Z, title=z['title'], sec=zsec, bpm=z['bpm'], startBar=a0, **({'loopAt': a0, 'loopSec': zsec, 'loopLen': 1} if clip else {})))
            if clip: xf.append('clip')
            reasons.append(f'Hopscotch (DVS1): a third deck only once the mix is stable. {z["title"]} is in {z["key"]}, {keyrel(y["key"], z["key"])} to {y["title"]} ({y["key"]}), and its breakdown is texture without a kick.')
            ears.append('Third deck: check that the atmosphere sits with both tracks.')
            if not clip: xf.append('aux')
            endb = max(endb, a0 + 17)
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
        scenes.append(dict(id=f'f{len(scenes) + 1}', kind='loop' if loopAt is not None and typ != 'cut' and not bridge else typ, tail=tail, xf=xf, title=f'{x["title"]} → {y["title"]}',
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
        elif (i + 1) in mash_of:
            _, M, info = mash_of[i + 1]
            scenes.append(mash_scene(y, M, info, i + 1, len(scenes), carry['d'] if carry else None))

    return scenes

B15 = {k: int(np.ceil(v * 1.5)) for k, v in BUDGET.items()}
AUXB = {'Locked opening': 0, 'Orientation': 2, 'Groove formation': 4, 'First pressure wave': 6, 'Micro reset': 1, 'Second pressure wave': 6, 'Handoff': 2}
AUXH = {k: (v + 1) // 2 for k, v in AUXB.items()}
STYLES = [
    dict(id='sheet', name='Sheet', desc='Your set sheet as planned, plus recommendations from the data: H loops, texture tails, breakdown swaps.',
         ST=dict(tails=pick_tails(BUDGET), aux=set(), lpf=True)),
    dict(id='hopscotch', name='Hopscotch (DVS1)', desc='Build around a core rhythm; a third deck joins only once the mix is stable (the breakdown of the track two changes ahead, as atmosphere); never loop a track that is about to end, start the next one earlier instead.',
         ST=dict(tails=set(), aux=pick_aux(AUXB), avoidH=True, core=True, lpf=True)),
    dict(id='deconstruct', name='Deconstruct (Hawtin)', desc='Take the tracks apart: compatible keys trade one band at a time (highs, mids, low end, low mids); key changes cross on a drum loop with the mids out; more loop textures.',
         ST=dict(tails=pick_tails(B15), aux=set(), parts=True, bridge=True, crunch=True)),
    dict(id='temple', name='Edit & clip (Paula Temple)', desc='Producer-minded and restless: changes land like edits (loop roll, filter and CRUNCH build, the new track drops in on the 1), quick swaps and crossfader cuts, and short loops of coming tracks layered on a third deck like samples. Built from her published descriptions, adapted from her Ableton hybrid rig to CDJs.',
         ST=dict(tails=set(), aux=pick_aux(AUXB), edit=True, clip=True, crunch=True)),
    dict(id='hybrid', name='Hybrid (DVS1 × Hawtin × Temple)', desc='Layered like DVS1 and Hawtin, moving like Temple: tracks trade part by part but quickly, then land with a roll and CRUNCH edit; key changes cross on short drum bridges; a third deck adds either an atmosphere (DVS1) or a short clip (Temple), built around a core rhythm, no loops on tracks about to end.',
         ST=dict(tails=pick_tails(BUDGET), aux=pick_aux(AUXH), parts=True, bridge=True, core=True, avoidH=True, crunch=True, lpf=True, fast=True, edit=True, clip='alt')),
]
for stl in STYLES: stl['scenes'] = build(stl['ST'])
scenes = [sc for stl in STYLES for sc in stl['scenes']]

KEYMOVE = [('⇈', 'a key lift (whole tone or minor third)'), ('⇊', 'a key drop (whole tone or minor third)'), ('⤴', 'a semitone lift'), ('⤵', 'a semitone drop'),
           ('!!', 'a key jump'), ('↔', 'a move to the relative key'), ('↕', 'a mood change (minor/major)'), ('↑', 'a lift one step up'), ('↓', 'a release one step down'), ('= hold', 'the same key')]
FLAG = {'blend': 'Blend', 'long': 'Long blend', 'swap': 'Quick swap', 'cut': 'Cut', 'hloop': 'H loop', 'tail': 'Texture tail', 'brk': 'Breakdown swap',
        'late': 'Late lows', 'layer': 'Layer', 'three': '3 decks', 'trim': 'Gain trim', 'parts': 'Part by part', 'bridge': 'Drum bridge',
        'aux': '3rd deck texture', 'early': 'Early start', 'core': 'Core rhythm', 'pair': 'Your pair', 'mik': 'MIK mashup', 'xfade': 'Crossfader cut', 'roll': 'Loop roll', 'hpf': 'HPF sweep', 'lpf': 'LPF reveal', 'crunch': 'Crunch', 'edit': 'Edit', 'clip': 'Clip layer'}
TAGS = [(r'^Edit:', 'Edit'), (r'^Land it on the 1', 'Drop in'), (r'^Third deck clip', 'Clip'), (r'^Third deck in as a clip', 'Clip in'), (r'^Crossfader:', 'Crossfader'), (r'^Loop roll', 'Loop roll'), (r'slam the crossfader', 'Cut'), (r'^Filter 1 on CH \d+, HPF', 'HPF sweep'), (r'^Open Filter 2', 'LPF reveal'), (r'^Mashup in', 'Mashup in'), (r'^Mashup out', 'Mashup out'), (r'^Third deck out', 'Third deck out'), (r'^Third deck', 'Third deck'), (r'^Hand over the mids', 'Mids swap'), (r'^Last part: LO MID', 'Low mids swap'),
        (r'melody arrives', 'Mids in'), (r'^Low end on the 1', 'Bass swap'), (r'^CDJ \d+ (plays|leads)', 'Prep'), (r'Set CH \d+ GAIN', 'Trim'), (r'Key Shift', 'Key Shift'), (r'Start next|press B', 'Cue in'),
        (r'reaches H|H loop', 'H loop'), (r'Strip', 'Strip'), (r'Energy drops', 'Hold lows'), (r'Bass swap|Swap on the 1', 'Bass swap'), (r'Cut on the 1', 'Cut'),
        (r'^Texture:', 'Texture'), (r'Fade the texture', 'Texture out'), (r'goes out with the old lead', 'Layer out'), (r'Raise|Bring CH|bring CH', 'Blend in'),
        (r'Scoop', 'Shape'), (r'Hold the layer', 'Layer'), (r'Fade CH|Close', 'Out')]
for sc in scenes:
    note = sc['why']; fl = []; xf = sc.get('xf', [])
    if 'bridge' in xf: fl.append('bridge')
    elif 'mik' in xf: fl.append('mik')
    elif sc['kind'] == 'layer': fl.append('layer')
    elif sc['kind'] == 'cut': fl.append('cut')
    elif sc['kind'] == 'swap': fl.append('swap')
    elif 'edit' in xf: fl.append('edit')
    else: fl.append('long' if re.search(r'= hold|YOUR PAIR', note) else 'blend')
    if any('Mix out 8 loop' in r for r in sc['reasons']): fl.append('hloop')
    if sc['tail']: fl.append('tail')
    if any('breaks down' in r for r in sc['reasons']): fl.append('brk')
    if 'cut its lows late' in note: fl.append('late')
    if any('Three decks' in r for r in sc['reasons']): fl.append('three')
    for f in ('pair', 'parts', 'aux', 'clip', 'core', 'early', 'xfade', 'roll', 'hpf', 'lpf', 'crunch'):
        if f in xf: fl.append(f)
    if any(k.endswith('.gain') and not k.startswith(DCH[sc['pair'][0]]) for k in sc['tracks']) and sc['kind'] != 'layer' and 'aux' not in xf: fl.append('trim')
    km = next((t for sym, t in KEYMOVE if sym in note), 'a key change')
    X, Y = sc['pair']; nX, nY = DNUM[X], DNUM[Y]
    base = {'long': f'Hand the floor over without a seam: {km}, so let both tracks play as one and swap the low end on the phrase.',
            'blend': f'{km[0].upper() + km[1:]}: bring CDJ {nY} in under CDJ {nX}, one low end at a time, and swap the bass on the phrase.',
            'swap': f'{km[0].upper() + km[1:]}: keys that clash if they overlap long, so keep it short, strip CDJ {nX} down to its drums or tops and swap on the 1.',
            'cut': f'{km[0].upper() + km[1:]}: no blend, a clean cut on the 1 (on a breakdown if you can).',
            'edit': (f'{km[0].upper() + km[1:]}, layered then cut like an edit: the tracks trade parts quickly (mids, low end on the 1, low mids), then CDJ {nX} rolls and crunches out in 2 bars and CDJ {nY} carries on alone.' if 'parts' in xf else f'{km[0].upper() + km[1:]}, played like an edit: CDJ {nY} comes in under CDJ {nX}, then CDJ {nX} rolls and crunches for 2 bars and the new track drops in on the 1.'),
            'mik': f'A mashup you already marked in Mixed In Key: CDJ {nY} adds its parts over CDJ {nX} for 24 bars, LO cut so the lead keeps the low end, then leaves before the next change.',
            'layer': f'Build a third thing: CDJ {nY} rides under CDJ {nX} as a layer, its lows cut, the lead stays in front.',
            'bridge': f'{km[0].upper() + km[1:]}: the melodies must not overlap, so the drums carry the floor across. CDJ {nX} loops its drums with the mids out, CDJ {nY}\'s melody arrives over them, then the low end swaps on the 1.'}[fl[0]]
    extra = []
    if 'hloop' in fl: extra.append(f'CDJ {nX} sits on its H loop, so there is no deadline')
    if 'brk' in fl: extra.append(f'land the swap in CDJ {nX}\'s breakdown, where its bass drops out anyway')
    if 'tail' in fl: extra.append(f'after the swap CDJ {nX}\'s loop stays underneath as background texture (LO cut, filter rising)')
    if 'late' in fl: extra.append('the energy steps down, so hold the old low end a little longer')
    if 'three' in fl: extra.append('the layer from the last scene is still in and goes out with the old lead')
    if 'pair' in fl: extra.append('this is one of your own pairs, so let them play as one for longer before CDJ ' + str(nX) + ' leaves')
    if 'clip' in fl: extra.append('a short loop of a track still to come rides on a third deck like a sample')
    if 'xfade' in fl: extra.append('the cut happens on the crossfader, so both channels are open and you only move one control on the 1' + (', after a loop roll that tightens into it' if 'roll' in fl else ''))
    if 'hpf' in fl: extra.append(f'Filter 1 sweeps CDJ {nX} up to its tops before the swap')
    if 'lpf' in fl: extra.append(f'CDJ {nY} arrives through Filter 2, a low-pass opening up')
    if 'crunch' in fl and 'tail' in fl: extra.append('the texture leaves through CRUNCH and resonance')
    if 'parts' in fl and 'edit' not in fl: extra.append('trade the tracks part by part: highs, then mids, then the low end on the 1, then the low mids')
    if 'core' in fl: extra.append(f'CDJ {nX} is this phase\'s core rhythm, so let it leave slowly')
    if 'early' in fl: extra.append(f'start CDJ {nY} earlier rather than loop the end of CDJ {nX}')
    if 'aux' in fl: extra.append('once it is stable, a third deck adds the breakdown of a track still to come as atmosphere, then goes back to its cue')
    LEARN = {'long': 'p1', 'blend': 'l1', 'swap': 'l4', 'hpf': 'l4', 'cut': 't5', 'xfade': 't5', 'roll': 't5', 'brk': 'p2', 'bridge': 't3', 'parts': 'l2', 'crunch': 't2',
             'tail': 't2' if 'crunch' in fl else 'l4', 'edit': 't5', 'clip': 'p6', 'lpf': 't1', 'aux': 'p3', 'layer': 'p3', 'mik': 'p3', 'late': 'l2', 'hloop': 't3'}
    sc['learn'] = list(dict.fromkeys(LEARN[f] for f in fl if f in LEARN))
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
           scenes=STYLES[0]['scenes'], styles=[dict(id=s_['id'], name=s_['name'], desc=s_['desc'], scenes=s_['scenes']) for s_ in STYLES])
json.dump(out, open(a.out, 'w'), ensure_ascii=False, indent=0)
k = {}
for s in scenes: k[s['kind']] = k.get(s['kind'], 0) + 1
for s_ in STYLES:
    c = {}
    for sc in s_['scenes']:
        for f in sc['flags']: c[f['k']] = c.get(f['k'], 0) + 1
    print(s_['id'], len(s_['scenes']), c)
print(f'{len(scenes)} scenes · {k} · texture tails {sum(s["tail"] for s in scenes)} · breakdown swaps {sum(any("breaks down" in r for r in s["reasons"]) for s in scenes)} · moved {moved}')

