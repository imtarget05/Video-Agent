"""
Interactive & CLI Video Generator for Video-Agent.
Uses:
- Hugging Face Free Tier (FLUX.1) as default image generator (zero cost).
- Optional fal.ai / Replicate if FAL_KEY / REPLICATE_API_TOKEN are set.
- Real Edge-TTS neural voiceover audio.
- Remotion Ken Burns camera motion + Word-level kinetic subtitles.
"""
import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Add repo root to python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.app.agent.state import VideoProjectState, AspectRatio, PipelineStatus
from backend.app.agent.graph import video_agent_graph
from backend.app.consistency.character_dna import CharacterDNAManager
from backend.app.agent.guardrails import PreflightGuard
from backend.app.providers.image_providers import get_default_image_provider


async def generate_scene_audio(text: str, output_path: str, voice: str = "vi-VN-HoaiMyNeural") -> float:
    """Uses edge-tts to generate high quality speech and returns duration in seconds."""
    import edge_tts
    comm = edge_tts.Communicate(text, voice)
    await comm.save(output_path)

    duration = 4.0
    try:
        res = subprocess.run(["afinfo", output_path], capture_output=True, text=True)
        for line in res.stdout.splitlines():
            if "estimated duration" in line:
                duration = float(line.split(":")[1].strip().split()[0])
                break
    except Exception:
        words = len(text.split())
        duration = max(2.5, round(words * 0.35, 2))

    return duration


def calculate_word_timestamps(text: str, total_duration: float):
    """Calculates evenly distributed word timestamps matching the real audio duration."""
    words = re.findall(r"\S+", text)
    if not words:
        return []
    
    word_dur = total_duration / len(words)
    timestamps = []
    current_time = 0.0

    for w in words:
        start = round(current_time, 2)
        end = round(current_time + word_dur, 2)
        timestamps.append({"word": w.upper(), "start": start, "end": end})
        current_time = end

    return timestamps


def build_scene_visual_prompt(topic: str, scene_title: str, scene_text: str) -> str:
    """Formulates a photorealistic English prompt for image generator based on scene context."""
    if "Hook" in scene_title or "1" in scene_title:
        return (
            f"Cinematic close-up portrait of young Vietnamese entrepreneur looking amazed at futuristic AI technology, "
            f"subject related to '{topic}', dramatic neon lighting, depth of field, 8k resolution, photorealistic"
        )
    elif "Value" in scene_title or "Core" in scene_title or "2" in scene_title:
        return (
            f"High-tech futuristic digital command center showing glowing AI workflows, floating holographic data graphs, "
            f"automation technology for '{topic}', cybernetic aesthetics, cinematic lighting, 8k photorealistic"
        )
    else:
        return (
            f"Inspiring modern creative studio setting, confident smiling presenter looking at camera, "
            f"subtle glowing notification bell and follow icons in background, warm cinematic lighting, 8k"
        )


async def run_pipeline(prompt: str, aspect_ratio_str: str, voice: str, do_render: bool):
    print("\n" + "=" * 70)
    print(f"🎬 VIDEO-AGENT: GENERATING VIDEO FROM PROMPT")
    print("=" * 70)
    print(f"  📝 Prompt / Chủ đề: {prompt}")
    print(f"  📐 Tỉ lệ khung hình: {aspect_ratio_str}")
    print(f"  🗣 Giọng đọc: {voice}")

    # Initialize Image Provider (Defaults to Hugging Face Free Tier)
    image_provider = get_default_image_provider()
    print(f"  🖼️ Image Provider: {image_provider.provider_name} (Zero-Cost Free Tier)")

    # 1. Preflight Check
    preflight = PreflightGuard.validate_brief(topic=prompt, target_duration_sec=30.0)
    if not preflight.passed:
        print(f"\n❌ Preflight Guardrail Chặn: {preflight.reason}")
        return

    print("  ✓ Preflight safety & budget check: PASSED")

    # 2. Decompose Script via LangGraph
    print("\n[Bước 1] Agent Swarm đang phân rã kịch bản & phân cảnh...")
    aspect_enum = AspectRatio.PORTRAIT_9_16 if aspect_ratio_str == "9:16" else AspectRatio.LANDSCAPE_16_9
    
    char = CharacterDNAManager.create_character(
        character_id="host_creator",
        name="AI Creator",
        prompt_prefix="Professional Vietnamese tech creator, casual stylish attire, clean cinematic lighting",
        seed=2026
    )

    initial_state = VideoProjectState(
        project_id="custom_gen",
        topic=prompt,
        target_duration_sec=20.0,
        aspect_ratio=aspect_enum,
        character_dna=char
    )

    res = video_agent_graph.invoke(initial_state)
    state = VideoProjectState(**res) if isinstance(res, dict) else res

    print(f"  ✓ Đã tạo kịch bản với {len(state.scenes)} phân cảnh.")

    # Prepare directories
    audio_dir = Path("remotion/public/audio")
    images_dir = Path("remotion/public/images")
    audio_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    manifest_scenes = []
    total_video_duration = 0.0
    ken_burns_cycles = ["zoomIn", "panLeft", "zoomOut"]

    # 3. Generate Real AI Images & Audio for each Scene
    print("\n[Bước 2] Đang tạo hình ảnh AI thực tế (HuggingFace/FLUX.1) & giọng đọc AI (Edge-TTS)...")
    for idx, scene in enumerate(state.scenes, start=1):
        print(f"\n  --- Phân cảnh #{idx} [{scene.title}] ---")
        print(f"  🗣 Lời thoại: '{scene.voiceover_text}'")

        # A. Voiceover Audio
        audio_filename = f"speech_scene_{idx}.mp3"
        audio_filepath = str(audio_dir / audio_filename)
        actual_duration = await generate_scene_audio(scene.voiceover_text, audio_filepath, voice=voice)
        scene_duration = round(actual_duration + 0.5, 2)
        total_video_duration += scene_duration
        word_ts = calculate_word_timestamps(scene.voiceover_text, actual_duration)
        print(f"  ✓ Âm thanh TTS: {audio_filename} ({actual_duration:.1f}s)")

        # B. Real AI Generated Image matching the scene
        img_prompt = build_scene_visual_prompt(prompt, scene.title, scene.voiceover_text)
        image_filename = f"scene_{idx}.jpg"
        image_filepath = str(images_dir / image_filename)

        print(f"  🎨 Generating AI Image: {img_prompt[:65]}...")
        img_w = 720 if aspect_ratio_str == "9:16" else 1280
        img_h = 1280 if aspect_ratio_str == "9:16" else 720
        image_provider.generate_image(img_prompt, image_filepath, width=img_w, height=img_h, seed=2026 + idx)
        print(f"  ✓ Ảnh AI hoàn thành: images/{image_filename}")

        # C. Assign Ken Burns Motion
        motion = ken_burns_cycles[(idx - 1) % len(ken_burns_cycles)]

        manifest_scenes.append({
            "sceneId": idx,
            "title": scene.title,
            "durationSec": scene_duration,
            "imageUrl": f"images/{image_filename}",
            "kenBurnsEffect": motion,
            "audioUrl": f"audio/{audio_filename}",
            "voiceover": scene.voiceover_text,
            "subtitles": word_ts,
            "audioDucking": {
                "musicVolumeNormal": 0.30,
                "musicVolumeDucked": 0.10,
                "duckDurationSec": scene_duration
            }
        })

    # 4. Save Remotion Manifest
    manifest = {
        "projectId": "custom_prompt_video",
        "aspectRatio": aspect_ratio_str,
        "totalDurationSec": total_video_duration,
        "bgMusicUrl": "audio/bg_music.wav",
        "scenes": manifest_scenes
    }

    manifest_path = Path("remotion/render_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"\n[Bước 3] Timeline Manifest đã được lưu: {manifest_path}")
    print(f"  ✓ Tổng thời lượng video: {total_video_duration:.1f} giây")

    # 5. Render Video with Remotion
    composition_name = "Shorts916" if aspect_ratio_str == "9:16" else "Landscape169"

    if do_render:
        print(f"\n[Bước 4] Đang kích hoạt Remotion Render xuất file MP4 ({composition_name})...")
        out_dir = Path(__file__).parent.parent / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r'[^a-zA-Z0-9]', '_', prompt[:20]).strip('_').lower() or "video"
        output_mp4 = out_dir / f"{safe_name}_{aspect_ratio_str.replace(':', '_')}.mp4"

        cmd = [
            "npx", "remotion", "render",
            "src/index.ts",
            composition_name,
            str(output_mp4),
            "--props=./render_manifest.json"
        ]

        print(f"  ▶ Chạy render: {output_mp4}...")
        render_proc = subprocess.run(cmd, cwd="remotion", capture_output=True, text=True)
        
        if render_proc.returncode == 0:
            print(f"\n🎉 RENDER THÀNH CÔNG! File video MP4 sẵn sàng tại:")
            print(f"  👉 {output_mp4.resolve()}")
            # Open video player on macOS
            subprocess.run(["open", str(output_mp4.resolve())])
        else:
            print(f"❌ Render gặp lỗi: {render_proc.stderr}")
    else:
        print("\n💡 Bạn có thể xem trước video trực tiếp trên Remotion Studio tại: http://localhost:3000")


def main():
    parser = argparse.ArgumentParser(description="Video-Agent Prompt-to-Video Generator")
    parser.add_argument("--prompt", type=str, help="Chủ đề hoặc prompt video cần tạo")
    parser.add_argument("--aspect", type=str, default="9:16", choices=["9:16", "16:9"], help="Tỉ lệ khung hình (9:16 hoặc 16:9)")
    parser.add_argument("--voice", type=str, default="vi-VN-HoaiMyNeural", help="Voice TTS (vi-VN-HoaiMyNeural hoặc vi-VN-NamMinhNeural)")
    parser.add_argument("--render", action="store_true", help="Render trực tiếp ra file MP4")

    args = parser.parse_args()

    prompt = args.prompt
    if not prompt:
        print("\n--- 🎬 Cung Cấp Prompt Cho Video-Agent ---")
        prompt = input("Nhập chủ đề / prompt video bạn muốn tạo: ").strip()
        if not prompt:
            prompt = "3 Bước Xây Dựng Kênh TikTok Triệu View Bằng AI"
            print(f"Sử dụng prompt mặc định: '{prompt}'")

        aspect_input = input("Chọn tỉ lệ (1: 9:16 Dọc TikTok/Shorts, 2: 16:9 Ngang) [Mặc định: 1]: ").strip()
        aspect = "16:9" if aspect_input == "2" else "9:16"

        voice_input = input("Chọn giọng đọc (1: Nữ Hoài My, 2: Nam Nam Minh) [Mặc định: 1]: ").strip()
        voice = "vi-VN-NamMinhNeural" if voice_input == "2" else "vi-VN-HoaiMyNeural"

        render_input = input("Bạn có muốn render luôn ra file video MP4 không? (y/n) [Mặc định: y]: ").strip().lower()
        do_render = render_input != "n"
    else:
        aspect = args.aspect
        voice = args.voice
        do_render = args.render

    asyncio.run(run_pipeline(prompt, aspect, voice, do_render))


if __name__ == "__main__":
    main()
