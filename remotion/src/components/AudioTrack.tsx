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

  if (!bgMusicUrl) {
    return null;
  }

  // Calculate ducked volume when speech is actively present
  const currentVolume = hasSpeech
    ? duckingConfig.musicVolumeDucked
    : duckingConfig.musicVolumeNormal;

  return (
    <Audio
      src={bgMusicUrl}
      volume={(f) => currentVolume}
    />
  );
};
