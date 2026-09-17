import React from "react";
import { Audio, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { AudioDuckingConfig } from "../types";

interface AudioTrackProps {
  bgMusicUrl?: string;
  duckingConfig?: AudioDuckingConfig;
  hasSpeech?: boolean;
}

export const AudioTrack: React.FC<AudioTrackProps> = ({
  bgMusicUrl,
  duckingConfig = {
    musicVolumeNormal: 0.35,
    musicVolumeDucked: 0.10,
    duckDurationSec: 5.0,
  },
  hasSpeech = true,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  void frame;

  if (!bgMusicUrl) {
    return null;
  }

  const { musicVolumeNormal, musicVolumeDucked, duckDurationSec } = duckingConfig;
  // Smooth ramp (up to 0.5s) derived from duckDurationSec so the music dips
  // under speech instead of hard-cutting between two static levels.
  const rampFrames = Math.max(
    1,
    Math.round(Math.min(duckDurationSec, 0.5) * fps)
  );

  return (
    <Audio
      src={bgMusicUrl}
      volume={(f) =>
        hasSpeech
          ? interpolate(f, [0, rampFrames], [musicVolumeNormal, musicVolumeDucked], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            })
          : musicVolumeNormal
      }
    />
  );
};
