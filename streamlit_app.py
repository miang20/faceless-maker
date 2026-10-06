import streamlit as st
import asyncio, re, random, shutil, subprocess, tempfile, time, json, zipfile
from pathlib import Path
from collections import Counter
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import edge_tts

APP_NAME = "FAISAL STUDIO"
HIST = Path("/tmp/fs_history")
HIST.mkdir(exist_ok=True)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

st.set_page_config(page_title=APP_NAME, page_icon="🛡️", layout="centered")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bangers&display=swap');
.stApp{background:linear-gradient(160deg,#0b0f1f 0%,#1a0a0f 60%,#000 100%);color:#fff}
h1.hero{font-family:'Bangers',cursive;font-size:3rem;letter-spacing:3px;text-align:center;
color:#f5c518;text-shadow:3px 3px 0 #e23636;margin-bottom:0}
p.sub{text-align:center;color:#ddd;margin-top:0}
.stButton>button,.stDownloadButton>button{background:#e23636;color:#fff;font-weight:700;
border:2px solid #f5c518;border-radius:10px;width:100%;font-family:'Bangers',cursive;font-size:1.3rem;letter-spacing:1px}
</style>""", unsafe_allow_html=True)


st.markdown("<style>" + (Path(__file__).parent / "style.css").read_text() + "</style>", unsafe_allow_html=True)

def cleanup_history():
    now = time.time()
    for d in HIST.iterdir():
        try:
            if now - d.stat().st_mtime > 86400:
                shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass


def run(cmd, cwd=None):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, cwd=cwd)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-700:])
    return r.stdout


def duration(p):
    try:
        return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", p]).strip())
    except Exception:
        return 0.0


def mask(w):
    core = re.sub(r"[^A-Za-z]", "", w).lower()
    bad = core.startswith(("fuck", "shit", "bitch", "asshole", "bastard")) or core == "dick"
    if not bad or len(w) < 3:
        return w
    return w[0] + re.sub(r"[A-Za-z]", "*", w[1:-1]) + w[-1]


async def _tts(text, voice, rate, out):
    try:
        c = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    except TypeError:
        c = edge_tts.Communicate(text, voice, rate=rate)
    words = []
    with open(out, "wb") as f:
        async for ch in c.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                s = ch["offset"] / 1e7
                words.append((ch["text"], s, s + ch["duration"] / 1e7))
    return words


def ts(t):
    t = max(t, 0)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def make_ass(words, W, H, path):
    fs = int(W * 0.085)
    head = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: %d\nPlayResY: %d\n\n"
        "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,"
        "BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,"
        "Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
        "Style: Default,DejaVu Sans,%d,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,%d,0,2,40,40,%d,1\n\n"
        "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    ) % (W, H, fs, max(3, fs // 14), int(H * 0.28))
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= 3 or re.search(r"[.!?,]$", w[0]):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    lines = []
    for ch in chunks:
        shown = [mask(x[0]).upper() for x in ch]
        for i, w in enumerate(ch):
            st_ = w[1]
            en = ch[i + 1][1] if i + 1 < len(ch) else w[2] + 0.05
            if en <= st_:
                en = st_ + 0.1
            txt = " ".join(("{\\c&H00FFFF&}" + s + "{\\c&HFFFFFF&}") if j == i else s
                           for j, s in enumerate(shown))
            lines.append("Dialogue: 0,%s,%s,Default,,0,0,0,,%s" % (ts(st_), ts(en), txt))
    Path(path).write_text(head + "\n".join(lines), encoding="utf-8")


def build_video(clips, adur, W, H, work, audio, out):
    info = [(c, duration(c)) for c in clips]
    info = [x for x in info if x[1] > 0.5]
    if not info:
        raise RuntimeError("Clips read nahi hui, dobara upload karo")
    segs, t, k, order = [], 0.0, 0, []
    while t < adur + 0.2:
        if not order:
            order = info[:]
            random.shuffle(order)
        c, cd = order.pop()
        seg = min(random.uniform(2.0, 3.2), cd)
        start = random.uniform(0, max(0, cd - seg))
        z = 1.0 if k % 2 == 0 else 1.22
        vf = f"scale={int(W*z)}:{int(H*z)}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30,setsar=1"
        if k > 0 and k % 3 == 0:
            vf += ",eq=brightness=0.12:enable='lt(t,0.12)'"
        sp = work / f"seg{k}.mp4"
        run(["ffmpeg", "-y", "-ss", start, "-t", seg, "-i", c, "-an", "-vf", vf,
             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p", sp])
        segs.append(sp)
        t += seg
        k += 1
    lst = work / "list.txt"
    lst.write_text("\n".join(f"file '{p}'" for p in segs))
    joined = work / "joined.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined])
    run(["ffmpeg", "-y", "-i", joined, "-i", audio, "-vf", "ass=subs.ass", "-map", "0:v", "-map", "1:a",
         "-t", adur + 0.3, "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-c:a", "aac",
         "-b:a", "160k", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out], cwd=work)
    return joined


def make_thumb(joined, title, work, out):
    d = duration(joined)
    best, bs = None, -1
    for i in range(1, 7):
        fp = work / f"f{i}.jpg"
        run(["ffmpeg", "-y", "-ss", d * i / 7, "-i", joined, "-frames:v", "1", "-q:v", "2", fp])
        im = Image.open(fp).convert("RGB")
        a = np.asarray(im.convert("L"), dtype=np.float32)
        score = a.std() + np.abs(np.diff(a, axis=0)).mean() * 3
        if score > bs:
            bs, best = score, im
    im = ImageEnhance.Contrast(ImageEnhance.Color(best).enhance(1.3)).enhance(1.15)
    W, H = im.size
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(ov).rectangle([0, 0, W, int(H * 0.42)], fill=(0, 0, 0, 120))
    im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
    words = re.sub(r"#\w+", "", title).upper().split()[:5]
    rows = [" ".join(words[i:i + 2]) for i in range(0, len(words), 2)]
    font = ImageFont.truetype(FONT, int(W * 0.12))
    dr = ImageDraw.Draw(im)
    y = int(H * 0.06)
    for r in rows:
        w = dr.textlength(r, font=font)
        dr.text(((W - w) / 2, y), r, font=font, fill=(255, 220, 0), stroke_width=8, stroke_fill=(0, 0, 0))
        y += int(W * 0.15)
    im.save(out, quality=92)


def make_meta(script):
    sents = re.split(r"(?<=[.!?])\s+", script.strip())
    title = " ".join(mask(w) for w in (sents[0] if sents else script).strip().rstrip(".!?").split())
    if len(title) > 70:
        title = title[:67].rsplit(" ", 1)[0] + "..."
    stop = set("the and but with this that have from what when your just like they there their about would could into then than them were been will".split())
    ws = [w for w in re.findall(r"[a-z]{4,}", script.lower()) if w not in stop and mask(w) == w]
    tags = ["#" + w for w, _ in Counter(ws).most_common(5)]
    desc = " ".join(mask(w) for w in " ".join(sents[:2]).split()) + "\n\n" + " ".join(tags + ["#shorts"])
    return title + " #shorts", desc


def save_result(work, final, thumb, title, desc):
    d = HIST / time.strftime("%Y%m%d-%H%M%S")
    d.mkdir()
    shutil.copy(final, d / "video.mp4")
    shutil.copy(thumb, d / "thumbnail.jpg")
    (d / "title.txt").write_text(title)
    (d / "description.txt").write_text(desc)
    with zipfile.ZipFile(d / "pack.zip", "w") as z:
        for n in ["video.mp4", "thumbnail.jpg", "title.txt", "description.txt"]:
            z.write(d / n, n)
    return d


def show_result(d):
    st.video(str(d / "video.mp4"))
    st.image(str(d / "thumbnail.jpg"), caption="Thumbnail")
    st.caption("Title")
    st.code((d / "title.txt").read_text(), language=None)
    st.caption("Description")
    st.code((d / "description.txt").read_text(), language=None)
    st.download_button("DOWNLOAD ZIP", (d / "pack.zip").read_bytes(), file_name=f"{d.name}.zip",
                       key="dl_" + d.name)


cleanup_history()
st.markdown(f"<h1 class='hero'>{APP_NAME}</h1><p class='sub'>Script + clips daalo, Short tayyar</p>",
            unsafe_allow_html=True)
tab1, tab2 = st.tabs(["CREATE", "HISTORY"])

VOICES = {"Andrew (US)": "en-US-AndrewNeural", "Guy (US)": "en-US-GuyNeural",
          "Christopher (US)": "en-US-ChristopherNeural", "Brian (US)": "en-US-BrianNeural",
          "Eric (US)": "en-US-EricNeural", "Jenny (US)": "en-US-JennyNeural"}

with tab1:
    script = st.text_area("Script", height=220, placeholder="Apni script yahan paste karo")
    files = st.file_uploader("Clips (around 10)", type=["mp4", "mov", "webm", "mkv"],
                             accept_multiple_files=True)
    c1, c2, c3 = st.columns(3)
    voice = c1.selectbox("Voice", list(VOICES))
    speed = c2.slider("Speed %", -10, 30, 8)
    qual = c3.selectbox("Quality", ["Fast 720p", "HD 1080p"])
    if st.button("MAKE SHORT"):
        if not script.strip() or not files:
            st.error("Script aur clips dono chahiye")
        else:
            W, H = (720, 1280) if qual.startswith("Fast") else (1080, 1920)
            work = Path(tempfile.mkdtemp())
            bar = st.progress(0, text="Start...")
            try:
                clips = []
                for i, f in enumerate(files):
                    p = work / f"clip{i}{Path(f.name).suffix}"
                    p.write_bytes(f.getbuffer())
                    clips.append(p)
                text = " ".join(script.split())
                bar.progress(10, text="Voiceover ban rahi hai...")
                audio = work / "voice.mp3"
                words = asyncio.run(_tts(text, VOICES[voice], f"{speed:+d}%", str(audio)))
                adur = duration(audio)
                if not words:
                    toks = text.split()
                    per = adur / len(toks)
                    words = [(t, i * per, (i + 1) * per) for i, t in enumerate(toks)]
                make_ass(words, W, H, work / "subs.ass")
                bar.progress(30, text="Video edit ho rahi hai (thora time lagega)...")
                final = work / "final.mp4"
                joined = build_video(clips, adur, W, H, work, audio, final)
                bar.progress(85, text="Thumbnail aur title...")
                title, desc = make_meta(script)
                thumb = work / "thumb.jpg"
                make_thumb(joined, title, work, thumb)
                st.session_state["last"] = str(save_result(work, final, thumb, title, desc))
                bar.progress(100, text="Ho gaya!")
            except Exception as e:
                st.error(f"Masla aaya: {e}")
            finally:
                shutil.rmtree(work, ignore_errors=True)
    if st.session_state.get("last") and Path(st.session_state["last"]).exists():
        show_result(Path(st.session_state["last"]))

with tab2:
    st.caption("Purani items 24 ghante baad khud delete ho jati hain")
    items = sorted([d for d in HIST.iterdir() if d.is_dir()], reverse=True)
    if not items:
        st.info("Abhi kuch nahi")
    for d in items:
        with st.expander(d.name):
            if (d / "video.mp4").exists():
                show_result(d)
