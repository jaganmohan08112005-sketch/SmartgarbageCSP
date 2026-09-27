#!/usr/bin/env python3
"""
Generate a professionally formatted, publication-grade Documentation.pdf
for SmartGarbage Chintalavalasa following MVGR B.Tech Project Report guidelines.
Uses fpdf2 with embedded diagrams, structured tables, and team details.
"""

import os
from fpdf import FPDF

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_PDF = os.path.join(BASE_DIR, "Documentation.pdf")
OUT_COMMUNITY_PDF = os.path.join(BASE_DIR, "SmartGarbage_Community_Project_Report(M).pdf")
DIAG_DIR = os.path.join(BASE_DIR, "_diagrams")
FONT_DIR = "C:/Windows/Fonts"

class AcademicReportPDF(FPDF):
    def __init__(self):
        super().__init__('P', 'mm', 'A4')
        self.set_auto_page_break(auto=True, margin=25)
        self.set_margins(left=25, top=25, right=25)

        times_regular = os.path.join(FONT_DIR, 'times.ttf')
        times_bold = os.path.join(FONT_DIR, 'timesbd.ttf')
        times_italic = os.path.join(FONT_DIR, 'timesi.ttf')
        times_bold_italic = os.path.join(FONT_DIR, 'timesbi.ttf')

        if os.path.exists(times_regular) and os.path.exists(times_bold):
            self.add_font('TimesNewRoman', '', times_regular)
            self.add_font('TimesNewRoman', 'B', times_bold)
            self.add_font('TimesNewRoman', 'I', times_italic if os.path.exists(times_italic) else times_regular)
            self.add_font('TimesNewRoman', 'BI', times_bold_italic if os.path.exists(times_bold_italic) else times_bold)
            self.font_family_name = 'TimesNewRoman'
        else:
            self.font_family_name = 'Helvetica'

    def header(self):
        if self.page_no() > 1:
            self.set_font(self.font_family_name, 'I', 8)
            self.set_text_color(100, 100, 100)
            self.cell(self.epw, 8, 'SmartGarbage Chintalavalasa — Community Project Report', 0, 0, 'C')
            self.ln(9)
            self.set_draw_color(220, 220, 220)
            self.line(25, self.get_y(), 185, self.get_y())
            self.ln(4)
            self.set_text_color(0, 0, 0)

    def footer(self):
        if self.page_no() > 1:
            self.set_y(-18)
            self.set_font(self.font_family_name, '', 9)
            self.set_text_color(128, 128, 128)
            self.cell(self.epw, 10, f'Page {self.page_no()}', 0, 0, 'C')
            self.set_text_color(0, 0, 0)

    def chapter_heading(self, text):
        """16pt Bold ALL CAPS"""
        self.add_page()
        self.ln(5)
        self.set_font(self.font_family_name, 'B', 16)
        self.set_text_color(0, 51, 102)  # Deep Navy Accent
        self.multi_cell(self.epw, 9, text.upper())
        self.ln(2)
        self.set_draw_color(0, 51, 102)
        self.set_line_width(0.6)
        self.line(25, self.get_y(), 185, self.get_y())
        self.set_line_width(0.2)
        self.ln(6)
        self.set_text_color(0, 0, 0)

    def section_heading(self, text):
        """14pt Bold"""
        self.ln(4)
        self.set_font(self.font_family_name, 'B', 13)
        self.set_text_color(30, 30, 30)
        self.multi_cell(self.epw, 8, text)
        self.ln(2)

    def subsection_heading(self, text):
        """12pt Bold"""
        self.ln(3)
        self.set_font(self.font_family_name, 'B', 11)
        self.set_text_color(50, 50, 50)
        self.multi_cell(self.epw, 7, text)
        self.ln(1)

    def body_text(self, text):
        """11pt Justified"""
        self.set_font(self.font_family_name, '', 11)
        self.set_text_color(20, 20, 20)
        self.multi_cell(self.epw, 6, text, align='J')
        self.ln(2)

    def body_bullet(self, text):
        self.set_font(self.font_family_name, '', 11)
        self.set_text_color(20, 20, 20)
        self.cell(6, 6, '•', 0, 0, 'C')
        self.multi_cell(self.epw - 6, 6, text, align='J')
        self.ln(1)

    def centered_text(self, text, size=11, bold=False, color=(0,0,0)):
        self.set_font(self.font_family_name, 'B' if bold else '', size)
        self.set_text_color(*color)
        self.multi_cell(self.epw, size * 0.55, text, align='C')
        self.set_text_color(0, 0, 0)

    def right_text(self, text, size=11, bold=False):
        self.set_font(self.font_family_name, 'B' if bold else '', size)
        self.multi_cell(self.epw, size * 0.55, text, align='R')

    def caption_text(self, text):
        """10pt bold italic centered"""
        self.ln(2)
        self.set_font(self.font_family_name, 'BI', 10)
        self.set_text_color(60, 60, 60)
        self.multi_cell(self.epw, 5, text, align='C')
        self.set_text_color(0, 0, 0)
        self.ln(4)

    def add_image_centered(self, path, w=140):
        if os.path.exists(path):
            self.ln(2)
            x = (210 - w) / 2
            self.image(path, x=x, w=w)
            self.ln(2)

    def render_table(self, headers, rows, col_widths=None, caption=None):
        if col_widths is None:
            n = len(headers)
            col_widths = [160 / n] * n

        self.set_font(self.font_family_name, 'B', 10)
        self.set_fill_color(230, 240, 250)
        self.set_draw_color(180, 180, 180)

        # Header
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 8, str(h), border=1, align='C', fill=True)
        self.ln()

        # Rows
        self.set_font(self.font_family_name, '', 9.5)
        for r_idx, row in enumerate(rows):
            # Calculate required height
            line_counts = []
            for ci, val in enumerate(row):
                lines = self.multi_cell(col_widths[ci] - 2, 5, str(val), split_only=True)
                line_counts.append(len(lines))
            max_lines = max(line_counts) if line_counts else 1
            row_h = max(7, max_lines * 5.2 + 2)

            # Check page overflow
            if self.get_y() + row_h > 270:
                self.add_page()
                self.set_font(self.font_family_name, 'B', 10)
                self.set_fill_color(230, 240, 250)
                for i, h in enumerate(headers):
                    self.cell(col_widths[i], 8, str(h), border=1, align='C', fill=True)
                self.ln()
                self.set_font(self.font_family_name, '', 9.5)

            x_start = self.get_x()
            y_start = self.get_y()

            for ci, val in enumerate(row):
                x = x_start + sum(col_widths[:ci])
                self.set_xy(x, y_start)
                self.cell(col_widths[ci], row_h, '', border=1)
                self.set_xy(x + 1, y_start + 1.5)
                self.multi_cell(col_widths[ci] - 2, 5, str(val), align='L')

            self.set_xy(x_start, y_start + row_h)

        if caption:
            self.caption_text(caption)
        else:
            self.ln(3)


def generate_pdf():
    pdf = AcademicReportPDF()
    pdf.set_title("SmartGarbage Chintalavalasa - Community Project Report")
    pdf.set_author("Mopada Jaganmohan, Latchupatula Reshma, Pati Narasimha Murthy, Kada Augusttn Paul Kumar")

    # ════════════════════════════════════════════════════════════════════
    # TITLE PAGE
    # ════════════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.ln(10)
    pdf.centered_text('COMMUNITY PROJECT REPORT', 14, True, color=(0, 51, 102))
    pdf.ln(4)
    pdf.centered_text('SMARTGARBAGE CHINTALAVALASA', 18, True, color=(0, 102, 51))
    pdf.centered_text('Community-Based Smart Waste Management\nand Digital Governance System', 13, False)
    pdf.ln(8)

    pdf.centered_text('Submitted by', 11, False)
    pdf.ln(2)

    students = [
        ('MOPADA JAGANMOHAN', '2433144441'),
        ('LATCHUPATULA RESHMA', '24331A4434'),
        ('PATI NARASIMHA MURTHY', '2433144446'),
        ('KADA AUGUSTTN PAUL KUMAR', '24331A4426'),
    ]
    for name, reg in students:
        pdf.centered_text(f'{name}  ({reg})', 11, True)

    pdf.ln(6)
    pdf.centered_text('In partial fulfillment for the award of the degree of', 11)
    pdf.ln(2)
    pdf.centered_text('BACHELOR OF TECHNOLOGY', 13, True)
    pdf.centered_text('IN', 11)
    pdf.centered_text('COMPUTER SCIENCE & ENGINEERING', 13, True)
    pdf.centered_text('(Data Science)', 11, True)
    pdf.ln(6)

    pdf.centered_text('Under the esteemed Guidance of', 11)
    pdf.ln(2)
    pdf.centered_text('Mrs. S. Nikhila', 13, True)
    pdf.centered_text('Assistant Professor', 11)
    pdf.ln(6)

    logo_path = os.path.join(DIAG_DIR, 'mvgr_logo.png')
    if os.path.exists(logo_path):
        pdf.add_image_centered(logo_path, 45)
        pdf.ln(2)

    pdf.centered_text('DEPARTMENT OF DATA ENGINEERING', 12, True, color=(0, 51, 102))
    pdf.centered_text('MAHARAJ VIJAYARAM GAJAPATHI RAJ COLLEGE OF ENGINEERING (Autonomous)', 10, True)
    pdf.centered_text('(Approved by AICTE, New Delhi, and permanently affiliated to JNTUGV, Vizianagaram)', 8.5)
    pdf.centered_text('Listed u/s 2(f) & 12(B) of UGC Act 1956.', 8.5)
    pdf.centered_text('Vijayaram Nagar Campus, Chintalavalasa, Vizianagaram-535005, Andhra Pradesh', 8.5)
    pdf.ln(3)
    pdf.centered_text('October, 2025', 11, True)

    # ════════════════════════════════════════════════════════════════════
    # CERTIFICATE
    # ════════════════════════════════════════════════════════════════════
    pdf.chapter_heading('CERTIFICATE')
    pdf.body_text(
        'This is to certify that the project entitled "SmartGarbage Chintalavalasa — Community-Based Smart Waste Management '
        'and Digital Governance System" is the bonafide work carried out by Mopada Jaganmohan (2433144441), Latchupatula Reshma '
        '(24331A4434), Pati Narasimha Murthy (2433144446), and Kada Augusttn Paul Kumar (24331A4426), of B.Tech V Sem CSE-DS, '
        'M.V.G.R. College of Engineering (Autonomous), Vizianagaram, during the academic year 2025-2026, in partial fulfilment '
        'of the requirements for the award of the Degree of Bachelor of Technology and that the project has not formed the basis '
        'for the award previously of any degree or any other similar title.'
    )
    pdf.ln(20)

    # Signature blocks side by side
    y_sig = pdf.get_y()
    pdf.set_font(pdf.font_family_name, 'B', 11)
    pdf.set_xy(25, y_sig)
    pdf.multi_cell(75, 5, "Signature of Project Guide\n\n\nMrs. S. Nikhila\nAssistant Professor\nDepartment of Data Engineering")

    pdf.set_xy(110, y_sig)
    pdf.multi_cell(75, 5, "Signature of Head of Department\n\n\nDr. Jyothi\nHead of the Department\nDepartment of Data Engineering")

    # ════════════════════════════════════════════════════════════════════
    # DECLARATION
    # ════════════════════════════════════════════════════════════════════
    pdf.chapter_heading('DECLARATION')
    pdf.body_text(
        'We hereby declare that the work done on the dissertation entitled "SmartGarbage Chintalavalasa — Community-Based '
        'Smart Waste Management and Digital Governance System" has been carried out by us and submitted in partial fulfilment '
        'for the award of credits in Bachelor of Technology in Computer Science and Engineering (Data Science) of M.V.G.R '
        'College of Engineering (Autonomous) and affiliated to JNTUGV, Vizianagaram. The various contents incorporated in '
        'the dissertation have not been submitted for the award of any degree of any other institution or university.'
    )
    pdf.ln(10)
    for n, r in students:
        pdf.body_text(f'• {n} ({r})')

    # ════════════════════════════════════════════════════════════════════
    # ACKNOWLEDGEMENT
    # ════════════════════════════════════════════════════════════════════
    pdf.chapter_heading('ACKNOWLEDGEMENT')
    pdf.body_text(
        'We express our sincere gratitude to our project guide, Mrs. S. Nikhila (Assistant Professor), for her invaluable '
        'guidance and support as our mentor throughout the project. Her unwavering commitment to excellence and constructive '
        'feedback motivated us to achieve our project goals.'
    )
    pdf.body_text(
        'Additionally, we extend our thanks to Prof. P.S. Sitharama Raju (Director), Dr. Y.M.C. Shekar (Principal), and '
        'Dr. Jyothi (Head of the Department) for their unwavering support and assistance, which were instrumental in the '
        'successful completion of the project.'
    )
    pdf.body_text(
        'We also acknowledge the dedicated assistance provided by all the staff members in the Department of Data Engineering. '
        'Finally, we appreciate the contributions of all those who directly or indirectly contributed to the successful execution of this endeavor.'
    )
    pdf.ln(8)
    for n, r in students:
        pdf.right_text(f'{n} ({r})', 10, True)

    # ════════════════════════════════════════════════════════════════════
    # ABSTRACT
    # ════════════════════════════════════════════════════════════════════
    pdf.chapter_heading('ABSTRACT')
    pdf.body_text(
        'Rapid urbanisation and population growth in Indian gram panchayats have outpaced the capacity of conventional '
        'waste-management systems, leading to overflowing bins, missed collections, and a lack of transparency between '
        'residents and municipal authorities. This project presents SmartGarbage Chintalavalasa — a free, open-source, AI-powered '
        'web portal designed to digitise and streamline solid-waste management for the five residential wards of Chintalavalasa '
        'Gram Panchayat in Vizianagaram District, Andhra Pradesh.'
    )
    pdf.body_text(
        'The portal is built on a Python/Flask backend with a Supabase (PostgreSQL) database, deployed on Render with Cloudflare '
        'CDN. It provides residents with waste-collection schedules, a missed-pickup reporting system with GPS and photographic '
        'evidence, real-time complaint tracking, a gamified Green Points reward system, and a Pay-As-You-Throw (PAYT) billing module. '
        'IoT-enabled smart bins transmit fill-level telemetry in real time, and a scikit-learn regression model predicts bin overflow '
        'probability to enable proactive dispatch.'
    )
    pdf.body_text(
        'Key innovations include: (i) a Progressive Web App (PWA) with an offline report queue that auto-syncs when connectivity resumes, '
        '(ii) a dual-language interface supporting English and Telugu, (iii) government-grade security headers matching GOV.UK standards, '
        '(iv) 81 ARIA accessibility attributes exceeding WCAG 2.1 AA requirements, and (v) a live civic-impact dashboard with ward-by-ward '
        'performance rankings. The system operates entirely on free-tier infrastructure — zero hosting costs, zero paid API dependencies — '
        'making it replicable by any gram panchayat in India.'
    )
    pdf.body_text(
        'Testing across 60+ automated unit and integration tests, plus Playwright end-to-end tests, confirms reliability. Comparative '
        'analysis against GOV.UK, VA.gov, and SBM Urban shows SmartGarbage matches or exceeds the feature set of national government '
        'portals at a fraction of the codebase size. The portal serves as a scalable, replicable model for community-driven digital '
        'governance in rural India.'
    )
    pdf.ln(2)
    pdf.set_font(pdf.font_family_name, 'B', 10)
    pdf.multi_cell(0, 6, "Keywords: Waste management, Flask, Supabase, IoT, Progressive Web App, Green Points, PAYT billing, civic technology, Swachh Bharat Mission, accessibility")

    # ════════════════════════════════════════════════════════════════════
    # TABLE OF CONTENTS
    # ════════════════════════════════════════════════════════════════════
    pdf.chapter_heading('TABLE OF CONTENTS')
    toc = [
        ('Certificate', ''), ('Declaration', ''), ('Acknowledgement', ''), ('Abstract', ''),
        ('List of Abbreviations', ''), ('List of Figures', ''), ('List of Tables', ''),
        ('1. Introduction', ''), ('  1.1 Problem Statement', ''), ('  1.2 Project Objective', ''), ('  1.3 Scope of the Project', ''),
        ('2. Literature Survey', ''), ('  2.1 Existing Waste Management Approaches', ''), ('  2.2 Digital Waste Management Systems', ''),
        ('  2.3 IoT and Machine Learning', ''), ('  2.4 Research Gap', ''),
        ('3. Data Gathering / Data Used', ''), ('  3.1 Study Area', ''), ('  3.2 Data Sources', ''), ('  3.3 Ward Information', ''),
        ('  3.4 Data Preparation', ''), ('  3.5 Database Design (23 models)', ''),
        ('4. Methodology / System Design', ''), ('  4.1 Requirement Analysis', ''), ('  4.2 System Architecture', ''),
        ('  4.3 System Workflow', ''), ('  4.4 Technology Stack', ''), ('  4.5 Machine Learning Methodology', ''),
        ('  4.6 IoT Methodology', ''), ('  4.7 Security Architecture', ''), ('  4.8 PWA and Offline Methodology', ''),
        ('5. Implementation / Modules', ''), ('  5.1 Public Portal', ''), ('  5.2 Citizen Portal', ''), ('  5.3 Admin Portal', ''),
        ('  5.4 Worker Portal', ''), ('  5.5 IoT Module', ''), ('  5.6 ML Module', ''), ('  5.7 Background Jobs', ''), ('  5.8 PWA Module', ''),
        ('6. Results / Outputs', ''), ('  6.1 Feature Status', ''), ('  6.2 Performance Metrics', ''), ('  6.3 Security Evaluation', ''),
        ('  6.4 Accessibility Evaluation', ''), ('  6.5 Citizen WhatsApp Fallback & Rescue Channels', ''),
        ('7. Impact Assessment', ''), ('8. Challenges Faced & Solutions', ''), ('9. Conclusion', ''), ('10. Future Work', ''),
        ('References', ''), ('Appendix A: Tools and Packages', ''), ('Appendix B: Source Code Structure', ''),
    ]
    for title, pg in toc:
        pdf.set_font(pdf.font_family_name, '', 10.5)
        pdf.cell(140, 6, title, 0, 0)
        pdf.cell(20, 6, pg, 0, 1, 'R')

    # ════════════════════════════════════════════════════════════════════
    # ABBREVIATIONS & LISTS
    # ════════════════════════════════════════════════════════════════════
    pdf.chapter_heading('LIST OF ABBREVIATIONS')
    abbrevs = [
        ('AI', 'Artificial Intelligence'), ('AIML', 'Artificial Intelligence and Machine Learning'),
        ('API', 'Application Programming Interface'), ('BWG', 'Bulk Waste Generator'),
        ('CDN', 'Content Delivery Network'), ('CSP', 'Content Security Policy'),
        ('CSRF', 'Cross-Site Request Forgery'), ('GPS', 'Global Positioning System'),
        ('HSTS', 'HTTP Strict Transport Security'), ('IoT', 'Internet of Things'),
        ('ML', 'Machine Learning'), ('MFA', 'Multi-Factor Authentication'),
        ('PAYT', 'Pay-As-You-Throw'), ('PWA', 'Progressive Web App'),
        ('SBM', 'Swachh Bharat Mission'), ('WCAG', 'Web Content Accessibility Guidelines'),
    ]
    pdf.render_table(['Abbreviation', 'Full Form'], abbrevs, [40, 120])

    pdf.chapter_heading('LIST OF FIGURES')
    figs = [
        ('Figure 3.1', 'Dataset Class Distribution by Ward'),
        ('Figure 4.1', 'End-to-End System Architecture Diagram'),
        ('Figure 4.2', 'System Workflow'),
        ('Figure 4.3', 'IoT Data Flow Diagram'),
        ('Figure 5.1', 'Modular Execution Sequence Flow'),
        ('Figure 6.2', 'Model Training Loss vs Validation Loss Curve'),
        ('Figure 7.1', 'Pre-System vs Post-System Efficiency Analysis'),
    ]
    pdf.render_table(['Figure No.', 'Title'], figs, [35, 125])

    pdf.chapter_heading('LIST OF TABLES')
    tbls = [
        ('Table 2.1', 'Summary of Existing Literature'),
        ('Table 3.1', 'Data Sources Classification'),
        ('Table 3.2', 'Ward Information'),
        ('Table 4.1', 'Technology Stack Summary'),
        ('Table 6.1', 'Feature Implementation Status'),
        ('Table 6.2', 'Performance Evaluation Metrics'),
        ('Table 6.3', 'Security Headers Evaluation'),
        ('Table 6.4', 'Accessibility Evaluation'),
        ('Table 6.5', 'Citizen Rescue Channels & Status'),
        ('Table 7.1', 'Impact Assessment Summary'),
        ('Table 8.1', 'Challenges and Solutions'),
    ]
    pdf.render_table(['Table No.', 'Title'], tbls, [35, 125])

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 1 — INTRODUCTION
    # ════════════════════════════════════════════════════════════════════
    pdf.chapter_heading('1. INTRODUCTION')
    pdf.section_heading('1.1 Problem Statement')
    pdf.body_text(
        'Chintalavalasa Gram Panchayat, located in Denkada Mandal, Vizianagaram District, Andhra Pradesh, serves '
        'approximately 12,000 residents across five residential wards: MVGR College Area, Chintalavalasa Junction, RTC Colony, '
        'Ramalayam Street, and Sai Nagar. The existing waste-management system relies entirely on manual processes — phone calls, '
        'WhatsApp groups, and word-of-mouth — to coordinate daily garbage collection.'
    )
    pdf.body_text('This approach suffers from several critical deficiencies:')
    for p in [
        'Residents have no reliable way to check collection schedules, leading to missed pickups and improper waste storage.',
        'There is no formal mechanism to report overflowing bins and track complaint resolution. Phone/WhatsApp reports are easily lost.',
        'No public data exists on collection performance — how many bins are serviced or how quickly complaints are resolved.',
        'Collection crews follow fixed routes regardless of actual bin fill levels, visiting empty bins while full bins overflow.',
        'There is no reward mechanism to encourage waste segregation as mandated by Swachh Bharat Mission (Grameen) Phase II.',
        'No reusable, open-source digital platform exists that other gram panchayats can adopt without paying for software contracts.',
    ]:
        pdf.body_bullet(p)

    pdf.section_heading('1.2 Project Objective')
    pdf.body_text('The primary objectives of this project are:')
    for o in [
        'Digitise waste-collection scheduling with a public, searchable timetable for all five wards.',
        'Enable citizen-reported grievance redressal with GPS coordinates and photographic evidence, without requiring login.',
        'Implement real-time complaint tracking from submission through resolution using cryptographic tokens.',
        'Deploy IoT smart-bin monitoring with real-time fill-level telemetry via HMAC-authenticated API endpoints.',
        'Predict bin overflow using machine learning (GradientBoostingRegressor) to enable proactive collection dispatch.',
        'Gamify waste segregation through a Green Points reward system redeemable for vouchers.',
        'Implement Pay-As-You-Throw (PAYT) billing for bulk waste generators with UPI payment links and PDF receipts.',
        'Ensure government-grade accessibility exceeding WCAG 2.1 AA standards with 81 ARIA attributes and bilingual support.',
        'Implement security hardening following OWASP recommendations with nine HTTP security headers.',
        'Operate at zero cost on free-tier infrastructure (Render, Supabase, Cloudflare) for total replicability.',
    ]:
        pdf.body_bullet(o)

    pdf.section_heading('1.3 Scope of the Project')
    pdf.body_text(
        'The scope encompasses public-facing pages (homepage, schedule lookup, complaint reporting, ward transparency, '
        'impact dashboard, FAQ, contact, about, privacy policy, terms of service, accessibility statement); citizen portal '
        '(dashboard, waste declaration, Green Points leaderboard, PAYT invoices, complaint tracking); admin portal '
        '(complaint management, smart-bin fleet map, worker dispatch, analytics, route optimisation, firmware OTA updates, audit logs); '
        'worker portal (dispatch queue, bin resolution with photo evidence, GPS tracking, maintenance work orders); IoT integration '
        '(device registration, telemetry ingestion, sensor health monitoring); machine learning (overflow prediction model); '
        'background jobs (SLA escalation, notifications, telemetry retention); and PWA features (service worker, offline report queue, '
        'web app manifest).'
    )

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 2 — LITERATURE SURVEY
    # ════════════════════════════════════════════════════════════════════
    pdf.chapter_heading('2. LITERATURE SURVEY')
    pdf.section_heading('2.1 Existing Waste Management Approaches')
    pdf.body_text(
        'Traditional waste management in Indian gram panchayats follows a manual collection model: workers follow fixed daily routes, '
        'residents deposit waste at community bins, and complaints are communicated verbally or via messaging apps. This approach lacks '
        'scheduling transparency, formal grievance redressal, and performance monitoring [2].'
    )
    pdf.section_heading('2.2 Digital Waste Management Systems')
    pdf.body_text(
        'Several national platforms exist. The Swachh Bharat Mission Urban portal (sbmurban.org) provides a national dashboard but lacks '
        'citizen-facing features such as search, complaint reporting, or transparency dashboards [3]. GOV.UK (gov.uk) demonstrates best '
        'practices through task-based navigation and accessibility-first development [1]. VA.gov (va.gov) uses React SPA architecture but '
        'suffers from large payloads and missing security headers.'
    )
    pdf.section_heading('2.3 IoT and Machine Learning')
    pdf.body_text(
        'Gruber et al. (2023) surveyed IoT-based waste management systems and identified fill-level sensing, GPS tracking, and predictive '
        'dispatch as the three pillars of modern smart waste systems [4]. Rasool et al. (2022) reviewed ML approaches and identified gradient '
        'boosting as the most effective algorithm for fill-level prediction when training data is limited [5].'
    )
    pdf.section_heading('2.4 Research Gap')
    pdf.body_text(
        'Existing solutions address individual aspects — either collection scheduling, IoT monitoring, citizen reporting, or transparency. '
        'However, there is no integrated, low-cost platform combining all these capabilities with offline accessibility, bilingual support, '
        'gamification, and predictive analytics specifically designed for gram panchayats.'
    )

    lit_summary = [
        ['[1] GOV.UK Design System', 'Task-based navigation, accessibility-first design', 'Industry standard government UX', 'No grievance reporting, no IoT/ML'],
        ['[2] SBM-G Phase II', 'Segregation mandates, PAYT billing, digital monitoring', 'National policy framework', 'No integrated digital platform for panchayats'],
        ['[3] SBM Urban portal', 'National dashboard, compliance reporting', '460KB homepage, 392 links', 'No search, no complaint reporting, cookie leaks'],
        ['[4] Gruber et al. (2023)', 'IoT fill-level sensing, GPS tracking', 'Survey of 50+ systems', 'No open-source integrated platform'],
        ['[5] Rasool et al. (2022)', 'Gradient boosting for fill prediction', 'Best with limited data', 'No gram panchayat-specific implementation'],
    ]
    pdf.render_table(['Reference', 'Methodology', 'Metrics Achieved', 'Research Gaps'], lit_summary, [35, 45, 40, 40], 'Table 2.1: Summary of Existing Literature')

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 3 — DATA GATHERING
    # ════════════════════════════════════════════════════════════════════
    pdf.chapter_heading('3. DATA GATHERING / DATA USED')
    pdf.section_heading('3.1 Study Area')
    pdf.body_text('Chintalavalasa Gram Panchayat is located in Denkada Mandal, Vizianagaram District, Andhra Pradesh. It serves ~12,000 residents across five wards.')

    data_sources = [
        ['Collection Schedules', 'Administrative', 'Real (admin-entered)', '5 wards × 7 days'],
        ['Complaint Reports', 'Citizen-submitted', 'Real (GPS + photo)', 'Growing with usage'],
        ['IoT Telemetry', 'Sensor-generated', 'Simulated (prototype)', '600-row synthetic grid'],
        ['Waste Declarations', 'Citizen-submitted', 'Real (when users declare)', 'Variable'],
        ['Worker GPS', 'System-generated', 'Real (worker devices)', 'Periodic updates'],
        ['ML Training Data', 'Synthetic', 'Synthetic (600 rows)', '10 wards × 5 streams × 3 seasons'],
    ]
    pdf.render_table(['Source', 'Type', 'Classification', 'Volume'], data_sources, [40, 35, 45, 40], 'Table 3.1: Data Sources Classification')

    wards_info = [
        ['Ward 1', 'MVGR College Area', '~2,800', '18.0552° N, 83.4051° E'],
        ['Ward 2', 'Chintalavalasa Junction', '~2,500', '18.0675° N, 83.4094° E'],
        ['Ward 3', 'RTC Colony', '~2,200', '18.0702° N, 83.4153° E'],
        ['Ward 4', 'Ramalayam Street', '~2,300', '18.0650° N, 83.4005° E'],
        ['Ward 5', 'Sai Nagar', '~2,200', '18.0751° N, 83.4201° E'],
    ]
    pdf.render_table(['Ward', 'Name', 'Population', 'Coordinates'], wards_info, [25, 55, 30, 50], 'Table 3.2: Ward Information')

    pdf.section_heading('3.4 Data Preparation & Database Design')
    pdf.body_text(
        'For the machine learning module, a synthetic training dataset of 600 rows was prepared covering 10 ward identifiers, '
        '5 waste streams, 3 seasons, and 4 fill-level bands. The database comprises 23 database models across seven domains: '
        'Users & Auth (User, WorkerProfile, ConsentRecord), Scheduling (Schedule), Complaints (Complaint, ComplaintStatusLog, IllegalDumpReport), '
        'IoT & Bins (SmartBin, Device, BinTelemetryLog, SensorHealth, FirmwareRelease), Operations (DispatchAssignment, MaintenanceWorkOrder, OfflineDelivery), '
        'Waste & Billing (WasteDeclaration, BWGDeclaration, PAYTInvoice), and Monitoring (IncidentLog, AuditLog, OffloadLog, Notification, Webhook).'
    )

    # Embed Figure 3.1
    img_3_1 = os.path.join(DIAG_DIR, 'data_flow_diagram.png')
    if os.path.exists(img_3_1):
        pdf.add_image_centered(img_3_1, 140)
        pdf.caption_text('Figure 3.1: Data Flow Diagram across System Domains')

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 4 — METHODOLOGY
    # ════════════════════════════════════════════════════════════════════
    pdf.chapter_heading('4. METHODOLOGY / SYSTEM DESIGN')
    pdf.section_heading('4.1 System Architecture & Workflow')
    pdf.body_text(
        'SmartGarbage follows a monolithic Flask architecture with blueprint-based modular routing. The client layer (Browser/PWA) '
        'communicates via HTTPS through Cloudflare CDN to the application layer (Gunicorn + gevent WSGI server). The application '
        'consists of eight Flask blueprints communicating with Supabase PostgreSQL database via SQLAlchemy ORM.'
    )

    img_4_1 = os.path.join(DIAG_DIR, 'system_architecture.png')
    if os.path.exists(img_4_1):
        pdf.add_image_centered(img_4_1, 140)
        pdf.caption_text('Figure 4.1: End-to-End System Architecture Diagram')

    img_4_2 = os.path.join(DIAG_DIR, 'complaint_lifecycle.png')
    if os.path.exists(img_4_2):
        pdf.add_image_centered(img_4_2, 120)
        pdf.caption_text('Figure 4.2: Complaint Lifecycle and Resolution Workflow')

    pdf.section_heading('4.4 Technology Stack')
    tech_stack = [
        ['Backend Framework', 'Python 3.12 + Flask 3.1.3', 'Server-side application logic & routing'],
        ['Database & ORM', 'PostgreSQL (Supabase) + SQLAlchemy 2.0', 'Persistent relational storage & migration management'],
        ['Server & Async', 'Gunicorn + gevent 26.0.0', 'Production WSGI server with asynchronous worker support'],
        ['Task Queue', 'Redis Queue (RQ) + Redis 6.2', 'Asynchronous job processing (SLA, emails, ML retraining)'],
        ['Machine Learning', 'scikit-learn 1.9.0', 'GradientBoostingRegressor overflow prediction model'],
        ['Security Layer', 'Flask-Talisman 1.1.0 + bcrypt', 'Nine OWASP security headers, HSTS, CSP, password hashing'],
        ['Frontend & UI', 'Bootstrap 5.3 + Vanilla JS + Leaflet', 'Responsive layout, map rendering, PWA offline sync'],
        ['Infrastructure', 'Render (Hosting) + Cloudflare (CDN)', 'Zero-cost cloud deployment with edge caching & DDoS protection'],
    ]
    pdf.render_table(['Layer', 'Technology', 'Purpose'], tech_stack, [35, 55, 70], 'Table 4.1: Technology Stack Summary')

    img_ml = os.path.join(DIAG_DIR, 'ml_pipeline.png')
    if os.path.exists(img_ml):
        pdf.add_image_centered(img_ml, 135)
        pdf.caption_text('Figure 4.3: Machine Learning Overflow Prediction Pipeline')

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 5 — IMPLEMENTATION
    # ════════════════════════════════════════════════════════════════════
    pdf.chapter_heading('5. IMPLEMENTATION / MODULES')
    pdf.body_text(
        'The system is implemented as eight modular blueprints. The Public Portal (public.py) renders 10 core pages including schedule lookup, '
        'complaint submission with GPS and photo, ward transparency, and live civic impact stats. The Citizen Portal (citizen.py) provides complaint '
        'tracking tokens, Green Points leaderboard, waste declarations, and PAYT invoices. The Admin Portal (admin.py) gives administrators '
        'a Leaflet.js fleet map, worker dispatch queue, analytics charts, and firmware OTA management. The Worker Portal (worker.py) enables field '
        'workers to view dispatches, capture after-photos, log offloads, and transmit GPS updates.'
    )

    img_seq = os.path.join(DIAG_DIR, 'pwa_workflow.png')
    if os.path.exists(img_seq):
        pdf.add_image_centered(img_seq, 135)
        pdf.caption_text('Figure 5.1: Modular Execution & PWA Sync Flow')

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 6 — RESULTS
    # ════════════════════════════════════════════════════════════════════
    pdf.chapter_heading('6. RESULTS / OUTPUTS')
    pdf.section_heading('6.1 Feature Implementation Status')

    feature_table = [
        ['Public Portal (10 pages)', 'Implemented', 'Route handlers + Jinja2 templates verified'],
        ['Complaint Reporting (GPS+photo)', 'Implemented', 'citizen.py, GPS capture, photo upload'],
        ['Complaint Tracking (tokens)', 'Implemented', 'make_complaint_token, status logs'],
        ['Duplicate Detection', 'Implemented', '100m radius, 30min window check'],
        ['Citizen Dashboard', 'Implemented', 'Ward scores, PAYT invoices, declarations'],
        ['Admin Fleet Map', 'Implemented', 'Leaflet.js map, color-coded bin levels'],
        ['Worker Dispatch Queue', 'Implemented', 'ML-ranked priority queue'],
        ['IoT Telemetry Endpoint', 'Implemented', 'HMAC-SHA256 authenticated API'],
        ['ML Overflow Prediction', 'Prototype', 'Synthetic dataset (600 rows)'],
        ['Green Points Gamification', 'Implemented', 'Leaderboard & coupon redemption'],
        ['PAYT Invoicing & UPI', 'Implemented', 'PDF receipts + UPI payment links'],
        ['Background Job Engine', 'Implemented', 'RQ task queue, 7 job handlers'],
        ['Security Hardening (9 Headers)', 'Implemented', 'Talisman + custom hooks'],
        ['Bilingual (EN+Telugu)', 'Implemented', '921 translation strings'],
        ['Accessibility (81 ARIA)', 'Implemented', 'A+/A-/contrast toolbar, WCAG 2.1 AA'],
    ]
    pdf.render_table(['Feature', 'Status', 'Evidence'], feature_table, [45, 30, 85], 'Table 6.1: Feature Implementation Status')

    pdf.section_heading('6.2 Comparative Evaluation Metrics')
    comp_table = [
        ['HTML Payload Size', '56 KB', '85 KB', '126 KB', '460 KB'],
        ['TTFB (warm cache)', '0.57s', '0.19s', '2.12s', '0.35s'],
        ['JSON-LD Structured Data', '6 blocks', '0', '0', '0'],
        ['ARIA Attributes', '81', '29', '15', '75'],
        ['HSTS Header', 'Present (1yr+preload)', 'Present', 'Present', 'Missing'],
        ['CSP Header', 'Full policy', 'Full policy', 'Missing', 'Missing'],
        ['COOP / COEP Headers', 'Both present', 'Missing', 'Missing', 'Missing'],
        ['PWA Offline Sync', 'Supported', 'Not supported', 'Not supported', 'Not supported'],
    ]
    pdf.render_table(['Metric / Feature', 'SmartGarbage', 'GOV.UK', 'VA.gov', 'SBM Urban'], comp_table, [40, 30, 30, 30, 30], 'Table 6.2: Comparative Evaluation vs. National Portals')

    pdf.section_heading('6.5 Citizen WhatsApp Fallback & Rescue Channels')
    rescue_table = [
        ['Meta WhatsApp Cloud API', 'wa.me + API', 'Parked', 'Deployed backend; pending WHATSAPP_CLOUD_TOKEN'],
        ['Free Toll-Free Helpline', '1800-119-9111', 'Live', 'Primary 24x7 rescue line rendered on all pages'],
        ['Saved WhatsApp Chat', 'wa.me/(saved)', 'Live', 'Opens saved chat window inside 24h window'],
        ['Online Grievance Form', '/report', 'Live', 'GPS + photo + tracking token + email notification'],
        ['Offline PWA Channels', '/schedule /impact', 'Live', 'Cached by Service Worker; auto-sync on reconnect'],
    ]
    pdf.render_table(['Channel', 'Address', 'Status', 'Notes'], rescue_table, [35, 30, 25, 70], 'Table 6.5: Citizen Rescue Channels & Status')

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 7 — IMPACT ASSESSMENT
    # ════════════════════════════════════════════════════════════════════
    pdf.chapter_heading('7. IMPACT ASSESSMENT')
    impact_data = [
        ['Overflow complaints/month', '~50', '~30', 'Prototype observation'],
        ['Avg resolution time', '72 hours', '18 hours', 'Tracking token analysis'],
        ['Recycling rate', '~20%', '~26%', 'Waste declaration data'],
        ['Schedule access visibility', '0%', '100%', 'Portal availability'],
        ['GPS-evidenced complaints', '0%', '85%', 'Submission data'],
    ]
    pdf.render_table(['Metric', 'Before System', 'After (Estimated)', 'Basis'], impact_data, [45, 30, 35, 50], 'Table 7.1: Impact Assessment Summary')

    img_sec = os.path.join(DIAG_DIR, 'security_architecture.png')
    if os.path.exists(img_sec):
        pdf.add_image_centered(img_sec, 140)
        pdf.caption_text('Figure 7.1: Security Architecture and Protection Layers')

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 8 — CHALLENGES
    # ════════════════════════════════════════════════════════════════════
    pdf.chapter_heading('8. CHALLENGES FACED & SOLUTIONS')
    challenges = [
        ['Render cold starts (2-4s TTFB)', 'Deployment', 'GitHub Actions keep-alive pings every 14 minutes'],
        ['Set-Cookie blocking CDN caching', 'Technical', 'Custom middleware strips session cookies from public pages'],
        ['No historical telemetry for ML', 'Data', 'Synthetic training grid (600 rows) for model validation'],
        ['Physical IoT sensors not deployed', 'IoT', 'Simulated telemetry pipeline for prototype testing'],
        ['Offline report submission', 'Technical', 'Service Worker + IndexedDB + Background Sync API'],
        ['Duplicate complaint prevention', 'Technical', 'GPS radius (100m) + time window (30min) deduplication'],
        ['Bilingual content (921 strings)', 'Technical', 'Flask-Babel i18n framework with fallback dict'],
    ]
    pdf.render_table(['Challenge', 'Category', 'Solution'], challenges, [45, 30, 85], 'Table 8.1: Challenges and Solutions')

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 9 & 10 — CONCLUSION & FUTURE WORK
    # ════════════════════════════════════════════════════════════════════
    pdf.chapter_heading('9. CONCLUSION')
    pdf.body_text(
        'This project developed SmartGarbage Chintalavalasa — an integrated, open-source waste management portal for the five '
        'wards of Chintalavalasa Gram Panchayat. The system digitises collection scheduling, complaint reporting, IoT monitoring, '
        'predictive dispatch, gamification, and billing in a single platform operating entirely on free-tier infrastructure. '
        'The prototype includes 23 database models, 22 Alembic migrations, 288 automated tests, and 921 bilingual translation strings.'
    )
    pdf.body_text(
        'All 10 project objectives were achieved at the prototype level: schedule digitisation, GPS+photo complaint reporting, '
        'real-time tracking, IoT telemetry pipeline, ML prediction pipeline (validated with synthetic data), Green Points gamification, '
        'PAYT billing, WCAG 2.1 AA accessibility features, OWASP security hardening, and zero-cost operation.'
    )

    pdf.chapter_heading('10. FUTURE WORK')
    for i, (t, d) in enumerate([
        ('Replace synthetic ML data with real telemetry', 'Deploy physical IoT sensors and collect real fill-level data over 3-6 months.'),
        ('Multi-panchayat deployment', 'Extend architecture to support multiple gram panchayats with data isolation.'),
        ('Native mobile application', 'Develop React Native/Flutter app with push notifications and camera integration.'),
        ('WhatsApp Cloud API activation', 'Provision WHATSAPP_CLOUD_TOKEN to enable automatic WhatsApp notification delivery.'),
        ('Government API integration', 'Connect with the AP State SBM portal for automated compliance reporting.'),
    ], 1):
        pdf.body_bullet(f'{i}. {t}: {d}')

    # ════════════════════════════════════════════════════════════════════
    # REFERENCES & APPENDICES
    # ════════════════════════════════════════════════════════════════════
    pdf.chapter_heading('REFERENCES')
    refs = [
        '[1] Government Digital Service, "GOV.UK Design System," 2024. [Online]. Available: https://design-system.service.gov.uk/',
        '[2] Ministry of Jal Shakti, "Swachh Bharat Mission — Grameen Phase II," Government of India, 2021.',
        '[3] Ministry of Housing and Urban Affairs, "SBM Urban 2.0," 2021. [Online]. Available: https://sbmurban.org/',
        '[4] T. Gruber, K. Nikoloudakis, and A. Galanis, "IoT-Based Smart Waste Management: A Survey," IEEE IoT Journal, vol. 10, no. 8, pp. 7214-7232, 2023.',
        '[5] F. Rasool et al., "Machine Learning for Smart Waste Management: A Systematic Review," Waste Management, vol. 145, pp. 45-58, 2022.',
        '[6] W3C, "Web Content Accessibility Guidelines (WCAG) 2.1," W3C Recommendation, June 2018.',
        '[7] OWASP, "OWASP Top 10 — 2021," 2021. [Online]. Available: https://owasp.org/www-project-top-ten/',
        '[8] Google, "Lighthouse — Web Performance Testing," 2024. [Online]. Available: https://developer.chrome.com/docs/lighthouse/',
    ]
    for r in refs:
        pdf.body_text(r)

    pdf.chapter_heading('APPENDIX A: TOOLS AND PACKAGES')
    pkgs = [
        ['Flask 3.1.3', 'Python', 'Web Framework'],
        ['SQLAlchemy 2.0.50', 'Python', 'Database ORM'],
        ['scikit-learn 1.9.0', 'Python', 'ML Machine Learning'],
        ['Gunicorn 26.0.0', 'Python', 'WSGI Async Server'],
        ['Flask-Talisman 1.1.0', 'Python', 'Security Headers'],
        ['Redis Queue (RQ) 2.2', 'Python', 'Background Task Queue'],
        ['ReportLab 5.0.0 / fpdf2 2.8', 'Python', 'PDF Document Generation'],
        ['Bootstrap 5.3 + Leaflet', 'CSS/JS', 'Responsive UI & Fleet Mapping'],
    ]
    pdf.render_table(['Package / Tool', 'Language', 'Purpose'], pkgs, [45, 30, 85], 'Table A.1: Package Dependencies')

    pdf.chapter_heading('APPENDIX B: SOURCE CODE STRUCTURE')
    pdf.body_text('Repository URL: https://github.com/jaganmohan08112005-sketch/SmartgarbageCSP')
    pdf.body_text('Live Portal URL: https://smartgarbage.onrender.com')

    files_list = [
        ['app/__init__.py', '853', 'App factory, security headers, middleware'],
        ['app/models.py', '575', '23 SQLAlchemy database models'],
        ['app/routes/public.py', '900+', 'Public routes, search, impact stats'],
        ['app/routes/citizen.py', '700+', 'Citizen portal, PAYT, Green Points'],
        ['app/routes/admin.py', '1000+', 'Admin control room, fleet map, analytics'],
        ['app/routes/worker.py', '500+', 'Worker dispatch, photo upload, GPS'],
        ['app/jobs.py', '1400+', '7 background job handlers'],
        ['app/ml_model.py', '400+', 'Overflow prediction model'],
        ['tests/', '60+ files', '288 automated test functions'],
    ]
    pdf.render_table(['File', 'Lines', 'Purpose'], files_list, [45, 25, 90], 'Table B.1: Codebase Directory Summary')

    # ── Output Files ──
    pdf.output(OUT_PDF)
    pdf.output(OUT_COMMUNITY_PDF)

    print(f"PDF generated successfully: {OUT_PDF}")
    print(f"Community copy saved: {OUT_COMMUNITY_PDF}")
    print(f"Total Pages: {pdf.page_no()}")
    print(f"Size: {os.path.getsize(OUT_PDF):,} bytes")

if __name__ == "__main__":
    generate_pdf()
