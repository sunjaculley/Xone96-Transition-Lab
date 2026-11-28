# Xone:96 + CDJ-3000 transition lab

An interactive, top-down drawing of an Allen & Heath Xone:96 with four Pioneer CDJ-3000s (standard order: CDJ 1, CDJ 2, mixer, CDJ 3, CDJ 4, with CDJ n on CH n) that walks through techno transition techniques; the band panel shows all four channels step by step or animated, with real audio. The built-in techniques use the inner pair, CDJ 2 and CDJ 3.

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

- **Two libraries** (switch at the top of the left column): **Techniques** holds the built-in techniques (Transitions, Low-end swaps, Phrasing & performance). **My set** holds your set: **Set preview** (the performance plan's scenes, continuous play, MP3 export) and **Sheet drills** (one drill per change from the set sheet, with loop and Key Shift versions, scores and phase runs). Learn, Practice and Explore work in both.
- **Export MP3**: in Set preview, record the changes only (about an hour, 192 kbps, short fades between scenes) or the whole set continuous (5½ h, 128 kbps, slow). It renders offline with the lab's mixer model from your own tracks (rekordbox library + music folder) and saves a tracklist with timestamps and the flags for each change. The encoder (lamejs 1.2.1) loads from jsDelivr, unpkg as a fallback.

- **Learn** watches the techniques (Animate or Step through). **Practice** has **Try it**, where you perform a technique on live audio with the mouse, touch or keys and get graded, and a **Beatmatch** trainer. **Explore** lets you tap any part of the gear.
- Techniques come in three groups: Transitions, Low-end swaps, and Phrasing & performance.
- **Rekordbox library**: in rekordbox choose File → Export Collection in xml format, open that file in the lab, then choose your music folder. Tracks play from your disk and are never uploaded; hot cues, memory cues, grid, BPM and key come from rekordbox. Folder picking works in Chrome, Edge, Safari and Firefox.

- **Set sheet**: import a set sheet (.md) from the set builder and every change in it becomes a drill under a Set group, sorted by phase. Sheet deck n plays on CDJ n / CH n (a 2-deck practice sheet uses CDJ 2 and CDJ 3, so the FLX4 and K2 maps line up). Each drill follows the sheet: the outgoing track starts 8 bars before Start next, you press B on the next track at Start next, and the bass swap lands where Bass out meets Bass in. The Note column sets the type: blend, SWAP (short overlap, outgoing stripped to drums), CUT, "cut its lows late" (swap 4 bars later), and trim notes become GAIN targets. `+ layer` rows become layer drills (layer LOW killed, gain down, in on the lead's phrase). With the rekordbox library open, each drill loads its two tracks, starts them at the sheet's times and plays them at the sheet's Play at tempo. The sheet is remembered in this browser.
- **Loop and Key Shift versions**: most set drills have a second version. Blends and swaps get a **loop version**: the outgoing track holds its Mix out 8 hot loop (pad H, key 5) while the next one comes in, with the swap on a loop boundary. Semitone CUTs get a **Key Shift version**: shift the new track a semitone to the old key (keys , and .), blend, then release the shift. Layer drills include the Key Shift the sheet suggests.
- **Key Lock and Key Shift audio**: every deck runs through a small pitch shifter, so tempo changes keep the key (Key Lock / MT on, as on your CDJs) and Key Shift changes the key without changing tempo. It adds about 25 ms of latency to every deck equally.
- **Scores and runs**: your best Try it score for each drill is saved in this browser and shown on its button. **Run this phase** plays every change in the current phase back to back and gives an average; **Drill weakest** opens the change you haven't practised yet, or your lowest score.
- **Performance preview**: `scripts/plan-performance.py` turns a set sheet, a rekordbox XML export and the track prep data (`analysis.json`, `harmony.json`, `mik.json` from `~/.local/share/rekordbox-tools/work`) into a performance plan (.json). Open it with the Set sheet button: every change in the set becomes a scene, and **Perform the set** plays them back to back (condensed: the stretches between changes are skipped) with a timeline of the whole set by phase. On top of the sheet, each scene recommends from the data: holding the outgoing track on its H Active Loop, a texture tail (the outgoing loop stays under the new track with LO cut and the filter rising, in compatible keys, budgeted by phase), moving a swap onto a breakdown, and carrying a sheet layer into the next change (three decks). Each scene is flagged by type (Long blend, Blend, Quick swap, Cut, Layer, plus H loop, Texture tail, Breakdown swap, Late lows, 3 decks, Gain trim) with a one-line intention, every step is tagged (Cue in, Blend in, Bass swap, Texture…), and a deck strip shows what each CDJ is doing (owns the low end, coming in, texture looping, layer, cued, free and what loads next). **Continuous** (the default) plays the whole set end to end; **Predict the move** stops at the top of each change and asks what the move is (and what else happens) before showing it, keeping a score; **Compare styles** plays the same change in two styles back to back and shows what changed; **Move warnings** glow the next control a bar early and count down to the next move with an 8-bar phrase counter. **Watch fullscreen** fills the screen with the rig and a heads-up bar (flags, intention, current step, what each CDJ is doing, set clock, timeline) so you can just watch it go. It, including the stretches between changes (1× with sound, or 2–16× muted). Reasons and "check by ear" flags show with each scene. Texture tails also weigh Mixed In Key energy so a texture never sits above the new track's energy. The plan holds titles and timings only. It is saved in this repo under `sets/` (with the set sheets) and loads automatically; push a new one and every browser picks it up on the next load.
- **Styles** (Set preview, the menu left of Perform the set): **Sheet** (your sheet plus data recommendations), **Hopscotch (DVS1)** (core rhythm, a third deck once the mix is stable, no loops on tracks about to end), **Deconstruct (Hawtin)** (trade tracks part by part, drum bridges across key changes, CRUNCH tails), **Edit & clip (Paula Temple)** (changes land like edits with a loop roll, filter and CRUNCH, short clips of coming tracks on a third deck) and **Hybrid (DVS1 × Hawtin × Temple)** (layered part by part, moving fast, landing with edits). All styles use the full Xone:96: EQ, both filters (HPF sweeps, LPF reveals, resonance, CRUNCH), the crossfader with X/Y assign and sharp curve for cuts, GAIN, CDJ loop rolls and Key Shift. Every scene links to the built-in techniques it uses (Learn these moves). Mashups from your pairs file (Mixed In Key favourites and Ableton rows) appear in every style. A four-lane view shows what each CDJ plays across the set.
- **MIDI**: the DDJ-FLX4 and Xone:K2 are mapped automatically in Chrome or Edge (quit rekordbox first); other controllers via MIDI learn. Optional headphone cue on the FLX4's headphone output (channels 3-4). Message numbers come from the Mixxx DDJ-FLX4 mapping.

Note: this repository is public, so anything in `tracks/` can be downloaded by anyone. The Rekordbox library option keeps your music on your computer.

## Moving around the booth (coming from the FLX4)

- **Navigation & recovery** techniques (N1–N5) in the Techniques library: preview on a free deck, beat jump to the drop, loop to buy time, change direction, and beatmatch by ear. Each animates on the rig and has Try it. N5's Try it opens the Beatmatch trainer.
  - The Xone:96 channel CUE buttons are live. With sound on, a cued channel plays quietly in the right ear while its fader is down, like SPLIT CUE.
  - In Try it, use `X` / `C` for CUE, `[` `]` for BEAT JUMP and `;` `'` for CUE/LOOP CALL on the incoming deck, and tap the pads for hot cues. Jumps are graded by count and timing, so your own hot cue layout works.
- **Free-deck hint** in the set preview names the CDJ nobody is hearing and the track due on it next, with links to N1 and (between changes) N3.
- **Booth tips** (header button): previewing, moving inside a track, loops, tempo and key, an Xone:96 vs FLX4 table, habits that change, and eight FLX4 home drills with a Done counter saved on the device. Each tip links to its drill or to the control in Explore.
- **Explore** shows a "Coming from the FLX4" line on most CDJ and mixer controls.
