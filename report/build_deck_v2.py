# -*- coding: utf-8 -*-
"""DOCUMENT_FINAL.pptx - v2 visual redesign.

Keeps the R24 template's title/footer chrome and the finalized slide 1
(template team table, guide/HoD boxes), and replaces every content slide's
body with a designed layout: diagram images, screenshot grids, stat callouts
and card rows - no idle bullet walls.

Design system (eco-civic):
    deep  1B5E3B   leaf 2E7D52   amber F2A541
    ink   1F2A24   mist EEF4F0   slate 5A6B62
"""
import copy
import os
import sys

from PIL import Image
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIAG = os.path.join(ROOT, "report", "_diagrams")
SHOTS = os.path.join(DIAG, "shots_v2")
ASSETS = os.path.join(DIAG, "deck_assets")
os.makedirs(ASSETS, exist_ok=True)

DEEP = RGBColor(0x1B, 0x5E, 0x3B)
LEAF = RGBColor(0x2E, 0x7D, 0x52)
AMBER = RGBColor(0xF2, 0xA5, 0x41)
INK = RGBColor(0x1F, 0x2A, 0x24)
MIST = RGBColor(0xEE, 0xF4, 0xF0)
SLATE = RGBColor(0x5A, 0x6B, 0x62)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

SRC = os.path.join(HERE, "_inputs", "DOCUMENT_FINAL_v1_backup.pptx")  # clean v1 baseline
DST = os.path.join(HERE, "DOCUMENT_FINAL.pptx")

prs = Presentation(SRC)
SW, SH = prs.slide_width, prs.slide_height
IW, IH = Emu(SW).inches, Emu(SH).inches  # 13.333 x 7.5


# --------------------------- helpers ---------------------------
def crop_to(path, ratio, out_name):
    """Center-crop an image to an exact w/h ratio; return path to the crop."""
    out = os.path.join(ASSETS, out_name)
    if os.path.exists(out):
        return out
    im = Image.open(path).convert("RGB")
    w, h = im.size
    cur = w / h
    if abs(cur - ratio) > 0.01:
        if cur > ratio:  # too wide -> trim sides
            nw = int(h * ratio)
            x0 = (w - nw) // 2
            im = im.crop((x0, 0, x0 + nw, h))
        else:            # too tall -> trim bottom (keep top: page headers)
            nh = int(w / ratio)
            im = im.crop((0, 0, w, nh))
    im.save(out, quality=92)
    return out


def clear_body(slide, keep_ph_types=None):
    """Remove every shape except title/footer/date/slide-number placeholders.

    Slide 1 (template team table) is never passed here, so BODY is always
    removed on content slides. Title text is left untouched (it already
    matches the required headings).
    """
    keep_types = {"TITLE", "CENTER_TITLE", "FTR", "DT", "SLDNUM"}
    for sh in list(slide.shapes):
        try:
            ph = sh.placeholder_format
        except (ValueError, AttributeError):
            # not a placeholder (text box, picture, card...) -> remove it
            sh._element.getparent().remove(sh._element)
            continue
        if ph is not None and ph.type is not None and str(ph.type).split(" ")[0] in keep_types:
            continue
        sh._element.getparent().remove(sh._element)


def _tf(shape, text, size, color, bold=False, align=PP_ALIGN.LEFT,
        font="Calibri", anchor=MSO_ANCHOR.TOP, space_after=2, line=None):
    tf = shape.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Pt(4)
    tf.margin_top = tf.margin_bottom = Pt(2)
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if space_after:
            p.space_after = Pt(space_after)
        if line:
            p.line_spacing = line
        r = p.add_run()
        r.text = ln
        f = r.font
        f.size = Pt(size)
        f.color.rgb = color
        f.bold = bold
        f.name = font
    return tf


def card(slide, x, y, w, h, fill=MIST, line=None, radius=0.06, shadow=False):
    sp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                Inches(x), Inches(y), Inches(w), Inches(h))
    try:
        sp.adjustments[0] = radius
    except Exception:
        pass
    sp.fill.solid()
    sp.fill.fore_color.rgb = fill
    if line:
        sp.line.color.rgb = line
        sp.line.width = Pt(1)
    else:
        sp.line.fill.background()
    sp.shadow.inherit = False
    return sp


def chip(slide, x, y, w, h, label, fill=DEEP, fg=WHITE, size=12, bold=True):
    sp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                Inches(x), Inches(y), Inches(w), Inches(h))
    try:
        sp.adjustments[0] = 0.5
    except Exception:
        pass
    sp.fill.solid()
    sp.fill.fore_color.rgb = fill
    sp.line.fill.background()
    sp.shadow.inherit = False
    _tf(sp, label, size, fg, bold=bold, align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE)
    return sp


def stat(slide, x, y, w, h, big, small, fill=WHITE, fg=DEEP, big_size=30, small_size=11):
    sp = card(slide, x, y, w, h, fill=fill, line=RGBColor(0xD8, 0xE4, 0xDC))
    tf = sp.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = tf.margin_right = Pt(6)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = big
    r.font.size = Pt(big_size); r.font.bold = True; r.font.color.rgb = fg; r.font.name = "Calibri"
    p2 = tf.add_paragraph(); p2.alignment = PP_ALIGN.CENTER
    r2 = p2.add_run(); r2.text = small
    r2.font.size = Pt(small_size); r2.font.color.rgb = SLATE; r2.font.name = "Calibri"
    return sp


def icon_row(slide, x, y, w, glyph, head, desc, glyph_fill=LEAF, h=0.92, desc_size=12):
    """Icon chip + bold header + one-line description."""
    g = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y + 0.06),
                               Inches(0.62), Inches(0.62))
    g.fill.solid(); g.fill.fore_color.rgb = glyph_fill
    g.line.fill.background(); g.shadow.inherit = False
    _tf(g, glyph, 18, WHITE, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    t = slide.shapes.add_textbox(Inches(x + 0.78), Inches(y), Inches(w - 0.78), Inches(h))
    _tf(t, head + "\n" + desc, 14, INK)
    # bold the first line
    for para in t.text_frame.paragraphs[:1]:
        for r in para.runs:
            r.font.bold = True
            r.font.color.rgb = DEEP
            r.font.size = Pt(14)
    for para in t.text_frame.paragraphs[1:]:
        for r in para.runs:
            r.font.size = Pt(desc_size)
            r.font.color.rgb = SLATE
            r.font.bold = False
    return t


def pic(slide, path, x, y, w, h, crop=True):
    """Insert an image filling the box exactly (center-crop, no distortion)."""
    if crop and os.path.exists(path):
        im = Image.open(path)
        ratio = w / h
        stem = os.path.splitext(os.path.basename(path))[0]
        path = crop_to(path, ratio, f"{stem}_{w:.2f}x{h:.2f}.jpg")
    return slide.shapes.add_picture(path, Inches(x), Inches(y), Inches(w), Inches(h))


def caption(slide, x, y, w, text, size=10):
    t = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(0.3))
    _tf(t, text, size, SLATE, align=PP_ALIGN.CENTER, bold=False)
    return t


def chevrons(slide, x, y, w, h, items, fill=DEEP, fg=WHITE):
    n = len(items)
    gap = 0.12
    cw = (w - gap * (n - 1)) / n
    for i, txt in enumerate(items):
        cx = x + i * (cw + gap)
        shp_type = MSO_SHAPE.PENTAGON if i == 0 else MSO_SHAPE.CHEVRON
        sp = slide.shapes.add_shape(shp_type, Inches(cx), Inches(y),
                                    Inches(cw), Inches(h))
        sp.fill.solid(); sp.fill.fore_color.rgb = fill if i % 2 == 0 else LEAF
        sp.line.fill.background(); sp.shadow.inherit = False
        _tf(sp, txt, 11.5, fg, bold=True, align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE)


def set_title(slide, text):
    """Replace the title placeholder's text, preserving its formatting."""
    for ph in slide.placeholders:
        if ph.placeholder_format.type is not None and "TITLE" in str(ph.placeholder_format.type):
            tf = ph.text_frame
            if tf.paragraphs and tf.paragraphs[0].runs:
                keep = tf.paragraphs[0].runs[0]
                keep.text = text
                for r in tf.paragraphs[0].runs[1:]:
                    r._r.getparent().remove(r._r)
                for p in tf.paragraphs[1:]:
                    p._p.getparent().remove(p._p)
            else:
                tf.text = text
            return


# --------------------------- slide 2 - Abstract ---------------------------
s = prs.slides[1]
clear_body(s)
card(s, 0.55, 1.35, 7.05, 3.6, fill=MIST)
t = s.shapes.add_textbox(Inches(0.85), Inches(1.55), Inches(6.5), Inches(3.3))
_tf(t, ("SmartGarbage connects ~12,000 residents of Chintalavalasa Gram Panchayat "
        "(5 wards) with their Panchayat through one accountable digital channel.\n\n"
        "Residents get street-level schedules, complaint tracking with signed links, "
        "WhatsApp reporting, PAYT billing and Green Points rewards.\n\n"
        "An HMAC-secured IoT telemetry pipeline feeds scikit-learn models for bin "
        "overflow ETA, anomaly alerts and route priority - with every action audit-logged."),
    14.5, INK, line=1.15)
chip(s, 0.85, 5.25, 1.55, 0.5, "Flask 3 | PWA")
chip(s, 2.55, 5.25, 2.0, 0.5, "PostgreSQL | 23 tables", fill=LEAF)
chip(s, 4.70, 5.25, 1.75, 0.5, "scikit-learn ML")
chip(s, 6.60, 5.25, 1.0, 0.5, "Docker", fill=AMBER, fg=INK)
for i, (big, small) in enumerate([("5", "wards live"), ("3", "user roles"),
                                  ("359", "tests green"), ("Rs 0", "running cost")]):
    stat(s, 8.0 + (i % 2) * 2.45, 1.35 + (i // 2) * 1.75, 2.25, 1.55,
         big, small, big_size=28)
pic(s, os.path.join(SHOTS, "sg_home_1280.png"), 8.0, 4.95, 4.7, 1.85)
caption(s, 8.0, 6.85, 4.7, "Live portal - smartgarbage.onrender.com")

# --------------------------- slide 3 - Introduction ---------------------------
s = prs.slides[2]
clear_body(s)
icon_row(s, 0.6, 1.5, 7.2, "01", "Study area",
         "Chintalavalasa Gram Panchayat, Denkada Mandal, Vizianagaram district, AP - "
         "5 wards, ~12,000 residents.")
icon_row(s, 0.6, 2.85, 7.2, "02", "Stakeholders",
         "Residents | sanitation workers (CV-01...05) | Panchayat admins | state reviewers.")
icon_row(s, 0.6, 4.2, 7.2, "!", "The gap",
         "No digital channel: paper notices, word-of-mouth complaints, zero data for planning.")
c = card(s, 8.2, 1.4, 4.5, 4.6, fill=WHITE, line=RGBColor(0xD8, 0xE4, 0xDC))
_tf(c, "The five wards", 15, DEEP, bold=True, align=PP_ALIGN.CENTER)
wards = ["Ward 1 - MVGR College Area", "Ward 2 - Chintalavalasa Junction",
         "Ward 3 - RTC Colony", "Ward 4 - Ramalayam Street", "Ward 5 - Sai Nagar"]
t = s.shapes.add_textbox(Inches(8.5), Inches(2.0), Inches(3.9), Inches(2.4))
_tf(t, "\n".join("-  " + w for w in wards), 13.5, INK, space_after=8)
b = card(s, 8.5, 4.7, 3.9, 0.95, fill=DEEP)
_tf(b, "~12,000 residents | 2 pickups per ward per week", 13, WHITE, bold=True,
    align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
caption(s, 8.2, 6.15, 4.5, "Field-surveyed boundaries & schedules (seed data)")

# --------------------------- slide 4 - Problem ---------------------------
s = prs.slides[3]
clear_body(s)
probs = [
    ("Info blackout", "No digital schedule - residents miss pickups or wait by the road.", "1"),
    ("Complaints vanish", "Word-of-mouth reporting; nothing is tracked, nothing is proved.", "2"),
    ("Segregation unproven", "Voluntary 4-stream sorting with no incentive and no record.", "3"),
    ("Reactive operations", "Fixed routes ignore real bin fill; overflows discovered late.", "4"),
]
for i, (h, d, g) in enumerate(probs):
    x = 0.6 + (i % 2) * 6.35
    y = 1.5 + (i // 2) * 1.85
    c = card(s, x, y, 6.0, 1.6, fill=WHITE, line=RGBColor(0xD8, 0xE4, 0xDC))
    gsp = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x + 0.25), Inches(y + 0.42),
                             Inches(0.72), Inches(0.72))
    gsp.fill.solid(); gsp.fill.fore_color.rgb = MIST
    gsp.line.fill.background(); gsp.shadow.inherit = False
    _tf(gsp, g, 20, DEEP, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    t = s.shapes.add_textbox(Inches(x + 1.2), Inches(y + 0.18), Inches(4.6), Inches(1.3))
    _tf(t, h, 15, DEEP, bold=True)
    t2 = s.shapes.add_textbox(Inches(x + 1.2), Inches(y + 0.62), Inches(4.6), Inches(0.9))
    _tf(t2, d, 12.5, SLATE)
chip(s, 0.6, 5.55, 1.9, 0.55, "Paper notices", fill=SLATE)
chevrons(s, 2.7, 5.5, 10.0, 0.65,
         ["Missed pickups", "Street overflow", "Health & odour risk", "Citizen distrust"])

# --------------------------- slide 5 - Objectives ---------------------------
s = prs.slides[4]
clear_body(s)
objs = [
    ("1", "Publish street-level collection schedules for every ward"),
    ("2", "Report & track complaints via signed 90-day tracking links"),
    ("3", "Reward verified segregation - Green Points + 4-stream declarations"),
    ("4", "Digitise PAYT billing with UPI payments and receipts"),
    ("5", "Give admins live telemetry, SLA escalation and audit-grade exports"),
]
for i, (n, txt) in enumerate(objs):
    y = 1.5 + i * 1.02
    g = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(0.7), Inches(y), Inches(0.66), Inches(0.66))
    g.fill.solid(); g.fill.fore_color.rgb = DEEP
    g.line.fill.background(); g.shadow.inherit = False
    _tf(g, n, 20, WHITE, bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    t = s.shapes.add_textbox(Inches(1.6), Inches(y - 0.04), Inches(6.6), Inches(0.95))
    _tf(t, txt, 15, INK, anchor=MSO_ANCHOR.MIDDLE)
for i, (big, small) in enumerate([("100%", "schedule visibility"),
                                  ("<48h", "complaint SLA"),
                                  ("Rs 0", "messaging via WhatsApp")]):
    stat(s, 8.75, 1.5 + i * 1.62, 3.9, 1.35, big, small, big_size=26)

# --------------------------- slide 6 - Scope ---------------------------
s = prs.slides[5]
clear_body(s)
c = card(s, 0.6, 1.45, 6.0, 4.35, fill=MIST)
t = s.shapes.add_textbox(Inches(0.9), Inches(1.65), Inches(5.4), Inches(0.4))
_tf(t, "IN SCOPE", 15, DEEP, bold=True)
t = s.shapes.add_textbox(Inches(0.9), Inches(2.15), Inches(5.4), Inches(3.5))
_tf(t, ("-  All 5 wards: schedules, reporting, transparency\n"
        "-  3 roles - citizen, worker, admin (+ public, no login)\n"
        "-  IoT ingestion: HMAC-signed telemetry (ESP32-ready)\n"
        "-  WhatsApp reporting bot + status alerts\n"
        "-  PAYT invoicing, UPI payment, receipts\n"
        "-  PWA offline shell + installable app"),
    13.5, INK, space_after=7, line=1.1)
c = card(s, 6.85, 1.45, 5.85, 4.35, fill=WHITE, line=RGBColor(0xD8, 0xE4, 0xDC))
t = s.shapes.add_textbox(Inches(7.15), Inches(1.65), Inches(5.2), Inches(0.4))
_tf(t, "OUT OF SCOPE (honest boundary)", 15, SLATE, bold=True)
t = s.shapes.add_textbox(Inches(7.15), Inches(2.15), Inches(5.2), Inches(3.5))
_tf(t, ("-  Native iOS/Android apps (PWA covers installability)\n"
        "-  Bin hardware manufacturing (ESP32 firmware is future work)\n"
        "-  Wards beyond Chintalavalasa (schema is multi-ward ready)\n"
        "-  Property-tax or other Panchayat services\n"
        "-  Card-on-file payments (UPI/PAYT only)"),
    13.5, INK, space_after=7, line=1.1)
chip(s, 0.6, 6.1, 12.1, 0.55, "Everything demonstrated in this deck runs on the live deployment - smartgarbage.onrender.com", fill=DEEP, size=13)

# --------------------------- slide 7 - Literature review ---------------------------
s = prs.slides[6]
clear_body(s)
rows, cols = 5, 4
tw, th = 12.1, 4.6
gt = s.shapes.add_table(rows, cols, Inches(0.6), Inches(1.5), Inches(tw), Inches(th)).table
headers = ["Dimension", "Notice boards / word-of-mouth", "Generic municipal apps", "SmartGarbage"]
data = [
    ["Schedule visibility", "Paper only, no updates", "City-level, no wards", "Street-level, per ward, live"],
    ["Complaint tracking", "None", "Email, no SLA", "Signed link + 48h SLA + auto-escalation"],
    ["Incentives", "None", "None", "Green Points + PAYT pricing"],
    ["Data for planning", "None", "Siloed dashboards", "Live telemetry + ML ETA + state exports"],
]
for c_, htxt in enumerate(headers):
    cell = gt.cell(0, c_)
    cell.text = htxt
    for p in cell.text_frame.paragraphs:
        for r in p.runs:
            r.font.bold = True; r.font.size = Pt(13); r.font.color.rgb = WHITE; r.font.name = "Calibri"
    cell.fill.solid(); cell.fill.fore_color.rgb = DEEP
# Kill the default table style's first-row banding (it overrides run colors in
# some renderers, painting dark header text on the dark header fill).
_tblPr = gt._tbl.find(qn('a:tblPr'))
if _tblPr is not None:
    _tblPr.set('firstRow', '0')
    _tblPr.set('bandRow', '0')
for r_ in range(1, rows):
    for c_ in range(cols):
        cell = gt.cell(r_, c_)
        cell.text = data[r_ - 1][c_]
        for p in cell.text_frame.paragraphs:
            for r in p.runs:
                r.font.size = Pt(12.5); r.font.name = "Calibri"
                r.font.color.rgb = INK if c_ < 3 else DEEP
                r.font.bold = (c_ == 3)
        cell.fill.solid()
        cell.fill.fore_color.rgb = WHITE if r_ % 2 else MIST
caption(s, 0.6, 6.35, 12.1, "Positioning: ward-level accountability + incentives + live data - the three gaps in existing systems")

# --------------------------- slide 8 - Data used ---------------------------
s = prs.slides[7]
clear_body(s)
cards8 = [
    ("A", "Field survey (primary)", "Ward boundaries, street-level schedules (10 rows), "
     "stakeholder interviews, helpline & contacts - from direct field observation."),
    ("B", "IoT telemetry (live path)", "Fill %, temperature, methane ppm, battery, tilt from 10 bins - "
     "HMAC-signed pings into PostgreSQL via the production ingestion API."),
    ("C", "Synthetic history (disclosed)", "600-row, 48-hour ramping grid per bin gives the fill-rate model "
     "velocity on a fresh install - documented as a limitation; retrains on live pings."),
]
for i, (g, h, d) in enumerate(cards8):
    x = 0.6 + i * 4.15
    c = card(s, x, 1.5, 3.9, 3.9, fill=WHITE, line=RGBColor(0xD8, 0xE4, 0xDC))
    gsp = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x + 1.5), Inches(1.8),
                             Inches(0.85), Inches(0.85))
    gsp.fill.solid(); gsp.fill.fore_color.rgb = MIST
    gsp.line.fill.background(); gsp.shadow.inherit = False
    _tf(gsp, g, 24, DEEP, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    t = s.shapes.add_textbox(Inches(x + 0.25), Inches(2.85), Inches(3.4), Inches(0.5))
    _tf(t, h, 14.5, DEEP, bold=True, align=PP_ALIGN.CENTER)
    t = s.shapes.add_textbox(Inches(x + 0.25), Inches(3.35), Inches(3.4), Inches(1.9))
    _tf(t, d, 11.5, SLATE, line=1.12)
c = card(s, 0.6, 5.7, 12.1, 0.95, fill=DEEP)
_tf(c, "No Panchayat stores last year's per-bin history - we say so, size models to the data, "
       "and retrain automatically as real pings accumulate.", 13.5, WHITE, bold=True,
    align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

# --------------------------- slide 9 - Methodology flow ---------------------------
s = prs.slides[8]
clear_body(s)
pic(s, os.path.join(DIAG, "report", "flow_wide.png"), 0.6, 1.7, 12.1, 3.9, crop=False)
caption(s, 0.6, 5.75, 12.1, "End-to-end workflow: every arrow is an implemented endpoint, queue job or DB write")
chevrons(s, 0.6, 6.25, 12.1, 0.6, ["Intake (web | WhatsApp | IoT)", "Validate & sign",
                                   "Store (PostgreSQL)", "Learn (ML)", "Act (routes | alerts | SLA)"])

# --------------------------- slide 10 - Architecture ---------------------------
s = prs.slides[9]
clear_body(s)
pic(s, os.path.join(DIAG, "architecture.png"), 0.55, 1.55, 7.9, 5.35, crop=False)
layers = [
    ("1 | Ingest", "Forms, WhatsApp bot, HMAC IoT pings"),
    ("2 | API", "9 Flask route modules, CSRF + rate limits"),
    ("3 | Data", "PostgreSQL | 23 tables | Alembic x29"),
    ("4 | ML", "ETA | anomaly | miss prediction"),
    ("5 | Real-time", "Socket.IO dashboards | SSE alerts"),
    ("6 | Deliver", "Docker on Render | /health | PWA"),
]
for i, (h, d) in enumerate(layers):
    y = 1.55 + i * 0.92
    c = card(s, 8.75, y, 4.0, 0.78, fill=MIST if i % 2 == 0 else WHITE,
             line=RGBColor(0xD8, 0xE4, 0xDC))
    t = s.shapes.add_textbox(Inches(8.95), Inches(y + 0.05), Inches(3.7), Inches(0.7))
    _tf(t, h, 12.5, DEEP, bold=True)
    t2 = s.shapes.add_textbox(Inches(8.95), Inches(y + 0.36), Inches(3.7), Inches(0.4))
    _tf(t2, d, 10.5, SLATE)

# --------------------------- slide 11 - Modules + database ---------------------------
s = prs.slides[10]
clear_body(s)
pic(s, os.path.join(DIAG, "database_er_diagram.png"), 0.55, 1.6, 6.7, 4.45, crop=False)
caption(s, 0.55, 6.15, 6.7, "23-table relational schema (Alembic-managed, 29 migrations)")
mods = [
    ("P", "Public portal", "Schedules, transparency, FAQ, search - no login"),
    ("C", "Citizen", "Complaints + tracking, declarations, PAYT, Green Points"),
    ("W", "Worker", "Route, geofence enforcement, offload proof"),
    ("A", "Admin", "Control room: incidents, SLA, OTA firmware, exports"),
]
for i, (g, h, d) in enumerate(mods):
    y = 1.6 + i * 1.18
    c = card(s, 7.65, y, 5.1, 1.02, fill=WHITE, line=RGBColor(0xD8, 0xE4, 0xDC))
    gsp = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(7.85), Inches(y + 0.2),
                             Inches(0.62), Inches(0.62))
    gsp.fill.solid(); gsp.fill.fore_color.rgb = MIST
    gsp.line.fill.background(); gsp.shadow.inherit = False
    _tf(gsp, g, 17, DEEP, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    t = s.shapes.add_textbox(Inches(8.65), Inches(y + 0.07), Inches(4.0), Inches(0.42))
    _tf(t, h, 13.5, DEEP, bold=True)
    t = s.shapes.add_textbox(Inches(8.65), Inches(y + 0.48), Inches(4.0), Inches(0.5))
    _tf(t, d, 11, SLATE)

# --------------------------- slide 12 - Deployment ---------------------------
s = prs.slides[11]
clear_body(s)
pic(s, os.path.join(DIAG, "report", "deploy.png"), 1.35, 1.55, 10.6, 4.35, crop=False)
caption(s, 1.35, 5.94, 10.6, "9 blueprints | 131 routes | 23 tables | 29 Alembic migrations | gunicorn + gevent x2")
chevrons(s, 0.6, 6.2, 12.1, 0.62,
         ["git push", "Docker build", "flask db upgrade", "gunicorn + gevent x2", "/health OK"])

# --------------------------- slide 13 - Results grid ---------------------------
s = prs.slides[12]
clear_body(s)
set_title(s, "Results - Live Portal (Every Feature)")
shots = [("sg_home_1280.png", "Home"), ("sg_schedule_1280.png", "Schedule lookup"),
         ("sg_report_1280.png", "Report & WhatsApp"), ("sg_transparency_1280.png", "Transparency"),
         ("sg_impact_1280.png", "Impact"), ("sg_track_1280.png", "Complaint tracking")]
for i, (f, label) in enumerate(shots):
    x = 0.6 + (i % 3) * 4.15
    y = 1.5 + (i // 3) * 2.65
    pic(s, os.path.join(SHOTS, f), x, y, 3.85, 2.08)
    lb = chip(s, x, y + 2.08, 3.85, 0.42, label, fill=DEEP, size=12)
caption(s, 0.6, 6.85, 12.1, "Captured from the live deployment - desktop PWA (1280px)")

# --------------------------- slide 14 - Impact ---------------------------
s = prs.slides[13]
clear_body(s)
for i, (big, small) in enumerate([("~12k", "residents served"), ("5", "wards live"),
                                  ("23 / 29", "tables / migrations"), ("359", "tests green")]):
    stat(s, 0.6 + i * 3.08, 1.45, 2.85, 1.5, big, small, big_size=30)
imp = [
    ("G", "Governance", "Audit trail on every privileged action; CSV/JSON state-compliance exports."),
    ("E", "Environment", "PAYT + 4-stream declarations steer waste to compost/recycle, not landfill."),
    ("S", "Social", "WhatsApp-first access - no app store, works on basic Android; offline PWA shell."),
    ("T", "Engineering", "Queue with retries + dead-letter alerts; /health; Prometheus-style metrics."),
]
for i, (g, h, d) in enumerate(imp):
    x = 0.6 + (i % 2) * 6.35
    y = 3.35 + (i // 2) * 1.75
    c = card(s, x, y, 6.0, 1.55, fill=MIST)
    gsp = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x + 0.22), Inches(y + 0.4),
                             Inches(0.7), Inches(0.7))
    gsp.fill.solid(); gsp.fill.fore_color.rgb = WHITE
    gsp.line.fill.background(); gsp.shadow.inherit = False
    _tf(gsp, g, 19, DEEP, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    t = s.shapes.add_textbox(Inches(x + 1.1), Inches(y + 0.1), Inches(4.7), Inches(0.45))
    _tf(t, h, 14, DEEP, bold=True)
    t = s.shapes.add_textbox(Inches(x + 1.1), Inches(y + 0.55), Inches(4.7), Inches(0.95))
    _tf(t, d, 11.5, SLATE, line=1.1)

# --------------------------- slide 15 - Challenges ---------------------------
s = prs.slides[14]
clear_body(s)
pairs = [
    ("No historical bin telemetry", "600-row synthetic grid + auto-retrain on live pings - limitation disclosed"),
    ("Free tier: no worker service", "In-process RQ worker, retry policies, dead-letter alerts, /health probes"),
    ("1 vCPU page-load stalls", "gevent x2 workers, compression, Redis cache, offline PWA shell"),
]
for i, (ch, so) in enumerate(pairs):
    y = 1.6 + i * 1.62
    c = card(s, 0.6, y, 5.3, 1.35, fill=WHITE, line=AMBER)
    t = s.shapes.add_textbox(Inches(0.85), Inches(y + 0.12), Inches(4.8), Inches(1.1))
    _tf(t, "CHALLENGE", 10.5, AMBER, bold=True)
    t2 = s.shapes.add_textbox(Inches(0.85), Inches(y + 0.42), Inches(4.8), Inches(0.85))
    _tf(t2, ch, 13.5, INK, bold=True)
    ar = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(6.05), Inches(y + 0.45),
                            Inches(0.95), Inches(0.45))
    ar.fill.solid(); ar.fill.fore_color.rgb = LEAF
    ar.line.fill.background(); ar.shadow.inherit = False
    c = card(s, 7.15, y, 5.55, 1.35, fill=MIST)
    t = s.shapes.add_textbox(Inches(7.4), Inches(y + 0.12), Inches(5.05), Inches(1.1))
    _tf(t, "OUR SOLUTION", 10.5, DEEP, bold=True)
    t2 = s.shapes.add_textbox(Inches(7.4), Inches(y + 0.42), Inches(5.05), Inches(0.85))
    _tf(t2, so, 12.5, INK)

# --------------------------- slide 16 - Conclusion ---------------------------
s = prs.slides[15]
clear_body(s)
c = card(s, 0.6, 1.7, 6.9, 3.0, fill=DEEP)
_tf(c, ("SmartGarbage replaces a notice board and a phone tree with one\n"
        "accountable, data-producing channel - schedules people can trust,\n"
        "complaints that cannot vanish, and operations data the Panchayat\n"
        "can finally act on."),
    16, WHITE, bold=True, anchor=MSO_ANCHOR.MIDDLE, line=1.2)
for i, ch in enumerate(["One accountable channel", "Data-driven operations", "Ready for the next ward"]):
    chip(s, 0.6 + i * 2.42, 5.0, 2.25, 0.55, ch, fill=MIST, fg=DEEP, size=11.5)
pic(s, os.path.join(SHOTS, "sg_transparency_1280.png"), 7.9, 1.7, 4.8, 3.4)
caption(s, 7.9, 5.2, 4.8, "Transparency dashboard - the Panchayat's public ledger")
chip(s, 0.6, 6.05, 12.1, 0.55, "Live: smartgarbage.onrender.com  |  fully open to inspection today", fill=AMBER, fg=INK, size=13)

# --------------------------- slide 17 - Future work ---------------------------
s = prs.slides[16]
clear_body(s)
mile = [
    ("ESP32 on real bins", "OTA firmware channel already ships in the admin console"),
    ("Retrain on live pings", "model_retraining_job swaps the synthetic grid out"),
    ("Nightly route optimisation", "ETA + miss predictions blended into worker routes"),
    ("District rollout", "Multi-panchayat schema is already ward-scoped"),
]
chevrons(s, 0.6, 1.9, 12.1, 1.0, [m[0] for m in mile])
for i, (h, d) in enumerate(mile):
    x = 0.6 + i * 3.08
    c = card(s, x, 3.3, 2.85, 1.9, fill=WHITE, line=RGBColor(0xD8, 0xE4, 0xDC))
    t = s.shapes.add_textbox(Inches(x + 0.18), Inches(3.5), Inches(2.5), Inches(1.6))
    _tf(t, f"Step {i+1}", 11, AMBER, bold=True)
    t2 = s.shapes.add_textbox(Inches(x + 0.18), Inches(3.85), Inches(2.5), Inches(1.3))
    _tf(t2, d, 11.5, SLATE, line=1.12)
c = card(s, 0.6, 5.7, 12.1, 0.95, fill=MIST)
_tf(c, "Each step reuses what already ships - no rewrite, only new data and configuration.",
    13.5, DEEP, bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

# --------------------------- slide 18 - References (styled, kept textual) ---------------------------
s = prs.slides[17]
refs = []
for sh in s.shapes:
    if sh.has_text_frame and sh.text_frame.text.strip():
        txt = sh.text_frame.text.strip()
        if "25-09-2026" not in txt and len(txt) > 60:
            refs = [ln.strip() for ln in txt.split("\n") if ln.strip() and "References" not in ln and "Municipal" not in ln]
            break
clear_body(s)
# Precision fix: the template's ML references cite RandomForest, but the code
# (app/ml_model.py) uses HistGradientBoostingRegressor + IsolationForest.
refs = [r.replace("scikit-learn documentation - RandomForestRegressor, cross-validation.",
                  "scikit-learn - HistGradientBoostingRegressor (overflow ETA) & IsolationForest (anomaly detection), as used in app/ml_model.py.")
         .replace("Leo Breiman (2001), Random Forests, Machine Learning 45(1), 5-32.",
                  "Liu, Ting & Zhou (2008), Isolation Forest, AAAI - the anomaly model actually deployed.")
         for r in refs]
col1 = refs[: len(refs) // 2 + 1]
col2 = refs[len(refs) // 2 + 1:]
for j, colr in enumerate([col1, col2]):
    x = 0.7 + j * 6.25
    y = 1.6
    for i, r in enumerate(colr):
        t = s.shapes.add_textbox(Inches(x), Inches(y), Inches(5.9), Inches(0.9))
        _tf(t, "-  " + r, 12, INK, line=1.05, space_after=8)
        y += 0.95

# --------------------------- slide 19 - Thank you ---------------------------
s = prs.slides[18]
clear_body(s, keep_ph_types=("TITLE", "FTR", "DT", "SLDNUM"))
c = card(s, 2.2, 1.9, 8.9, 3.4, fill=DEEP)
_tf(c, "Thank You\nOpen Floor for Discussion", 34, WHITE, bold=True,
    align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
chip(s, 4.15, 5.7, 5.0, 0.6, "Live demo: smartgarbage.onrender.com", fill=AMBER, fg=INK, size=14)

prs.save(DST)
print("WROTE", DST, f"{os.path.getsize(DST)//1024} KB")
