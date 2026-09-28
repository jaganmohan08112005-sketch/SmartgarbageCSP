#!/usr/bin/env python3
"""Print-ready cue-card PDF of docs/PANEL_CHEATSHEET.md.

Layout: A4 landscape, two cards per page separated by a dashed cut line —
cut along it and you hold 16 cards (15 tough questions + the lightning
round). Reuses the Times New Roman font setup from generate_pdf.py.

Usage:  python report/generate_cheatsheet_cards.py
Output: report/PANEL_CHEATSHEET_CARDS.pdf
"""
import os
import re
import sys

from fpdf import FPDF

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SOURCE = os.path.join(ROOT, 'docs', 'PANEL_CHEATSHEET.md')
OUTPUT = os.path.join(HERE, 'PANEL_CHEATSHEET_CARDS.pdf')
FONT_DIR = 'C:/Windows/Fonts'

# Times New Roman on Windows ships these; anything else (emoji, arrows) is
# normalised below so no card ever prints a missing-glyph box.
_SANITISE = [
    ('🎤', ''), ('₹', 'Rs.'), ('→', '->'),
    ('“', '"'), ('”', '"'), ('‘', "'"), ('’', "'"),
]


def clean(text):
    for a, b in _SANITISE:
        text = text.replace(a, b)
    return text


def strip_md(text):
    """Remove inline markdown emphasis, keep the words."""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    return text


def parse_cards(md_text):
    """Return (main_cards, lightning_cards).

    main_cards: dicts with number, question, ref, body, hook.
    lightning_cards: dicts with label, body, ref.
    """
    main, lightning = [], []
    md_text, _, lightning_md = md_text.partition('### 15-second lightning round')

    # Questions are separated by the next '**N. "..."**' header.
    for m in re.finditer(
            r'^\*\*(\d+)\.\s+"(.+?)"\*\*\s*(\[[^\]]+\])?\s*\n(.*?)'
            r'(?=^\*\*\d+\.\s+"|\Z)', md_text, re.S | re.M):
        num, question, ref, rest = m.groups()
        hook = ''
        hm = re.search(r'\*\s*(Hook:.*?)\s*\*\s*$', rest, re.S)
        if hm:
            hook = strip_md(hm.group(1))
            rest = rest[:hm.start()].strip()
        rm = re.search(r'\[(§[^\]]+)\]\s*$', rest)
        if rm and not ref:
            ref, rest = rm.group(1), rest[:rm.start()].strip()
        main.append({'number': int(num), 'question': clean(question),
                     'ref': ref or '', 'body': clean(strip_md(rest)),
                     'hook': clean(hook)})

    for line in lightning_md.splitlines():
        line = line.strip()
        m = re.match(r'^-\s+\*\*(.+?)\*\*\s+(.*)$', line)
        if m:
            label, rest = m.group(1), m.group(2)
            ref = ''
            rm = re.search(r'\[(§[^\]]+)\]\s*$', rest)
            if rm:
                ref, rest = rm.group(1), rest[:rm.start()].strip()
            lightning.append({'label': label.rstrip('??. '), 'body': rest, 'ref': ref})
    return main, lightning


class CardPDF(FPDF):
    def __init__(self):
        super().__init__(orientation='L', unit='mm', format='A4')
        self.add_font('TNR', '', os.path.join(FONT_DIR, 'times.ttf'))
        self.add_font('TNR', 'B', os.path.join(FONT_DIR, 'timesbd.ttf'))
        self.add_font('TNR', 'I', os.path.join(FONT_DIR, 'timesi.ttf'))
        self.add_font('TNR', 'BI', os.path.join(FONT_DIR, 'timesbi.ttf'))
        self.set_auto_page_break(False)
        self.set_margins(0, 0, 0)

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font('TNR', 'I', 8)
        self.set_text_color(120, 120, 120)
        self.set_xy(16, 5)
        self.cell(0, 4, 'SmartGarbage - Panel Cheat-Sheet (cue cards, cut along the dashes)')
        self.set_text_color(0, 0, 0)

    def footer(self):
        self.set_font('TNR', '', 8)
        self.set_text_color(120, 120, 120)
        self.set_y(-9)
        self.cell(0, 5, f'{self.page_no()}/{{nb}}', align='C')
        self.set_text_color(0, 0, 0)


def draw_card(pdf, x, y, w, h, card):
    pdf.set_line_width(0.3)
    pdf.set_draw_color(70, 70, 70)
    pdf.rect(x, y, w, h)

    # Numbered badge + reference tag.
    pdf.set_font('TNR', 'B', 16)
    pdf.set_xy(x + 6, y + 5)
    pdf.cell(12, 8, f'{card["number"]:02d}')
    pdf.set_font('TNR', 'I', 9)
    pdf.set_text_color(90, 90, 90)
    if card['ref']:
        pdf.set_xy(x + w - 26, y + 5)
        pdf.cell(20, 8, card['ref'], align='R')
    pdf.set_text_color(0, 0, 0)

    # Question.
    pdf.set_font('TNR', 'B', 12.5)
    pdf.set_xy(x + 6, y + 14)
    pdf.multi_cell(w - 12, 6, card['question'])
    q_end = pdf.get_y()

    # Answer body.
    pdf.set_font('TNR', '', 10.5)
    pdf.set_xy(x + 6, q_end + 3)
    pdf.multi_cell(w - 12, 5.2, card['body'])
    body_end = pdf.get_y()

    # Hook line pinned near the card's bottom edge.
    if card['hook']:
        pdf.set_font('TNR', 'I', 10)
        pdf.set_xy(x + 6, y + h - 20)
        pdf.multi_cell(w - 12, 5, card['hook'])

    pdf.set_font('TNR', '', 8)
    pdf.set_text_color(120, 120, 120)
    pdf.set_xy(x + 6, y + h - 8)
    pdf.cell(0, 4, f'Card {card["number"]} of 15')
    pdf.set_text_color(0, 0, 0)


def draw_lightning_card(pdf, x, y, w, h, items):
    pdf.set_line_width(0.3)
    pdf.set_draw_color(70, 70, 70)
    pdf.rect(x, y, w, h)
    pdf.set_font('TNR', 'B', 12.5)
    pdf.set_xy(x + 6, y + 6)
    pdf.multi_cell(w - 12, 6, '15-second lightning round')
    yy = pdf.get_y() + 3
    for it in items:
        pdf.set_font('TNR', 'B', 10.5)
        pdf.set_xy(x + 6, yy)
        pdf.multi_cell(w - 12, 5.2, f'- {it["label"]}:')
        yy = pdf.get_y()
        pdf.set_font('TNR', '', 10.5)
        pdf.set_xy(x + 9, yy)
        pdf.multi_cell(w - 15, 5.2, f'{it["body"]}  {it["ref"]}')
        yy = pdf.get_y() + 2


def main():
    with open(SOURCE, encoding='utf-8') as f:
        md = f.read()
    main_cards, lightning = parse_cards(md)
    if len(main_cards) != 15:
        raise SystemExit(f'expected 15 question cards, parsed {len(main_cards)}')
    if len(lightning) < 4:
        raise SystemExit(f'expected >= 4 lightning items, parsed {len(lightning)}')

    pdf = CardPDF()
    pw, ph = pdf.w, pdf.h          # 297 x 210 landscape
    gap = 8
    margin = 10
    card_w = (pw - 2 * margin - gap) / 2
    card_h = ph - 2 * margin - 4   # leave room for header/footer

    cards = main_cards + [None]    # None = lightning card
    for i in range(0, len(cards), 2):
        pdf.add_page()
        pair = cards[i:i + 2]
        draw_card(pdf, margin, margin + 4, card_w, card_h, pair[0])
        # Dashed vertical cut line between the two cards.
        cx = margin + card_w + gap / 2
        pdf.set_dash_pattern(dash=2, gap=2)
        pdf.set_line_width(0.25)
        pdf.set_draw_color(150, 150, 150)
        pdf.line(cx, 6, cx, ph - 6)
        pdf.set_dash_pattern()
        if len(pair) > 1:
            if pair[1] is None:
                draw_lightning_card(pdf, margin + card_w + gap, margin + 4,
                                    card_w, card_h, lightning)
            else:
                draw_card(pdf, margin + card_w + gap, margin + 4, card_w, card_h,
                          pair[1])

    pdf.output(OUTPUT)
    print(f'OK {OUTPUT} pages={pdf.page_no()} cards={len(cards)} '
          f'lightning={len(lightning)}')


if __name__ == '__main__':
    sys.exit(main())
