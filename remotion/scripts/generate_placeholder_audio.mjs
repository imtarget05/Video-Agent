#!/usr/bin/env node
// Generate PLACEHOLDER audio for the default demo compositions.
//
// WHY THIS EXISTS
// The default `Shorts916` / `Landscape169` manifests in `src/Root.tsx` reference
// four audio files. None of them ship with this repository, and no third-party
// audio is vendored here because the project has no licence to redistribute it.
// Without them `npm run build` (remotion render) aborts on the first frame with
// a 404 for `public/audio/bg_music.wav` -- the video had never actually rendered.
//
// These files are SYNTHETIC PLACEHOLDERS, generated from scratch with the Node
// standard library. They are not music and they are not speech: the music bed is
// a quiet three-note sine chord, and each "voiceover" is a low hum gated at a
// syllable-ish rate purely so the AudioTrack ducking envelope is audible during
// a demo render.
//
// REPLACE THEM
// Drop real, licensed media into `remotion/public/audio/` using the same file
// names and they will be picked up automatically. The generator never overwrites
// an existing file unless you pass `--force`.
//
// The files are covered by `.gitignore` (`*.wav`), so no binary media is ever
// committed.
//
// Run: node scripts/generate_placeholder_audio.mjs [--force]
import { writeFileSync, mkdirSync, existsSync, statSync } from "node:fs";
import { resolve, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SAMPLE_RATE = 44100;
const CHANNELS = 1;
const BITS_PER_SAMPLE = 16;

// Durations mirror the default manifest in `src/Root.tsx` (17.8s total).
const BG_MUSIC_SEC = 17.8;
const SCENES = [
  { name: "speech_scene_1.wav", durationSec: 5.2 },
  { name: "speech_scene_2.wav", durationSec: 6.8 },
  { name: "speech_scene_3.wav", durationSec: 5.8 },
];

const force = process.argv.includes("--force");
const here = dirname(fileURLToPath(import.meta.url));
const audioDir = resolve(here, "..", "public", "audio");

/** Soft sustained G3/B3/D4 chord, deliberately quiet (music sits at ~0.35 gain). */
function musicSamples(n) {
  const out = new Float64Array(n);
  const partials = [
    { hz: 196.0, gain: 1.0 },
    { hz: 246.94, gain: 0.7 },
    { hz: 293.66, gain: 0.55 },
  ];
  const peak = 0.18;
  for (let i = 0; i < n; i++) {
    const t = i / SAMPLE_RATE;
    let v = 0;
    for (const p of partials) v += p.gain * Math.sin(2 * Math.PI * p.hz * t);
    // 0.25 Hz tremolo so the bed is obviously synthetic rather than a dead tone.
    out[i] = peak * v * (0.9 + 0.1 * Math.sin(2 * Math.PI * 0.25 * t));
  }
  return out;
}

/**
 * Stand-in "voiceover": a 130 Hz hum plus its 2nd harmonic, amplitude-gated at
 * 3.6 Hz so the AudioTrack music-ducking is audible when the scene plays.
 * This is a placeholder tone, NOT speech.
 */
function speechSamples(n) {
  const out = new Float64Array(n);
  const peak = 0.55;
  for (let i = 0; i < n; i++) {
    const t = i / SAMPLE_RATE;
    const carrier =
      Math.sin(2 * Math.PI * 130 * t) + 0.45 * Math.sin(2 * Math.PI * 260 * t);
    // 3.6 Hz gate with ~45% duty cycle and 25 ms edges to avoid clicks.
    const phase = (t * 3.6) % 1;
    const edge = 0.025;
    let gate;
    if (phase < 0.45 - edge) gate = 1;
    else if (phase < 0.45) gate = 1 - (phase - (0.45 - edge)) / edge;
    else gate = 0;
    out[i] = peak * gate * carrier;
  }
  return out;
}

/** Encode mono float samples in [-1, 1] as a 16-bit PCM RIFF/WAVE buffer. */
function encodeWav(samples) {
  const dataBytes = samples.length * 2;
  const buf = Buffer.alloc(44 + dataBytes);
  buf.write("RIFF", 0, "ascii");
  buf.writeUInt32LE(36 + dataBytes, 4);
  buf.write("WAVE", 8, "ascii");
  buf.write("fmt ", 12, "ascii");
  buf.writeUInt32LE(16, 16); // PCM fmt chunk size
  buf.writeUInt16LE(1, 20); // audioFormat = PCM
  buf.writeUInt16LE(CHANNELS, 22);
  buf.writeUInt32LE(SAMPLE_RATE, 24);
  buf.writeUInt32LE((SAMPLE_RATE * CHANNELS * (BITS_PER_SAMPLE / 8)) >>> 0, 28); // byteRate
  buf.writeUInt16LE((CHANNELS * (BITS_PER_SAMPLE / 8)) >>> 0, 32); // blockAlign
  buf.writeUInt16LE(BITS_PER_SAMPLE, 34);
  buf.write("data", 36, "ascii");
  buf.writeUInt32LE(dataBytes, 40);
  for (let i = 0; i < samples.length; i++) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    buf.writeInt16LE(Math.round(clamped * 32767), 44 + i * 2);
  }
  return buf;
}

function emit(fileName, durationSec, samplesFor) {
  const target = join(audioDir, fileName);
  if (existsSync(target) && !force) {
    const bytes = statSync(target).size;
    console.log(`  SKIP  audio/${fileName} (${bytes} bytes already present; pass --force to overwrite)`);
    return false;
  }
  const n = Math.round(durationSec * SAMPLE_RATE);
  const wav = encodeWav(samplesFor(n));
  writeFileSync(target, wav);
  console.log(`  WRITE audio/${fileName}  ${durationSec.toFixed(1)}s  ${wav.length} bytes`);
  return true;
}

console.log("Generating PLACEHOLDER audio (synthetic; replace with licensed media).");
mkdirSync(audioDir, { recursive: true });

const written = [];
if (emit("bg_music.wav", BG_MUSIC_SEC, musicSamples)) written.push("bg_music.wav");
for (const scene of SCENES) {
  if (emit(scene.name, scene.durationSec, speechSamples)) written.push(scene.name);
}

console.log(
  written.length === 0
    ? "All placeholder audio already present; nothing to do."
    : `Done. ${written.length} placeholder file(s) written. These are NOT licensed media.`
);