"""Local motion slideshow and original synthesized soundtrack. No AI or network."""
import base64
import hashlib
import io
import json
import os
import re
import threading
import math
import subprocess
import wave
from array import array
from pathlib import Path

import storage

RENDER_LOCK = threading.Lock()
OUTPUT = Path(__file__).resolve().parent / "data" / "videos"


def scenes_for(post, supplied=None):
    scenes = supplied or post.get("slides")
    if not scenes:
        scenes = [s.strip() for s in re.split(r"\n\s*\n", post.get("text", "")) if s.strip()]
    if not scenes or not 3 <= len(scenes) <= 10:
        raise ValueError("Video needs 3–10 scenes. Supply scene text or use an Instagram carousel.")
    if any(not isinstance(s, str) or not s.strip() or len(s) > 450 for s in scenes):
        raise ValueError("Each scene must contain 1–450 characters. Shorten long paragraphs first.")
    return [s.strip() for s in scenes]


def fingerprint(post, scenes, seconds, music=True):
    return hashlib.sha256(json.dumps([post.get("image"), scenes, seconds, music, "sharp-v4"],
                                    ensure_ascii=False).encode()).hexdigest()


def start(post, scenes, seconds, music=True):
    if post.get("status") not in ("approved", "scheduled", "ready_to_publish", "feedback_recorded"):
        raise ValueError("Finish and approve the content before creating a video.")
    scenes = scenes_for(post, scenes)
    key = fingerprint(post, scenes, seconds, music)
    for saved in storage.listing("video"):
        if saved["post_id"] == post["id"] and saved["fingerprint"] == key:
            if saved["status"] == "rendering" or (saved["status"] == "ready" and output_path(saved["id"]).exists()):
                return saved, False
    if not RENDER_LOCK.acquire(blocking=False):
        raise ValueError("Another video is rendering. Wait for it to finish before starting another.")
    try:
        item = storage.save("video", dict(post_id=post["id"], status="rendering", scenes=scenes,
            seconds_per_scene=seconds, fingerprint=key, width=720, height=1280, fps=15,
            audio="original_synth_music" if music else "silent", style="sharp-v4",
            renderer="local_ffmpeg", created_at=storage.now()))
        storage.audit(post["id"], "video", {"event": "render_started", "video_id": item["id"],
            "reason": "Reuse existing content and image; local slideshow with burned-in scene captions. No AI calls."})
        return item, True
    except Exception:
        RENDER_LOCK.release()
        raise


def output_path(id, suffix=".mp4"):
    if not re.fullmatch(r"[0-9a-f-]{36}", id):
        raise ValueError("Invalid video ID")
    return OUTPUT / (id + suffix)


def font(size, bold=False):
    from PIL import ImageFont
    candidates = [Path(os.getenv("WINDIR", "C:/Windows")) / "Fonts" / ("arialbd.ttf" if bold else "arial.ttf"),
                  Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def caption_lines(draw, text, face, width):
    lines = []
    for paragraph in text.splitlines():
        line = ""
        for word in paragraph.split():
            if draw.textlength(word, font=face) > width:
                raise ValueError("A caption word is too wide. Add spaces or shorten it.")
            candidate = (line + " " + word).strip()
            if line and draw.textlength(candidate, font=face) > width:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
    return lines


def scene_card(text, index, total, image_data=None, brand_name="CreatorOS"):
    from PIL import Image, ImageDraw, ImageOps, ImageFilter
    palettes = [("#b6a3ff", (37, 22, 67)), ("#87e4d3", (13, 48, 52)), ("#ffb184", (63, 32, 39))]
    accent, shade = palettes[index % len(palettes)]
    gradient = Image.new("RGB", (1, 1280))
    gradient.putdata([tuple(int(11+(c-11)*(1-y/1280)) for c in shade) for y in range(1280)])
    canvas = gradient.resize((720, 1280))
    glow = Image.new("RGBA", canvas.size)
    gd = ImageDraw.Draw(glow)
    gd.ellipse((380, -140, 950, 430), fill=accent+"40")
    canvas = Image.alpha_composite(canvas.convert("RGBA"), glow.filter(ImageFilter.GaussianBlur(90))).convert("RGB")
    if image_data and image_data.startswith("data:image/"):
        raw = base64.b64decode(image_data.split(",", 1)[1], validate=True)
        if len(raw) > 30_000_000:
            raise ValueError("Image exceeds the 30 MB local video limit")
        with Image.open(io.BytesIO(raw)) as source:
            visual = ImageOps.fit(source.convert("RGB"), (600, 390))
            mask = Image.new("L", visual.size)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, 599, 389), radius=24, fill=255)
            canvas.paste(visual, (60, 740), mask)
    draw = ImageDraw.Draw(canvas)
    brand = brand_name[:32]
    draw.rounded_rectangle((50, 80, 670, 140), radius=30, outline="#777187", width=1)
    draw.text((76, 96), brand, font=font(23, True), fill="#f9f5ff")
    draw.text((550, 98), f"{index+1:02d} / {total:02d}", font=font(21), fill=accent)
    phase = "THE IDEA" if index == 0 else "YOUR NEXT MOVE" if index == total-1 else "MAKE IT HAPPEN"
    draw.text((60, 205), phase, font=font(20, True), fill=accent)
    draw.rounded_rectangle((60, 247, 140, 254), radius=3, fill=accent)
    for size in (66, 58, 50, 42, 34, 28):
        face = font(size, True)
        try:
            lines = caption_lines(draw, text, face, 590)
        except ValueError:
            # A long brand/tool name may fit at the next smaller font size.
            # Never abort on the first size or truncate the customer's caption.
            continue
        if len(lines) * (size + 12) <= 410:
            break
    else:
        raise ValueError("Scene caption does not fit. Shorten it before rendering.")
    y = 300
    for line in lines:
        draw.text((60, y), line, font=face, fill="#fffaff")
        y += size + 12
    if not image_data or not image_data.startswith("data:image/"):
        draw.rounded_rectangle((60, 760, 660, 1100), radius=28, outline=accent, width=2)
        draw.text((100, 800), f"{index+1:02d}", font=font(180, True), fill=accent)
        draw.text((110, 1020), "One idea. Put it into action.", font=font(25), fill="#e4dcec")
    for i in range(total):
        x = 60 + i * (600 / total)
        draw.rounded_rectangle((x, 1172, x+600/total-10, 1178), radius=3,
                               fill=accent if i <= index else "#51495e")
    draw.text((60, 1210), "SAVE THE IDEA. TRY IT NEXT.", font=font(18, True), fill="#cec3dc")
    return canvas


def soundtrack(path, seconds):
    """Compose an original 80 BPM major-key ambient track; no samples or percussion."""
    rate, beat = 22050, 60/80
    chords = [(130.813, 164.814, 195.998, 246.942),
              (174.614, 220, 261.626, 329.628),
              (195.998, 246.942, 293.665, 329.628),
              (130.813, 195.998, 261.626, 293.665)]
    samples = array("h")
    for i in range(int(seconds*rate)):
        t = i/rate
        chord_index = int(t/(beat*4)) % len(chords)
        chord = chords[chord_index]
        previous = chords[(chord_index-1) % len(chords)]
        blend = min(1, (t % (beat*4))/.6)
        pad = (sum(math.sin(2*math.pi*f*t) for f in chord)*blend +
               sum(math.sin(2*math.pi*f*t) for f in previous)*(1-blend)) / 4 * .13
        note = chord[int(t/beat) % 4]*2
        local = t % beat
        envelope_note = min(1, local/.025)*math.exp(-3.8*local)
        bell = (math.sin(2*math.pi*note*local)+.15*math.sin(2*math.pi*note*2*local))*.07*envelope_note
        bass = math.sin(2*math.pi*chord[0]/2*t)*.035
        envelope = min(1, t/2, max(0, (seconds-t)/3))
        value = (pad+bell+bass)*envelope
        samples.append(int(max(-1, min(1, value))*32767))
    import sys
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 2, rate, len(samples), "NONE", "not compressed"))
        output.writeframes(samples.tobytes())


def timestamp(seconds):
    milliseconds = int(seconds * 1000)
    return f"{milliseconds//3600000:02}:{milliseconds//60000%60:02}:{milliseconds//1000%60:02}.{milliseconds%1000:03}"


def render(item, post):
    temporary = output_path(item["id"], ".partial.mp4")
    music_path = output_path(item["id"], ".music.wav")
    mux_path = output_path(item["id"], ".mux.mp4")
    try:
        import imageio_ffmpeg
        OUTPUT.mkdir(parents=True, exist_ok=True)
        writer = imageio_ffmpeg.write_frames(str(temporary), (720, 1280), fps=item["fps"],
            codec="libx264", pix_fmt_in="rgb24", pix_fmt_out="yuv420p",
            output_params=["-movflags", "+faststart", "-preset", "veryfast", "-crf", "24"],
            macro_block_size=1, ffmpeg_log_level="error")
        writer.send(None)
        try:
            frames = item["seconds_per_scene"] * item["fps"]
            preview_frames = []
            frame_dir = OUTPUT / item["id"]
            frame_dir.mkdir(exist_ok=True)
            previous = None
            brand = storage.get(post.get("brand_id", "")) or {}
            for index, text in enumerate(item["scenes"]):
                card = scene_card(text, index, len(item["scenes"]), post.get("image"), brand.get("name", "CreatorOS"))
                from PIL import Image
                for frame in range(frames):
                    # Gentle camera push, crossfade transitions and a continuous timeline.
                    scale = 1 + .022 * frame / max(1, frames-1)
                    enlarged = card.resize((int(720*scale), int(1280*scale)), Image.Resampling.BICUBIC)
                    x, y = (enlarged.width-720)//2, (enlarged.height-1280)//2
                    current = enlarged.crop((x, y, x+720, y+1280))
                    if previous is not None and frame < 6:
                        current = Image.blend(previous, current, (frame+1)/6)
                    from PIL import ImageDraw
                    progress = (index + (frame+1)/frames)/len(item["scenes"])
                    ImageDraw.Draw(current).rectangle((0, 1274, int(720*progress), 1279), fill="#b6a3ff")
                    if frame % 5 == 0:
                        current.save(frame_dir / f"{len(preview_frames):03d}.jpg", quality=92, subsampling=0)
                        preview_frames.append(current.resize((240, 426), Image.Resampling.LANCZOS))
                    writer.send(current.tobytes())
                previous = current
        finally:
            writer.close()
        if not temporary.exists() or temporary.stat().st_size < 1000:
            raise ValueError("FFmpeg did not produce a valid video file")
        if item.get("audio") == "original_synth_music":
            duration = len(item["scenes"]) * item["seconds_per_scene"]
            soundtrack(music_path, duration)
            result = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(temporary), "-i", str(music_path), "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(mux_path)],
                capture_output=True, timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            if result.returncode or not mux_path.exists():
                raise ValueError("FFmpeg could not attach the background music")
            mux_path.replace(output_path(item["id"]))
            temporary.unlink()
        else:
            temporary.replace(output_path(item["id"]))
        from PIL import Image
        sheet = Image.new("RGB", (240*4, 426*math.ceil(len(preview_frames)/4)))
        for number, picture in enumerate(preview_frames):
            sheet.paste(picture, ((number%4)*240, (number//4)*426))
        sheet.save(output_path(item["id"], ".preview.webp"), quality=85)
        with Image.open(frame_dir / "000.jpg") as first_frame:
            first_frame.save(output_path(item["id"], ".poster.jpg"), quality=92)
        subtitles = "WEBVTT\n\n" + "\n\n".join(
            f"{timestamp(i * item['seconds_per_scene'])} --> {timestamp((i+1) * item['seconds_per_scene'])}\n{text.replace('-->', '→')}"
            for i, text in enumerate(item["scenes"]))
        output_path(item["id"], ".vtt").write_text(subtitles, encoding="utf-8")
        saved = storage.save("video", dict(item, status="ready", duration_seconds=len(item["scenes"]) * item["seconds_per_scene"],
            preview_kind="frames", frame_url=f"/videos/{item['id']}/frames/",
            preview_fps=3, preview_frames=len(preview_frames), preview_width=240, preview_height=426,
            preview_url=f"/videos/{item['id']}/preview", poster_url=f"/videos/{item['id']}/poster",
            completed_at=storage.now(), url=f"/videos/{item['id']}/file", captions_url=f"/videos/{item['id']}/captions"), item["id"])
        storage.audit(post["id"], "video", {"event": "render_complete", "video_id": item["id"],
            "duration_seconds": saved["duration_seconds"], "audio": item.get("audio"),
            "reason": "Motion slideshow with original synthesized music when enabled; no publishing or AI calls."})
    except Exception as exc:
        message = str(exc) if isinstance(exc, ValueError) else f"{type(exc).__name__}: local renderer failed; check FFmpeg installation"
        storage.save("video", dict(item, status="failed", error=message), item["id"])
        storage.audit(post["id"], "video", {"event": "render_failed", "video_id": item["id"], "reason": message})
        if temporary.exists():
            temporary.unlink()
    finally:
        for scratch in (music_path, mux_path):
            if scratch.exists():
                scratch.unlink()
        RENDER_LOCK.release()
