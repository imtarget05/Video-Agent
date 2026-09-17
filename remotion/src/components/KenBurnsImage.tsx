import React from "react";
import { Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { KenBurnsMotion } from "../types";

interface KenBurnsImageProps {
  imageSrc: string;
  durationFrames: number;
  motion?: KenBurnsMotion;
}

export const KenBurnsImage: React.FC<KenBurnsImageProps> = ({
  imageSrc,
  durationFrames,
  motion = "zoomIn",
}) => {
  const frame = useCurrentFrame();

  let scale = 1.0;
  let translateX = 0;
  let translateY = 0;

  if (motion === "zoomIn") {
    scale = interpolate(frame, [0, durationFrames], [1.05, 1.22], {
      extrapolateRight: "clamp",
    });
    translateY = interpolate(frame, [0, durationFrames], [0, -15], {
      extrapolateRight: "clamp",
    });
  } else if (motion === "zoomOut") {
    scale = interpolate(frame, [0, durationFrames], [1.22, 1.05], {
      extrapolateRight: "clamp",
    });
    translateY = interpolate(frame, [0, durationFrames], [-15, 0], {
      extrapolateRight: "clamp",
    });
  } else if (motion === "panLeft") {
    scale = 1.15;
    translateX = interpolate(frame, [0, durationFrames], [40, -40], {
      extrapolateRight: "clamp",
    });
  } else if (motion === "panRight") {
    scale = 1.15;
    translateX = interpolate(frame, [0, durationFrames], [-40, 40], {
      extrapolateRight: "clamp",
    });
  }

  // Support local static files or full remote URLs
  const resolvedSrc = imageSrc.startsWith("http") ? imageSrc : staticFile(imageSrc);

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        overflow: "hidden",
        position: "absolute",
        top: 0,
        left: 0,
      }}
    >
      <Img
        src={resolvedSrc}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `scale(${scale}) translate(${translateX}px, ${translateY}px)`,
          filter: "brightness(0.92) contrast(1.05)",
        }}
      />
    </div>
  );
};
