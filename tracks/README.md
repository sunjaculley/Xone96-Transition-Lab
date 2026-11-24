# Tracks

Drop audio files into this folder and push. The Pages workflow lists every audio file here in `manifest.json`, and the lab's **CDJ 1** and **CDJ 2** pickers show them next to the two built-in demo tracks.

- **Formats:** `.mp3`, `.m4a`, `.aac`, `.wav`, `.ogg`, `.opus`, `.flac`. MP3 or M4A at 192–320 kbps keeps files small; aim for under 25 MB per file.
- **Names:** `Artist - Title.mp3` fills in artist and title on the CDJ screen.
- **Tempo and grid:** the lab estimates BPM and the first downbeat when a track loads. If the grid is off, or you want the techniques to start at specific bars, add a JSON file with the same name:

```json
// tracks/Artist - Title.json   (no comments in the real file)
{
  "bpm": 130,
  "firstBeat": 0.42,
  "key": "Am",
  "cues": { "mixOut": 96, "mixIn": 0, "drop": 32, "kickIntro": 0 }
}
```

- `firstBeat`: seconds from the start of the file to the first downbeat (bar 1, beat 1).
- `cues` are bar numbers counted from `firstBeat`:
  - `mixOut`: where CDJ 1 sits when a technique starts (pick a full-energy phrase about 16 bars before you would mix out).
  - `mixIn`: where CDJ 2 starts for most techniques (usually the intro, bar 0).
  - `drop`: where CDJ 2 is cued for **T5 Loop roll into hard cut** (the first downbeat of a drop).
  - `kickIntro`: a kick-only bar for **L5 Looped kick bridge**.

Tracks at the same BPM mix cleanly. If they differ, CDJ 2 is sped up or slowed down to match CDJ 1, which also shifts its pitch (no Master Tempo yet).

These files are public on GitHub Pages: only add music you're happy to share.
