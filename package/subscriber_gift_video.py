#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Subscriber Gift Video Generator (Bulk)
========================================
अपने सब्सक्राइबर्स को गिफ्ट के तौर पर भेजने के लिए — उनके चैनल के नाम से
प्रोफाइल फोटो + नाम अपने-आप निकालकर, एक प्रीमियम-लुक "सब्सक्राइबर माइलस्टोन"
वीडियो बनाता है। एक चैनल के लिए भी चला सकते हैं, या CSV लिस्ट देकर एक साथ
सैकड़ों वीडियो (bulk / unlimited) भी बना सकते हैं।

आउटपुट डिफ़ॉल्ट लोकेशन (चाहें तो --outdir से बदल सकते हैं):
    D:\\ALL AUTOMATION FILE\\youtube rendr

फाइल नाम पैटर्न (डिफ़ॉल्ट, --name-pattern से बदल सकते हैं):
    <ChannelName> - <count> SUBSCRIBER - GIFT VIDEO.mp4


इस्तेमाल
--------
    # एक चैनल के लिए
    python subscriber_gift_video.py --channel "@channelhandle" --target 2000

    # चैनल का नाम दिया (handle नहीं पता) — नाम से ढूंढ लेगा
    python subscriber_gift_video.py --channel "Rahul Gaming" --target 5000

    # एक साथ बहुत सारे (bulk) — CSV फाइल दें: channel,target[,message]
    python subscriber_gift_video.py --batch list.csv

    # फोल्डर/फाइलनेम कस्टम
    python subscriber_gift_video.py --channel "@xyz" --target 1000 ^
        --outdir "D:\\ALL AUTOMATION FILE\\youtube rendr" ^
        --name-pattern "{name} - {count} SUBSCRIBER - GIFT VIDEO"

list.csv का उदाहरण:
    channel,target,message
    @rahulgaming,2000,Thanks for being part of the journey!
    Priya Vlogs,5000,

Requirements
------------
    pip install yt-dlp pillow numpy requests
    ffmpeg सिस्टम PATH में होना चाहिए
    (assets/ फोल्डर — फॉन्ट्स — इस स्क्रिप्ट के साथ उसी फोल्डर में रखें)
"""

import argparse
import csv
import math
import os
import random
import re
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path, PureWindowsPath

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

# --------------------------------------------------------------------------
# कॉन्फ़िग / DESIGN TOKENS
# --------------------------------------------------------------------------
W, H = 1080, 1920         # प्रीमियम फुल-HD वर्टिकल
FPS = 30
MILESTONES = [1000, 2000, 3000, 4000, 5000, 10000]

DEFAULT_OUTDIR = r"D:\ALL AUTOMATION FILE\youtube rendr"
DEFAULT_NAME_PATTERN = "{name} - {count} SUBSCRIBER - GIFT VIDEO"

COLORS = {
    "bg_top":    (8, 10, 22),
    "bg_bottom": (20, 16, 40),
    "gold":      (255, 200, 87),
    "gold_soft": (255, 224, 150),
    "coral":     (255, 99, 132),
    "violet":    (154, 111, 255),
    "teal":      (56, 209, 176),
    "white":     (250, 250, 255),
    "muted":     (176, 176, 200),
}
CONFETTI_COLORS = [COLORS["gold"], COLORS["coral"], COLORS["teal"], COLORS["violet"], COLORS["white"]]

ASSET_DIR = Path(__file__).resolve().parent / "assets"
FONT_DISPLAY = ASSET_DIR / "Baloo2-Variable.ttf"     # बड़ा काउंटर नंबर
FONT_TITLE = ASSET_DIR / "Poppins-SemiBold.ttf"      # चैनल का नाम
FONT_LABEL = ASSET_DIR / "Poppins-Regular.ttf"       # लेबल / मैसेज

random.seed()


# --------------------------------------------------------------------------
# फाइलनेम / फोल्डर helpers
# --------------------------------------------------------------------------
def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "", name)   # Windows में मना किए गए characters
    name = re.sub(r"\s+", " ", name).strip()
    return name


def build_output_path(outdir: str, name_pattern: str, channel_name: str, count: int) -> Path:
    fname = name_pattern.format(name=channel_name, count=f"{count:,}")
    fname = sanitize_filename(fname) + ".mp4"
    out_dir = Path(outdir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / fname


# --------------------------------------------------------------------------
# 1) चैनल की जानकारी (नाम + प्रोफाइल फोटो) निकालना — handle, URL या सिर्फ नाम
# --------------------------------------------------------------------------
def resolve_channel_url(query: str) -> str:
    query = query.strip()
    if query.startswith("http"):
        return query
    if query.startswith("@"):
        return f"https://www.youtube.com/{query}"
    # सिर्फ नाम दिया है -> सर्च करके सबसे ऊपर वाले चैनल का URL निकालो
    import yt_dlp
    ydl_opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch3:{query}", download=False)
    for entry in info.get("entries", []):
        ch_url = entry.get("channel_url") or entry.get("uploader_url")
        if ch_url:
            return ch_url
    raise RuntimeError(f"'{query}' नाम से कोई चैनल नहीं मिला — कृपया @handle या पूरा चैनल URL दें।")


def fetch_channel_info(query: str):
    """नाम / handle / URL — किसी से भी चैनल का नाम + सबसे बड़ी प्रोफाइल-फोटो का URL निकालता है."""
    import yt_dlp

    url = resolve_channel_url(query)
    ydl_opts = {
        "quiet": True, "no_warnings": True, "skip_download": True,
        "extract_flat": True, "playlist_items": "0",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    name = info.get("channel") or info.get("uploader") or info.get("title") or query
    thumbs = info.get("thumbnails") or []
    avatar_url = None
    if thumbs:
        thumbs_sorted = sorted(thumbs, key=lambda t: (t.get("width") or 0) * (t.get("height") or 0))
        avatar_url = thumbs_sorted[-1]["url"]
    return name, avatar_url


def download_image(url: str, dest_path: Path):
    import requests
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    dest_path.write_bytes(r.content)
    return dest_path


# --------------------------------------------------------------------------
# 2) फॉन्ट helpers
# --------------------------------------------------------------------------
def load_font(path: Path, size: int, variation: str = None):
    font = ImageFont.truetype(str(path), size)
    if variation:
        try:
            font.set_variation_by_name(variation)
        except Exception:
            pass
    return font


# --------------------------------------------------------------------------
# 3) एवतार (गोल प्रोफाइल फोटो + प्रीमियम ग्लो रिंग)
# --------------------------------------------------------------------------
def make_circular_avatar(src_path: Path, size: int) -> Image.Image:
    img = Image.open(src_path).convert("RGB")
    img = ImageOps.fit(img, (size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def placeholder_avatar(size: int, initial: str) -> Image.Image:
    img = Image.new("RGB", (size, size), (60, 50, 90))
    d = ImageDraw.Draw(img)
    font = load_font(FONT_DISPLAY, int(size * 0.45), "Bold")
    bbox = d.textbbox((0, 0), initial, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]), initial,
           font=font, fill=COLORS["gold_soft"])
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


# --------------------------------------------------------------------------
# 4) प्रीमियम बैकग्राउंड (ग्रेडिएंट + सॉफ्ट बोकेह लाइट्स) — एक बार बनाकर कैश
# --------------------------------------------------------------------------
def make_background(w, h) -> Image.Image:
    bg = Image.new("RGB", (w, h))
    top, bottom = COLORS["bg_top"], COLORS["bg_bottom"]
    px = bg.load()
    for y in range(h):
        t = y / (h - 1)
        row = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(w):
            px[x, y] = row

    bokeh_layer = Image.new("RGB", (w, h), (0, 0, 0))
    bd = ImageDraw.Draw(bokeh_layer)
    bokeh_spots = [
        (int(w * 0.15), int(h * 0.18), 220, COLORS["violet"]),
        (int(w * 0.85), int(h * 0.30), 260, COLORS["coral"]),
        (int(w * 0.20), int(h * 0.80), 240, COLORS["teal"]),
        (int(w * 0.80), int(h * 0.88), 200, COLORS["gold"]),
    ]
    for (cx, cy, r, col) in bokeh_spots:
        bd.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col)
    bokeh_layer = bokeh_layer.filter(ImageFilter.GaussianBlur(140))
    bg = Image.blend(bg, bokeh_layer, 0.35)

    vign = Image.new("L", (w, h), 0)
    ImageDraw.Draw(vign).ellipse((-w * 0.25, -h * 0.15, w * 1.25, h * 1.05), fill=70)
    vign = vign.filter(ImageFilter.GaussianBlur(180))
    bg = Image.composite(bg, Image.new("RGB", (w, h), (0, 0, 0)), vign)
    return bg


# --------------------------------------------------------------------------
# 5) कंफेटी + फायरवर्क-रे पार्टिकल सिस्टम
# --------------------------------------------------------------------------
class Confetti:
    __slots__ = ("x", "y", "vx", "vy", "size", "color", "rot", "vrot", "shape", "life", "age")

    def __init__(self, cx, cy, big=False):
        angle = random.uniform(-math.pi * 0.9, -math.pi * 0.1)
        speed = random.uniform(9, 22) if big else random.uniform(6, 15)
        self.x = cx + random.uniform(-50, 50)
        self.y = cy + random.uniform(-10, 10)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.size = random.uniform(7, 16)
        self.color = random.choice(CONFETTI_COLORS)
        self.rot = random.uniform(0, 360)
        self.vrot = random.uniform(-16, 16)
        self.shape = random.choice(["rect", "circle"])
        self.life = random.uniform(55, 85)
        self.age = 0

    def step(self):
        self.vy += 0.55
        self.vx *= 0.99
        self.x += self.vx
        self.y += self.vy
        self.rot += self.vrot
        self.age += 1

    def alive(self):
        return self.age < self.life

    def draw(self, draw: ImageDraw.ImageDraw):
        t = self.age / self.life
        alpha = max(0, 1 - t)
        color = tuple(int(c) for c in self.color)
        s = self.size
        if self.shape == "rect":
            pts = []
            for (dx, dy) in [(-s, -s * 0.4), (s, -s * 0.4), (s, s * 0.4), (-s, s * 0.4)]:
                rad = math.radians(self.rot)
                rx = dx * math.cos(rad) - dy * math.sin(rad)
                ry = dx * math.sin(rad) + dy * math.cos(rad)
                pts.append((self.x + rx, self.y + ry))
            draw.polygon(pts, fill=color + (int(255 * alpha),))
        else:
            draw.ellipse((self.x - s / 2, self.y - s / 2, self.x + s / 2, self.y + s / 2),
                         fill=color + (int(255 * alpha),))


class RayBurst:
    """पल भर की चमकती किरणों वाली फ्लैश — प्रीमियम/फायरवर्क फील के लिए."""
    __slots__ = ("cx", "cy", "age", "life", "n")

    def __init__(self, cx, cy):
        self.cx, self.cy, self.age, self.life, self.n = cx, cy, 0, 22, 16

    def step(self):
        self.age += 1

    def alive(self):
        return self.age < self.life

    def draw(self, draw):
        t = self.age / self.life
        alpha = max(0, 1 - t)
        length = 40 + t * 260
        for i in range(self.n):
            ang = (2 * math.pi / self.n) * i
            x2 = self.cx + math.cos(ang) * length
            y2 = self.cy + math.sin(ang) * length
            draw.line((self.cx, self.cy, x2, y2), fill=COLORS["gold_soft"] + (int(180 * alpha),),
                      width=max(1, int(5 * alpha)))


class EffectSystem:
    def __init__(self):
        self.particles = []
        self.rays = []

    def burst(self, cx, cy, count=140, big=False):
        self.particles.extend(Confetti(cx, cy, big) for _ in range(count))
        self.rays.append(RayBurst(cx, cy))

    def step_and_draw(self, base_img: Image.Image):
        overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for r in self.rays:
            r.step()
            if r.alive():
                r.draw(draw)
        self.rays = [r for r in self.rays if r.alive()]

        alive = []
        for p in self.particles:
            p.step()
            if p.alive():
                p.draw(draw)
                alive.append(p)
        self.particles = alive
        base_img.paste(overlay, (0, 0), overlay)


# --------------------------------------------------------------------------
# 6) टेक्स्ट helper
# --------------------------------------------------------------------------
def draw_center_text(draw, cx, y, text, font, fill, tracking=0):
    if tracking:
        widths = [draw.textbbox((0, 0), ch, font=font)[2] for ch in text]
        total = sum(widths) + tracking * (len(text) - 1)
        x = cx - total / 2
        for ch, w in zip(text, widths):
            draw.text((x, y), ch, font=font, fill=fill)
            x += w + tracking
    else:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        draw.text((cx - tw / 2 - bbox[0], y), text, font=font, fill=fill)


def ease_out_cubic(t):
    return 1 - (1 - t) ** 3


# --------------------------------------------------------------------------
# 7) एक फ्रेम रेंडर करना
# --------------------------------------------------------------------------
AVATAR_SIZE = 440
RING_PAD = 18


def render_frame(bg, avatar, channel_name, count, fx: EffectSystem, ring_pulse, gift_message=None):
    frame = bg.copy().convert("RGBA")
    draw = ImageDraw.Draw(frame)
    cx = W // 2
    ay = int(H * 0.30)

    # प्रीमियम डबल ग्लो रिंग (pulse के साथ)
    ring_r = AVATAR_SIZE // 2 + RING_PAD + int(ring_pulse * 14)
    ring_color = COLORS["gold"] if ring_pulse < 0.5 else COLORS["white"]
    glow = Image.new("RGBA", (ring_r * 2 + 100, ring_r * 2 + 100), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((50, 50, 50 + ring_r * 2, 50 + ring_r * 2), outline=ring_color + (255,), width=8)
    gd.ellipse((30, 30, 30 + (ring_r + 20) * 2 - 40, 30 + (ring_r + 20) * 2 - 40),
               outline=COLORS["violet"] + (120,), width=3)
    glow = glow.filter(ImageFilter.GaussianBlur(8))
    frame.paste(glow, (cx - glow.width // 2, ay - glow.height // 2), glow)

    frame.paste(avatar, (cx - AVATAR_SIZE // 2, ay - AVATAR_SIZE // 2), avatar)

    title_font = load_font(FONT_TITLE, 62)
    draw_center_text(draw, cx, ay + AVATAR_SIZE // 2 + 46, channel_name, title_font, COLORS["white"])

    label_font = load_font(FONT_LABEL, 36)
    draw_center_text(draw, cx, ay + AVATAR_SIZE // 2 + 122, "Subscribers", label_font, COLORS["muted"], tracking=3)

    scale = 1.0 + ring_pulse * 0.06
    num_font = load_font(FONT_DISPLAY, int(210 * scale), "ExtraBold")
    count_text = f"{count:,}"
    draw_center_text(draw, cx, int(H * 0.56), count_text, num_font, COLORS["gold"])

    if gift_message:
        msg_font = load_font(FONT_LABEL, 34)
        draw_center_text(draw, cx, int(H * 0.86), gift_message, msg_font, COLORS["muted"])

    fx.step_and_draw(frame)
    return frame.convert("RGB")


# --------------------------------------------------------------------------
# 8) साउंड: हर माइलस्टोन पर "ding" + आख़िर में थोड़ी लंबी chime
# --------------------------------------------------------------------------
SAMPLE_RATE = 44100


def synth_ding(duration=0.4, freq1=1046.5, freq2=1568.0, vol=1.0):
    n = int(SAMPLE_RATE * duration)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env = math.exp(-6 * t)
        val = 0.5 * math.sin(2 * math.pi * freq1 * t) + 0.35 * math.sin(2 * math.pi * freq2 * t)
        out.append(val * env * vol)
    return out


def build_audio_track(total_frames, burst_frame_indices, final_frame, out_wav: Path):
    total_samples = int(total_frames / FPS * SAMPLE_RATE)
    track = [0.0] * total_samples
    ding = synth_ding()
    for fidx in burst_frame_indices:
        start = int(fidx / FPS * SAMPLE_RATE)
        for i, v in enumerate(ding):
            pos = start + i
            if pos < total_samples:
                track[pos] += v
    finale = synth_ding(duration=0.9, freq1=1318.5, freq2=1975.5, vol=1.2)
    start = int(final_frame / FPS * SAMPLE_RATE)
    for i, v in enumerate(finale):
        pos = start + i
        if pos < total_samples:
            track[pos] += v

    peak = max(1e-6, max(abs(v) for v in track))
    if peak > 1:
        track = [v / peak * 0.9 for v in track]

    with wave.open(str(out_wav), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        frames = b"".join(struct.pack("<h", int(max(-1, min(1, v)) * 32767)) for v in track)
        wf.writeframes(frames)


# --------------------------------------------------------------------------
# 9) टाइमलाइन + एनकोडिंग
# --------------------------------------------------------------------------
def build_timeline(target, start_override=None):
    thresholds = [m for m in MILESTONES if m <= target]
    if not thresholds or thresholds[-1] != target:
        thresholds.append(target)

    start = start_override if start_override is not None else max(0, thresholds[0] - random.randint(35, 85))

    segments, prev = [], start
    for m in thresholds:
        is_big_jump = (m - prev) > 2500
        secs = 3.2 if not is_big_jump else 3.6
        segments.append((prev, m, secs, is_big_jump))
        prev = m
    return start, segments


def render_video(channel_name, avatar_img, target, out_path: Path,
                  start_override=None, with_sound=True, gift_message=None,
                  tmp_dir: Path = None, keep_frames=False):
    tmp_dir = tmp_dir or Path(tempfile.mkdtemp(prefix="giftvideo_"))
    frames_dir = tmp_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    bg = make_background(W, H)
    fx = EffectSystem()

    start, segments = build_timeline(target, start_override)
    print(f"  [{channel_name}] शुरुआत: {start:,} -> लक्ष्य: {target:,}  पड़ाव: {[s[1] for s in segments]}")

    hold_frames = int(1.0 * FPS)
    intro_frames = int(0.6 * FPS)
    outro_frames = int(1.4 * FPS)
    frame_idx = 0
    burst_frames = []

    # छोटा इंट्रो (0 pulse, स्थिर)
    for _ in range(intro_frames):
        img = render_frame(bg, avatar_img, channel_name, start, fx, 0.0, gift_message)
        img.save(frames_dir / f"f_{frame_idx:05d}.png")
        frame_idx += 1

    for (frm, to, secs, big_jump) in segments:
        n_frames = int(secs * FPS)
        for f in range(n_frames):
            t = ease_out_cubic(f / max(1, n_frames - 1))
            count = int(frm + (to - frm) * t)
            img = render_frame(bg, avatar_img, channel_name, count, fx, 0.0, gift_message)
            img.save(frames_dir / f"f_{frame_idx:05d}.png")
            frame_idx += 1

        burst_frames.append(frame_idx)
        fx.burst(W // 2, int(H * 0.30), count=170 if big_jump else 120, big=big_jump)
        for hf in range(hold_frames):
            pulse = math.sin((hf / hold_frames) * math.pi)
            img = render_frame(bg, avatar_img, channel_name, to, fx, pulse, gift_message)
            img.save(frames_dir / f"f_{frame_idx:05d}.png")
            frame_idx += 1

    final_burst_frame = frame_idx
    for _ in range(outro_frames):
        img = render_frame(bg, avatar_img, channel_name, target, fx, 0.0, gift_message)
        img.save(frames_dir / f"f_{frame_idx:05d}.png")
        frame_idx += 1

    total_frames = frame_idx
    print(f"  कुल फ्रेम्स: {total_frames}  (~{total_frames / FPS:.1f} सेकंड)")

    audio_path = None
    if with_sound:
        audio_path = tmp_dir / "audio.wav"
        build_audio_track(total_frames, burst_frames, final_burst_frame, audio_path)

    cmd = ["ffmpeg", "-y", "-framerate", str(FPS), "-i", str(frames_dir / "f_%05d.png")]
    if audio_path:
        cmd += ["-i", str(audio_path)]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS)]
    if audio_path:
        cmd += ["-c:a", "aac", "-shortest"]
    cmd += [str(out_path)]

    subprocess.run(cmd, check=True)
    print(f"  ✅ सेव हुआ: {out_path}")

    if not keep_frames:
        try:
            for f in frames_dir.glob("*.png"):
                f.unlink()
        except Exception:
            pass


# --------------------------------------------------------------------------
# 10) एक चैनल को पूरी तरह प्रोसेस करना (fetch + render)
# --------------------------------------------------------------------------
def process_one(channel_query, target, outdir, name_pattern, message=None,
                 manual_name=None, manual_avatar=None, with_sound=True):
    channel_name = manual_name
    avatar_source = manual_avatar

    if channel_query and not (channel_name and avatar_source):
        print(f"'{channel_query}' की जानकारी निकाली जा रही है...")
        try:
            fetched_name, avatar_url = fetch_channel_info(channel_query)
            channel_name = channel_name or fetched_name
            if not avatar_source and avatar_url:
                avatar_source = avatar_url
        except Exception as e:
            print(f"[चेतावनी] जानकारी नहीं मिल पाई ({e}). manual_name/manual_avatar चेक करें.")

    channel_name = channel_name or channel_query or "Channel"

    tmp_dir = Path(tempfile.mkdtemp(prefix="giftvideo_"))
    if avatar_source:
        if avatar_source.startswith("http"):
            local_avatar = tmp_dir / "avatar_src.jpg"
            download_image(avatar_source, local_avatar)
        else:
            local_avatar = Path(avatar_source)
        avatar_img = make_circular_avatar(local_avatar, AVATAR_SIZE)
    else:
        avatar_img = placeholder_avatar(AVATAR_SIZE, channel_name[:1].upper())

    out_path = build_output_path(outdir, name_pattern, channel_name, target)

    render_video(
        channel_name=channel_name,
        avatar_img=avatar_img,
        target=target,
        out_path=out_path,
        with_sound=with_sound,
        gift_message=message,
        tmp_dir=tmp_dir,
    )
    return out_path


# --------------------------------------------------------------------------
# 11) CLI
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Subscriber Gift Video Generator (Bulk)")
    ap.add_argument("--channel", help="चैनल का @handle, पूरा URL, या सिर्फ नाम")
    ap.add_argument("--target", type=int, choices=MILESTONES, help=f"{MILESTONES}")
    ap.add_argument("--name", help="चैनल का नाम मैन्युअली (fetch न हो तो)")
    ap.add_argument("--avatar", help="प्रोफाइल फोटो का लोकल पाथ/URL मैन्युअली")
    ap.add_argument("--message", help="वीडियो में नीचे दिखने वाला छोटा गिफ्ट मैसेज")
    ap.add_argument("--batch", help="CSV फाइल: channel,target[,message] — bulk जनरेशन के लिए")
    ap.add_argument("--outdir", default=DEFAULT_OUTDIR, help="आउटपुट फोल्डर")
    ap.add_argument("--name-pattern", default=DEFAULT_NAME_PATTERN,
                     help='फाइलनेम पैटर्न, {name} और {count} इस्तेमाल करें')
    ap.add_argument("--no-sound", action="store_true")
    args = ap.parse_args()

    if args.batch:
        with open(args.batch, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        print(f"बल्क मोड: {len(rows)} वीडियो बनने वाले हैं...")
        for i, row in enumerate(rows, 1):
            channel = row.get("channel", "").strip()
            target = int(row.get("target", "1000").strip())
            message = (row.get("message") or "").strip() or args.message
            print(f"\n[{i}/{len(rows)}] {channel} -> {target}")
            try:
                process_one(channel, target, args.outdir, args.name_pattern,
                            message=message, with_sound=not args.no_sound)
            except Exception as e:
                print(f"  ❌ फेल: {channel} — {e}")
        print("\nसारे वीडियो प्रोसेस हो गए।")
        return

    if not args.channel or not args.target:
        ap.error("--channel और --target दें, या --batch से CSV दें।")

    process_one(
        args.channel, args.target, args.outdir, args.name_pattern,
        message=args.message, manual_name=args.name, manual_avatar=args.avatar,
        with_sound=not args.no_sound,
    )


if __name__ == "__main__":
    main()
