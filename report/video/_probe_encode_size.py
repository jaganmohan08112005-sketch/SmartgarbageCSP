"""Measure the encode settings that fit the cut under GitHub's 100 MB push limit.

Re-encodes a sample of scenes through exactly the pipeline to_mp4 uses (same
crop/scale/tpad/caption chain, same preset/audio) at two candidate CRFs and
extrapolates the whole-cut size from the sample's compression ratio. The
existing segments are the CRF 21 baseline.
"""
import importlib.util
import os
import subprocess
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("mvl", os.path.join(HERE, "_make_video_live.py"))
mvl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mvl)

VD = mvl.VD
SAMPLE = [1, 4, 17, 23, 29]
CANDIDATES = [24, 25]
OUT = os.path.join(VD, "_measure")
os.makedirs(OUT, exist_ok=True)


def encode(i, crf, dest):
    name = mvl.SCENES[i][0]
    raw_dir = os.path.join(VD, "raw_" + name)
    webm = [os.path.join(raw_dir, f) for f in os.listdir(raw_dir) if f.endswith(".webm")][0]
    done = os.path.join(VD, name + "_m.webm.done")
    if os.path.exists(done):
        webm = open(done).read().strip()
    wav = os.path.join(VD, "narr%02d.wav" % i)
    with wave.open(wav, "rb") as w:
        dur = w.getnframes() / float(w.getframerate())
    total = dur + 1.0
    leading, cut = mvl.trim_window(webm)
    ins = []
    if leading > 0.2:
        ins += ["-ss", "%.2f" % leading]
    if cut:
        ins += ["-t", "%.2f" % cut]
    vf = ("crop=iw:ih-8:0:0,"
          "scale=1280:720:force_original_aspect_ratio=decrease,"
          "pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30")
    if cut:
        vf += ",tpad=stop_mode=clone:stop_duration=%.2f" % max(0.0, total - cut + 2.0)
    caption = mvl.CAPTIONS[i]
    if caption:
        vf += "," + mvl.caption_filter(caption, total)
    cmd = ([mvl.FF, "-y"] + ins + ["-i", webm, "-i", wav, "-t", "%.2f" % total,
           "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
           "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "1",
           "-pix_fmt", "yuv420p", dest])
    subprocess.run(cmd, check=True, capture_output=True)
    return os.path.getsize(dest)


base = {i: os.path.getsize(os.path.join(VD, "seg%02d.mp4" % i)) for i in range(len(mvl.SCENES))}
total_now = sum(base.values())
print("cut now: %.1f MB over %d segments (CRF 21, preset medium)"
      % (total_now / 1e6, len(base)))
print("sample: %s\n" % [mvl.SCENES[i][0] for i in SAMPLE])

for crf in CANDIDATES:
    sizes = {}
    for i in SAMPLE:
        dest = os.path.join(OUT, "seg%02d_crf%d.mp4" % (i, crf))
        sizes[i] = encode(i, crf, dest)
        print("  %-28s crf21=%6.2f MB  crf%d=%6.2f MB  (%+.0f%%)"
              % (mvl.SCENES[i][0], base[i] / 1e6, crf, sizes[i] / 1e6,
                 100.0 * (sizes[i] - base[i]) / base[i]))
    ratio = sum(sizes.values()) / float(sum(base[i] for i in SAMPLE))
    print("  -> sample ratio %.3f  =>  whole cut ~%.1f MB at CRF %d\n"
          % (ratio, total_now * ratio / 1e6, crf))
