#!/usr/bin/env node
// Slice B verification: remotion-only static checks (TDD gate).
// Run: node scripts/check_sliceB.mjs  (cwd = remotion/ OR repo root)
import { readFileSync, existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url)); // remotion/scripts
const remotionRoot = resolve(here, "..");
const src = (p) => resolve(remotionRoot, p);

let failures = [];
function check(name, cond, hint) {
  if (cond) {
    console.log(`PASS: ${name}`);
  } else {
    console.log(`FAIL: ${name} -- ${hint}`);
    failures.push(name);
  }
}
function read(p) {
  const f = src(p);
  if (!existsSync(f)) return null;
  return readFileSync(f, "utf8");
}

const types = read("src/types.ts");
const subs = read("src/components/DynamicSubtitles.tsx");
const audio = read("src/components/AudioTrack.tsx");
const main = read("src/compositions/MainVideo.tsx");
const brollPath = src("src/components/BRollStitcher.tsx");
const broll = existsSync(brollPath) ? readFileSync(brollPath, "utf8") : null;

// 1. types.ts: bRollUrl + bRollLayout
check("types:bRollUrl", !!types && types.includes("bRollUrl"), "types.ts must declare bRollUrl");
check(
  "types:bRollLayout",
  !!types && types.includes("bRollLayout") && types.includes("overlay") && types.includes("pip"),
  'types.ts must declare bRollLayout: "overlay" | "pip"'
);

// 2. DynamicSubtitles: offset prop + karaoke 3-state
check(
  "subs:sceneOffsetSec",
  !!subs && subs.includes("sceneOffsetSec"),
  "DynamicSubtitles must accept sceneOffsetSec"
);
check(
  "subs:karaoke-3state",
  !!subs &&
    /isPast|isActive|isFuture|past|future/.test(subs) &&
    subs.includes("#FACC15"),
  "DynamicSubtitles must implement karaoke 3-state (past/active/future) with active highlight"
);
check(
  "subs:offset-math",
  !!subs && !subs.includes("frame / fps - sceneOffsetSec"),
  "DynamicSubtitles must NOT use buggy 'frame / fps - sceneOffsetSec' (frame is sequence-local)"
);

// 3. AudioTrack: interpolate envelope + duckDurationSec
check(
  "audio:interpolate-envelope",
  !!audio && audio.includes("interpolate") && audio.includes("duckDurationSec"),
  "AudioTrack must build volume envelope with interpolate() + duckDurationSec"
);
check(
  "audio:volume-callback-uses-frame",
  !!audio && /volume=\{\s*\(f\)\s*=>/.test(audio) && !audio.includes("volume={(f) => currentVolume}"),
  "AudioTrack volume callback must derive from frame f (no static currentVolume passthrough)"
);

// 4. BRollStitcher: overlay + PiP
check("broll:exists", !!broll, "src/components/BRollStitcher.tsx must exist");
check(
  "broll:overlay-pip",
  !!broll && broll.includes("overlay") && broll.includes("pip"),
  "BRollStitcher must support overlay + pip layouts"
);
check(
  "broll:video-or-img",
  !!broll && (broll.includes("<Video") || broll.includes("<Img")),
  "BRollStitcher must render <Video> or <Img>"
);

// 5. MainVideo: computeSceneOffsets + wiring + fade + SceneBody
check(
  "main:computeSceneOffsets",
  !!main && /computeSceneOffsets|sceneOffsets|sceneOffsetSec/.test(main),
  "MainVideo must compute cumulative scene offsets and pass sceneOffsetSec"
);
check(
  "main:audiotrack-wiring",
  !!main && main.includes("AudioTrack"),
  "MainVideo must wire AudioTrack component"
);
check(
  "main:broll-wiring",
  !!main && main.includes("BRollStitcher"),
  "MainVideo must wire BRollStitcher component"
);
check(
  "main:fade",
  !!main && main.includes("FADE_FRAMES") && main.includes("15"),
  "MainVideo must define FADE_FRAMES 15 fade in/out"
);
check(
  "main:scenebody",
  !!main && main.includes("SceneBody"),
  "MainVideo must extract SceneBody component"
);
check(
  "main:subs-offset-pass",
  !!main && /sceneOffsetSec/.test(main),
  "MainVideo must pass sceneOffsetSec to DynamicSubtitles"
);

if (failures.length > 0) {
  console.log(`\n${failures.length} check(s) FAILED`);
  process.exit(1);
}
console.log("\nAll Slice B checks passed.");
