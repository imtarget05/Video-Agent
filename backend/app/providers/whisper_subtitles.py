"""
Whisper subtitle extractor with deterministic offline fallback.
"""
import re
from typing import List, Dict, Any


class WhisperSubtitleExtractor:
    @staticmethod
    def extract(text: str, duration_sec: float = 0.0, word_duration: float = 0.35) -> List[Dict[str, Any]]:
        words = re.findall(r"\w+", text or "", re.UNICODE) or ["silent"]
        if duration_sec and duration_sec > 0:
            word_duration = round(duration_sec / len(words), 2)
        out, t = [], 0.0
        for w in words:
            out.append({"word": w, "start": round(t, 2), "end": round(t + word_duration, 2)})
            t += word_duration
        return out

    def transcribe(self, audio_path: str, fallback_text: str = "", duration_sec: float = 0.0) -> List[Dict[str, Any]]:
        try:
            import whisper  # type: ignore
            model = whisper.load_model("tiny")
            result = model.transcribe(audio_path)
            words = []
            for seg in result.get("segments", []):
                for w in re.findall(r"\w+", seg.get("text", "")):
                    words.append({"word": w, "start": round(seg.get("start", 0.0), 2), "end": round(seg.get("end", 0.0), 2)})
            if words:
                return words
        except Exception:
            pass
        return self.extract(fallback_text or "silent narration", duration_sec=duration_sec)
