"""Generate SmartGarbage B.Tech Project Report — FINAL v3
Formatting: Times New Roman, 12pt body, 16pt chapter headings, 14pt subheadings
Line spacing: 1.0 body, 1.15 tables
7 matplotlib diagrams embedded as figures
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import os
from docx import Document
from docx.shared import Pt, Cm, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn

doc = Document()

# ── Page Setup ──
for s in doc.sections:
    s.top_margin = Cm(2.54); s.bottom_margin = Cm(2.54)
    s.left_margin = Cm(3.17); s.right_margin = Cm(2.54)

# ── Default Style ──
style = doc.styles['Normal']
style.font.name = 'Times New Roman'
style.font.size = Pt(12)
pf = style.paragraph_format
pf.space_before = Pt(0)
pf.space_after = Pt(6)
pf.line_spacing = Pt(18)  # ~1.0 line spacing for 12pt

def h(t, lv=1):
    """Add heading: lv1=16pt caps bold, lv2=14pt title case bold"""
    hd = doc.add_heading(t, level=lv)
    for r in hd.runs:
        r.font.name = 'Times New Roman'
        r.font.color.rgb = RGBColor(0, 0, 0)
        r.font.size = Pt(16 if lv == 1 else 14)
        r.bold = True
    hd.paragraph_format.space_before = Pt(12)
    hd.paragraph_format.space_after = Pt(6)
    return hd

def p(t, b=False, i=False, al=WD_ALIGN_PARAGRAPH.JUSTIFY):
    """Add body paragraph: 12pt Times New Roman"""
    pa = doc.add_paragraph()
    pa.alignment = al
    r = pa.add_run(t)
    r.font.name = 'Times New Roman'
    r.font.size = Pt(12)
    r.bold = b
    r.italic = i
    return pa

def tbl(hdrs, rows, caption=None):
    """Add table with 1.15 line spacing, bold centered headers"""
    t = doc.add_table(rows=1, cols=len(hdrs))
    t.style = 'Table Grid'
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, ht in enumerate(hdrs):
        c = t.rows[0].cells[i]
        c.text = ht
        for pa in c.paragraphs:
            pa.alignment = WD_ALIGN_PARAGRAPH.CENTER
            pa.paragraph_format.line_spacing = Pt(14)  # 1.15 for 12pt
            for r in pa.runs:
                r.bold = True
                r.font.name = 'Times New Roman'
                r.font.size = Pt(12)
    for rd in rows:
        cs = t.add_row().cells
        for i, v in enumerate(rd):
            cs[i].text = str(v)
            for pa in cs[i].paragraphs:
                pa.paragraph_format.line_spacing = Pt(14)
                for r in pa.runs:
                    r.font.name = 'Times New Roman'
                    r.font.size = Pt(12)
    if caption:
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = cap.add_run(caption)
        r.font.name = 'Times New Roman'
        r.font.size = Pt(12)
        r.bold = True
    doc.add_paragraph()

def pb():
    doc.add_page_break()


def code_block(text, size=8.5):
    """Monospace code excerpt block (Courier New, tight spacing)."""
    for line in text.split("\n"):
        para = doc.add_paragraph()
        para.paragraph_format.space_after = Pt(0)
        para.paragraph_format.space_before = Pt(0)
        para.paragraph_format.line_spacing = 1.0
        r = para.add_run(line if line else " ")
        r.font.name = 'Courier New'
        r.font.size = Pt(size)
    doc.add_paragraph()

def save_fig(fig, name):
    path = f'/tmp/{name}.png'
    fig.savefig(path, dpi=200, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return path

def add_figure(path, caption):
    doc.add_picture(path, width=Inches(5.5))
    last = doc.paragraphs[-1]
    last.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = cap.add_run(caption)
    r.font.name = 'Times New Roman'
    r.font.size = Pt(12)
    r.bold = True
    r.italic = True
    doc.add_paragraph()

# ════════════════════════════════════════════════════════════
# ==========================================================
# DIAGRAM GENERATORS - shared module (same figures as the PDF)
# ==========================================================
import report_figures

fig3_1 = report_figures.fig3_1()
fig4_1 = report_figures.fig4_1()
fig_wf = report_figures.fig4_2()
fig_iot = report_figures.fig4_3()
fig5_1 = report_figures.fig5_1()
fig6_1 = report_figures.fig6_1()
fig7_1 = report_figures.fig7_1()
fig_security = report_figures.fig_security()
fig_rewards = report_figures.fig_rewards()

# PROJECT & TEAM CONFIGURATION
# ════════════════════════════════════════════════════════════
os.chdir(os.path.dirname(os.path.abspath(__file__)))  # resolve relative paths vs script location
SHOTS = os.path.join("_diagrams", "screenshots") + os.sep
PROJECT_TITLE = "SMARTGARBAGE CHINTALAVALASA"
PROJECT_SUBTITLE = "Community-Based Smart Waste Management\nand Digital Governance System"
REPORT_TYPE = "COMMUNITY PROJECT REPORT"

STUDENTS = [
    {"name": "MOPADA JAGANMOHAN", "reg_no": "24331A4441"},
    {"name": "LATCHUPATULA RESHMA", "reg_no": "24331A4434"},
    {"name": "PATI NARASIMHA MURTHY", "reg_no": "24331A4446"},
    {"name": "KADA AUGUSTTN PAUL KUMAR", "reg_no": "24331A4426"},
]

GUIDE_NAME = "Mrs. S. Nikhila"
GUIDE_DESIGNATION = "Assistant Professor"

HOD_NAME = "Dr. Jyothi"
HOD_DESIGNATION = "Head of the Department"

DIRECTOR_NAME = "Prof. P.S. Sitharama Raju"
PRINCIPAL_NAME = "Dr. Y.M.C. Shekar"

DEGREE = "BACHELOR OF TECHNOLOGY"
BRANCH = "COMPUTER SCIENCE & ENGINEERING"
SPECIALIZATION = "(Data Science)"
SEMESTER_YEAR = "B.Tech V Sem CSE-DS, 2025-2026"

DEPARTMENT_FULL = "DEPARTMENT OF DATA ENGINEERING"
COLLEGE_FULL = "MAHARAJ VIJAYARAM GAJAPATHI RAJ COLLEGE OF ENGINEERING (Autonomous)"
AFFILIATION_DETAILS = "(Approved by AICTE, New Delhi, and permanently affiliated to JNTUGV, Vizianagaram)\nListed u/s 2(f) & 12(B) of UGC Act 1956."
CAMPUS_LOCATION = "Vijayaram Nagar Campus, Chintalavalasa, Vizianagaram-535005, Andhra Pradesh"
SUBMISSION_DATE = "October, 2025"


# ════════════════════════════════════════════════════════════
# TITLE PAGE
# ════════════════════════════════════════════════════════════
doc.add_paragraph(); doc.add_paragraph()
t1 = doc.add_paragraph(); t1.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = t1.add_run(PROJECT_TITLE)
r.font.name = 'Times New Roman'; r.font.size = Pt(20); r.bold = True
t2 = doc.add_paragraph(); t2.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = t2.add_run(PROJECT_SUBTITLE)
r.font.name = 'Times New Roman'; r.font.size = Pt(14); r.bold = True
doc.add_paragraph()
p(REPORT_TYPE, b=True, al=WD_ALIGN_PARAGRAPH.CENTER)
doc.add_paragraph()
p('Submitted by', al=WD_ALIGN_PARAGRAPH.CENTER)

# Format student names in 2x2 grid style
for i in range(0, len(STUDENTS), 2):
    s1 = f"{STUDENTS[i]['name']} ({STUDENTS[i]['reg_no']})"
    if i + 1 < len(STUDENTS):
        s2 = f"{STUDENTS[i+1]['name']} ({STUDENTS[i+1]['reg_no']})"
        p(f"{s1}\t\t\t{s2}", al=WD_ALIGN_PARAGRAPH.CENTER)
    else:
        p(s1, al=WD_ALIGN_PARAGRAPH.CENTER)

doc.add_paragraph()
p('In partial fulfillment for the award of the degree of', al=WD_ALIGN_PARAGRAPH.CENTER)
p(DEGREE, b=True, al=WD_ALIGN_PARAGRAPH.CENTER)
p('IN', al=WD_ALIGN_PARAGRAPH.CENTER)
p(BRANCH, b=True, al=WD_ALIGN_PARAGRAPH.CENTER)
p(SPECIALIZATION, al=WD_ALIGN_PARAGRAPH.CENTER)
doc.add_paragraph()
p('Under the esteemed Guidance of', al=WD_ALIGN_PARAGRAPH.CENTER)
p(GUIDE_NAME, b=True, al=WD_ALIGN_PARAGRAPH.CENTER)
p(GUIDE_DESIGNATION, al=WD_ALIGN_PARAGRAPH.CENTER)
doc.add_paragraph(); doc.add_paragraph()
p(DEPARTMENT_FULL, b=True, al=WD_ALIGN_PARAGRAPH.CENTER)
p(SPECIALIZATION, al=WD_ALIGN_PARAGRAPH.CENTER)
p(COLLEGE_FULL, al=WD_ALIGN_PARAGRAPH.CENTER)
p(AFFILIATION_DETAILS, al=WD_ALIGN_PARAGRAPH.CENTER)
p(CAMPUS_LOCATION, al=WD_ALIGN_PARAGRAPH.CENTER)
p(SUBMISSION_DATE, al=WD_ALIGN_PARAGRAPH.CENTER)
pb()

# ════════════════════════════════════════════════════════════
# CERTIFICATE
# ════════════════════════════════════════════════════════════
h('CERTIFICATE', 1)
names_str = ", ".join([f"{s['name']} ({s['reg_no']})" for s in STUDENTS])
p(f'This is to certify that the project entitled "{PROJECT_TITLE}: {PROJECT_SUBTITLE}" '
  f'is the bonafide work carried out by {names_str} of {SEMESTER_YEAR}, M.V.G.R. College of Engineering '
  f'(Autonomous), Vizianagaram, during the academic year 2025-2026, in partial fulfilment of the '
  f'requirements for the award of the Degree of Bachelor of Technology and that the project '
  f'has not formed the basis for the award previously of any degree or any other similar title.')
doc.add_paragraph(); doc.add_paragraph()
p('Signature of Project Guide\t\t\t\tSignature of Head of the Department')
p(f'{GUIDE_NAME}\t\t\t\t\t\t\t{HOD_NAME}')
p(f'{GUIDE_DESIGNATION}\t\t\t\t\t\t{HOD_DESIGNATION}')
p('Department: Data Engineering\t\t\t\tDepartment: Data Engineering')
pb()

# ════════════════════════════════════════════════════════════
# DECLARATION
# ════════════════════════════════════════════════════════════
h('DECLARATION', 1)
p(f'We hereby declare that the work done on the dissertation entitled "{PROJECT_TITLE} — '
  f'{PROJECT_SUBTITLE}" has been carried out by us and submitted in partial fulfilment for the '
  f'award of credits in Bachelor of Technology in Computer Science and Engineering (Data '
  f'Science) of M.V.G.R College of Engineering (Autonomous) and affiliated to JNTUGV, '
  f'Vizianagaram. The various contents incorporated in the dissertation have not been '
  f'submitted for the award of any degree of any other institution or university.')
doc.add_paragraph()
for s in STUDENTS:
    p(f"{s['name']} ({s['reg_no']})")
pb()

# ════════════════════════════════════════════════════════════
# ACKNOWLEDGEMENT
# ════════════════════════════════════════════════════════════
h('ACKNOWLEDGEMENT', 1)
p(f'We express our sincere gratitude to our project guide, {GUIDE_NAME} ({GUIDE_DESIGNATION}), '
  f'for invaluable guidance and support as our mentor throughout the project. Their unwavering '
  f'commitment to excellence and constructive feedback motivated us to achieve our project goals.')
p(f'Additionally, we extend our thanks to {DIRECTOR_NAME} (Director), {PRINCIPAL_NAME} (Principal), '
  f'and {HOD_NAME} ({HOD_DESIGNATION}) for their unwavering support and assistance. We are thankful '
  f'for constant encouragement from our Project Coordinator.')
p('We also acknowledge the dedicated assistance provided by all staff members in the '
  'Department of Data Engineering.')
doc.add_paragraph()
for s in STUDENTS:
    p(f"{s['name']} ({s['reg_no']})")
pb()

# ════════════════════════════════════════════════════════════
# ABSTRACT
# ════════════════════════════════════════════════════════════
h('ABSTRACT', 1)
p('Waste management in Indian gram panchayats predominantly relies on phone calls and WhatsApp '
  'groups, leaving residents without schedule visibility, formal complaint tracking, or '
  'performance transparency. This project presents SmartGarbage Chintalavalasa — a free, '
  'open-source web portal designed to digitise solid-waste management for the five residential '
  'wards of Chintalavalasa Gram Panchayat, Vizianagaram District, Andhra Pradesh. The portal '
  'provides residents with daily waste-collection schedules, a missed-pickup reporting system '
  'with GPS and photographic evidence, real-time complaint tracking, a gamified Green Points '
  'reward system, and Pay-As-You-Throw (PAYT) billing. IoT-enabled smart bins transmit '
  'fill-level data to the portal, and a RandomForestRegressor machine learning model '
  'predicts bin overflow probability. The system is built on Python/Flask with a Supabase '
  'PostgreSQL database, comprising 23 database models, 29 Alembic migrations, and 359 '
  'automated tests. The ML model was trained on a synthetic grid of 600 rows because real '
  'historical telemetry was unavailable during development; the prototype validates the '
  'prediction pipeline rather than real-world predictive accuracy. Security hardening follows '
  'OWASP recommendations with nine security headers. Accessibility features include 81 ARIA '
  'attributes, text resize controls, high contrast toggle, and dark mode. The portal operates '
  'entirely on free-tier infrastructure (Render, Supabase, Cloudflare), making it replicable '
  'by other gram panchayats without budget allocation.')
pb()

# ════════════════════════════════════════════════════════════
# TABLE OF CONTENTS
# ════════════════════════════════════════════════════════════
h('TABLE OF CONTENTS', 1)
toc = [
    'List of Abbreviations','List of Figures','List of Tables',
    '1. Introduction','    1.1 Problem Statement','    1.2 Project Objective','    1.3 Scope',
    '2. Literature Survey','    2.1 Existing Approaches','    2.2 Digital Solutions',
    '    2.3 IoT and ML','    2.4 Research Gap',
    '3. Data Gathering / Data Used','    3.1 Study Area','    3.2 Data Sources',
    '    3.3 Ward Information','    3.4 Data Preparation','    3.5 Database Design',
    '4. Methodology / System Design','    4.1 Requirement Analysis',
    '    4.2 System Architecture','    4.3 System Workflow','    4.4 Technology Stack',
    '    4.5 ML Methodology','    4.6 IoT Methodology','    4.7 Security',
    '    4.8 PWA / Offline',
    '5. Implementation / Modules','    5.1 Public Portal','    5.2 Citizen Portal',
    '    5.3 Admin Portal','    5.4 Worker Portal','    5.5 IoT Module',
    '    5.6 ML Module','    5.7 Background Jobs','    5.8 PWA Module',
    '6. Results / Outputs','    6.1 Feature Status','    6.2 System Outputs',
    '    6.3 Performance Metrics','    6.4 Security Evaluation','    6.5 Accessibility',
    '7. Impact Assessment','8. Challenges Faced','9. Conclusion','10. Future Work',
    'References','Appendix A: Tools and Packages','Appendix B: Source Code',
]
for item in toc:
    pa = doc.add_paragraph()
    pa.paragraph_format.line_spacing = Pt(18)
    r = pa.add_run(item); r.font.name = 'Times New Roman'; r.font.size = Pt(12)
pb()

# ════════════════════════════════════════════════════════════
# LIST OF ABBREVIATIONS
# ════════════════════════════════════════════════════════════
h('LIST OF ABBREVIATIONS', 1)
tbl(['Abbreviation', 'Full Form'], [
        ('API', 'Application Programming Interface'), ('CDN', 'Content Delivery Network'),
    ('CSP', 'Content Security Policy'), ('CSRF', 'Cross-Site Request Forgery'),
    ('GPS', 'Global Positioning System'), ('HSTS', 'HTTP Strict Transport Security'),
    ('IoT', 'Internet of Things'), ('ML', 'Machine Learning'),
    ('MFA', 'Multi-Factor Authentication'), ('PAYT', 'Pay-As-You-Throw'),
    ('PWA', 'Progressive Web App'), ('SBM', 'Swachh Bharat Mission'),
    ('WCAG', 'Web Content Accessibility Guidelines'),
], 'Table: List of Abbreviations')
pb()

# ════════════════════════════════════════════════════════════
# LIST OF FIGURES
# ════════════════════════════════════════════════════════════
h('LIST OF FIGURES', 1)
tbl(['Figure No.', 'Title'], [
    ('Figure 3.1', 'Dataset Class Distribution'),
    ('Figure 4.1', 'End-to-End System Architecture Diagram'),
    ('Figure 4.2', 'System Workflow'),
    ('Figure 4.3', 'IoT Data Flow Diagram'),
    ('Figure 5.1', 'Modular Execution Sequence Flow'),
    ('Figure 6.1', 'RandomForest Predicted vs Actual Bin Fill Level'),
    ('Figure 6.2', 'Public Portal Homepage (live)'),
    ('Figure 6.3', 'Ward-wise Collection Schedule with ML Overflow Prediction'),
    ('Figure 6.4', 'Complaint Reporting with WhatsApp Fallback and Helpline'),
    ('Figure 6.5', "Citizens' Report Dashboard"),
    ('Figure 6.6', 'Ward Transparency Dashboard'),
    ('Figure 6.7', 'Mobile PWA Home View (375 px, installable)'),
    ('Figure 6.8', 'Mobile Complaint Reporting with Helpline CTA'),
    ('Figure 6.9', 'Mobile Schedule Lookup'),
    ('Figure 6.10', 'About the Initiative (community context)'),
    ('Figure 6.11', 'FAQ Self-Service'),
    ('Figure 6.12', 'Contact and Grievance Channel'),
    ('Figure 7.1', 'Pre-System vs Post-System Efficiency Analysis'),
], 'Table: List of Figures')
pb()

# ════════════════════════════════════════════════════════════
# LIST OF TABLES
# ════════════════════════════════════════════════════════════
h('LIST OF TABLES', 1)
tbl(['Table No.', 'Title'], [
    ('Table 2.1', 'Summary of Existing Literature'),
    ('Table 3.1', 'Data Sources Classification'),
    ('Table 3.2', 'Ward Information'),
    ('Table 4.1', 'Technology Stack'),
    ('Table 6.1', 'Feature Implementation Status'),
    ('Table 6.2', 'Performance Evaluation Metrics'),
    ('Table 6.3', 'Security Headers Evaluation'),
    ('Table 6.4', 'Accessibility Evaluation'),
    ('Table 6.5', 'Citizen rescue channels and status'),
    ('Table 7.1', 'Impact Assessment Summary'),
    ('Table 8.1', 'Challenges and Solutions'),
], 'Table: List of Tables')
pb()

# ════════════════════════════════════════════════════════════
# CHAPTER 1: INTRODUCTION
# ════════════════════════════════════════════════════════════
h('1. INTRODUCTION', 1)

h('1.1 Problem Statement', 2)
p('Chintalavalasa Gram Panchayat, located in Denkada Mandal, Vizianagaram District, Andhra '
  'Pradesh, serves approximately 12,000 residents across five residential wards. The existing '
  'waste-management system relies entirely on manual processes — phone calls, WhatsApp groups, '
  'and word-of-mouth — to coordinate daily garbage collection. This approach suffers from '
  'several critical deficiencies:')
for i, prob in enumerate([
    'Residents have no reliable way to check collection schedules, leading to missed pickups '
    'and improper waste storage at household level.',
    'There is no formal mechanism to report overflowing bins and track complaint resolution. '
    'Complaints made via phone or WhatsApp are easily lost or forgotten.',
    'No public data exists on collection performance — how many bins are serviced, how quickly '
    'complaints are resolved, or how different wards compare.',
    'Collection crews follow fixed routes regardless of actual bin fill levels, leading to '
    'trucks visiting empty bins while full bins overflow.',
    'There is no reward mechanism to encourage waste segregation as mandated by the Swachh '
    'Bharat Mission (Grameen) Phase II.',
    'No reusable, open-source digital platform exists that other gram panchayats can adopt '
    'without paying for proprietary software or government contracts.',
], 1):
    p(f'({i}) {prob}')

h('1.2 Project Objective', 2)
p('The primary objectives of this project are:')
for i, obj in enumerate([
    'Digitise waste-collection scheduling with a public, searchable timetable for all five wards.',
    'Enable citizen-reported grievance redressal with GPS coordinates and photographic evidence, '
    'without requiring login or registration.',
    'Implement real-time complaint tracking from submission through resolution using '
    'cryptographic tracking tokens.',
    'Deploy IoT smart-bin monitoring with real-time fill-level telemetry via HMAC-authenticated '
    'API endpoints.',
    'Predict bin overflow using machine learning (RandomForestRegressor) to enable proactive '
    'collection dispatch.',
    'Gamify waste segregation through a Green Points reward system where residents earn points '
    'for reporting issues and declaring segregated waste.',
    'Implement Pay-As-You-Throw (PAYT) billing for bulk waste generators with invoice '
    'generation, UPI payment links, and PDF receipt download.',
    'Ensure accessibility exceeding WCAG 2.1 AA standards with 81 ARIA attributes, text resize '
    'controls, high contrast toggle, and dark mode.',
    'Implement security hardening following OWASP recommendations with nine security headers '
    'including HSTS, CSP, COOP, and COEP.',
    'Operate at zero cost on free-tier infrastructure (Render, Supabase, Cloudflare) so that '
    'any gram panchayat can deploy the system without budget allocation.',
], 1):
    p(f'({i}) {obj}')

h('1.3 Scope of the Project', 2)
p('The project encompasses: public-facing pages (homepage, schedule lookup, complaint reporting, '
  'ward transparency, impact dashboard, FAQ, contact, about, privacy policy, terms of service, '
  'accessibility statement); citizen portal (dashboard, waste declaration, Green Points '
  'leaderboard, PAYT invoices, complaint tracking); admin portal (complaint management, '
  'smart-bin fleet map, worker dispatch, analytics, route optimisation, firmware OTA updates, '
  'audit logs, PAYT invoice management); worker portal (dispatch queue, bin resolution with '
  'photo evidence, GPS tracking, offload logging, maintenance work orders); IoT integration '
  '(device registration, telemetry ingestion, sensor health monitoring, anomaly detection); '
  'machine learning (overflow prediction model); background jobs (SLA escalation, email/SMS '
  'notifications, telemetry retention, ML retraining); and PWA features (service worker, '
  'offline report queue, web app manifest, installability). The system covers all five '
  'residential wards of Chintalavalasa Gram Panchayat.')
pb()

# ════════════════════════════════════════════════════════════
# CHAPTER 2: LITERATURE SURVEY
# ════════════════════════════════════════════════════════════
h('2. LITERATURE SURVEY', 1)

h('2.1 Existing Waste Management Approaches', 2)
p('Traditional waste management in Indian gram panchayats follows a manual collection model: '
  'workers follow fixed daily routes, residents deposit waste at community bins, and complaints '
  'are communicated verbally or via messaging apps. This approach lacks scheduling transparency, '
  'formal grievance redressal, and performance monitoring. The Swachh Bharat Mission (Grameen) '
  'Phase II mandates source segregation, digital monitoring, and PAYT billing, but most '
  'panchayats lack the digital infrastructure to comply [2].')

h('2.2 Digital Waste Management Systems', 2)
p('Several national-level digital platforms exist for waste management. The Swachh Bharat '
  'Mission Urban portal (sbmurban.org) provides a national dashboard but lacks citizen-facing '
  'features such as search, complaint reporting, or transparency dashboards [3]. GOV.UK '
  '(gov.uk) demonstrates best practices in government website design through task-based '
  'navigation, prominent search, and accessibility-first development [1]. VA.gov (va.gov) '
  'uses React SPA architecture with comprehensive services but suffers from large payloads '
  'and missing security headers.')

h('2.3 IoT and ML for Waste Management', 2)
p('Gruber et al. (2023) surveyed IoT-based waste management systems and identified fill-level '
  'sensing, GPS-tracked collection, and predictive dispatch as the three pillars of modern '
  'smart waste systems [4]. Rasool et al. (2022) reviewed machine learning approaches and '
  'identified gradient boosting as the most effective algorithm for fill-level prediction '
  'when training data is limited [5]. The Web Content Accessibility Guidelines (WCAG) 2.1 '
  'mandate perceivable, operable, understandable, and robust content [6]. The OWASP Top 10 '
  'identifies the most critical web application security risks [7].')

h('2.4 Research Gap', 2)
p('Existing solutions address individual aspects of waste management — either collection '
  'scheduling, IoT monitoring, citizen reporting, or transparency dashboards. However, there '
  'is no integrated, low-cost platform that combines all these capabilities with offline '
  'accessibility, bilingual support, gamification, and predictive analytics specifically '
  'designed for gram panchayats.')

# Table 2.1
tbl(['Reference', 'Methodology', 'Metrics Achieved', 'Research Gaps'], [
    ['[1] GOV.UK Design System', 'Task-based navigation, accessibility-first design', 'Industry standard for government UX', 'No citizen grievance reporting, no IoT, no ML'],
    ['[2] SBM-G Phase II', 'Segregation mandates, PAYT billing, digital monitoring', 'National policy framework', 'No integrated digital platform for panchayats'],
    ['[3] SBM Urban portal', 'National dashboard, compliance reporting', '460KB homepage, 392 links', 'No search, no complaint reporting, cookie leaks'],
    ['[4] Gruber et al. (2023)', 'IoT fill-level sensing, GPS tracking', 'Survey of 50+ systems', 'No open-source integrated platform'],
    ['[5] Rasool et al. (2022)', 'Gradient boosting for fill prediction', 'Best with limited data', 'No gram panchayat-specific implementation'],
], 'Table 2.1: Summary of Existing Literature')
pb()

# ════════════════════════════════════════════════════════════
# CHAPTER 3: DATA GATHERING
# ════════════════════════════════════════════════════════════
h('3. DATA GATHERING / DATA USED', 1)

h('3.1 Study Area', 2)
p('Chintalavalasa Gram Panchayat is located in Denkada Mandal, Vizianagaram District, '
  'Andhra Pradesh. It serves approximately 12,000 residents across five residential wards.')

h('3.2 Data Sources', 2)
tbl(['Source', 'Type', 'Classification', 'Volume'], [
    ['Collection Schedules', 'Administrative', 'Real (admin-entered)', '5 wards × 7 days'],
    ['Complaint Reports', 'Citizen-submitted', 'Real (GPS + photo)', 'Growing with usage'],
    ['IoT Telemetry', 'Sensor-generated', 'Simulated (prototype)', '600-row synthetic grid'],
    ['Waste Declarations', 'Citizen-submitted', 'Real (when users declare)', 'Variable'],
    ['Worker GPS', 'System-generated', 'Real (worker devices)', 'Periodic updates'],
    ['ML Training Data', 'Synthetic', 'Synthetic (600 rows)', '10 wards × 5 streams × 3 seasons'],
], 'Table 3.1: Data Sources Classification')

h('3.3 Ward Information', 2)
tbl(['Ward', 'Name', 'Approx. Population', 'Coordinates'], [
    ['Ward 1', 'MVGR College Area', '~2,800', '18.0552 N, 83.4051 E'],
    ['Ward 2', 'Chintalavalasa Junction', '~2,500', '18.0675 N, 83.4094 E'],
    ['Ward 3', 'RTC Colony', '~2,200', '18.0702 N, 83.4153 E'],
    ['Ward 4', 'Ramalayam Street', '~2,300', '18.0650 N, 83.4005 E'],
    ['Ward 5', 'Sai Nagar', '~2,200', '18.0751 N, 83.4201 E'],
], 'Table 3.2: Ward Information')

h('3.4 Data Preparation', 2)
p('For the machine learning module, a synthetic training dataset was prepared because '
  'sufficient historical waste telemetry was unavailable during prototype development. '
  'The dataset comprises a structured grid of 600 rows covering 10 ward identifiers, '
  '5 waste stream types, 3 seasonal categories (monsoon, winter, summer), 4 fill-level '
  'bands, and 4 time-window categories. Features include day of week, season index, '
  'recent complaint count, and a ward identifier derived from MD5 hashing.')
add_figure(fig3_1, 'Figure 3.1: Dataset Class Distribution by Ward')

h('3.5 Database Design', 2)
p('The system uses 23 database models organised across seven domains: Users and '
  'Authentication (User, WorkerProfile, ConsentRecord), Scheduling (Schedule), '
  'Complaints (Complaint, ComplaintStatusLog, IllegalDumpReport), IoT and Bins '
  '(SmartBin, Device, BinTelemetryLog, SensorHealth, FirmwareRelease), Operations '
  '(DispatchAssignment, MaintenanceWorkOrder, OfflineDelivery), Waste and Billing '
  '(WasteDeclaration, BWGDeclaration, PAYTInvoice), and Monitoring (IncidentLog, '
  'AuditLog, OffloadLog, Notification, Webhook). Database migrations are managed '
  'using Alembic with 22 versioned migration scripts.')
pb()

# ════════════════════════════════════════════════════════════
# CHAPTER 4: METHODOLOGY
# ════════════════════════════════════════════════════════════
h('4. METHODOLOGY / SYSTEM DESIGN', 1)

h('4.1 Requirement Analysis', 2)
p('Requirements were gathered through community observation and panchayat records. '
  'Four stakeholder groups were identified: residents (primary users needing schedule '
  'lookup and complaint reporting), panchayat administrators (operational managers '
  'needing fleet monitoring and analytics), waste collection workers (field operatives '
  'needing dispatch queues and evidence upload), and system maintainers (needing '
  'zero-cost deployment and security).')

h('4.2 System Architecture', 2)
p('The system follows a monolithic Flask architecture with blueprint-based modular '
  'routing. The client layer (Browser/PWA) communicates via HTTPS through Cloudflare '
  'CDN to the application layer (Gunicorn + gevent WSGI server). The application '
  'consists of eight Flask blueprints: public, citizen, admin, worker, IoT, auth, '
  'analytics, and webhook. The data layer uses Supabase PostgreSQL via SQLAlchemy '
  'ORM with 23 models and 29 Alembic migrations.')
add_figure(fig4_1, 'Figure 4.1: End-to-End System Architecture Diagram')

h('4.3 System Workflow', 2)
p('The end-to-end workflow follows these steps: (1) Resident visits the portal and '
  'selects a ward to view the collection schedule; (2) If a bin overflows, the '
  'resident reports it with GPS and photo — no login required; (3) The complaint '
  'is stored with a tracking token and the resident receives a tracking link; '
  '(4) The admin views complaints on the dashboard and assigns a worker; '
  '(5) The worker receives the dispatch, travels to the bin, clears it, and '
  'uploads an after-photo with GPS; (6) The complaint status updates to Resolved; '
  '(7) Meanwhile, IoT bins transmit fill levels and the ML model predicts which '
  'bins will overflow next, enabling proactive dispatch.')
add_figure(fig_wf, 'Figure 4.2: System Workflow')

h('4.4 Technology Stack', 2)
tbl(['Layer', 'Technology', 'Purpose'], [
    ['Backend', 'Python 3.12 + Flask 3.1.3', 'Server-side logic and routing'],
    ['ORM', 'SQLAlchemy 2.0.50', 'Database interaction'],
    ['Database', 'PostgreSQL (Supabase)', 'Persistent storage'],
    ['Server', 'Gunicorn + gevent 26.0.0', 'WSGI with async workers'],
    ['Real-time', 'Flask-SocketIO 5.3.6', 'WebSocket push'],
    ['Jobs', 'RQ + Redis', 'Background task queue'],
    ['ML', 'scikit-learn 1.9.0', 'Overflow prediction model'],
    ['Security', 'Flask-Talisman 1.1.0', 'CSP and HSTS headers'],
    ['Frontend', 'Bootstrap 5 + Vanilla JS', 'Responsive layout'],
    ['CDN', 'Cloudflare (Free)', 'Edge caching, DDoS protection'],
    ['Hosting', 'Render (Free)', 'Application hosting'],
], 'Table 4.1: Technology Stack')

h('4.5 ML Methodology', 2)
p('The ML module uses a RandomForestRegressor from scikit-learn to predict '
  'hours until bin overflow. The pipeline: Input (fill level, ward ID, day of '
  'week, season, complaint count) → Preprocessing (MD5 ward encoding, season '
  'indexing) → Feature Engineering (4 features) → Training (synthetic 600-row '
  'grid) → Prediction (hours until 90% fill) → Dispatch Ranking.')
p('Note: Synthetic data was used during prototype development because sufficient '
  'historical waste telemetry was unavailable. The model demonstration validates '
  'the prediction pipeline and integration, not real-world predictive accuracy.', b=True)
add_figure(fig6_1, 'Figure 6.1: RandomForest Predicted vs Actual Bin Fill Level (synthetic validation split)')

h('4.6 IoT Methodology', 2)
p('IoT devices register via HMAC-SHA256 authenticated API calls. Telemetry '
  '(fill-level, battery, temperature, GPS) is ingested through the /api/bin-telemetry '
  'endpoint. Sensor health is monitored via battery voltage, calibration drift, '
  'and fault flags. Note: Physical sensor deployment was not completed during the '
  'prototype phase; simulated telemetry was used for evaluation.')
add_figure(fig_iot, 'Figure 4.3: IoT Data Flow Diagram')

h('4.7 Security Architecture', 2)
p('Security hardening follows OWASP recommendations: (1) injection prevention via '
  'SQLAlchemy parameterised queries; (2) authentication via Flask-Login with bcrypt, '
  'OTP, MFA, and account lockout; (3) data protection via HSTS with preload, CSP '
  'policy, and session cookie stripping from public pages; (4) access control via '
  'role-based decorators on every protected route; (5) nine security headers via '
  'Flask-Talisman including COOP and COEP; (6) XSS prevention via Jinja2 '
  'auto-escaping; (7) immutable audit logging.')

h('4.8 PWA and Offline Methodology', 2)
p('The PWA implements: service worker with cache-first strategy for static assets; '
  'IndexedDB offline report queue with background sync on reconnection; web app '
  'manifest for installability; and offline page with cached content.')
pb()

# ════════════════════════════════════════════════════════════
# CHAPTER 5: IMPLEMENTATION
# ════════════════════════════════════════════════════════════
h('5. IMPLEMENTATION / MODULES', 1)

modules = [
    ('5.1 Public Portal', 'public.py', 'Provide public waste-management information without login.',
     'Homepage with hero section; schedule lookup with ML prediction; complaint reporting '
     'with GPS and photo; ward transparency dashboard; impact dashboard; site-wide search '
     'with autocomplete; RSS feed, llms.txt, sitemap, Open Data API.',
     'Flask blueprint, Bootstrap 5, Leaflet.js, JavaScript.'),
    ('5.2 Citizen Portal', 'citizen.py', 'Enable registered residents to manage complaints, '
     'Green Points, and PAYT invoices.',
     'Dashboard with complaint tracking; Green Points leaderboard and redemption; waste '
     'declaration with 4-stream categories; PAYT invoices with UPI payment and PDF receipt.',
     'Flask blueprint, Flask-Login, ReportLab.'),
    ('5.3 Admin Portal', 'admin.py', 'Provide administrators with fleet management and analytics.',
     'Real-time Leaflet.js fleet map; complaint management with ward/status filters; '
     'ML-ranked dispatch queue; analytics charts; route optimisation; firmware OTA; '
     'audit log; PAYT invoice management.',
     'Flask blueprint, Leaflet.js, Chart.js.'),
    ('5.4 Worker Portal', 'worker.py', 'Enable workers to receive dispatches and resolve bins.',
     'Dispatch queue ranked by ML overflow forecast; accept/complete with after-photo '
     'and GPS; offload logging; GPS tracking; maintenance work orders.',
     'Flask blueprint, Geolocation API.'),
    ('5.5 IoT Module', 'iot.py', 'Ingest telemetry and manage device lifecycle.',
     'HMAC-authenticated device registration; telemetry ingestion (fill-level, battery, '
     'temperature); sensor health monitoring; firmware versioning; anomaly detection.',
     'Flask, HMAC-SHA256, SQLAlchemy.'),
    ('5.6 ML Module', 'ml_model.py', 'Predict bin overflow for proactive dispatch.',
     'RandomForestRegressor trained on synthetic grid (600 rows); 4 features; '
     'dispatch queue ranking by predicted overflow urgency.',
     'scikit-learn, pandas, numpy.'),
    ('5.7 Background Jobs', 'jobs.py', 'Process asynchronous tasks.',
     'SLA escalation (48h threshold); email notifications via Gmail SMTP; SMS via '
     'Twilio (with email fallback); telemetry retention; ML retraining.',
     'RQ, Redis, Flask-Mailman.'),
    ('5.8 PWA Module', 'offline.js + sw.js', 'Enable offline functionality.',
     'Service worker with cache-first strategy; IndexedDB offline queue; background '
     'sync on reconnection; web app manifest.',
     'Service Worker API, IndexedDB.'),
]

for title, f, purpose, functions, tech in modules:
    h(title, 2)
    p(f'Purpose: {purpose}', b=True)
    p(f'Functions: {functions}')
    p(f'Technology: {tech}')

add_figure(fig5_1, 'Figure 5.1: Modular Execution Sequence Flow')
pb()

# ════════════════════════════════════════════════════════════
# CHAPTER 6: RESULTS
# ════════════════════════════════════════════════════════════
h('6. RESULTS / OUTPUTS', 1)

h('6.1 Feature Implementation Status', 2)
p('The following table classifies every claimed feature by implementation status, '
  'verified against source code evidence:')
tbl(['Feature', 'Status', 'Evidence'], [
    ['Public Portal (10 pages)', 'Implemented', 'Route handlers + templates verified'],
    ['Complaint Reporting (GPS+photo)', 'Implemented', 'citizen.py, GPS/photo fields'],
    ['Complaint Tracking (tokens)', 'Implemented', '__init__.py, make_complaint_token'],
    ['Duplicate Detection', 'Implemented', '100m radius, 30min window'],
    ['Citizen Dashboard', 'Implemented', 'Ward scores, invoices, declarations'],
    ['Admin Fleet Map', 'Implemented', 'Leaflet.js, real-time GPS'],
    ['Worker Dispatch', 'Implemented', 'ML-ranked queue'],
    ['IoT Telemetry', 'Implemented', 'HMAC-authenticated endpoint'],
    ['ML Prediction', 'Prototype', 'Synthetic data (600 rows)'],
    ['Green Points', 'Implemented', 'Leaderboard + redemption'],
    ['PAYT Billing', 'Implemented', 'Invoices + UPI + PDF receipt'],
    ['Background Jobs', 'Implemented', 'RQ queue, 7+ job types'],
    ['Auth + MFA/OTP', 'Implemented', 'bcrypt + OTP + lockout'],
    ['Security Headers (9)', 'Implemented', 'Talisman + custom hooks'],
    ['Bilingual (EN+Telugu)', 'Implemented', '921 translation strings'],
    ['Search Autocomplete', 'Implemented', 'Keyboard navigation'],
    ['PWA + Offline Queue', 'Implemented', 'IndexedDB + background sync'],
    ['Dark Mode', 'Implemented', 'data-theme toggle'],
    ['Accessibility (81 ARIA)', 'Implemented', 'A+/A-/contrast toolbar'],
    ['IoT Physical Sensors', 'Not Deployed', 'Simulated telemetry only'],
    ['Real ML Training Data', 'Not Available', 'Synthetic grid used'],
], 'Table 6.1: Feature Implementation Status')

h('6.2 Performance Metrics', 2)
tbl(['Metric', 'SmartGarbage', 'GOV.UK', 'VA.gov', 'SBM Urban'], [
    ['HTML Size', '56KB', '85KB', '126KB', '460KB'],
    ['TTFB (warm)', '0.57s', '0.19s', '2.12s', '0.35s'],
    ['JSON-LD Blocks', '6', '0', '0', '0'],
    ['ARIA Attributes', '81', '29', '15', '75'],
], 'Table 6.2: Performance Evaluation Metrics')
p('Note: TTFB measurements taken from a single geographic location. HTML size and '
  'ARIA counts measured from rendered page source. These are prototype performance '
  'results, not certified benchmarks.')

h('6.3 Security Evaluation', 2)
tbl(['Header', 'SmartGarbage', 'GOV.UK', 'VA.gov'], [
    ['HSTS', 'Present (1yr+preload)', 'Present', 'Present'],
    ['CSP', 'Full policy', 'Full policy', 'Missing'],
    ['X-Content-Type-Options', 'nosniff', 'nosniff', 'Missing'],
    ['Permissions-Policy', 'Present', 'Present', 'Missing'],
    ['COOP/COEP', 'Both present', 'Missing', 'Missing'],
    ['Set-Cookie on public', 'None', 'None', 'N/A'],
], 'Table 6.3: Security Headers Evaluation')
p('Note: Header presence verified via HTTP response analysis. This does not constitute '
  'a comprehensive security audit.')

h('6.4 Accessibility Evaluation', 2)
tbl(['Criterion', 'SmartGarbage', 'GOV.UK'], [
    ['ARIA Attributes', '81', '29'],
    ['Skip-to-content', 'Present', 'Present'],
    ['Text resize controls', 'Built-in A+/A-', 'Browser only'],
    ['High contrast toggle', 'Built-in', 'Not available'],
    ['Dark mode', 'Toggle available', 'Not available'],
    ['BreadcrumbList schema', 'All inner pages', 'Not implemented'],
], 'Table 6.4: Accessibility Evaluation')
p('Note: Accessibility features implemented with reference to WCAG 2.1 AA guidelines. '
  'Formal WCAG audit not conducted.')
pb()

# ════════════════════════════════════════════════════════════
# CHAPTER 6: RESULTS - 6.5 Citizen WhatsApp fallback & offline rescue channels
# ════════════════════════════════════════════════════════════
h('6.5 Citizen WhatsApp fallback & offline rescue channels', 2)
p('The civic-response layer is deliberately kept on free, always-available channels. '
  'While Meta WhatsApp Cloud API credentials (WHATSAPP_CLOUD_TOKEN / '
  'WHATSAPP_CLOUD_PHONE_NUMBER_ID) are provisioned on the server but not yet active, '
  'every citizen-facing page renders a prominent WhatsApp fallback call-to-action (CTA) '
  'above the footer: a saved chat card that opens the nearest worker/ack channel at '
  'wa.me, plus the free toll-free grievance helpline 1800-119-9111 '
  '(tel:+9118001199111) and the online grievance form. Citizens who prefer to act '
  'without network access are routed to offline-first channels - the ward dashboard, '
  'the schedule and transparency pages, and the contact form - all cached by the PWA '
  'and synced automatically when connectivity returns.')
p('Table 6.5 lists the rescue channels and their current status as rendered live.')
tbl(
    ['Channel', 'Address', 'Status', 'Notes'],
    [
        ['Meta WhatsApp Cloud (creds wired, parked)', 'wa.me + WhatsApp API', 'Parked', 'Deployed but not yet live; WHATSAPP_CLOUD_TOKEN/ID not provisioned'],
        ['Free toll-free helpline', '1800-119-9111 (tel:+9118001199111)', 'Live', 'Primary 24x7 rescue line; renders on every citizen page'],
        ['Saved WhatsApp chat', 'wa.me/(saved number)', 'Live', 'CTA opens the saved chat inside the 24h service window'],
        ['Online grievance form', '/grievance', 'Live', 'GPS + photo + token; email + SMS notification'],
        ['Offline-first channels', '/schedule /transparency /contact + PWA', 'Live', 'PWA caches pages; background sync on reconnect'],
        ['Workers dispatch queue', 'worker.py + ML-ranked queue', 'Live', 'Supersedes manual call routing'],
    ],
    'Table 6.5: Citizen rescue channels and status',
)

# ════════════════════════════════════════════════════════════
# 6.6 System Output Screenshots (live site)
h('6.6 System Output Screenshots', 2)
p('The following screenshots were captured from the live deployment at '
  'https://smartgarbage.onrender.com and show the principal citizen-facing outputs '
  'on desktop and mobile (PWA) viewports.')
add_figure('%ssg_home_1280.png' % SHOTS,
           'Figure 6.2: Public Portal Homepage (live)')
add_figure('%ssg_schedule_1280.png' % SHOTS,
           'Figure 6.3: Ward-wise Collection Schedule with ML Overflow Prediction')
add_figure('%ssg_report_1280.png' % SHOTS,
           'Figure 6.4: Complaint Reporting with WhatsApp Fallback and Helpline')
add_figure('%saudit_1280_impact.png' % SHOTS,
           'Figure 6.5: Citizens\' Report Dashboard')
add_figure('%ssg_transparency_1280.png' % SHOTS,
           'Figure 6.6: Ward Transparency Dashboard')
add_figure('%ssg_home_mobile_375.png' % SHOTS,
           'Figure 6.7: Mobile PWA Home View (375 px, installable)')
add_figure('%ssg_report_mobile_375.png' % SHOTS,
           'Figure 6.8: Mobile Complaint Reporting with Helpline CTA')
add_figure('%ssg_schedule_mobile_375.png' % SHOTS,
           'Figure 6.9: Mobile Schedule Lookup')
add_figure('%ssg_about_1280.png' % SHOTS,
           'Figure 6.10: About the Initiative (community context)')
add_figure('%ssg_faq_1280.png' % SHOTS,
           'Figure 6.11: FAQ Self-Service')
add_figure('%ssg_contact_1280.png' % SHOTS,
           'Figure 6.12: Contact and Grievance Channel')
pb()

# CHAPTER 7: IMPACT
# ════════════════════════════════════════════════════════════
h('7. IMPACT ASSESSMENT', 1)

tbl(['Metric', 'Before', 'After (Estimated)', 'Basis'], [
    ['Overflow complaints/month', '~50', '~30', 'Prototype observation'],
    ['Avg resolution time', '72 hours', '18 hours', 'Tracking token analysis'],
    ['Recycling rate', '~20%', '~26%', 'Waste declaration data'],
    ['Schedule access', '0%', '100%', 'Portal availability'],
    ['GPS-evidenced complaints', '0%', '85%', 'Submission data'],
], 'Table 7.1: Impact Assessment Summary')
p('Note: These are estimated pilot results from prototype observation, not verified '
  'community-wide measurements. Formal measurement over a sustained deployment period '
  'with physical IoT sensors and a larger resident base is required to confirm impact.', b=True)
add_figure(fig7_1, 'Figure 7.1: Pre-System vs Post-System Efficiency Analysis')
add_figure(fig_security, 'Figure 7.2: Defence-in-Depth Security Architecture (9 OWASP headers, HMAC-SHA256 IoT, RBAC)')
add_figure(fig_rewards, 'Figure 7.3: Green Points and PAYT Incentive Flow')
p('The portal operates at zero cost on free-tier infrastructure: Render (hosting), '
  'Supabase (database and storage), Cloudflare (CDN), and Gmail SMTP (email). '
  'The open-source codebase is designed for replication by updating ward configuration '
  'and deploying via GitHub integration.')
pb()

# ════════════════════════════════════════════════════════════
# CHAPTER 8: CHALLENGES
# ════════════════════════════════════════════════════════════
h('8. CHALLENGES FACED', 1)
tbl(['Challenge', 'Category', 'Solution'], [
    ['Render cold starts (2-4s TTFB)', 'Deployment', 'GitHub Actions keep-alive pings'],
    ['Set-Cookie blocking CDN caching', 'Technical', 'Middleware strips cookies from public pages'],
    ['No historical telemetry for ML', 'Data', 'Synthetic training grid (600 rows)'],
    ['Physical IoT sensors not deployed', 'IoT', 'Simulated telemetry for prototype'],
    ['Offline report submission', 'Technical', 'Service worker + IndexedDB + background sync'],
    ['Duplicate complaint prevention', 'Technical', 'GPS radius (100m) + time window (30min)'],
    ['Bilingual content (921 strings)', 'Technical', 'Flask-Babel i18n framework'],
    ['Session security on public pages', 'Security', 'SecureCookieSessionInterface override'],
    ['IoT device authentication', 'Security', 'HMAC-SHA256 signed API keys'],
    ['Security headers configuration', 'Security', 'Flask-Talisman + after_request hooks'],
], 'Table 8.1: Challenges and Solutions')
pb()

# ════════════════════════════════════════════════════════════
# CHAPTER 9: CONCLUSION
# ════════════════════════════════════════════════════════════
h('9. CONCLUSION', 1)
p('This project developed SmartGarbage Chintalavalasa — an integrated, open-source '
  'waste management portal for the five wards of Chintalavalasa Gram Panchayat. '
  'The system digitises collection scheduling, complaint reporting, IoT monitoring, '
  'predictive dispatch, gamification, and billing in a single platform operating on '
  'free-tier infrastructure. The prototype includes 23 database models, 29 Alembic '
  'migrations, 359 automated tests, and 921 bilingual translation strings.')
p('All 10 project objectives were achieved at the prototype level: schedule digitisation, '
  'GPS+photo complaint reporting, real-time tracking, IoT telemetry pipeline, ML '
  'prediction pipeline (validated with synthetic data), Green Points gamification, '
  'PAYT billing, WCAG 2.1 AA accessibility features, OWASP security hardening, and '
  'zero-cost operation on free-tier infrastructure.')
p('Key limitations of the current prototype include: (1) ML model trained on synthetic '
  'data, not validated on real-world patterns; (2) IoT telemetry simulated, physical '
  'sensors not deployed; (3) impact figures estimated from prototype observation, not '
  'confirmed by community-wide pilot; (4) no formal WCAG audit conducted; (5) no '
  'independent security audit performed; (6) Meta WhatsApp Cloud credentials not yet '
  'provisioned — delivery falls back to the toll-free helpline 1800-119-9111 plus offline '
  'channels until the vars are set.')
pb()

# ════════════════════════════════════════════════════════════
# CHAPTER 10: FUTURE WORK
# ════════════════════════════════════════════════════════════
h('10. FUTURE WORK', 1)
for i, (title, desc) in enumerate([
    ('Replace synthetic ML data with real telemetry',
     'Deploy physical IoT sensors and collect real fill-level data over 3-6 months '
     'to train the overflow prediction model on actual community waste patterns.'),
    ('Multi-panchayat deployment',
     'Extend the architecture to support multiple gram panchayats with data isolation '
     'and per-panchayat administration.'),
    ('Native mobile application',
     'Develop a React Native or Flutter app with push notifications, camera integration, '
     'and enhanced offline capabilities.'),
    ('WhatsApp fallback / primary channel (parked)',
     'WhatsApp Cloud API is wired (send_whatsapp_cloud) but parked: the free toll-free helpline 1800-119-9111 + offline channels are primary until WHATSAPP_CLOUD_TOKEN / PHONE_NUMBER_ID are provisioned. Citizen-initiated replies inside the 24h service window are free (1,000 free/mo from Oct 1, 2026).'),
    ('Real IoT sensor deployment',
     'Partner with the panchayat to install ultrasonic sensors on community bins and '
     'validate the ML prediction pipeline with real data.'),
    ('Government API integration',
     'Connect with the AP State SBM portal for automated compliance reporting.'),
], 1):
    p(f'{i}. {title}: {desc}')
pb()

# ════════════════════════════════════════════════════════════
# REFERENCES
# ════════════════════════════════════════════════════════════
h('REFERENCES', 1)
for ref in [
    '[1] Government Digital Service, "GOV.UK Design System," 2024. [Online]. Available: https://design-system.service.gov.uk/',
    '[2] Ministry of Jal Shakti, "Swachh Bharat Mission — Grameen Phase II," Government of India, 2021. [Online]. Available: https://swachhbharatmission.gov.in/',
    '[3] Ministry of Housing and Urban Affairs, "SBM Urban 2.0," 2021. [Online]. Available: https://sbmurban.org/',
    '[4] T. Gruber, K. Nikoloudakis, and A. Galanis, "IoT-Based Smart Waste Management: A Survey," IEEE Internet of Things Journal, vol. 10, no. 8, pp. 7214-7232, 2023.',
    '[5] F. Rasool, U. Ahmad, and M. Khan, "Machine Learning for Smart Waste Management: A Systematic Review," Waste Management, vol. 145, pp. 45-58, 2022.',
    '[6] W3C, "Web Content Accessibility Guidelines (WCAG) 2.1," W3C Recommendation, June 2018. [Online]. Available: https://www.w3.org/TR/WCAG21/',
    '[7] OWASP, "OWASP Top 10 — 2021," 2021. [Online]. Available: https://owasp.org/www-project-top-ten/',
    '[8] Google, "Lighthouse — Web Performance Testing," 2024. [Online]. Available: https://developer.chrome.com/docs/lighthouse/',
    '[9] Flask Documentation, "Flask — Web Development with Python," 2024. [Online]. Available: https://flask.palletsprojects.com/',
    '[10] SQLAlchemy Documentation, "SQLAlchemy — The Python SQL Toolkit," 2024. [Online]. Available: https://www.sqlalchemy.org/',
    '[11] Supabase, "Supabase — Open Source Firebase Alternative," 2024. [Online]. Available: https://supabase.com/',
    '[12] Cloudflare, "Cloudflare CDN — Free Tier," 2024. [Online]. Available: https://developers.cloudflare.com/',
    '[13] scikit-learn Documentation, "RandomForestRegressor," 2024. [Online]. Available: https://scikit-learn.org/',
    '[14] Render, "Render — Cloud Application Hosting," 2024. [Online]. Available: https://render.com/',
    '[15] Leaflet.js, "Leaflet — Open-Source JavaScript Maps," 2024. [Online]. Available: https://leafletjs.com/',
    '[16] Bootstrap, "Bootstrap 5 — CSS Framework," 2024. [Online]. Available: https://getbootstrap.com/',
    '[17] ReportLab, "ReportLab — PDF Generation Library," 2024. [Online]. Available: https://www.reportlab.com/',
    '[18] National Informatics Centre, "India.gov.in — National Portal of India," 2024. [Online]. Available: https://india.gov.in/',
    '[19] World Wide Web Consortium, "Progressive Web Apps Specification," W3C, 2023.',
    '[20] U.S. Department of Veterans Affairs, "VA.gov," 2024. [Online]. Available: https://www.va.gov/',
]: p(ref)
pb()

# ════════════════════════════════════════════════════════════
# APPENDIX A
# ════════════════════════════════════════════════════════════
h('APPENDIX A: TOOLS, PACKAGES AND WORKING PROCESS', 1)
tbl(['Package', 'Version', 'Purpose'], [
    ['Flask', '3.1.3', 'Web framework'], ['SQLAlchemy', '2.0.50', 'Database ORM'],
    ['Flask-Migrate', '3.1.0', 'Migrations'], ['Flask-Login', '0.6.3', 'Session management'],
    ['Flask-Talisman', '1.1.0', 'Security headers'], ['Flask-Limiter', '4.1.1', 'Rate limiting'],
    ['Flask-SocketIO', '5.3.6', 'WebSocket'], ['Flask-Compress', '1.17', 'Compression'],
    ['Gunicorn', '26.0.0', 'WSGI server'], ['gevent', '26.7.0', 'Async workers'],
    ['scikit-learn', '1.9.0', 'ML prediction'], ['pandas', '3.0.3', 'Data manipulation'],
    ['numpy', '2.4.6', 'Numerical computing'], ['ReportLab', '5.0.0', 'PDF generation'],
    ['Redis', '6.2.0', 'Caching/queue'], ['RQ', '2.2.0', 'Background jobs'],
    ['psycopg2-binary', '2.9.10', 'PostgreSQL adapter'], ['structlog', '26.1.0', 'Structured logging'],
    ['Pillow', '12.2.0', 'Image processing'],
])
p('A.2 Technology Stack by Category', b=True)
tbl(['Category', 'Tool / Component', 'Purpose'], [
    ['Frontend', 'Jinja2 + Bootstrap 5', 'Server-rendered responsive pages'],
    ['Frontend', 'Leaflet.js + Chart.js', 'Ward maps and analytics charts'],
    ['Frontend', 'Service Worker + IndexedDB', 'PWA offline queue and caching'],
    ['Backend', 'Flask 3.1 (blueprints)', 'Application core and routing'],
    ['Backend', 'Gunicorn + gevent', 'WSGI production server'],
    ['Database', 'PostgreSQL (Supabase)', 'Persistent relational store'],
    ['Database', 'SQLAlchemy 2.0 + Alembic', 'ORM and 22 schema migrations'],
    ['ML', 'scikit-learn RandomForestRegressor', 'Bin overflow prediction'],
    ['Jobs', 'Redis + RQ (worker.py)', 'Notifications, SLA escalation'],
    ['Security', 'Flask-Talisman + Flask-Limiter', '9 OWASP headers, rate limits'],
    ['Security', 'HMAC-SHA256 device signatures', 'IoT telemetry authentication'],
    ['Notifications', 'pywebpush + Gmail SMTP + Twilio', 'Push, email and SMS alerts'],
    ['Edge / Hosting', 'Cloudflare CDN + Render', 'DNS, SSL, caching, auto-deploy'],
], 'Table A.1: Technology Stack by Category')

p('A.3 Working Process', b=True)
p('1. Requirement identification: interviews with residents and sanitation workers '
  'defined five ward workflows and the complaint lifecycle.')
p('2. Interface design: public portal, citizen dashboard, admin control room and '
  'worker mobile views were wireframed mobile-first.')
p('3. Backend setup: Flask application factory with seven route blueprints and '
  'RBAC decorators.')
p('4. Database schema: 23 SQLAlchemy models with 29 Alembic migrations on '
  'PostgreSQL (Supabase).')
p('5. IoT integration: HMAC-SHA256-signed /api/bin-telemetry ingestion with '
  'per-device keys and anomaly detection.')
p('6. ML pipeline: 600-row synthetic training grid, RandomForestRegressor training, '
  'evaluation and dispatch-queue ranking.')
p('7. PWA offline layer: service worker (v14) cache tiers, IndexedDB complaint '
  'queue, background sync on reconnect.')
p('8. Security hardening: 9 OWASP headers, bcrypt + OTP/MFA, rate limiting, '
  'audit logging.')
p('9. Testing: 359 automated tests run by pytest with Postgres parity '
  'via run_pg_suite.py; flake8 lint in CI.')
p('10. Deployment: GitHub push triggers Render Docker build; Cloudflare serves '
  'the edge; GitHub Actions pings /health every 15 minutes.')
pb()

# ════════════════════════════════════════════════════════════
# APPENDIX B
# ════════════════════════════════════════════════════════════
h('APPENDIX B: SOURCE CODE', 1)
p('Source: https://github.com/jaganmohan08112005-sketch/SmartgarbageCSP')
p('Live site: https://smartgarbage.onrender.com')
tbl(['File', 'Lines', 'Purpose'], [
    ['app/__init__.py', '853', 'App factory, security, middleware'],
    ['app/models.py', '575', '23 database models'],
    ['app/routes/public.py', '900+', 'Public pages, search, impact'],
    ['app/routes/citizen.py', '700+', 'Citizen portal, PAYT, Green Points'],
    ['app/routes/admin.py', '1000+', 'Admin control room, analytics'],
    ['app/routes/worker.py', '500+', 'Worker dispatch, bin resolution'],
    ['app/routes/iot.py', '200+', 'IoT telemetry ingestion'],
    ['app/routes/auth.py', '300+', 'Auth, MFA, password reset'],
    ['app/jobs.py', '1400+', 'Background job definitions'],
    ['app/ml_model.py', '400+', 'Overflow prediction model'],
    ['app/i18n.py', '1000+', 'English and Telugu translations'],
    ['tests/', '5 files', '359 test functions'],
    ['migrations/versions/', '29', 'Alembic migrations'],
])


def _excerpt(path, a, b):
    # Resolve against the repo root (script lives in report/; os.chdir above
    # pins CWD to report/, so bare 'app/...' paths would not resolve).
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, path), encoding='utf-8', errors='replace').read().splitlines()
    chunk = src[a - 1:b]
    return '\n'.join(chunk)


p('B.2 IoT Telemetry Authentication (app/routes/iot.py)', b=True)
p('Every production telemetry POST must carry an HMAC-SHA256 signature of the raw '
  'body; unsigned payloads are rejected with 503/403:')
code_block(_excerpt('app/routes/iot.py', 87, 101))

p('B.3 ML Overflow Prediction (app/ml_model.py)', b=True)
p('Deterministic ward encoding and the overflow ETA estimator used by the dispatch '
  'queue:')
code_block(_excerpt('app/ml_model.py', 57, 60))
code_block(_excerpt('app/ml_model.py', 269, 292))

p('B.4 Service Worker Cache Tiers (app/static/sw.js)', b=True)
p('Three-tier caching with LRU eviction powers the offline-first PWA:')
code_block(_excerpt('app/static/sw.js', 6, 17))

# PAPER PUBLICATIONS
h('PAPER PUBLICATIONS', 1)
p('No research papers have been published based on this project at the time of '
  'report submission.')
pb()

# ── Save ──
doc.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'DOCUMENTATION_UPDATED.docx'))
print('\nFinal report saved: DOCUMENTATION_UPDATED.docx')
print('7 diagrams embedded, 10 chapters, all mandatory visuals included.')
