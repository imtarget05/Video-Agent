import React from "react";
import { Img, staticFile, Video } from "remotion";
import { BRollLayout } from "../types";

interface BRollStitcherProps {
  bRollUrl?: string;
  layout?: BRollLayout;
  isPortrait?: boolean;
}

export const BRollStitcher: React.FC<BRollStitcherProps> = ({
  bRollUrl,
  layout = "overlay",
  isPortrait = true,
}) => {
  if (!bRollUrl) {
    return null;
  }

  const resolvedSrc = bRollUrl.startsWith("http") ? bRollUrl : staticFile(bRollUrl);
  const isVideo = resolvedSrc.endsWith(".mp4") || resolvedSrc.endsWith(".webm");

  if (layout === "pip") {
    // Picture-in-picture: bottom-right corner card above subtitles layer
    return (
      <div
        style={{
          position: "absolute",
          right: isPortrait ? 40 : 60,
          bottom: isPortrait ? 420 : 160,
          width: isPortrait ? "42%" : "28%",
          aspectRatio: "16 / 9",
          borderRadius: 24,
          overflow: "hidden",
          border: "3px solid rgba(255,255,255,0.85)",
          boxShadow: "0 12px 40px rgba(0,0,0,0.55)",
          zIndex: 40,
        }}
      >
        {isVideo ? (
          <Video
            src={resolvedSrc}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        ) : (
          <Img
            src={resolvedSrc}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        )}
      </div>
    );
  }

  // Default "overlay": full-cover secondary take above the base visual
  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        width: "100%",
        height: "100%",
        zIndex: 30,
      }}
    >
      {isVideo ? (
        <Video
          src={resolvedSrc}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      ) : (
        <Img
          src={resolvedSrc}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      )}
    </div>
  );
};
