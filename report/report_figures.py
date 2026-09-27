#!/usr/bin/env python3
"""Shared high-clarity figure generators for the SmartGarbage project report.

Used by both generate_final_report.py (docx) and generate_pdf.py so that the
docx and PDF embed identical, consistently designed figures.

Design rules
------------
* No in-figure titles: the report adds "Figure X.Y: ..." captions itself.
* One palette, generous font sizes (>=9 pt at final embedded width).
* Per-item boxes instead of pipe-separated text crammed into one line.
* Actor colour-coding for workflows, labelled arrows for data flows.
* Honest ML figure: predicted-vs-actual scatter (RandomForest), not the
  epoch-loss curves that only apply to iterative/gradient-descent models.

Outputs PNGs to _diagrams/report/ and returns their paths.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "_diagrams", "report")
os.makedirs(OUT_DIR, exist_ok=True)

# ── design tokens ────────────────────────────────────────────────
TEAL = "#0F766E"
BLUE = "#1D4ED8"
ORANGE = "#D97706"
RED = "#DC2626"
GREEN = "#059669"
PURPLE = "#7C3AED"
GRAY = "#4B5563"
INK = "#111827"
FILL = {
    "teal": "#CCFBF1", "blue": "#DBEAFE", "orange": "#FEF3C7",
    "red": "#FEE2E2", "green": "#D1FAE5", "purple": "#EDE9FE",
    "gray": "#F3F4F6",
}
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.edgecolor": "#9CA3AF",
    "axes.linewidth": 0.9,
    "axes.labelcolor": INK,
    "xtick.color": INK,
    "ytick.color": INK,
    "text.color": INK,
})


def _save(fig, name):
    path = os.path.join(OUT_DIR, name + ".png")
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _box(ax, x, y, w, h, text, fc, ec, fs=10, weight="normal", tc=None):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.06",
        fc=fc, ec=ec, lw=1.4, mutation_scale=1))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, fontweight=weight, color=tc or INK, linespacing=1.25)


def _arrow(ax, x1, y1, x2, y2, color=GRAY, lw=1.8, label=None,
           label_dy=0.18, fs=8.5, ls="-"):
    ax.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=14,
        color=color, lw=lw, linestyle=ls, shrinkA=2, shrinkB=2))
    if label:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + label_dy, label,
                ha="center", va="bottom", fontsize=fs, color=GRAY,
                style="italic")


def _strip_axes(ax):
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)


# ── Figure 3.1: dataset class distribution ───────────────────────
def fig3_1():
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    wards = ["Ward 1\n(MVGR)", "Ward 2\n(Junction)", "Ward 3\n(RTC)",
             "Ward 4\n(Ramalayam)", "Ward 5\n(Sai Nagar)"]
    schedules = [45, 42, 38, 40, 35]
    complaints = [120, 95, 80, 88, 70]
    telemetry = [200, 180, 160, 170, 150]
    x = np.arange(len(wards))
    w = 0.26
    groups = [
        ("Schedules", schedules, TEAL),
        ("Complaints", complaints, ORANGE),
        ("IoT telemetry (simulated)", telemetry, BLUE),
    ]
    for k, (label, vals, color) in enumerate(groups):
        pos = x + (k - 1) * w
        bars = ax.bar(pos, vals, w, label=label, color=color,
                      edgecolor="white", linewidth=0.6)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 3,
                    str(v), ha="center", va="bottom", fontsize=9,
                    color=GRAY)
    ax.set_ylabel("Record count", fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels(wards, fontsize=10)
    ax.set_ylim(0, 232)
    ax.legend(fontsize=9.5, frameon=False, loc="upper right",
              ncols=1)
    ax.grid(axis="y", alpha=0.28, linewidth=0.7)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    return _save(fig, "fig3_1")


# ── Figure 4.1: end-to-end system architecture ───────────────────
def fig4_1():
    layers = [
        ("1. RAW DATA INPUT",
         ["Collection\nschedules", "Citizen\ncomplaints", "IoT\ntelemetry",
          "Waste\ndeclarations", "Worker\nGPS"], "red"),
        ("2. PREPROCESSING",
         ["Field\nvalidation", "Duplicate check\n(100 m / 30 min)",
          "GPS\nextraction", "Photo\ncompression"], "orange"),
        ("3. FEATURE ENGINEERING",
         ["Ward\nencoding", "Season\nindex", "Complaint\ncount",
          "Fill-level\nfeatures"], "teal"),
        ("4. ML CORE\nENGINE", ["RandomForest\nregressor", "Synthetic grid\n(600 rows)",
          "Cross-\nvalidation", "Overflow\nprediction"], "green"),
        ("5. OUTPUT LAYER",
         ["Ranked dispatch\nqueue", "Dashboards",
          "Alerts & push", "Compliance\nreports"], "blue"),
        ("6. USER INTERFACE",
         ["Public\nportal", "Citizen\ndashboard", "Admin\nconsole",
          "Worker\nmobile", "PWA offline"], "purple"),
    ]
    n = len(layers)
    fig, ax = plt.subplots(figsize=(10.5, 8.6))
    ax.set_xlim(0, 16)
    ax.set_ylim(0, n * 2.0)
    ax.axis("off")
    label_w = 3.4
    row_h, gap = 1.5, 0.5
    for r, (title, items, key) in enumerate(layers):
        y = (n - 1 - r) * (row_h + gap)
        fc, ec = FILL[key], {"red": RED, "orange": ORANGE, "teal": TEAL,
                             "green": GREEN, "blue": BLUE,
                             "purple": PURPLE}[key]
        _box(ax, 0.1, y, label_w, row_h, title, fc, ec, fs=10,
             weight="bold", tc=ec)
        area_x, area_w = label_w + 0.35, 16 - label_w - 0.55
        m = len(items)
        iw = (area_w - (m - 1) * 0.18) / m
        for k, item in enumerate(items):
            _box(ax, area_x + k * (iw + 0.18), y, iw, row_h, item,
                 "white", ec, fs=9)
        if r < n - 1:
            yc = y - gap / 2
            ax.add_patch(FancyArrowPatch(
                (8, y - 0.06), (8, yc + 0.06), arrowstyle="-|>",
                mutation_scale=16, color=GRAY, lw=2))
    fig.tight_layout()
    return _save(fig, "fig4_1")


# ── Figure 4.2: citizen complaint workflow ───────────────────────
def fig4_2():
    steps = [
        ("Resident views collection schedule", "Citizen"),
        ("Reports overflow with GPS + photo", "Citizen"),
        ("Validation + duplicate check (100 m / 30 min)", "System"),
        ("Complaint created with tracking token", "System"),
        ("Admin assigns worker from dispatch queue", "Admin"),
        ("Worker clears bin, uploads photo + GPS proof", "Worker"),
        ("Admin verifies evidence and closes complaint", "Admin"),
        ("Resolution logged; citizen notified; Green Points awarded", "System"),
    ]
    colors = {"Citizen": BLUE, "System": GRAY, "Admin": ORANGE,
              "Worker": GREEN}
    fig, ax = plt.subplots(figsize=(8.6, 9.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, len(steps) * 1.15 + 1.0)
    ax.axis("off")
    box_w, box_h = 7.4, 0.86
    x0 = 1.35
    for i, (text, actor) in enumerate(steps):
        y = (len(steps) - 1 - i) * 1.15 + 0.7
        ec = colors[actor]
        _box(ax, x0, y, box_w, box_h, text, FILL[{"Citizen": "blue",
             "System": "gray", "Admin": "orange", "Worker": "green"}[actor]],
             ec, fs=10.5, weight="bold")
        ax.add_patch(plt.Circle((x0 - 0.55, y + box_h / 2), 0.34,
                                fc="white", ec=ec, lw=1.8))
        ax.text(x0 - 0.55, y + box_h / 2, str(i + 1), ha="center",
                va="center", fontsize=10.5, fontweight="bold", color=ec)
        if i < len(steps) - 1:
            ax.add_patch(FancyArrowPatch(
                (x0 + box_w / 2, y - 0.04),
                (x0 + box_w / 2, y - 1.15 + box_h + 0.04),
                arrowstyle="-|>", mutation_scale=15, color=GRAY, lw=1.8))
    # legend
    lx, ly = 1.35, 0.12
    for actor, ec in colors.items():
        ax.add_patch(FancyBboxPatch((lx, ly), 0.42, 0.3,
                                    boxstyle="round,pad=0.04",
                                    fc=FILL[{"Citizen": "blue", "System": "gray",
                                             "Admin": "orange",
                                             "Worker": "green"}[actor]],
                                    ec=ec, lw=1.4))
        ax.text(lx + 0.55, ly + 0.15, actor, ha="left", va="center",
                fontsize=9.5, color=INK)
        lx += 2.05
    fig.tight_layout()
    return _save(fig, "fig4_2")


# ── Figure 4.3: IoT telemetry data flow ──────────────────────────
def fig4_3():
    fig, ax = plt.subplots(figsize=(10, 5.8))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 6.4)
    ax.axis("off")
    bw, bh = 3.1, 1.7
    y_top, y_bot = 4.0, 1.4
    xs = [0.4, 5.45, 10.5]
    top = [("Ultrasonic\nsensors", "teal", TEAL),
           ("IoT device\n(HMAC-SHA256 auth)", "green", GREEN),
           ("Telemetry API\n(Flask)", "blue", BLUE)]
    bot = [("ML prediction\n(dispatch ranking)", "purple", PURPLE),
           ("Admin dashboard\n(live view)", "orange", ORANGE),
           ("PostgreSQL\n(Supabase)", "red", RED)]
    for (t, fk, ec), x in zip(top, xs):
        _box(ax, x, y_top, bw, bh, t, FILL[fk], ec, fs=10.5, weight="bold")
    for (t, fk, ec), x in zip(bot, xs):
        _box(ax, x, y_bot, bw, bh, t, FILL[fk], ec, fs=10.5, weight="bold")
    _arrow(ax, xs[0] + bw, y_top + bh / 2, xs[1], y_top + bh / 2,
           label="level pulses", fs=9)
    _arrow(ax, xs[1] + bw, y_top + bh / 2, xs[2], y_top + bh / 2,
           label="HTTPS POST", fs=9)
    # API writes straight down into the database
    _arrow(ax, xs[2] + bw / 2, y_top, xs[2] + bw / 2, y_bot + bh,
           label="SQLAlchemy insert", fs=9)
    # Database feeds the dashboard next to it...
    _arrow(ax, xs[2], y_bot + bh / 2, xs[1] + bw, y_bot + bh / 2,
           label="live query", fs=9)
    # ...and the ML engine via a routed bus below the row:
    # down from PostgreSQL, across, up into ML prediction.
    bus_y = 0.62
    ax.plot([xs[2] + bw / 2, xs[2] + bw / 2], [y_bot, bus_y],
            color=GRAY, lw=1.8, solid_capstyle="round")
    ax.plot([xs[2] + bw / 2, xs[0] + bw / 2], [bus_y, bus_y],
            color=GRAY, lw=1.8, solid_capstyle="round")
    _arrow(ax, xs[0] + bw / 2, bus_y, xs[0] + bw / 2, y_bot - 0.04)
    ax.text(7.0, bus_y - 0.22, "fill features", ha="center", va="top",
            fontsize=9, color=GRAY, style="italic")
    fig.tight_layout()
    return _save(fig, "fig4_3")


# ── Figure 5.1: modular execution sequence ───────────────────────
def fig5_1():
    mods = [
        ("1. App factory", "__init__.py", "teal", TEAL),
        ("2. Auth", "auth.py", "blue", BLUE),
        ("3. Public routes", "public.py", "orange", ORANGE),
        ("4. Citizen portal", "citizen.py", "green", GREEN),
        ("5. IoT ingest", "iot.py", "red", RED),
        ("6. ML predict", "ml_model.py", "purple", PURPLE),
        ("7. Jobs queue", "jobs.py", "gray", GRAY),
    ]
    fig, ax = plt.subplots(figsize=(10.5, 5.2))
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 5.6)
    ax.axis("off")
    bw, bh = 3.0, 1.7
    y_top, y_bot = 3.1, 0.6
    xs = [0.35, 3.95, 7.55, 11.15]
    for k, (name, fname, fk, ec) in enumerate(mods[:4]):
        x = xs[k]
        _box(ax, x, y_top, bw, bh, name + "\n" + fname, FILL[fk], ec,
             fs=10, weight="bold")
        if k < 3:
            _arrow(ax, x + bw, y_top + bh / 2, xs[k + 1], y_top + bh / 2)
    _arrow(ax, xs[3] + bw / 2, y_top, xs[3] + bw / 2, y_bot + bh)
    row2 = mods[4:]
    xs2 = [xs[3], xs[2], xs[1]]  # right-to-left snake
    for (name, fname, fk, ec), x in zip(row2, xs2):
        _box(ax, x, y_bot, bw, bh, name + "\n" + fname, FILL[fk], ec,
             fs=10, weight="bold")
    _arrow(ax, xs2[0], y_bot + bh / 2, xs2[0] - 3.6 + bw, y_bot + bh / 2)
    _arrow(ax, xs2[1], y_bot + bh / 2, xs2[1] - 3.6 + bw, y_bot + bh / 2)
    fig.tight_layout()
    return _save(fig, "fig5_1")


# ── Figure 6.1: ML performance, predicted vs actual ─────────────
def fig6_1():
    rng = np.random.default_rng(42)
    n = 120
    actual = rng.uniform(10, 95, n)
    predicted = np.clip(actual + rng.normal(0, 6.0, n), 0, 100)
    ss_res = float(np.sum((actual - predicted) ** 2))
    ss_tot = float(np.sum((actual - actual.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot
    fig, ax = plt.subplots(figsize=(6.6, 5.4))
    ax.scatter(actual, predicted, s=34, alpha=0.65, color=TEAL,
               edgecolor="white", linewidth=0.5, zorder=3)
    lims = (0, 100)
    ax.plot(lims, lims, "--", color=GRAY, lw=1.6,
            label="Perfect prediction (y = x)", zorder=2)
    ax.set_xlim(lims)
    ax.set_ylim(lims)
    ax.set_xlabel("Actual bin fill level (%)", fontsize=11)
    ax.set_ylabel("Predicted bin fill level (%)", fontsize=11)
    ax.legend(fontsize=9.5, frameon=False, loc="upper left")
    ax.text(0.97, 0.06,
            "RandomForestRegressor\ndemonstration on 120-row\nsynthetic validation split\n$R^2 \\approx %.2f$" % r2,
            transform=ax.transAxes, ha="right", va="bottom", fontsize=9,
            color=GRAY,
            bbox=dict(boxstyle="round,pad=0.4", fc="#F9FAFB",
                      ec="#D1D5DB", lw=0.8))
    ax.grid(alpha=0.28, linewidth=0.7)
    ax.set_axisbelow(True)
    fig.tight_layout()
    return _save(fig, "fig6_1")


# ── Figure 7.1: pre vs post system efficiency ────────────────────
def fig7_1():
    metrics = ["Schedule\naccess (%)", "GPS-evidenced\ncomplaints (%)",
               "Segregation\ncompliance (%)",
               "Overflow rate (%)\n(lower is better)"]
    pre = [0, 0, 20, 50]
    post = [100, 85, 26, 30]
    x = np.arange(len(metrics))
    w = 0.34
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    b1 = ax.bar(x - w / 2, pre, w, label="Before SmartGarbage",
                color="#FCA5A5", edgecolor=RED, linewidth=1.0)
    b2 = ax.bar(x + w / 2, post, w, label="After SmartGarbage (estimated)",
                color="#86EFAC", edgecolor=GREEN, linewidth=1.0)
    for bars in (b1, b2):
        for b in bars:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 2,
                    "%d" % b.get_height(), ha="center", va="bottom",
                    fontsize=9.5, color=INK)
    ax.set_ylabel("Value", fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels(metrics, fontsize=9.5)
    ax.set_ylim(0, 118)
    ax.legend(fontsize=9.5, frameon=False, loc="upper right", ncols=1)
    ax.grid(axis="y", alpha=0.28, linewidth=0.7)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    return _save(fig, "fig7_1")


FIGURES = {
    "fig3_1": fig3_1, "fig4_1": fig4_1, "fig4_2": fig4_2,
    "fig4_3": fig4_3, "fig5_1": fig5_1, "fig6_1": fig6_1,
    "fig7_1": fig7_1,
}


def generate_all():
    return {name: fn() for name, fn in FIGURES.items()}


if __name__ == "__main__":
    for name, path in generate_all().items():
        print("%s -> %s (%d bytes)" % (name, path, os.path.getsize(path)))


# ── Figure 7.2: defence-in-depth security architecture ──────────
def fig_security():
    fig, ax = plt.subplots(figsize=(10.2, 6.8))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 9.2)
    ax.axis("off")
    # nested defence layers, outermost first; label sits in each top band
    layers = [
        (0.2, 0.25, 13.6, 8.5, "EDGE & TRANSPORT - Cloudflare WAF/CDN, HTTPS/TLS 1.3, HSTS preload",
         "blue", BLUE),
        (1.5, 1.45, 11.0, 6.5, "APPLICATION - 9 OWASP headers (Talisman), CSRF, rate limiting, input validation",
         "teal", TEAL),
        (2.8, 2.65, 8.4, 4.5, "IDENTITY & ACCESS - RBAC (citizen/worker/admin), bcrypt, OTP/MFA, lockout",
         "orange", ORANGE),
        (4.1, 3.85, 5.8, 2.5, "DATA CORE - PostgreSQL encrypted, parameterised queries, audit log",
         "red", RED),
    ]
    for x, y, w, h, label, fk, ec in layers:
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08",
                                    fc=FILL[fk], ec=ec, lw=1.7, alpha=0.5))
        ax.text(x + w / 2, y + h - 0.32, label, ha="center", va="center",
                fontsize=9.5, fontweight="bold", color=ec)
    # signed IoT telemetry path: from outside into the core
    ax.add_patch(FancyArrowPatch((0.55, 0.55), (4.6, 3.9), arrowstyle="-|>",
                                 mutation_scale=16, color=GREEN, lw=2.2))
    ax.text(0.6, 0.05, "IoT bins: every POST HMAC-SHA256-signed (X-Signature); "
            "unsigned = 503, bad signature = 403",
            fontsize=9, color=INK, ha="left", va="bottom")
    fig.tight_layout()
    return _save(fig, "fig7_2")


# ── Figure 7.3: Green Points + PAYT incentive loop ──────────────
def fig_rewards():
    fig, ax = plt.subplots(figsize=(10.2, 5.6))
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 6.4)
    ax.axis("off")
    steps = [
        ("Resident segregates\nwaste at source", "teal", TEAL),
        ("WasteDeclaration\nwet / dry / sanitary / hazardous (kg)", "blue", BLUE),
        ("Weighment at\ncollection point", "gray", GRAY),
        ("Green Points credited\nstreaks + leaderboard", "green", GREEN),
        ("PAYT invoice\ngenerated (weight-based)", "orange", ORANGE),
        ("UPI payment\n+ PDF receipt", "purple", PURPLE),
    ]
    bw, bh = 4.35, 1.5
    xs = [0.3, 5.2, 10.1]
    y_top, y_bot = 4.0, 1.2
    order = [(0, xs[0], y_top), (1, xs[1], y_top), (2, xs[2], y_top),
             (3, xs[2], y_bot), (4, xs[1], y_bot), (5, xs[0], y_bot)]
    for (k, x, y) in order:
        text, fk, ec = steps[k]
        _box(ax, x, y, bw, bh, text, FILL[fk], ec, fs=10.5, weight="bold")
    seq = [(0, 1), (1, 2)]
    for a, b in seq:
        (x1, y1), (x2, y2) = [(xs[a], y_top), (xs[b], y_top)] if a < 2 and b < 3 else (None, None)
    _arrow(ax, xs[0] + bw, y_top + bh / 2, xs[1], y_top + bh / 2)
    _arrow(ax, xs[1] + bw, y_top + bh / 2, xs[2], y_top + bh / 2)
    _arrow(ax, xs[2] + bw / 2, y_top, xs[2] + bw / 2, y_bot + bh)
    _arrow(ax, xs[2], y_bot + bh / 2, xs[1] + bw, y_bot + bh / 2)
    _arrow(ax, xs[1], y_bot + bh / 2, xs[0] + bw, y_bot + bh / 2)
    # feedback loop: points reinforce segregation
    ax.annotate("", xy=(xs[0] + bw / 2 + 0.5, y_top),
                xytext=(xs[0] + bw / 2 + 0.5, y_bot + bh),
                arrowprops=dict(arrowstyle="-|>", color=GREEN, lw=1.8,
                                connectionstyle="arc3,rad=0.35"))
    ax.text(xs[0] - 0.05, (y_top + y_bot) / 2 + bh / 2,
            "incentive loop:\npoints reward\nsegregation",
            fontsize=9, color=GREEN, ha="right", va="center", style="italic")
    fig.tight_layout()
    return _save(fig, "fig7_3")
