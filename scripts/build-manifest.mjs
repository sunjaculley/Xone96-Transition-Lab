#!/usr/bin/env node
// Builds tracks/manifest.json from the audio files in tracks/.
// Runs in the GitHub Pages workflow on every push, so dropping a file into tracks/ is all it takes.
// Optional: a JSON file with the same base name next to a track overrides any field, e.g.
//   tracks/My Artist - My Track.mp3
//   tracks/My Artist - My Track.json  -> {"bpm":128,"firstBeat":0.42,"key":"8A","cues":{"mixOut":96,"mixIn":0,"drop":32,"kickIntro":0}}
// Names like "8A - 128 - Title - Artist.mp3" set key and BPM from the name; a sidecar can also fix title/artist.
// Usage: node scripts/build-manifest.mjs [siteRoot]
import { readdirSync, readFileSync, writeFileSync, existsSync, statSync } from 'node:fs';
import { join, extname, basename } from 'node:path';

const root = process.argv[2] || '.';
const dir = join(root, 'tracks');
const AUDIO = new Set(['.mp3', '.m4a', '.aac', '.wav', '.ogg', '.oga', '.opus', '.flac', '.webm']);
const tracks = [];

if (existsSync(dir)) {
  for (const f of readdirSync(dir).sort((a, b) => a.localeCompare(b))) {
    const ext = extname(f).toLowerCase();
    if (!AUDIO.has(ext) || f.startsWith('.')) continue;
    const base = basename(f, extname(f));
    // "8A - 128 - Title - Artist" (rekordbox-style key and BPM prefix) fills key, bpm, title and artist.
    // "Artist - Title" fills artist and title; anything else becomes the title.
    const k = base.match(/^(\d{1,2}[AB])\s+[-–]\s+(\d{2,3}(?:\.\d+)?)\s+[-–]\s+(.+?)\s+[-–]\s+(.+)$/i);
    const m = k ? null : base.match(/^(.+?)\s+[-–]\s+(.+)$/);
    const entry = {
      file: 'tracks/' + encodeURIComponent(f).replace(/%2F/g, '/'),
      title: (k ? k[3] : m ? m[2] : base).replace(/[_]+/g, ' ').trim(),
      artist: k ? k[4].trim() : m ? m[1].trim() : '',
      bytes: statSync(join(dir, f)).size,
    };
    if (k) { entry.key = k[1].toUpperCase(); entry.bpm = +k[2]; }
    const side = join(dir, base + '.json');
    if (existsSync(side)) {
      try {
        Object.assign(entry, JSON.parse(readFileSync(side, 'utf8')));
      } catch (e) {
        console.error(`warning: ${base}.json is not valid JSON (${e.message}); ignored`);
      }
    }
    if (entry.bytes > 25 * 1024 * 1024) console.error(`warning: ${f} is over 25 MB; it will load slowly`);
    tracks.push(entry);
  }
}

writeFileSync(join(dir, 'manifest.json'), JSON.stringify({ generated: new Date().toISOString(), tracks }, null, 2) + '\n');
console.log(`tracks/manifest.json: ${tracks.length} track(s)`);
for (const t of tracks) console.log(`  - ${t.artist ? t.artist + ' – ' : ''}${t.title}${t.bpm ? ` (${t.bpm} BPM)` : ''}`);
