#!/usr/bin/env python3
"""
Generate a professionally formatted PDF version of the SmartGarbage
B.Tech Community Project Report using fpdf2 with Times New Roman fonts.
"""

from fpdf import FPDF
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "SmartGarbage_Community_Project_Report.pdf")
DIAG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_diagrams")

FONT_DIR = "C:/Windows/Fonts"

class ReportPDF(FPDF):
    def __init__(self):
        super().__init__('P', 'mm', 'A4')
        self.set_auto_page_break(auto=True, margin=25)
        # Register Times New Roman
        self.add_font('TNR', '', os.path.join(FONT_DIR, 'times.ttf'))
        self.add_font('TNR', 'B', os.path.join(FONT_DIR, 'timesbd.ttf'))
        self.add_font('TNR', 'I', os.path.join(FONT_DIR, 'timesi.ttf'))
        self.add_font('TNR', 'BI', os.path.join(FONT_DIR, 'timesbi.ttf'))
        self.page_count = 0

    def header(self):
        if self.page_no() > 1:
            self.set_font('TNR', 'I', 8)
            self.set_text_color(128, 128, 128)
            self.cell(0, 8, 'SmartGarbage Chintalavalasa — Community Project Report', 0, 0, 'C')
            self.ln(10)
            self.set_draw_color(200, 200, 200)
            self.line(20, self.get_y(), 190, self.get_y())
            self.ln(3)
            self.set_text_color(0, 0, 0)

    def footer(self):
        self.set_y(-15)
        self.set_font('TNR', '', 9)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'{self.page_no()}', 0, 0, 'C')
        self.set_text_color(0, 0, 0)

    # ── Content helpers ─────────────────────────────────────────────
    def chapter_heading(self, text):
        """16pt Bold ALL CAPS"""
        self.add_page()
        self.ln(8)
        self.set_font('TNR', 'B', 16)
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 10, text.upper())
        self.ln(4)

    def section_heading(self, text):
        """14pt Bold"""
        self.ln(6)
        self.set_font('TNR', 'B', 14)
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 8, text)
        self.ln(2)

    def subsection_heading(self, text):
        """12pt Bold"""
        self.ln(4)
        self.set_font('TNR', 'B', 12)
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 7, text)
        self.ln(1)

    def body_text(self, text):
        """12pt justified"""
        self.set_font('TNR', '', 12)
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 6.5, text, align='J')
        self.ln(2)

    def body_bullet(self, text):
        self.set_font('TNR', '', 12)
        self.set_text_color(0, 0, 0)
        self.cell(8, 6.5, '\u2022', 0, 0)
        x = self.get_x()
        self.multi_cell(0, 6.5, text, align='J')
        self.ln(1)

    def centered_text(self, text, size=12, bold=False):
        self.set_font('TNR', 'B' if bold else '', size)
        self.set_text_color(0, 0, 0)
        self.cell(0, size * 0.5, text, 0, 1, 'C')

    def right_text(self, text, size=12, bold=False):
        self.set_font('TNR', 'B' if bold else '', size)
        self.set_text_color(0, 0, 0)
        self.cell(0, size * 0.5, text, 0, 1, 'R')

    def caption_text(self, text):
        """Figure/table caption: 12pt bold centered"""
        self.ln(2)
        self.set_font('TNR', 'B', 12)
        self.set_text_color(0, 0, 0)
        self.cell(0, 7, text, 0, 1, 'C')
        self.ln(2)

    def add_image_centered(self, path, w=160):
        """Insert an image centered on the page."""
        if os.path.exists(path):
            x = (210 - w) / 2
            self.image(path, x=x, w=w)
            self.ln(3)

    def simple_table(self, headers, rows, col_widths=None):
        """Render a table with header row shading."""
        if col_widths is None:
            n = len(headers)
            col_widths = [170 / n] * n
        # Header
        self.set_font('TNR', 'B', 10)
        self.set_fill_color(217, 226, 243)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 7, h, 1, 0, 'C', True)
        self.ln()
        # Rows
        self.set_font('TNR', '', 10)
        self.set_fill_color(255, 255, 255)
        for row in rows:
            max_h = 7
            # Calculate row height
            for ci, val in enumerate(row):
                lines = self.multi_cell(col_widths[ci], 6, str(val), border=0, split_only=True)
                h = len(lines) * 6
                if h > max_h:
                    max_h = h
            # Check page break
            if self.get_y() + max_h > 270:
                self.add_page()
                # Re-draw header
                self.set_font('TNR', 'B', 10)
                self.set_fill_color(217, 226, 243)
                for i, h in enumerate(headers):
                    self.cell(col_widths[i], 7, h, 1, 0, 'C', True)
                self.ln()
                self.set_font('TNR', '', 10)
            # Draw cells
            x_start = self.get_x()
            y_start = self.get_y()
            for ci, val in enumerate(row):
                x = x_start + sum(col_widths[:ci])
                self.set_xy(x, y_start)
                self.cell(col_widths[ci], max_h, '', 1, 0)
                self.set_xy(x + 1, y_start + 1)
                self.multi_cell(col_widths[ci] - 2, 6, str(val))
            self.set_xy(x_start, y_start + max_h)
        self.ln(3)

    def page_break(self):
        self.add_page()


# ════════════════════════════════════════════════════════════════════
# BUILD THE PDF
# ════════════════════════════════════════════════════════════════════
pdf = ReportPDF()
pdf.set_margins(20, 20, 20)
pdf.add_page()

# ── TITLE PAGE ──────────────────────────────────────────────────────
for _ in range(4): pdf.ln(12)
pdf.centered_text('COMMUNITY PROJECT REPORT', 16, True)
pdf.ln(12)
pdf.set_text_color(0, 100, 0)
pdf.centered_text('SMARTGARBAGE CHINTALAVALASA', 18, True)
pdf.set_text_color(0, 0, 0)
pdf.ln(2)
pdf.centered_text('Community-Based Smart Waste Management', 14)
pdf.centered_text('and Digital Governance System', 14)
pdf.ln(16)
pdf.centered_text('Submitted by', 12)
pdf.ln(4)
for name, reg in [
    ('MOPADA JAGANMOHAN', '2433144441'),
    ('LATCHUPATULA RESHMA', '24331A4434'),
    ('PATI NARASIMHA MURTHY', '2433144446'),
    ('KADA AUGUSTTN PAUL KUMAR', '24331A4426'),
]:
    pdf.centered_text(f'{name}  ({reg})', 12)
pdf.ln(8)
pdf.centered_text('In partial fulfillment for the award of the degree of', 12)
pdf.ln(4)
pdf.centered_text('BACHELOR OF TECHNOLOGY', 14, True)
pdf.centered_text('IN', 12)
pdf.centered_text('COMPUTER SCIENCE & ENGINEERING', 14, True)
pdf.centered_text('(Data Science)', 12)
pdf.ln(8)
pdf.centered_text('Under the esteemed Guidance of', 12)
pdf.ln(2)
pdf.centered_text('Mrs. S. Nikhila', 14, True)
pdf.centered_text('Assistant Professor', 12)
pdf.ln(8)
# MVGR College Logo (in the middle)
logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_diagrams', 'mvgr_logo.png')
if os.path.exists(logo_path):
    pdf.add_image_centered(logo_path, 60)
    pdf.ln(4)
pdf.centered_text('DEPARTMENT OF DATA ENGINEERING', 12, True)
pdf.centered_text('MAHARAJ VIJAYARAM GAJAPATHI RAJ COLLEGE OF ENGINEERING (Autonomous)', 11, True)
pdf.centered_text('(Approved by AICTE, New Delhi, and permanently affiliated to JNTUGV, Vizianagaram)', 9)
pdf.centered_text('Vijayaram Nagar Campus, Chintalavalasa, Vizianagaram-535005, Andhra Pradesh', 9)
pdf.ln(4)
pdf.centered_text('October, 2025', 12, True)

# ── CERTIFICATE ─────────────────────────────────────────────────────
pdf.chapter_heading('CERTIFICATE')
pdf.body_text('This is to certify that the project entitled "SmartGarbage Chintalavalasa \u2014 Community-Based Smart Waste Management and Digital Governance System" is the bonafide work carried out by Mopada Jaganmohan (2433144441), Latchupatula Reshma (24331A4434), Pati Narasimha Murthy (2433144446), and Kada Augusttn Paul Kumar (24331A4426), of B.Tech V Sem CSE-DS, M.V.G.R. College of Engineering (Autonomous), Vizianagaram, during the year 2025-2026, in partial fulfilment of the requirements for the award of the Degree of Bachelor of Technology and that the project has not formed the basis for the award previously of any degree or any other similar title.')
pdf.ln(16)
pdf.set_font('TNR', 'B', 12)
pdf.cell(0, 7, 'Signature of Project Guide', 0, 1)
pdf.body_text('Mrs. S. Nikhila\nAssistant Professor\nDepartment: Data Engineering')
pdf.ln(8)
pdf.set_font('TNR', 'B', 12)
pdf.cell(0, 7, 'Signature of Head of the Department', 0, 1)
pdf.body_text('Dr. Jyothi\nHead of the Department\nDepartment: Data Engineering')

# ── DECLARATION ─────────────────────────────────────────────────────
pdf.chapter_heading('DECLARATION')
pdf.body_text('We hereby declare that the work done on the dissertation entitled "SmartGarbage Chintalavalasa \u2014 Community-Based Smart Waste Management and Digital Governance System" has been carried out by us and submitted in partial fulfilment for the award of credits in Bachelor of Technology in Computer Science and Engineering (Data Science) of M.V.G.R College of Engineering (Autonomous) and affiliated to JNTUGV, Vizianagaram. The various contents incorporated in the dissertation have not been submitted for the award of any degree of any other institution or university.')
pdf.ln(8)
for n in ['MOPADA JAGANMOHAN (2433144441)', 'LATCHUPATULA RESHMA (24331A4434)',
          'PATI NARASIMHA MURTHY (2433144446)', 'KADA AUGUSTTN PAUL KUMAR (24331A4426)']:
    pdf.body_text(n)

# ── ACKNOWLEDGEMENT ─────────────────────────────────────────────────
pdf.chapter_heading('ACKNOWLEDGEMENT')
pdf.body_text('We express our sincere gratitude to our project guide for their invaluable guidance and support as our mentor throughout the project. Their unwavering commitment to excellence and constructive feedback motivated us to achieve our project goals. We are greatly indebted to them for their exceptional guidance.')
pdf.body_text('Additionally, we extend our thanks to Prof. P.S. Sitharama Raju (Director), Dr. Y.M.C. Shekar (Principal), and Dr. Jyothi (Head of the Department) for their unwavering support and assistance, which were instrumental in the successful completion of the project.')
pdf.body_text('We also acknowledge the dedicated assistance provided by all the staff members in the Department of Data Engineering. Finally, we appreciate the contributions of all those who directly or indirectly contributed to the successful execution of this endeavor.')
pdf.ln(4)
for n in ['MOPADA JAGANMOHAN (2433144441)', 'LATCHUPATULA RESHMA (24331A4434)',
          'PATI NARASIMHA MURTHY (2433144446)', 'KADA AUGUSTTN PAUL KUMAR (24331A4426)']:
    pdf.right_text(n)

# ── ABSTRACT ────────────────────────────────────────────────────────
pdf.chapter_heading('ABSTRACT')
pdf.body_text('Waste management in semi-urban Indian communities like Chintalavalasa, Andhra Pradesh, is plagued by informal collection schedules, paper-based complaint tracking, and overflowing bins with no accountability.')
pdf.body_text('SmartGarbage is a community-based smart waste management system built for the Chintalavalasa Gram Panchayat. It lets citizens check collection schedules, report missed pickups with photos and GPS, and track complaint resolution in real time. Administrators monitor operations through a live dashboard, assign workers, and view ward-level analytics.')
pdf.body_text('The system uses IoT-enabled smart bins to monitor fill levels and predict overflow risk, enabling proactive collection. A pay-as-you-throw billing mechanism charges residents for non-segregated waste, encouraging proper segregation. Green Points gamification rewards citizens for consistent segregation behaviour.')
pdf.body_text('For low-connectivity areas, Progressive Web App capabilities allow offline complaint filing with automatic sync. Bilingual support in English and Telugu ensures wide accessibility.')
pdf.body_text('The prototype is deployed and tested for Chintalavalasa. While synthetic data is used for machine learning training and IoT telemetry is simulated, the architecture is ready for real sensor integration and community-scale deployment.')

# ── ABBREVIATIONS ──────────────────────────────────────────────────
pdf.chapter_heading('LIST OF ABBREVIATIONS')
abbrevs = [
    ('AI', 'Artificial Intelligence'), ('API', 'Application Programming Interface'),
    ('ARIA', 'Accessible Rich Internet Applications'), ('CDN', 'Content Delivery Network'),
    ('CSP', 'Content Security Policy'), ('CSS', 'Cascading Style Sheets'),
    ('GPS', 'Global Positioning System'), ('HTML', 'HyperText Markup Language'),
    ('HTTP', 'HyperText Transfer Protocol'), ('IoT', 'Internet of Things'),
    ('ML', 'Machine Learning'), ('MFA', 'Multi-Factor Authentication'),
    ('OTP', 'One-Time Password'), ('OWASP', 'Open Web Application Security Project'),
    ('PAYT', 'Pay-As-You-Throw'), ('PWA', 'Progressive Web App'),
    ('RBAC', 'Role-Based Access Control'), ('RQ', 'Redis Queue'),
    ('SBM', 'Swachh Bharat Mission'), ('SQL', 'Structured Query Language'),
    ('SSL', 'Secure Sockets Layer'), ('SW', 'Service Worker'),
    ('TTFB', 'Time to First Byte'), ('VAPID', 'Voluntary Application Server Identification'),
    ('WCAG', 'Web Content Accessibility Guidelines'), ('XML', 'Extensible Markup Language'),
]
pdf.simple_table(['Abbreviation', 'Full Form'], abbrevs, [35, 135])

# ════════════════════════════════════════════════════════════════════
# CHAPTER 1 — INTRODUCTION
# ════════════════════════════════════════════════════════════════════
pdf.chapter_heading('1. INTRODUCTION')
pdf.section_heading('1.1 Problem Statement')
pdf.body_text('Chintalavalasa is a semi-urban panchayat in Vizianagaram district, Andhra Pradesh, with a population of approximately 12,000 residents across five administrative wards. The current waste management system relies on manual collection schedules communicated informally, resulting in inconsistent service delivery. Citizens have no reliable mechanism to report missed collections, and complaint resolution lacks transparency and accountability.')
pdf.body_text('Key problems include: (a) lack of centralized collection schedules; (b) absence of digital grievance redressal; (c) no real-time bin monitoring; (d) no data-driven resource allocation; (e) limited citizen engagement in segregation; and (f) no usage-based billing accountability.')

pdf.section_heading('1.2 Project Objective')
pdf.body_text('The primary objective is to design, develop, and deploy a community-based smart waste management and digital governance system for Chintalavalasa Gram Panchayat. Specific objectives include:')
for o in [
    'Web platform for schedules, complaint filing and tracking',
    'Admin dashboard for real-time monitoring and worker dispatch',
    'IoT smart-bin telemetry for fill levels and environmental monitoring',
    'ML module for overflow risk prediction',
    'PAYT billing with UPI/Razorpay integration',
    'PWA capabilities with offline support',
    'Comprehensive security aligned with OWASP recommendations',
    'Bilingual support (English and Telugu)',
]:
    pdf.body_bullet(o)

pdf.section_heading('1.3 Scope of the Project')
pdf.body_text('\u2022  In Scope: Web application with four portals; IoT telemetry integration; ML overflow prediction; PAYT billing; Green Points gamification; PWA offline support; push notifications; bilingual support; and security architecture.')
pdf.body_text('\u2022  Out of Scope: Native mobile apps; physical IoT hardware manufacturing; external municipal API integration; blockchain-based carbon credits; production WhatsApp/SMS (integrated but requiring API keys); and community-scale IoT deployment.')

# ════════════════════════════════════════════════════════════════════
# CHAPTER 2 — LITERATURE SURVEY
# ════════════════════════════════════════════════════════════════════
pdf.chapter_heading('2. LITERATURE SURVEY')
pdf.body_text('A comprehensive review of existing literature and systems was conducted to identify gaps that SmartGarbage addresses.')
pdf.section_heading('2.1 Existing Waste Management Approaches')
pdf.body_text('Traditional waste management in Indian semi-urban areas relies on manual collection with fixed schedules and paper-based registers. The Swachh Bharat Mission (SBM) Grameen Phase II promotes source segregation and digital monitoring, but implementation remains inconsistent at the panchayat level.')
pdf.section_heading('2.2 Digital Waste Management Systems')
pdf.body_text('SBM Urban provides complaint registration for urban areas but lacks IoT integration and offline capabilities. GOV.UK sets the benchmark for government digital services with strong accessibility compliance. SmartGarbage draws design inspiration from these platforms while adding domain-specific waste management features.')
pdf.section_heading('2.3 IoT-Based Smart Waste Management')
pdf.body_text('Anagnostopoulos et al. (2015) demonstrated that IoT-based waste monitoring using ultrasonic sensors can reduce collection costs by 30-50%. Kumar and Sharma (2021) identified that most solutions focus on individual components rather than integrated platforms. SmartGarbage addresses this by integrating IoT with complaint management, citizen engagement, and ML prediction.')
pdf.section_heading('2.4 Machine Learning for Waste Prediction')
pdf.body_text('Afshin et al. (2021) applied gradient boosting to predict waste generation. Chen et al. (2020) demonstrated that Random Forest achieves comparable accuracy for short-term prediction. SmartGarbage implements a RandomForest regressor for bin overflow prediction with transparent fallback heuristics.')
pdf.section_heading('2.5 Accessibility and Government Standards')
pdf.body_text('WCAG 2.1 Level AA provides international accessibility standards. OWASP Top 10 identifies critical web security risks. SmartGarbage implements ARIA landmarks, skip-to-content links, keyboard navigation, and all nine OWASP-recommended security headers.')
pdf.section_heading('2.6 Research / Implementation Gap')
pdf.body_text('Existing solutions address individual aspects of waste management. There is no integrated, low-cost platform combining citizen grievance reporting, collection scheduling, IoT monitoring, ML prediction, PAYT billing, offline support, and comprehensive security \u2014 all designed for semi-urban Indian communities. SmartGarbage fills this gap.')
pdf.section_heading('2.7 Proposed Contribution')
pdf.body_text('SmartGarbage contributes an integrated, open-source platform combining citizen engagement, administrative oversight, worker coordination, IoT monitoring, and ML prediction with offline-first PWA capabilities, PAYT billing with gamification, and strong security and accessibility compliance \u2014 suitable for semi-urban Indian panchayats.')

# ════════════════════════════════════════════════════════════════════
# CHAPTER 3 — DATA GATHERING
# ════════════════════════════════════════════════════════════════════
pdf.chapter_heading('3. DATA GATHERING / DATA USED')
pdf.section_heading('3.1 Study Area / Community Profile')
pdf.body_text('Chintalavalasa is a semi-urban panchayat in Vizianagaram district, Andhra Pradesh, serving approximately 12,000 residents across five wards. Coordinates range from latitude 18.0552 to 18.0751 and longitude 83.4005 to 83.4201.')
pdf.section_heading('3.2 Data Collection Methods')
pdf.body_text('\u2022  Community Interaction: Interviews with residents, ward members, and sanitation workers.\n\u2022  Field Observation: On-site observation of collection routes and complaint handling.\n\u2022  Administrative Data: Ward boundaries and population estimates from the Gram Panchayat.\n\u2022  System-Generated Data: Synthetic test data for ML training and IoT simulation.\n\u2022  Public Records: SBM Grameen guidelines, GOV.UK documentation, WCAG standards.')
pdf.section_heading('3.3 Data Sources')
pdf.simple_table(['Data Source', 'Type', 'Description', 'Use'], [
    ('Community Surveys', 'Qualitative', 'Resident interviews', 'Requirements'),
    ('Field Observations', 'Qualitative', 'On-site observation', 'System design'),
    ('Administrative Records', 'Semi-structured', 'Ward boundaries', 'Study area'),
    ('Synthetic ML Data', 'Quantitative', '600-row grid', 'ML training'),
    ('Synthetic IoT Data', 'Quantitative', 'Simulated sensors', 'IoT testing'),
], [40, 30, 55, 45])
pdf.section_heading('3.4 Ward Information')
pdf.simple_table(['Ward', 'Name', 'Latitude', 'Longitude'], [
    ('Ward 1', 'MVGR College Area', '18.0552', '83.4051'),
    ('Ward 2', 'Chintalavalasa Junction', '18.0675', '83.4094'),
    ('Ward 3', 'RTC Colony', '18.0702', '83.4153'),
    ('Ward 4', 'Ramalayam Street', '18.0650', '83.4005'),
    ('Ward 5', 'Sai Nagar', '18.0751', '83.4201'),
], [25, 60, 40, 45])
pdf.section_heading('3.5 Data Used by the Application')
pdf.body_text('\u2022  User Data: Registrations, roles, OTP records, Green Points.\n\u2022  Complaint Data: GPS, photos, status history, resolution timestamps.\n\u2022  Schedule Data: Ward-specific collection schedules.\n\u2022  IoT Telemetry: Fill level, battery, temperature, methane.\n\u2022  Waste Declaration Data: Wet, dry, sanitary, hazardous quantities.\n\u2022  Billing Data: PAYT invoices with payment status.')
pdf.section_heading('3.6 Data Preparation')
pdf.body_text('A synthetic ML training dataset of 600 rows was generated because sufficient historical telemetry was unavailable. Features include day-of-week, season index, recent complaint volume, and ward identifier. The model is designed to accept real historical data when available.')
pdf.section_heading('3.7 Database Design')
pdf.simple_table(['Entity', 'Key Attributes'], [
    ('User', 'id, username, email, password_hash, role, phone, green_points'),
    ('Complaint', 'id, name, phone, ward, description, photo, status, lat, lon'),
    ('ComplaintStatusLog', 'id, complaint_id, status, note, created_at'),
    ('SmartBin', 'id, hardware_id, lat, lon, level, battery, temp, methane'),
    ('WorkerProfile', 'id, user_id, vehicle_id, lat, lon, status, rating'),
    ('WasteDeclaration', 'id, user_id, wet_kg, dry_kg, sanitary_kg, hazardous_kg'),
    ('PAYTInvoice', 'id, user_id, period, weight_kg, amount_rs, status'),
    ('PushSubscription', 'id, user_id, endpoint, p256dh, auth'),
    ('NotificationPreference', 'id, user_id, complaint_submitted, etc.'),
], [45, 125])

# ════════════════════════════════════════════════════════════════════
# CHAPTER 4 — METHODOLOGY
# ════════════════════════════════════════════════════════════════════
pdf.chapter_heading('4. METHODOLOGY / SYSTEM DESIGN')
pdf.section_heading('4.1 Requirement Analysis')
pdf.body_text('Requirements were categorized into functional (FR) and non-functional (NFR):')
pdf.subsection_heading('Functional Requirements')
pdf.simple_table(['ID', 'Module', 'Description'], [
    ('FR-01', 'Public Portal', 'Schedules, anonymous complaints'),
    ('FR-02', 'Citizen Portal', 'Track complaints, Green Points'),
    ('FR-03', 'Admin Portal', 'Dashboard, worker dispatch, analytics'),
    ('FR-04', 'Worker Portal', 'GPS tracking, evidence upload'),
    ('FR-05', 'IoT Integration', 'Smart-bin telemetry ingestion'),
    ('FR-06', 'ML Prediction', 'Overflow risk prediction'),
    ('FR-07', 'PAYT Billing', 'Usage-based invoicing'),
    ('FR-08', 'Push Notifications', 'Web push alerts'),
    ('FR-09', 'Offline Support', 'PWA with IndexedDB queue'),
    ('FR-10', 'Bilingual Support', 'English and Telugu'),
], [20, 40, 110])
pdf.subsection_heading('Non-Functional Requirements')
pdf.simple_table(['ID', 'Category', 'Description'], [
    ('NFR-01', 'Performance', 'TTFB < 1s, compressed responses'),
    ('NFR-02', 'Security', 'OWASP headers, RBAC, bcrypt, OTP'),
    ('NFR-03', 'Accessibility', 'WCAG 2.1 AA, ARIA landmarks'),
    ('NFR-04', 'Scalability', 'Horizontal via gunicorn workers'),
    ('NFR-05', 'Offline', 'PWA with service worker + IndexedDB'),
], [20, 40, 110])

pdf.section_heading('4.2 System Architecture')
pdf.body_text('The system follows a layered architecture with five distinct layers: Presentation (Browser/PWA with Jinja2 and Bootstrap), Application (Flask route modules), Business Logic (ML engine, job queue, push notifications, PAYT billing), Data (PostgreSQL via SQLAlchemy with Redis caching), and External Services (Open-Meteo, Supabase, Sentry, Twilio).')
pdf.caption_text('Figure 4.2: Overall System Architecture')
arch_path = os.path.join(DIAG_DIR, 'architecture.png')
if os.path.exists(arch_path):
    pdf.add_image_centered(arch_path, 150)

pdf.section_heading('4.3 Development Methodology')
pdf.body_text('The project followed an iterative approach across six phases: Requirements Gathering (Weeks 1-2), System Design (Weeks 3-4), Core Development (Weeks 5-10), Integration (Weeks 11-14), Enhancement (Weeks 15-18), and Testing/Deployment (Weeks 19-20).')

pdf.section_heading('4.4 Technology Stack')
pdf.simple_table(['Component', 'Technology', 'Purpose'], [
    ('Backend', 'Flask 3.1.3', 'Web framework'),
    ('Database', 'PostgreSQL (Supabase)', 'Relational DB'),
    ('ORM', 'SQLAlchemy 2.0', 'Python ORM'),
    ('Frontend', 'Bootstrap 5 + CSS', 'Responsive UI'),
    ('ML', 'scikit-learn 1.9', 'RandomForest'),
    ('Task Queue', 'Redis + RQ 2.2', 'Background jobs'),
    ('WSGI', 'Gunicorn 26.0', 'Production server'),
    ('Push', 'pywebpush 2.0', 'Web push'),
    ('Security', 'Flask-Talisman, Limiter', 'Headers, rate limit'),
    ('Hosting', 'Render.com', 'Cloud hosting'),
    ('Docker', 'Dockerfile', 'Containerization'),
], [35, 55, 80])

pdf.section_heading('4.5 System Workflow')
pdf.body_text('The end-to-end workflow: Citizens register, file complaints (GPS + photo), system validates and stores, admin assigns workers, workers visit location, upload evidence, admin verifies, complaint resolved, citizen notified via push/email, Green Points awarded.')
pdf.caption_text('Figure 4.4: Complaint Lifecycle Flowchart')
complaint_path = os.path.join(DIAG_DIR, 'complaint.png')
if os.path.exists(complaint_path):
    pdf.add_image_centered(complaint_path, 130)

pdf.section_heading('4.6 Data Flow Diagram')
pdf.body_text('Primary data flows: (1) Citizen to Complaint API to Database to Admin Dashboard to Worker Dispatch to Evidence Upload to Resolution; (2) IoT Sensors to Telemetry API to SmartBin Table to Admin Monitor to ML Prediction to Priority Queue; (3) Schedule Request to ML Prediction to Response.')

pdf.section_heading('4.7 Machine Learning Methodology')
pdf.body_text('The ML module implements a RandomForest regressor trained on a synthetic 600-row dataset. Features: day_of_week, season_idx, recent_complaint_count, ward_id. The model predicts hours_until_90pct_fill for dispatch prioritization. A transparent heuristic fallback ensures the route never errors when the model artifact is unavailable.')
pdf.body_text('Note: Synthetic data was used during prototype development because sufficient historical telemetry was unavailable. The demonstration validates the prediction pipeline, not real-world accuracy.')
pdf.caption_text('Figure 4.7: Machine Learning Pipeline')
ml_path = os.path.join(DIAG_DIR, 'ml_pipeline.png')
if os.path.exists(ml_path):
    pdf.add_image_centered(ml_path, 150)

pdf.section_heading('4.8 Security Architecture')
pdf.body_text('\u2022  Authentication: Flask-Login with bcrypt + OTP/MFA.\n\u2022  Authorization: RBAC with citizen/worker/admin roles.\n\u2022  Security Headers: All 9 OWASP-recommended headers.\n\u2022  Rate Limiting: Flask-Limiter with Redis storage.\n\u2022  Input Validation: Flask-WTF with CSRF protection.\n\u2022  SQL Injection Prevention: SQLAlchemy parameterized queries.')

pdf.section_heading('4.9 PWA and Offline Methodology')
pdf.body_text('\u2022  Service Worker: Versioned precache manifest for offline support.\n\u2022  IndexedDB Queue: Complaints stored offline, synced on reconnection.\n\u2022  Background Sync: Automatic submission when connectivity returns.\n\u2022  Web App Manifest: Installable with shortcuts, screenshots, standalone mode.')
pdf.caption_text('Figure 4.9: PWA Offline Workflow')
pwa_path = os.path.join(DIAG_DIR, 'pwa_workflow.png')
if os.path.exists(pwa_path):
    pdf.add_image_centered(pwa_path, 150)

# ════════════════════════════════════════════════════════════════════
# CHAPTER 5 — IMPLEMENTATION
# ════════════════════════════════════════════════════════════════════
pdf.chapter_heading('5. IMPLEMENTATION / MODULES')
modules = [
    ('5.1 Public Portal', 'Provides waste-management information to all visitors.',
     'Schedule display, anonymous complaints, tracking, ward transparency, FAQ, search, RSS',
     'Flask + Jinja2 + Bootstrap 5', 'Fully implemented'),
    ('5.2 Citizen Portal', 'Authenticated portal for citizens.',
     'Registration with OTP, complaint filing, dashboard, Green Points, waste declarations',
     'Flask-Login + SQLAlchemy + Socket.IO', 'Fully implemented'),
    ('5.3 Admin Portal', 'Comprehensive admin dashboard.',
     'Complaint overview, worker dispatch, IoT monitoring, ML display, PAYT, push analytics',
     'Flask-Login + RBAC + Socket.IO', 'Fully implemented'),
    ('5.4 Worker Portal', 'Mobile-friendly worker portal.',
     'Dispatch acceptance, GPS tracking, photo evidence, task queue',
     'Flask-Login + Geolocation API', 'Fully implemented'),
    ('5.5 IoT Smart Bin Module', 'Telemetry ingestion and monitoring.',
     'Authenticated API, fill level, battery, temperature, methane, status classification',
     'Flask API + SQLAlchemy', 'Implemented (simulated)'),
    ('5.6 ML Module', 'Overflow risk prediction.',
     'RandomForest regressor, feature engineering, transparent fallback',
     'scikit-learn + pandas + numpy', 'Implemented (synthetic data)'),
    ('5.7 Green Points Module', 'Gamification for segregation.',
     'Points earned, streak tracking, leaderboard, redemption',
     'Flask-Login + SQLAlchemy', 'Fully implemented'),
    ('5.8 PAYT Module', 'Usage-based billing.',
     'Invoice generation, compliance scoring, UPI/Razorpay, PDF via ReportLab',
     'Flask + ReportLab + Razorpay', 'Implemented (test mode)'),
    ('5.9 Background Jobs', 'Async task processing.',
     'Status notifications, SLA escalation, dunning, email, push dispatch',
     'Redis + RQ', 'Fully implemented'),
    ('5.10 PWA and Offline', 'Offline capabilities.',
     'Service worker, IndexedDB queue, background sync, manifest, splash screen',
     'SW API + IndexedDB', 'Fully implemented'),
]
for heading, purpose, functions, tech, status in modules:
    pdf.section_heading(heading)
    pdf.subsection_heading('Purpose')
    pdf.body_text(purpose)
    pdf.subsection_heading('Key Functions')
    pdf.body_text(functions)
    pdf.subsection_heading('Technology')
    pdf.body_text(tech)
    pdf.subsection_heading('Status')
    pdf.body_text(status)

# ════════════════════════════════════════════════════════════════════
# CHAPTER 6 — RESULTS
# ════════════════════════════════════════════════════════════════════
pdf.chapter_heading('6. RESULTS / OUTPUTS')
pdf.section_heading('6.1 Implemented Features Summary')
pdf.simple_table(['Module', 'Features', 'Status', 'Verification'], [
    ('Public Portal', 'Homepage, schedule, transparency, search', 'Fully Implemented', '200 OK'),
    ('Citizen Portal', 'Registration, complaints, dashboard', 'Fully Implemented', '200 OK'),
    ('Admin Portal', 'Dashboard, dispatch, IoT, ML', 'Fully Implemented', '200 OK'),
    ('Worker Portal', 'Dispatch, GPS, evidence', 'Fully Implemented', '200 OK'),
    ('IoT Integration', 'Telemetry API, monitoring', 'Simulated', 'API functional'),
    ('ML Prediction', 'RandomForest prediction', 'Synthetic Data', 'Pipeline OK'),
    ('PAYT Billing', 'Invoice, payment', 'Test Mode', 'Invoice OK'),
    ('Push Notifications', 'Web push, preferences', 'Fully Implemented', 'API functional'),
    ('PWA / Offline', 'SW, IndexedDB, manifest', 'Fully Implemented', 'All 200'),
    ('Security', 'OWASP headers, RBAC, OTP', 'Fully Implemented', '9/9 headers'),
    ('Accessibility', 'ARIA, skip-to-content', 'Implemented', 'Checks pass'),
], [35, 60, 40, 35])

pdf.section_heading('6.2 Homepage Output')
pdf.body_text('The homepage displays collection schedule lookup, complaint filing shortcut, ward transparency map, weather widget, and community impact statistics.')
pdf.section_heading('6.3 Collection Schedule Output')
pdf.body_text('The schedule page shows ward-specific collection timetables with ML overflow prediction.')
pdf.section_heading('6.4 Complaint Reporting Output')
pdf.body_text('The complaint form captures name, phone, ward, address, description, photo, and automatic GPS coordinates.')
pdf.section_heading('6.5 Citizen Dashboard Output')
pdf.body_text('The citizen dashboard shows complaint history, Green Points, waste declarations, and notification preferences.')
pdf.section_heading('6.6 Admin Dashboard Output')
pdf.body_text('The admin control room displays real-time complaints, IoT bin status, worker queue, and push analytics.')

pdf.section_heading('6.7 Performance Evaluation')
pdf.simple_table(['Metric', 'Value', 'Notes'], [
    ('Homepage TTFB', '~0.5s', 'Gunicorn sync worker'),
    ('Static Cache', '31,536,000s', 'Immutable, version-busted'),
    ('HTML Cache (repeat)', '60s', 'Browser + ETag 304'),
    ('Brotli Compression', 'Level 4', 'All text responses'),
    ('Preload Hints', '4 Link headers', 'Critical resources'),
    ('FCP', '~0.5s', 'With preload hints'),
], [45, 50, 75])

pdf.section_heading('6.8 Security Evaluation')
pdf.simple_table(['Header', 'Status', 'Purpose'], [
    ('Content-Security-Policy', 'Present', 'Restricts resource loading'),
    ('Strict-Transport-Security', 'Present', 'Enforces HTTPS'),
    ('X-Content-Type-Options', 'Present', 'nosniff'),
    ('X-Frame-Options', 'Present', 'DENY clickjacking'),
    ('X-XSS-Protection', 'Present', 'Legacy XSS protection'),
    ('Referrer-Policy', 'Present', 'strict-origin-when-cross-origin'),
    ('Permissions-Policy', 'Present', 'Restricts browser features'),
    ('Cross-Origin-Opener-Policy', 'Present', 'same-origin isolation'),
    ('Cross-Origin-Embedder-Policy', 'Present', 'require-corp'),
], [55, 25, 90])

pdf.section_heading('6.9 Accessibility Evaluation')
pdf.body_text('\u2022  Skip-to-content link for keyboard navigation.\n\u2022  ARIA landmarks on all pages.\n\u2022  Semantic HTML5 elements.\n\u2022  Sufficient color contrast (minimum 4.5:1).\n\u2022  Form labels associated with inputs.\n\u2022  Keyboard-navigable elements.')

# ════════════════════════════════════════════════════════════════════
# CHAPTER 7
# ════════════════════════════════════════════════════════════════════
pdf.chapter_heading('7. IMPACT ASSESSMENT')
pdf.body_text('Note: As a prototype, impact values are estimated projections based on system capabilities, not measured community pilot results.')
pdf.section_heading('7.1 Social Impact')
pdf.body_text('\u2022  Citizen Empowerment: Transparent access to schedules, complaints, and performance metrics.\n\u2022  Accessibility: Bilingual support and PWA offline for low-connectivity areas.\n\u2022  Accountability: Digital tracking with status timelines and SLA monitoring.')
pdf.section_heading('7.2 Operational Impact')
pdf.simple_table(['Metric', 'With SmartGarbage', 'Without'], [
    ('Schedule Access', '100% digital', 'Verbal/informal'),
    ('Complaint Tracking', 'Real-time', 'Untracked'),
    ('Worker Dispatch', 'GPS-tracked', 'Manual'),
    ('Data Decisions', 'ML + analytics', 'Experience-based'),
], [45, 60, 65])
pdf.section_heading('7.3 Environmental Impact')
pdf.body_text('\u2022  Green Points incentivize source segregation.\n\u2022  IoT monitoring prevents overflow and contamination.\n\u2022  Estimated CO2 savings: 0.5 kg CO2 per kg recycled (EPA estimate).')
pdf.section_heading('7.4 Economic Feasibility')
pdf.body_text('\u2022  Zero-cost deployment on Render.com free tier.\n\u2022  PAYT billing generates revenue.\n\u2022  Optimized routes reduce fuel costs.\n\u2022  Open source eliminates vendor lock-in.')
pdf.section_heading('7.5 Scalability')
pdf.body_text('Architecture supports horizontal scaling via gunicorn workers. Multi-panchayat deployment achievable by extending WARD_COORDINATES mapping.')

# ════════════════════════════════════════════════════════════════════
# CHAPTER 8
# ════════════════════════════════════════════════════════════════════
pdf.chapter_heading('8. CHALLENGES FACED')
challenges = [
    ('Data Unavailability', 'Insufficient historical telemetry for ML', 'Generated 600-row synthetic dataset; documented limitation'),
    ('Offline Architecture', 'Complaint filing without internet', 'Service Worker + IndexedDB + Background Sync API'),
    ('Real-time Updates', 'Live dashboard without refresh', 'Flask-SocketIO with Redis broker'),
    ('IoT Simulation', 'No physical hardware', 'Authenticated API with test data generators'),
    ('Security Hardening', 'Comprehensive security without usability loss', 'All 9 OWASP headers via Flask-Talisman'),
    ('Performance', 'TTFB on free-tier hosting', 'Multi-layer caching, Brotli, preload hints'),
    ('Bilingual Support', 'Consistent translations', 'Flask-Babel with gettext markers'),
    ('Push Notifications', 'Reliable delivery', 'pywebpush with VAPID + preference filtering'),
    ('Deployment', 'Dev/prod consistency', 'Docker containerization + env vars + health check'),
    ('Payment Integration', 'Testing without live merchant', 'Razorpay test keys + UPI primary method'),
]
for challenge, problem, solution in challenges:
    pdf.subsection_heading(challenge)
    pdf.set_font('TNR', '', 12)
pdf.cell(0, 6.5, f'Problem: {problem}', new_x='LMARGIN', new_y='NEXT')
pdf.cell(0, 6.5, f'Solution: {solution}', new_x='LMARGIN', new_y='NEXT')
pdf.ln(4)

# ════════════════════════════════════════════════════════════════════
# CHAPTER 9
# ════════════════════════════════════════════════════════════════════
pdf.chapter_heading('9. CONCLUSION')
pdf.section_heading('9.1 Summary')
pdf.body_text('SmartGarbage Chintalavalasa is a community-based smart waste management and digital governance system integrating Flask, PostgreSQL, IoT telemetry, ML prediction, PWA offline capabilities, PAYT billing, and comprehensive security into a unified platform.')
pdf.section_heading('9.2 Achievement of Objectives')
pdf.body_text('The project successfully achieved all eight stated objectives: web platform, admin dashboard, IoT integration, ML prediction, PAYT billing, PWA capabilities, security implementation, and bilingual support.')
pdf.section_heading('9.3 Limitations')
pdf.body_text('\u2022  ML trained on synthetic data, not validated with real telemetry.\n\u2022  IoT telemetry simulated without physical sensors.\n\u2022  PAYT in test mode without live merchant account.\n\u2022  Impact values are estimated, not measured from a pilot.\n\u2022  Not tested with real users at community scale.\n\u2022  SMS/WhatsApp require third-party API keys.')

# ════════════════════════════════════════════════════════════════════
# CHAPTER 10
# ════════════════════════════════════════════════════════════════════
pdf.chapter_heading('10. FUTURE WORK')
for section, items in [
    ('10.1 Real-World Data Integration', ['Replace synthetic ML data with real telemetry', 'Conduct community pilot with actual residents', 'Collect baseline data for before/after studies']),
    ('10.2 IoT Hardware Deployment', ['Deploy ultrasonic fill-level sensors', 'GPS trackers on collection vehicles', 'LoRaWAN or NB-IoT connectivity']),
    ('10.3 Mobile Application', ['Native Android application', 'WhatsApp Business API chatbot', 'SMS schedule notifications']),
    ('10.4 Advanced Analytics', ['Time-series forecasting', 'Route optimization', 'Computer vision waste classification']),
    ('10.5 Multi-Panchayat Deployment', ['Tenant isolation for multiple panchayats', 'District-level aggregation', 'SBM Grameen reporting compliance']),
    ('10.6 Payment and Billing', ['Live Razorpay merchant account', 'Recurring billing via UPI mandates', 'Payment analytics and revenue reporting']),
]:
    pdf.section_heading(section)
    for item in items:
        pdf.body_bullet(item)

# ════════════════════════════════════════════════════════════════════
# REFERENCES
# ════════════════════════════════════════════════════════════════════
pdf.chapter_heading('REFERENCES')
refs = [
    '[1] GOV.UK, "Design System," Government Digital Service, 2024.',
    '[2] Ministry of Housing and Urban Affairs, "Swachh Bharat Mission \u2014 Urban," 2024.',
    '[3] Ministry of Jal Shakti, "SBM \u2014 Grameen Phase II," 2024.',
    '[4] T. Anagnostopoulos et al., "Waste Management as IoT-Enabled Service," Springer, 2015.',
    '[5] M. A. ad Din et al., "Smart Bin: IoT-Based Waste Monitoring," Proc. IT, 2020.',
    '[6] S. Kumar and R. Sharma, "IoT-Based Smart Waste Management: A Review," J. Cleaner Production, 2021.',
    '[7] M. Afshin et al., "ML Approaches for MSW Generation Prediction," Waste Management, 2021.',
    '[8] Y. Chen et al., "Predicting MSW Using ML Methods," Env. Sci. Pollution Research, 2020.',
    '[9] D. Thung and M. Yang, "Waste Classification using CNN," AISI, Springer, 2016.',
    '[10] W3C, "WCAG 2.1," World Wide Web Consortium, 2018.',
    '[11] OWASP Foundation, "OWASP Top Ten 2021," 2021.',
    '[12] U.S. EPA, "Pay-As-You-Throw," 2023.',
    '[13] Flask Documentation, "Flask \u2014 Pallets Projects," 2024.',
    '[14] SQLAlchemy Documentation, "SQLAlchemy," 2024.',
    '[15] scikit-learn Documentation, "scikit-learn," 2024.',
    '[16] MDN Web Docs, "Progressive Web Apps," Mozilla, 2024.',
    '[17] Web Push Protocol, "Push API \u2014 MDN," Mozilla, 2024.',
    '[18] Supabase Documentation, "Supabase," 2024.',
    '[19] Render Documentation, "Render," 2024.',
    '[20] Razorpay Documentation, "Razorpay Docs," 2024.',
]
for r in refs:
    pdf.body_text(r)

# ════════════════════════════════════════════════════════════════════
# APPENDIX A
# ════════════════════════════════════════════════════════════════════
pdf.chapter_heading('APPENDIX A: PACKAGES, TOOLS USED & WORKING PROCESS')
pdf.section_heading('A.1 Packages and Tools')
pdf.simple_table(['Package', 'Category', 'Purpose'], [
    ('Flask 3.1.3', 'Python', 'Web framework'),
    ('Flask-SQLAlchemy 3.1.1', 'Python', 'ORM'),
    ('Flask-Login 0.6.3', 'Python', 'Sessions'),
    ('Flask-Talisman 1.1.0', 'Python', 'Security headers'),
    ('Flask-Limiter 4.1.1', 'Python', 'Rate limiting'),
    ('Flask-Compress 1.17', 'Python', 'Compression'),
    ('SQLAlchemy 2.0.50', 'Python', 'ORM'),
    ('Redis 6.2.0', 'Python', 'Cache client'),
    ('RQ 2.2.0', 'Python', 'Job queue'),
    ('scikit-learn 1.9.0', 'Python', 'ML'),
    ('pandas 3.0.3', 'Python', 'Data processing'),
    ('pywebpush 2.0.0', 'Python', 'Push notifications'),
    ('reportlab 5.0.0', 'Python', 'PDF generation'),
    ('gunicorn 26.0.0', 'Python', 'WSGI server'),
    ('Bootstrap 5', 'CSS/JS', 'UI framework'),
    ('Docker', 'DevOps', 'Containerization'),
    ('PostgreSQL (Supabase)', 'Database', 'Relational DB'),
    ('Render.com', 'Cloud', 'Hosting'),
], [50, 30, 90])

pdf.section_heading('A.2 Working Process')
pdf.body_text('1. Environment Setup: Python 3.12 virtual env, Flask dependencies, PostgreSQL on Supabase, Redis on Upstash.\n2. Project Structure: app/routes/, app/templates/, app/static/, app/models.py.\n3. Version Control: Git with GitHub repository.\n4. Iterative Development: Public, Citizen, Admin, Worker, IoT, ML, PWA.\n5. Testing: Flask test client, python -m compileall, curl security checks.\n6. Deployment: Docker multi-stage build, Render.com auto-deploy from GitHub.\n7. Monitoring: Sentry integration, /health endpoint, structured logging.')

# APPENDIX B
pdf.chapter_heading('APPENDIX B: IMPORTANT SOURCE CODE')
pdf.section_heading('B.1 Application Factory (app/__init__.py)')
pdf.body_text('Flask application factory initializing extensions, security headers, caching, and background jobs.')
pdf.section_heading('B.2 Database Models (app/models.py)')
pdf.body_text('SQLAlchemy models: User, Complaint, SmartBin, WorkerProfile, WasteDeclaration, PAYTInvoice, PushSubscription, NotificationPreference, ConsentRecord.')
pdf.section_heading('B.3 ML Module (app/ml_model.py)')
pdf.body_text('RandomForest regressor with synthetic data training and transparent heuristic fallback.')
pdf.section_heading('B.4 Service Worker (app/static/sw.js)')
pdf.body_text('Versioned precache manifest, stale-while-revalidate for HTML, cache-first for assets, push event handler.')
pdf.section_heading('B.5 Push Module (app/push.py)')
pdf.body_text('VAPID key management, preference-based filtering, delivery logging, complaint lifecycle integration.')

# PAPER PUBLICATIONS
pdf.chapter_heading('PAPER PUBLICATIONS')
pdf.body_text('No research papers have been published based on this project at the time of report submission.')

# ════════════════════════════════════════════════════════════════════
# SAVE
# ════════════════════════════════════════════════════════════════════
pdf.output(OUT)
sz = os.path.getsize(OUT)
print(f"PDF generated: {OUT}")
print(f"Size: {sz:,} bytes ({sz/1024:.1f} KB)")
print(f"Pages: {pdf.pages_count}")
