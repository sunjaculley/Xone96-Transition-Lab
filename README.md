# Xone:96 + CDJ-3000 transition lab

An interactive, top-down drawing of an Allen & Heath Xone:96 between two Pioneer CDJ-3000s that walks through ten techno transition techniques (five transitions, five low-end swaps), step by step or animated, with real audio.

**Live:** https://sunjaculley.github.io/Xone96-Transition-Lab/

## What's here

| Path | What it is |
|---|---|
| `index.html` | The whole lab: one self-contained HTML file (CSS and JS inline). |
| `tracks/` | Drop audio files here. See `tracks/README.md`. |
| `scripts/build-manifest.mjs` | Lists the files in `tracks/` into `tracks/manifest.json`; the Pages workflow runs it on every push. |
| `.github/workflows/pages.yml` | Builds the manifest and deploys the site to GitHub Pages. |

## How the audio works

- **Sound on** starts the audio engine (browsers need a click first). Without it, the lab runs silently as an illustration.
- Each CDJ plays its track; each mixer channel runs gain → 4-band EQ (full kill on HI and LO) → the assigned Xone filter (CRUNCH drive, HPF/BPF/LPF, RES) → channel fader → crossfader curve → master. The same step timelines that move the drawing drive these nodes. EQ band frequencies are approximations of the 96's, not measured values.
- The CDJ screens draw a 3-band colour waveform, overview, time and BPM from the loaded file. Loops, the loop roll and hot cue A play the real audio on the beat grid.
- The **Who owns each band** meter measures each channel's real lows, low mids, high mids and highs while sound is on.
- With sound on, time runs at the real tempo (the speed controls lock).
- In **Step through**, each step plays its stretch of the transition, then keeps the last bar looping with every control frozen, so you can listen to the result. **Replay step** runs it again.

## Running locally

Open it through a local server so the browser can load `tracks/` (opening the file directly works too, but only the demo tracks appear):

```sh
node scripts/build-manifest.mjs .
python3 -m http.server 8000
# then open http://localhost:8000
```

## Practice and your own library

- **Learn** watches the techniques (Animate or Step through). **Practice** has **Try it**, where you perform a technique on live audio with the mouse, touch or keys and get graded, and a **Beatmatch** trainer. **Explore** lets you tap any part of the gear.
- Techniques come in three groups: Transitions, Low-end swaps, and Phrasing & performance.
- **Rekordbox library**: in rekordbox choose File → Export Collection in xml format, open that file in the lab, then choose your music folder. Tracks play from your disk and are never uploaded; hot cues, memory cues, grid, BPM and key come from rekordbox. Folder picking works in Chrome, Edge, Safari and Firefox.

- **MIDI**: the DDJ-FLX4 is mapped automatically in Chrome or Edge (quit rekordbox first); other controllers via MIDI learn. Optional headphone cue on the FLX4's headphone output (channels 3-4). Message numbers come from the Mixxx DDJ-FLX4 mapping.

Note: this repository is public, so anything in `tracks/` can be downloaded by anyone. The Rekordbox library option keeps your music on your computer.
