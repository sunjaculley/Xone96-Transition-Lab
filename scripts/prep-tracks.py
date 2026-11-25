#!/usr/bin/env python3
"""Track prep for the lab, after the rekordbox-track-prep method.

For every audio file in tracks/ it measures the grid (beat 1 on the first kick, tempo from the
"Key - BPM - Title - Artist" name, drift check), maps the structure bar by bar (kick, bass, mids,
highs), places Sunja's cue layout, and picks the bars each lab technique should start on.
Results go into the track's sidecar JSON (tracks/<name>.json); existing title/artist fixes are kept.

Cue layout (same as her Rekordbox prep):
  A  first kick (beat 1)            B  'Mix in 8'  8-bar hot loop
  C  'Play'  first full groove      D/E 'Break 1'/'Drop 1', F/G 'Break 2'/'Drop 2' (E 'Jump' if no breakdown)
  H  'Mix out 8'  8-bar hot loop at the outro
  memory markers 'Bass in' / 'Bass out'
  Energy E1-E5 (relative to the tracks in this folder)

Lab start bars (cues.*), chosen for what each technique needs to be heard:
  mixOut     CDJ 1, every technique: kick and bass running for the first 12 bars, kick to bar 14
  mixIn      CDJ 2, T1-T4: the intro, B 'Mix in 8'
  bassSwap   CDJ 2, L1-L4: the incoming bass is in by technique bar 8, where the swap happens
  kickIntro  CDJ 2, L5: the barest kick bar before the bass, for the looped kick
  drop       CDJ 2, T5: Drop 1, so the hard cut lands on a drop

usage: python3 scripts/prep-tracks.py [tracks_dir] [--print]
Needs ffmpeg, numpy and scipy. Runs locally (not in the Pages build).
"""
import json, os, re, subprocess, sys
import numpy as np
from scipy.signal import butter, sosfiltfilt

SR = 22050
HOP = 64                     # 2.9 ms envelope resolution
AUDIO = ('.mp3', '.m4a', '.aac', '.wav', '.ogg', '.oga', '.opus', '.flac')
NAME = re.compile(r'^(\d{1,2}[AB])\s+[-–]\s+(\d{2,3}(?:\.\d+)?)\s+[-–]\s+(.+?)\s+[-–]\s+(.+)$', re.I)


def decode(path):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).astype(np.float64)


def env(x, lo, hi):
    sos = butter(4, [lo, hi], 'bandpass', fs=SR, output='sos') if lo else butter(4, hi, 'lowpass', fs=SR, output='sos')
    y = np.abs(sosfiltfilt(sos, x))
    n = len(y) // HOP
    return y[:n * HOP].reshape(n, HOP).max(1)


def smooth(a, k):
    return np.convolve(a, np.ones(k) / k, 'same')


def analyse(path, bpm):
    x = decode(path)
    dur = len(x) / SR
    eps = SR / HOP                                       # envelope frames per second
    kick = env(x, 40, 120)
    bass = env(x, 35, 160)
    mid = env(x, 250, 2500)
    high = env(x, 5000, 10500)
    flux = np.maximum(0, np.diff(smooth(kick, 3), prepend=0))

    # tempo and phase: the name's BPM is Mixed In Key's, rounded. Measure the exact tempo near it
    # (phase coherence of the kick onsets), so the grid holds across the whole track.
    t = np.arange(len(flux)) / eps
    wgt = flux.copy()
    wgt[wgt < np.percentile(wgt, 97)] = 0                 # only real onsets
    nz = wgt > 0
    tt, ww = t[nz], wgt[nz]
    def coh(b, sel=None):
        P = 60 / b
        z = ww * np.exp(2j * np.pi * tt / P) if sel is None else ww[sel] * np.exp(2j * np.pi * tt[sel] / P)
        return z.sum()
    cands = np.arange(bpm - 1.0, bpm + 1.0001, 0.005)
    mags = np.array([abs(coh(b)) for b in cands])
    tempo = float(cands[mags.argmax()])
    # snap like her prep: whole number, else .5, only when the measurement supports it
    for snap in (round(tempo), round(tempo * 2) / 2):
        if abs(coh(snap)) >= 0.97 * mags.max():
            tempo = float(snap); break
    P = 60 / tempo
    off = (np.angle(coh(tempo)) / (2 * np.pi) * P) % P
    # drift: local phase in 32-bar windows that have a clear kick, spread in ms
    loc = []
    for t0 in np.arange(0, dur - 128 * P, 64 * P):
        sel = (tt >= t0) & (tt < t0 + 128 * P)
        if sel.sum() < 40: continue
        z = coh(tempo, sel)
        if abs(z) < 0.4 * ww[sel].sum(): continue
        d = (np.angle(z) / (2 * np.pi) * P - off + P / 2) % P - P / 2
        loc.append(d)
    drift_ms = float(np.ptp(loc) * 1000) if len(loc) > 1 else 0.0

    # per-beat kick strength on the grid
    grid = np.arange(off, dur - P, P)
    gi = (grid * eps).astype(int)
    w = int(0.02 * eps)
    ks = np.array([flux[max(0, i - w):i + w + 1].max() for i in gi])
    kref = np.percentile(ks, 90)
    kick_on = ks > 0.3 * kref

    # first kick: first beat that starts a run of kicks (3 of the next 4 beats)
    first = next(i for i in range(len(kick_on) - 4) if kick_on[i] and kick_on[i:i + 4].sum() >= 3)
    fb = float(grid[first])
    beats = grid[first:]
    kon = kick_on[first:]
    nbars = len(beats) // 4

    def frames(t0, t1):
        return slice(int(t0 * eps), max(int(t0 * eps) + 1, int(t1 * eps)))

    # bar features
    K, Bs, M, H, E = [], [], [], [], []
    for b in range(nbars):
        bt = beats[b * 4:b * 4 + 4]
        K.append(kon[b * 4:b * 4 + 4].mean())
        # bass between the kicks: 0.5..0.95 of each beat, after the kick has decayed
        Bs.append(np.mean([np.sqrt(np.mean(bass[frames(t + 0.5 * P, t + 0.95 * P)] ** 2)) for t in bt]))
        sl = frames(bt[0], bt[0] + 4 * P)
        M.append(np.sqrt(np.mean(mid[sl] ** 2)))
        H.append(np.sqrt(np.mean(high[sl] ** 2)))
        E.append(np.sqrt(np.mean(x[int(bt[0] * SR):int((bt[0] + 4 * P) * SR)] ** 2)))
    K, Bs, M, H, E = map(np.array, (K, Bs, M, H, E))
    nrm = lambda a: a / max(1e-9, np.percentile(a, 90))
    Bn, Mn, Hn = nrm(Bs), nrm(M), nrm(H)
    kick = K >= 0.5
    bassp = Bn > 0.45
    return dict(dur=dur, bpm=tempo, fb=fb, drift_ms=drift_ms, nbars=nbars, kick=kick, bass=bassp,
                K=K, B=Bn, M=Mn, H=Hn, E=E, x=x)


def runs(mask, val=True):
    out, s = [], None
    for i, v in enumerate(list(mask) + [not val]):
        if v == val and s is None: s = i
        if v != val and s is not None: out.append((s, i)); s = None
    return out


a8 = lambda b: 8 * int(round(b / 8))       # nearest phrase line from A
d8 = lambda b: 8 * (b // 8)


def place(r):
    n, kick, bass = r['nbars'], r['kick'], r['bass']
    notes = []
    kruns = runs(kick)
    last_kick = max(e for s, e in kruns if e - s >= 4)          # bar after the last kick
    # bass: first and last sustained run (4+ bars)
    bruns = [(s, e) for s, e in runs(bass) if e - s >= 4]
    bass_in = bruns[0][0] if bruns else None
    bass_out = bruns[-1][1] if bruns else None

    # breaks: kick gaps of 4+ bars inside the body (after 8 bars of kick, before the last kick)
    breaks = []
    for s, e in runs(kick, False):
        if s >= 8 and e < last_kick and e - s >= 4:
            if e >= last_kick - 8: continue                      # a gap just before the end is outro, not a breakdown
            # snap to the 8-count from A only when within a bar; otherwise keep where the music changes, and flag it
            bs = a8(s) if abs(a8(s) - s) <= 1 else s
            de = a8(e) if abs(a8(e) - e) <= 1 else e
            if bs % 8 or de % 8:
                notes.append(f'PHRASE? break bars {s}-{e} sit off the 8-count from A (cue kept where the kick stops/returns)')
            breaks.append((bs, de, e - s))
    # biggest two breaks, kept in time order
    breaks = sorted(sorted(breaks, key=lambda b: -b[2])[:2])

    full = lambda b, L=8: b + L <= n and kick[b:b + L].mean() >= 0.85 and bass[b:b + L].mean() >= 0.75
    cues = {'A': 0, 'B': 0}
    first_drop = breaks[0][1] if breaks else None
    lim = breaks[0][0] if breaks else n - 8
    C = next((b for b in range(8, lim, 8) if full(b)), None)
    if C is None: C = next((b for b in range(8, lim, 8) if kick[b:b + 8].mean() >= 0.85), None)
    if C is None: C = 8
    cues['C'] = C
    if len(breaks) == 2:
        cues['D'], cues['E'], cues['F'], cues['G'] = breaks[0][0], breaks[0][1], breaks[1][0], breaks[1][1]
        names = {'D': 'Break 1', 'E': 'Drop 1', 'F': 'Break 2', 'G': 'Drop 2'}
    elif len(breaks) == 1:
        cues['D'], cues['E'] = breaks[0][0], breaks[0][1]
        names = {'D': 'Break', 'E': 'Drop'}
    else:
        cues['E'] = d8(n // 2)
        names = {'E': 'Jump'}
    # H: the outro. Where the bass leaves for good if that is well before the last kick, else 16 bars from the end of the kick
    if bass_out is not None and bass_out <= last_kick - 8:
        H = d8(bass_out)
    else:
        H = d8(last_kick - 16)
    H = max(H, C + 8)
    while H in [cues.get(k) for k in 'DEFG'] and H + 16 <= last_kick: H += 8
    cues['H'] = H

    # lab start bars
    # CDJ 1: latest phrase where kick and bass run for 12 bars and the kick for 14
    def out_ok(m):
        return m + 16 <= n and kick[m:m + 14].mean() >= 0.85 and bass[m:m + 12].mean() >= 0.8
    cand = [m for m in range(0, n - 16, 8) if out_ok(m)]
    mixOut = cand[-1] if cand else max(0, d8(H - 16))
    # CDJ 2, low-end swaps: bass in by technique bar 8
    def swap_ok(m):
        return m + 16 <= n and kick[m:m + 16].mean() >= 0.85 and bass[m + 8:m + 16].mean() >= 0.75
    cand = [m for m in range(0, n - 16, 8) if swap_ok(m)]
    bassSwap = cand[0] if cand else 0
    # CDJ 2, looped kick: the barest kick bar before the bass (or in the first 16 bars)
    lim = max(4, min(bass_in if bass_in is not None else 16, 32))
    bare = [b for b in range(0, lim) if kick[b]]
    kickIntro = min(bare, key=lambda b: (r['B'][b] * 2 + r['M'][b] + r['H'][b], -b)) if bare else 0
    drop = cues.get('E') if breaks else C

    markers = {}
    if bass_in is not None: markers['Bass in'] = int(bass_in)
    if bass_out is not None: markers['Bass out'] = int(bass_out)
    return dict(cues=cues, names=names, markers=markers, last_kick=last_kick, breaks=breaks, notes=notes,
                lab=dict(mixOut=int(mixOut), mixIn=0, bassSwap=int(bassSwap), kickIntro=int(kickIntro), drop=int(drop)))


def main():
    d = next((a for a in sys.argv[1:] if not a.startswith('--')), 'tracks')
    files = sorted(f for f in os.listdir(d) if f.lower().endswith(AUDIO) and not f.startswith('.'))
    res = []
    for f in files:
        base = os.path.splitext(f)[0]
        m = NAME.match(base)
        if not m:
            print(f'skip (no Key - BPM in name): {f}'); continue
        bpm = float(m.group(2))
        r = analyse(os.path.join(d, f), bpm)
        p = place(r)
        body = r['E'][(r['kick']) & (r['bass'])]
        r['energy_raw'] = float(np.mean(body) if len(body) else np.mean(r['E'])) * (0.6 + 0.4 * float(np.mean(r['H'] > 0.5)))
        res.append((f, base, r, p))
    # Energy E1-E5 relative to this folder
    vals = np.array([r['energy_raw'] for _, _, r, _ in res])
    ranks = vals.argsort().argsort()
    for (f, base, r, p), rk in zip(res, ranks):
        en = 1 + int(round(4 * rk / max(1, len(res) - 1)))
        side = os.path.join(d, base + '.json')
        data = {}
        if os.path.exists(side):
            data = json.load(open(side))
        cl = {}
        for k, v in p['cues'].items():
            e = {'bar': int(v)}
            if k == 'A': e['name'] = 'First kick'
            elif k in ('B', 'H'): e.update(name='Mix in 8' if k == 'B' else 'Mix out 8', loop=8)
            elif k == 'C': e['name'] = 'Play'
            else: e['name'] = p['names'][k]
            cl[k] = e
        data.update({
            'firstBeat': round(r['fb'], 4),
            'bpm': round(r['bpm'], 2),
            'cues': p['lab'],
            'hotcues': cl,
            'memory': p['markers'],
            'energy': f'E{en}',
            'prep': {'method': 'rekordbox-track-prep', 'bars': int(r['nbars']), 'lastKickBar': int(p['last_kick']),
                     'gridDriftMs': round(r['drift_ms'], 1), 'notes': p['notes']},
        })
        json.dump(data, open(side, 'w'), indent=2)
        open(side, 'a').write('\n')
        if '--print' in sys.argv:
            k = ''.join('K' if v else '.' for v in r['kick'])
            b = ''.join('B' if v else '.' for v in r['bass'])
            print(f'\n{base}  bpm {r["bpm"]:.2f}  fb {r["fb"]:.3f}s  bars {r["nbars"]}  drift {r["drift_ms"]:.0f} ms  E{en}')
            for i in range(0, len(k), 64):
                print(f'  {i:4d} kick {k[i:i+64]}\n       bass {b[i:i+64]}')
            print('  hot', {kk: (v['bar'], v['name']) for kk, v in cl.items()}, 'mem', p['markers'])
            print('  lab', p['lab'], p['notes'])


if __name__ == '__main__':
    main()
