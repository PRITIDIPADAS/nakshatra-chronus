"""Build the 30 second demo video, docs/media/chronos_demo.mp4, from figures and captures of the observatory page.

Run after scripts/make_figures.py. Page captures are read from /tmp/vid (see the capture step in this file's README notes).
"""
import os
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG = os.path.join(ROOT, "docs", "figures")
CAP = sys.argv[1] if len(sys.argv) > 1 else "/tmp/vid"
WORK = "/tmp/vid_work"
OUT = os.path.join(ROOT, "docs", "media", "chronos_demo.mp4")
W, H, FPS = 1920, 1080, 30
PAPER, INK, INK2, ACC = (245, 240, 230), (46, 42, 51), (93, 87, 99), (110, 86, 131)
FONT = os.path.join(ROOT, "scripts", "fonts", "EBGaramond-400-normal.ttf")
FONT_I = os.path.join(ROOT, "scripts", "fonts", "EBGaramond-400-italic.ttf")
FONT_B = os.path.join(ROOT, "scripts", "fonts", "EBGaramond-600-normal.ttf")


def f(path, size):
    return ImageFont.truetype(path, size)


def canvas(bg=PAPER):
    return Image.new("RGB", (W, H), bg)


def fit(im, box_w, box_h):
    r = min(box_w / im.width, box_h / im.height)
    return im.resize((int(im.width * r), int(im.height * r)), Image.LANCZOS)


def caption(c, text, sub=None, dark=False):
    d = ImageDraw.Draw(c)
    col = PAPER if dark else INK
    d.rectangle([0, H - 150, W, H], fill=INK if not dark else (36, 33, 40))
    d.text((90, H - 128), text, font=f(FONT, 46), fill=PAPER)
    if sub:
        d.text((90, H - 66), sub, font=f(FONT_I, 30), fill=(201, 184, 216))
    d.text((W - 360, 36), "Nakshatra CHRONOS", font=f(FONT_B, 32), fill=col if not dark else PAPER)
    return c


def place(c, im, y0=60, box=(1760, 840)):
    im = fit(im, *box)
    c.paste(im, ((W - im.width) // 2, y0 + (box[1] - im.height) // 2))
    return c


def still(name, img, dur):
    p = os.path.join(WORK, name + ".jpg")
    img.save(p, quality=92)
    tmp = os.path.join(WORK, name + "_tmp.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", p, "-vf",
                    f"format=yuv420p,loop=-1:1,trim=duration={dur},fade=t=in:st=0:d=0.35:color=0xf5f0e6,fade=t=out:st={dur - 0.35}:d=0.35:color=0xf5f0e6",
                    "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", str(FPS), tmp], check=True)
    os.replace(tmp, os.path.join(WORK, name + ".mp4"))


def seq(name, frames, dur):
    d = os.path.join(WORK, name)
    os.makedirs(d, exist_ok=True)
    n = int(round(dur * FPS))
    for i in range(n):
        frames(i, n).save(os.path.join(d, f"{i:04d}.jpg"), quality=92)
    tmp = os.path.join(WORK, name + "_tmp.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(d, "%04d.jpg"), "-vf",
                    f"format=yuv420p,fade=t=in:st=0:d=0.35:color=0xf5f0e6,fade=t=out:st={dur - 0.35}:d=0.35:color=0xf5f0e6",
                    "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", str(FPS), tmp], check=True)
    os.replace(tmp, os.path.join(WORK, name + ".mp4"))


def title():
    c = canvas(INK)
    d = ImageDraw.Draw(c)
    d.text((140, 250), "NASA SPACE APPS · PLANET X AND SPHEREx", font=f(FONT, 34), fill=(201, 184, 216))
    d.text((140, 320), "Nakshatra CHRONOS", font=f(FONT, 150), fill=PAPER)
    d.text((140, 520), "You cannot blink SPHEREx.", font=f(FONT_I, 70), fill=PAPER)
    d.text((140, 630), "So we built an observatory that asks what changed,", font=f(FONT, 44), fill=(217, 208, 196))
    d.text((140, 690), "and then tries to prove itself wrong.", font=f(FONT, 44), fill=(217, 208, 196))
    return c


def numbers():
    c = canvas()
    d = ImageDraw.Draw(c)
    d.text((140, 120), "Three detectors. Their disagreement is a measurement.", font=f(FONT, 64), fill=INK)
    items = [("34%", "seen by one method", "are real"), ("77%", "seen by two", "are real"), ("91%", "seen by all three", "are real"), ("5%", "seen by the anomaly", "model alone")]
    for k, (v, a, b) in enumerate(items):
        x = 140 + k * 420
        d.text((x, 300), v, font=f(FONT, 170), fill=ACC)
        d.text((x, 510), a, font=f(FONT, 40), fill=INK2)
        d.text((x, 560), b, font=f(FONT, 40), fill=INK2)
    d.text((140, 700), "512 candidates on 109 practice fields that the engine never saw.", font=f(FONT_I, 40), fill=INK2)
    return caption(c, "A change seen only by the anomaly model is almost always the camera.")


def end():
    c = canvas(INK)
    d = ImageDraw.Draw(c)
    d.text((140, 300), "Same sky. Same color.", font=f(FONT, 110), fill=PAPER)
    d.text((140, 430), "Then ask what changed.", font=f(FONT_I, 110), fill=PAPER)
    d.text((140, 640), "pritidipadas.github.io/nakshatra-chronus", font=f(FONT, 46), fill=(201, 184, 216))
    d.text((140, 710), "github.com/PRITIDIPADAS/nakshatra-chronus", font=f(FONT, 46), fill=(201, 184, 216))
    d.text((140, 820), "Candidate language only. Nothing here is a confirmed discovery.", font=f(FONT_I, 34), fill=(217, 208, 196))
    return c


def main():
    if os.path.exists(WORK):
        shutil.rmtree(WORK)
    os.makedirs(WORK)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    scenes = []
    still("s1", title(), 3.0)
    scenes.append("s1")
    micro = Image.open(os.path.join(FIG, "microscope.png")).convert("RGB")
    c = place(canvas(), micro, 120, (1780, 760))
    still("s2", caption(c, "Every pixel sees its own color, so a raw difference shows 27 false changes.", "Fair pairs and honest noise leave one: the real change."), 4.5)
    scenes.append("s2")
    sky = [Image.open(os.path.join(CAP, f"sky_{v}.png")).convert("RGB") for v in range(4)]
    seq("s3", lambda i, n: caption(place(canvas(), sky[(i // 12) % 4], 70, (1780, 840)), "Every exposure on one grid. Blink the visits, read any pixel.",
                                   "Barnard's Star drifts; the space and time slice leans."), 4.0)
    scenes.append("s3")
    cubes = sorted(x for x in os.listdir(CAP) if x.startswith("cube_"))
    cim = [Image.open(os.path.join(CAP, x)).convert("RGB") for x in cubes]
    seq("s4", lambda i, n: caption(place(canvas(), cim[min(len(cim) - 1, int(i / n * len(cim)))], 70, (1400, 820)),
                                   "The temporal cube I(α, δ, t): time as the third axis."), 3.0)
    scenes.append("s4")
    dos = Image.open(os.path.join(FIG, "app_dossier.png")).convert("RGB")
    dos = dos.resize((1600, int(dos.height * 1600 / dos.width)), Image.LANCZOS)
    span = max(0, dos.height - 860)

    def pan(i, n):
        y = int(span * min(1, max(0, (i / n - 0.1) / 0.8)))
        c = canvas()
        c.paste(dos.crop((0, y, 1600, y + 860)), (160, 60))
        return caption(c, "Every candidate defends itself: five hypotheses, tests that try to break the answer,", "and a report where every sentence points to a measurement.")
    seq("s5", pan, 5.0)
    scenes.append("s5")
    still("s6", numbers(), 4.0)
    scenes.append("s6")
    px = Image.open(os.path.join(FIG, "app_planetx.png")).convert("RGB")
    still("s7", caption(place(canvas(), px, 70, (1780, 840)), "The Planet X lab: what SPHEREx could see, honestly.",
                        "NASA states that Planet X has not been discovered. CHRONOS reaches the candidate rung, no further."), 3.5)
    scenes.append("s7")
    still("s8", end(), 3.0)
    scenes.append("s8")
    lst = os.path.join(WORK, "list.txt")
    open(lst, "w").write("".join(f"file '{os.path.join(WORK, s + '.mp4')}'\n" for s in scenes))
    tmp = OUT.replace(".mp4", "_tmp.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-movflags", "+faststart", tmp], check=True)
    os.replace(tmp, OUT)
    print("video", OUT)


if __name__ == "__main__":
    main()
