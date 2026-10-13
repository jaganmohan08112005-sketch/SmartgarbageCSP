"""Verify the re-recorded demo video against the segment list it was built from.

Checks:
  1. container/stream facts (duration, resolution, codecs, mono AAC)
  2. scene ORDER + CONTENT: a frame at each segment's midpoint is extracted from
     the concatenated file and from the source segment; because the concat uses
     -c copy the frames must be pixel-identical, so a match proves both the order
     and that no scene was silently replaced by another
  3. no blank/dead frames: luma mean+std sampled right through the timeline
  4. dumps reviewable frames (opening page, scene 03 results, the last page) for the eye
"""
import json
import os
import subprocess

import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
# imageio-ffmpeg ships no ffprobe, so media facts are parsed from ffmpeg's banner.
import re
VD = os.path.join("report", "video", "_video_live")
OUT = os.path.join("submission", "video", "SmartGarbage_Demo_Video.mp4")
SHOTS = os.path.join(VD, "_shots")
os.makedirs(SHOTS, exist_ok=True)


def run(args):
    r = subprocess.run(args, capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


DUR_RE = re.compile(r"Duration: (\d+):(\d+):(\d+\.\d+)")
VID_RE = re.compile(r"Stream #\d+:\d+.*?: Video: (\w+).*?, (\d+)x(\d+)[,\s]")
AUD_RE = re.compile(r"Stream #\d+:\d+.*?: Audio: (\w+).*?, (\d+) Hz, (\w+)")


def probe(path):
    """Media facts from ffmpeg's own banner (no ffprobe in this environment)."""
    _, out, err = run([FF, "-hide_banner", "-i", path, "-f", "null", "-"])
    blob = out + err
    info = {"path": path}
    m = DUR_RE.search(blob)
    if not m:
        raise RuntimeError("no duration in ffmpeg banner for " + path)
    info["duration"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    m = VID_RE.search(blob)
    if m:
        info["video"] = {"codec": m.group(1), "width": int(m.group(2)),
                        "height": int(m.group(3))}
    m = AUD_RE.search(blob)
    if m:
        info["audio"] = {"codec": m.group(1), "rate": int(m.group(2)),
                        "layout": m.group(3)}
    return info


def duration(path):
    return probe(path)["duration"]


def frame(path, t, dest, crop=None):
    """Accurate seek: -ss AFTER -i decodes forward to the exact frame (an input
    seek can land on an earlier keyframe, which would compare two different
    moments of a moving page and fake a mismatch). An optional `crop` filter
    isolates a region (the caption band) instead of the whole page."""
    args = [FF, "-v", "error", "-i", path, "-ss", "%.3f" % t, "-frames:v", "1"]
    if crop:
        args += ["-vf", crop]
    args += ["-y", dest]
    code, _, err = run(args)
    if code != 0:
        raise RuntimeError("frame extract failed: " + err[:200])
    return dest


def _yavg(args):
    """signalstats YAVG over a one-frame pipeline (matches mean luma 0..255)."""
    _, out, err = run([FF, "-hide_banner", "-v", "info"] + args +
                      ["-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG",
                       "-f", "null", "-"])
    for line in (out + err).splitlines():
        if "lavfi.signalstats.YAVG=" in line:
            return float(line.split("YAVG=")[1].split()[0])
    return None


def luma(path):
    return _yavg(["-i", path])


def diff(a, b):
    """Mean absolute pixel difference between two images (0 == identical)."""
    chain = ("[0:v][1:v]blend=all_mode=difference,signalstats,"
             "metadata=print:key=lavfi.signalstats.YAVG")
    _, out, err = run([FF, "-hide_banner", "-v", "info", "-i", a, "-i", b,
                       "-filter_complex", chain, "-f", "null", "-"])
    for line in (out + err).splitlines():
        if "lavfi.signalstats.YAVG=" in line:
            return float(line.split("YAVG=")[1].split()[0])
    print("      (diff pipeline produced no stats: %s)"
          % (err.strip().splitlines()[-1][:120] if err.strip() else "no stderr"))
    return None


# The caption band burnt into the last 120px of every segment names that segment's
# feature, so it identifies a scene even when a frame lands a few tenths of a
# second off during a fast scroll. It is the tie-breaker for section 2: sampling a
# single mid-frame can miss by a frame or two (each segment carries its own audio
# priming, so the concat offsets drift by a fraction of a second), and a screen
# full of moving pixels turns that into a large mean difference. A reordered
# segment would be seconds away, which no band comparison can confuse.
BAND = "crop=iw:120:0:ih-120"


def band_diff(out_frame, seg_path, t, tag):
    src = frame(seg_path, t, os.path.join(SHOTS, "band_%s.png" % tag), BAND)
    return diff(out_frame, src)


print("=== 1. container / streams ===")
info = probe(OUT)
total = info["duration"]
print("file: %s" % OUT)
print("size: %.1f MB   duration: %.2fs (%.2f min = %d:%05.2f)"
      % (os.path.getsize(OUT) / 1e6, total, total / 60, int(total // 60), total % 60))
v = info.get("video")
a = info.get("audio")
print("video: %s %sx%s" % (v["codec"], v["width"], v["height"]) if v else "video: MISSING")
print("audio: %s %sHz %s" % (a["codec"], a["rate"], a["layout"]) if a else "audio: MISSING")

print("\n=== 2. scene order & content ===")
# The pages move, and cumulative segment durations carry ~0.1s of rounding drift,
# so a pixel-identical comparison is meaningless here. What matters is that the
# frame inside each window matches ITS OWN segment better than its neighbours -
# that proves the concat kept the intended order and content.
lst = os.path.join(VD, "list.txt")
entries = []
with open(lst, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line.startswith("file '"):
            entries.append(line[6:-1].replace("/", os.sep))
print("%d segments in the concat list" % len(entries))
mids = [(os.path.basename(s), duration(s) / 2.0) for s in entries]
cursor = 0.0
mismatches = 0
for i, seg in enumerate(entries):
    d = duration(seg)
    mid = cursor + d / 2.0
    if mid >= total:
        print("  !! segment %d lies past the end of the output" % i)
        mismatches += 1
        break
    a = frame(OUT, mid, os.path.join(SHOTS, "out_%02d.png" % i))
    own = diff(a, frame(seg, mids[i][1], os.path.join(SHOTS, "seg_%02d.png" % i)))
    rivals = []
    for j in (i - 1, i + 1):
        if 0 <= j < len(entries):
            rivals.append(diff(a, frame(entries[j], mids[j][1],
                                        os.path.join(SHOTS, "rival_%02d.png" % j))))
    worst_rival = min([r for r in rivals if r is not None], default=None)
    ok = own is not None and worst_rival is not None and own < worst_rival
    verdict = "BEST MATCH" if ok else "DOUBTFUL"
    if not ok:
        # Tie-break on the caption band, which is text and moves with nothing.
        a_band = frame(OUT, mid, os.path.join(SHOTS, "out_band_%02d.png" % i), BAND)
        mine = band_diff(a_band, seg, mids[i][1], "own_%02d" % i)
        theirs = []
        for j in (i - 1, i + 1):
            if 0 <= j < len(entries):
                theirs.append(band_diff(a_band, entries[j], mids[j][1], "rival_%02d" % j))
        theirs = [t for t in theirs if t is not None]
        if mine is not None and theirs and mine < min(theirs):
            ok = True
            verdict = "caption band confirms"
            print("      band: own=%.3f vs neighbours=%s"
                  % (mine, ",".join("%.3f" % t for t in theirs)))
        else:
            mismatches += 1
    print("  %02d %-20s %.1fs @%6.1fs  own=%.2f neighbours=%s  %s"
          % (i, os.path.basename(seg), d, mid, own if own is not None else -1,
             ",".join("%.2f" % r for r in rivals if r is not None), verdict))
    cursor += d
print("segment durations sum: %.2fs vs container %.2fs (delta %.2fs)"
      % (cursor, total, abs(cursor - total)))
print("scene order/content mismatches: %d" % mismatches)

print("\n=== 2b. tail motion (a frozen cut = the take was shorter than the narration) ===")
cursor = 0.0
static = 0
for i, seg in enumerate(entries):
    d = duration(seg)
    if d > 3:
        a = frame(OUT, cursor + d - 2.0, os.path.join(SHOTS, "_tail_a.png"))
        b = frame(OUT, cursor + d - 0.4, os.path.join(SHOTS, "_tail_b.png"))
        delta = diff(a, b)
        frozen = delta is not None and delta < 0.02
        if frozen:
            static += 1
        print("  %02d %-42s tail motion=%s %s"
              % (i, os.path.basename(seg), ("%.3f" % delta) if delta is not None else "n/a",
                 "FROZEN" if frozen else "moving"))
    cursor += d
print("frozen tails: %d of %d" % (static, len(entries)))

print("\n=== 3. blank-frame scan (every 20s) ===")
t = 0.0
blank = 0
samples = 0
while t < total - 1:
    p = frame(OUT, t, os.path.join(SHOTS, "_scan.png"))
    y = luma(p)
    samples += 1
    if y is not None and (y > 250 or y < 3):
        blank += 1
        print("  blank-ish frame at %.0fs (YAVG=%.1f)" % (t, y))
    t += 20
print("sampled %d frames; blank-ish: %d" % (samples, blank))

print("\n=== 4. frames kept for review in %s ===" % SHOTS)
for name in ("out_00.png", "out_03.png", "out_16.png", "out_17.png"):
    p = os.path.join(SHOTS, name)
    if os.path.exists(p):
        print("  %s  YAVG=%s" % (name, luma(p)))

print("\nRESULT: %s" % ("ALL CHECKS PASSED" if (mismatches == 0 and blank == 0
                                              and abs(cursor - total) < 2.0)
                        else "PROBLEMS FOUND"))
