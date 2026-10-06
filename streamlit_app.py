import streamlit as st
import asyncio, re, random, shutil, subprocess, tempfile, time, zipfile
from pathlib import Path
from collections import Counter
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import edge_tts

APP_NAME = "FAISAL STUDIO"
HIST = Path("/tmp/fs_history")
HIST.mkdir(exist_ok=True)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
UA = {"User-Agent": "FaisalStudio/1.0 (streamlit app)"}

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
try:
    st.markdown("<style>" + (Path(__file__).parent / ".streamlit" / "style.css").read_text() + "</style>",
                unsafe_allow_html=True)
except Exception:
    pass


@st.cache_data(ttl=21600, show_spinner=False)
def bg_pool():
    urls = []
    for q in ["Iron Man cosplay", "Spider-Man cosplay", "Captain America cosplay", "Thor cosplay",
              "Black Panther cosplay", "Hulk cosplay", "Marvel cosplay"]:
        try:
            r = requests.get("https://commons.wikimedia.org/w/api.php", params={
                "action": "query", "format": "json", "generator": "search", "gsrsearch": q,
                "gsrnamespace": 6, "gsrlimit": 25, "prop": "imageinfo",
                "iiprop": "url|size|mime", "iiurlwidth": 1080}, headers=UA, timeout=15).json()
            for p in r.get("query", {}).get("pages", {}).values():
                ii = p["imageinfo"][0]
                if ii.get("mime") == "image/jpeg" and ii.get("height", 0) > ii.get("width", 1) * 1.1 and ii.get("thumburl"):
                    urls.append(ii["thumburl"])
        except Exception:
            pass
    return urls


try:
    _pool = bg_pool()
    if _pool:
        _u = random.choice(_pool)
        st.markdown("<style>.stApp{background-image:linear-gradient(rgba(0,0,0,.5),rgba(0,0,0,.78)),url('" + _u + "') !important;background-size:cover !important;background-position:center top !important;background-attachment:fixed !important}</style>", unsafe_allow_html=True)
except Exception:
    pass


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


STOP = set("the and but with this that have from what when your just like they there their about would could into then than them were been will does much even only really more some very over also back still here where while those these which because every nothing anything everything something nature town nobody".split())


def keywords(script):
    ws = [w for w in re.findall(r"[a-z]{4,}", script.lower()) if w not in STOP and mask(w) == w]
    return [w for w, _ in Counter(ws).most_common(5)]


def auto_queries(script):
    kw = keywords(script)
    qs = []
    if len(kw) >= 2:
        qs.append(kw[0] + " " + kw[1])
    qs += kw
    return qs or ["nature"]


def dl(url, path, limit=45_000_000):
    with requests.get(url, stream=True, timeout=30, headers=UA) as r:
        r.raise_for_status()
        n = 0
        with open(path, "wb") as f:
            for ch in r.iter_content(1 << 16):
                n += len(ch)
                if n > limit:
                    raise RuntimeError("file too big")
                f.write(ch)


def pixabay_clips(queries, need, work, key):
    got = []
    for q in queries:
        if len(got) >= need:
            break
        try:
            r = requests.get("https://pixabay.com/api/videos/", params={
                "key": key, "q": q, "per_page": 12, "safesearch": "true"}, timeout=20).json()
            hits = r.get("hits", [])
            random.shuffle(hits)
            for h in hits[:2]:
                v = h["videos"].get("medium") or h["videos"].get("small")
                p = work / f"px{len(got)}.mp4"
                try:
                    dl(v["url"], p, 40_000_000)
                    got.append(p)
                except Exception:
                    continue
                if len(got) >= need:
                    break
        except Exception:
            pass
    return got


def commons_clips(queries, need, work):
    got = []
    for q in queries:
        if len(got) >= need:
            break
        try:
            r = requests.get("https://commons.wikimedia.org/w/api.php", params={
                "action": "query", "format": "json", "generator": "search",
                "gsrsearch": q + " filetype:video", "gsrnamespace": 6, "gsrlimit": 10,
                "prop": "imageinfo", "iiprop": "url|size|mime"}, headers=UA, timeout=20).json()
            pages = list(r.get("query", {}).get("pages", {}).values())
            random.shuffle(pages)
            for pg in pages[:3]:
                ii = pg["imageinfo"][0]
                mime = ii.get("mime", "")
                if (mime.startswith("video") or mime == "application/ogg") and ii.get("size", 0) < 35_000_000:
                    ext = Path(ii["url"]).suffix or ".webm"
                    p = work / f"wm{len(got)}{ext}"
                    try:
                        dl(ii["url"], p, 35_000_000)
                        got.append(p)
                    except Exception:
                        continue
                    if len(got) >= need:
                        break
        except Exception:
            pass
    return got


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
    ) % (W, H, fs, max(3, fs // 14), int(H * 0.20))
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


def detect_crop(p, cd):
    try:
        ss = min(1.0, cd / 3)
        r = subprocess.run(["ffmpeg", "-ss", str(ss), "-t", "2", "-i", str(p), "-vf",
                            "cropdetect=limit=24:round=2:reset=0", "-f", "null", "-"],
                           capture_output=True, text=True)
        m = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", r.stderr)
        if m:
            w, h, x, y = map(int, m[-1])
            if w >= 200 and h >= 200:
                return f"crop={w}:{h}:{x}:{y},"
    except Exception:
        pass
    return ""


def build_video(clips, adur, W, H, work, audio, out):
    info = []
    for c in clips:
        cd = duration(c)
        if cd > 0.5:
            lo, hi = 0.2, cd - 0.7
            if hi - lo < 1.0:
                lo, hi = 0.0, cd
            info.append((c, lo, hi, detect_crop(c, cd)))
    if not info:
        raise RuntimeError("Clips read nahi hui, dobara upload karo")
    segs, t, k, order = [], 0.0, 0, []
    while t < adur + 0.2:
        if not order:
            order = info[:]
            random.shuffle(order)
        c, lo, hi, crop = order.pop()
        seg = min(random.uniform(2.0, 3.2), hi - lo)
        start = random.uniform(lo, max(lo, hi - seg))
        z = 1.0 if k % 2 == 0 else 1.22
        vf = f"{crop}scale={int(W*z)}:{int(H*z)}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30,setsar=1"
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
    best, bs, fallback = None, -1, None
    for i in range(1, 9):
        fp = work / f"f{i}.jpg"
        run(["ffmpeg", "-y", "-ss", d * (0.1 + 0.8 * i / 9), "-i", joined, "-frames:v", "1", "-q:v", "2", fp])
        im = Image.open(fp).convert("RGB")
        fallback = fallback or im
        g = np.asarray(im.convert("L"), dtype=np.float32)
        if g.mean() < 35 or g.mean() > 215:
            continue
        score = g.std() + np.abs(np.diff(g, axis=0)).mean() * 3
        if score > bs:
            bs, best = score, im
    im = best or fallback
    im = ImageEnhance.Contrast(ImageEnhance.Color(im).enhance(1.35)).enhance(1.15)
    W, H = im.size
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(ov).rectangle([0, 0, W, int(H * 0.38)], fill=(0, 0, 0, 130))
    im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
    words = [mask(w) for w in re.sub(r"#\w+", "", title).upper().split()][:4]
    rows = [" ".join(words[i:i + 2]) for i in range(0, len(words), 2)]
    font = ImageFont.truetype(FONT, int(W * 0.13))
    dr = ImageDraw.Draw(im)
    y = int(H * 0.05)
    for n, r in enumerate(rows):
        w = dr.textlength(r, font=font)
        col = (255, 220, 0) if n % 2 == 0 else (255, 60, 60)
        dr.text(((W - w) / 2, y), r, font=font, fill=col, stroke_width=8, stroke_fill=(0, 0, 0))
        y += int(W * 0.16)
    im.save(out, quality=92)


def make_meta(script, custom_title):
    sents = re.split(r"(?<=[.!?])\s+", script.strip())
    if custom_title.strip():
        title = custom_title.strip()
    else:
        title = " ".join(mask(w) for w in (sents[0] if sents else script).strip().rstrip(".!?").split())
        if len(title) > 70:
            title = title[:67].rsplit(" ", 1)[0] + "..."
    tags = ["#" + w for w in keywords(script)]
    desc = " ".join(mask(w) for w in " ".join(sents[:2]).split()) + "\n\n" + " ".join(tags + ["#shorts"])
    return title + " #shorts", desc


def save_result(final, thumb, title, desc):
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


def _topic_queries():
    t = globals().get("topic", "") or ""
    qs = [q.strip() for q in re.split(r"[,\n]", t) if q.strip()]
    return qs or auto_queries(globals().get("script", "") or "")


def pixabay_clips(queries, need, work, key):
    got, seen = [], set()
    for rank in range(3):
        for q in queries:
            if len(got) >= need:
                return got
            try:
                r = requests.get("https://pixabay.com/api/videos/", params={
                    "key": key, "q": q, "per_page": 6, "safesearch": "true", "order": "popular"},
                    timeout=20).json()
                hits = r.get("hits", [])
                if rank >= len(hits) or hits[rank]["id"] in seen:
                    continue
                h = hits[rank]
                v = h["videos"].get("medium") or h["videos"].get("small")
                p = work / f"px{len(got)}.mp4"
                dl(v["url"], p, 40_000_000)
                seen.add(h["id"])
                got.append(p)
            except Exception:
                continue
    return got


def _img_score(im):
    g = np.asarray(im.convert("L").resize((270, 480)), dtype=np.float32)
    s = np.asarray(im.convert("HSV").resize((270, 480)), dtype=np.float32)[..., 1]
    return g.std() + np.abs(np.diff(g, axis=0)).mean() * 3 + s.mean() * 0.15


def _cover(im, W, H):
    r = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1), Image.LANCZOS)
    x = (im.width - W) // 2
    y = (im.height - H) // 2
    return im.crop((x, y, x + W, y + H))


def _topic_image(queries, work):
    try:
        key = st.secrets.get("PIXABAY_KEY", "")
    except Exception:
        key = ""
    urls = []
    for q in queries[:3]:
        if key:
            try:
                r = requests.get("https://pixabay.com/api/", params={
                    "key": key, "q": q, "image_type": "photo", "orientation": "vertical",
                    "per_page": 6, "safesearch": "true", "order": "popular"}, timeout=20).json()
                for h in r.get("hits", [])[:4]:
                    u = h.get("largeImageURL") or h.get("webformatURL")
                    if u:
                        urls.append((u, 20))
            except Exception:
                pass
        try:
            r = requests.get("https://commons.wikimedia.org/w/api.php", params={
                "action": "query", "format": "json", "generator": "search", "gsrsearch": q,
                "gsrnamespace": 6, "gsrlimit": 8, "prop": "imageinfo",
                "iiprop": "url|size|mime", "iiurlwidth": 1280}, headers=UA, timeout=15).json()
            for p in r.get("query", {}).get("pages", {}).values():
                ii = p["imageinfo"][0]
                if ii.get("mime") == "image/jpeg" and ii.get("width", 0) >= 900 and ii.get("thumburl"):
                    urls.append((ii["thumburl"], 0))
        except Exception:
            pass
    best, bs = None, -1
    for n, (u, bonus) in enumerate(urls[:14]):
        try:
            p = work / f"ti{n}.jpg"
            dl(u, p, 12_000_000)
            im = Image.open(p).convert("RGB")
            if im.width < 600 or im.height < 600:
                continue
            sc = _img_score(im) + bonus
            if sc > bs:
                bs, best = sc, im
        except Exception:
            continue
    return best


def _video_frame(joined, work):
    d = duration(joined)
    best, bs, fb = None, -1, None
    for i in range(1, 9):
        fp = work / f"f{i}.jpg"
        run(["ffmpeg", "-y", "-ss", d * (0.1 + 0.8 * i / 9), "-i", joined, "-frames:v", "1", "-q:v", "2", fp])
        im = Image.open(fp).convert("RGB")
        fb = fb or im
        m = np.asarray(im.convert("L"), dtype=np.float32).mean()
        if m < 35 or m > 215:
            continue
        sc = _img_score(im)
        if sc > bs:
            bs, best = sc, im
    return best or fb


def make_thumb(joined, title, work, out, queries=None):
    W, H = 1080, 1920
    im = None
    try:
        im = _topic_image(queries or _topic_queries(), work)
    except Exception:
        im = None
    if im is None:
        im = _video_frame(joined, work)
    im = _cover(im, W, H)
    im = ImageEnhance.Contrast(ImageEnhance.Color(im).enhance(1.3)).enhance(1.12)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    for yy in range(int(H * 0.42)):
        a = int(170 * (1 - yy / (H * 0.42)))
        od.line([(0, yy), (W, yy)], fill=(0, 0, 0, a))
    im = Image.alpha_composite(im.convert("RGBA"
                                          
                                          cleanup_history()
st.markdown(f"<h1 class='hero'>{APP_NAME}</h1><p class='sub'>Script + clips daalo, Short tayyar</p>",
            unsafe_allow_html=True)
tab1, tab2 = st.tabs(["CREATE", "HISTORY"])

VOICES = {"Andrew (US)": "en-US-AndrewNeural", "Guy (US)": "en-US-GuyNeural",
          "Christopher (US)": "en-US-ChristopherNeural", "Brian (US)": "en-US-BrianNeural",
          "Eric (US)": "en-US-EricNeural", "Jenny (US)": "en-US-JennyNeural"}

with tab1:
    script = st.text_area("Script", height=220, placeholder="Apni script yahan paste karo")
    files = st.file_uploader("Clips (apni, around 10)", type=["mp4", "mov", "webm", "mkv"],
                             accept_multiple_files=True)
    ctitle = st.text_input("Thumbnail title (2-3 words, optional)", placeholder="EARTH JUST SPLIT")
    topic = st.text_input("Stock search words (optional, comma se)", placeholder="flood, earthquake, tornado")
    extra = st.slider("Extra stock clips (Pixabay + Wikimedia)", 0, 10, 4)
    c1, c2, c3 = st.columns(3)
    voice = c1.selectbox("Voice", list(VOICES))
    speed = c2.slider("Speed %", -10, 30, 8)
    qual = c3.selectbox("Quality", ["Fast 720p", "HD 1080p"])
    if st.button("MAKE SHORT"):
        n_extra = int(extra)
        if not script.strip() or (not files and n_extra == 0):
            st.error("Script chahiye, aur clips ya extra stock clips")
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
                n_own = len(clips)
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
                if n_extra > 0:
                    bar.progress(22, text="Stock clips dhoond rahi hai...")
                    qs = [q.strip() for q in re.split(r"[,\n]", topic) if q.strip()] or auto_queries(script)
                    key = ""
                    try:
                        key = st.secrets.get("PIXABAY_KEY", "")
                    except Exception:
                        key = ""
                    n_cm = n_extra // 3
                    n_px = n_extra - n_cm
                    if key:
                        clips += pixabay_clips(qs, n_px, work, key)
                    else:
                        st.warning("Pixabay key nahi mili, sirf Wikimedia use hui")
                        n_cm = n_extra
                    clips += commons_clips(qs, n_cm, work)
                    st.info(f"{len(clips) - n_own} stock clips add hui")
                if not clips:
                    raise RuntimeError("Koi clip nahi mili")
                bar.progress(35, text="Video edit ho rahi hai (thora time lagega)...")
                final = work / "final.mp4"
                joined = build_video(clips, adur, W, H, work, audio, final)
                bar.progress(85, text="Thumbnail aur title...")
                title, desc = make_meta(script, ctitle)
                tt = ctitle.strip() or " ".join(keywords(script)[:2]) or "WATCH THIS"
                thumb = work / "thumb.jpg"
                make_thumb(joined, tt, work, thumb)
                st.session_state["last"] = str(save_result(final, thumb, title, desc))
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
