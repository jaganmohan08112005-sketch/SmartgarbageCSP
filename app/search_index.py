"""
Static search index for site-wide search.

Each entry is a searchable page/block with:
  - path: URL path (linked from results)
  - title: page title shown in results
  - description: short snippet shown in results
  - keywords: searchable terms (lowercased)
  - category: for grouping results (Service, Information, Support)

The index is intentionally small (static dict) so it loads instantly
with zero DB queries — matching GOV.UK's instant-search pattern.
"""

SEARCH_INDEX = [
    # ── Core Services ──────────────────────────────────────────────
    {
        "path": "/schedule",
        "title": "Collection Schedules",
        "description": "Check daily waste collection timetables for all 5 wards in Chintalavalasa. Select your ward to see today's pickup schedule.",
        "keywords": "schedule timetable collection pickup garbage waste ward calendar daily morning time slot",
        "category": "Service",
        "icon": "fa-calendar-days",
    },
    {
        "path": "/report",
        "title": "Report a Missed Pickup",
        "description": "File a missed-service complaint with GPS coordinates and photos. No login needed. Average resolution time under 24 hours.",
        "keywords": "report complaint missed pickup overflow bin垃圾 waste garbage problem issue file grievance",
        "category": "Service",
        "icon": "fa-triangle-exclamation",
    },
    {
        "path": "/transparency",
        "title": "Ward Transparency Dashboard",
        "description": "View live bin fill levels, complaint resolution rates, and segregation percentages for each ward.",
        "keywords": "transparency dashboard ward bin fill level resolution status live data statistics",
        "category": "Service",
        "icon": "fa-location-dot",
    },
    {
        "path": "/register",
        "title": "Resident Registration",
        "description": "Create an account to track complaints, earn Green Points, and manage Pay-As-You-Throw billing.",
        "keywords": "register signup account citizen resident create login green points tracking",
        "category": "Service",
        "icon": "fa-user-plus",
    },
    {
        "path": "/register/picker",
        "title": "Waste Picker Registration",
        "description": "Register as a sanitation worker. Access fleet dispatch, task assignment, and route optimization tools.",
        "keywords": "register picker waste worker sanitation crew staff registration",
        "category": "Service",
        "icon": "fa-recycle",
    },
    {
        "path": "/login",
        "title": "Municipal Staff Login",
        "description": "Login portal for municipal staff. Access control room, GIS telemetry, fleet dispatch and analytics.",
        "keywords": "login staff officer admin control room municipal government employee",
        "category": "Service",
        "icon": "fa-right-to-bracket",
    },

    # ── Information Pages ──────────────────────────────────────────
    {
        "path": "/about",
        "title": "About SmartGarbage",
        "description": "Who operates this portal, which areas it serves, mission, services, team, and editorial policy.",
        "keywords": "about mission team directorate waste management sanitation gram panchayat governance editorial credentials",
        "category": "Information",
        "icon": "fa-circle-info",
    },
    {
        "path": "/faq",
        "title": "Frequently Asked Questions",
        "description": "Answers to common questions about schedules, reporting, Green Points, segregation, wards, and billing.",
        "keywords": "faq questions answers help schedule report green points segregation wards billing fee",
        "category": "Information",
        "icon": "fa-circle-question",
    },
    {
        "path": "/contact",
        "title": "Contact Us",
        "description": "Reach the grievance hotline at 1800-119-9111, visit our Gram Panchayat office, or send a message via the contact form.",
        "keywords": "contact phone hotline email address office grievance help support reach call",
        "category": "Support",
        "icon": "fa-envelope",
    },
    {
        "path": "/privacy",
        "title": "Privacy Policy",
        "description": "DPDP Act 2023 compliant privacy policy. Learn what data we collect, how it is used, and your rights.",
        "keywords": "privacy policy dpdp act data protection cookies gps personal information rights consent",
        "category": "Information",
        "icon": "fa-shield-halved",
    },
    {
        "path": "/terms",
        "title": "Terms of Service",
        "description": "Terms of use for the SmartGarbage portal including Green Points rules, PAYT billing, and user responsibilities.",
        "keywords": "terms service rules green points payt billing user agreement conditions",
        "category": "Information",
        "icon": "fa-file-contract",
    },

    # ── Ward Information ───────────────────────────────────────────
    {
        "path": "/schedule",
        "title": "Ward 1 — MVGR College Area",
        "description": "Student housing and campus surroundings. Collection timetable and bin status for Ward 1.",
        "keywords": "ward 1 mvgr college area student housing campus",
        "category": "Ward",
        "icon": "fa-location-dot",
    },
    {
        "path": "/schedule",
        "title": "Ward 2 — Chintalavalasa Junction",
        "description": "Commercial hub and main road corridor. Collection timetable and bin status for Ward 2.",
        "keywords": "ward 2 chintalavalasa junction commercial hub main road",
        "category": "Ward",
        "icon": "fa-location-dot",
    },
    {
        "path": "/schedule",
        "title": "Ward 3 — RTC Colony",
        "description": "Residential area near the bus depot. Collection timetable and bin status for Ward 3.",
        "keywords": "ward 3 rtc colony residential bus depot",
        "category": "Ward",
        "icon": "fa-location-dot",
    },
    {
        "path": "/schedule",
        "title": "Ward 4 — Ramalayam Street",
        "description": "Temple district and heritage neighborhood. Collection timetable and bin status for Ward 4.",
        "keywords": "ward 4 ramalayam street temple district heritage",
        "category": "Ward",
        "icon": "fa-location-dot",
    },
    {
        "path": "/schedule",
        "title": "Ward 5 — Sai Nagar",
        "description": "Newer residential extension with growing population. Collection timetable and bin status for Ward 5.",
        "keywords": "ward 5 sai nagar residential extension new",
        "category": "Ward",
        "icon": "fa-location-dot",
    },

    # ── FAQ Answers (high-value search targets) ────────────────────
    {
        "path": "/schedule",
        "title": "How do I check my garbage collection schedule?",
        "description": "Open the schedule page and select your ward. Schedules update every morning before 7 AM for all 5 wards.",
        "keywords": "schedule check collection time garbage pickup when morning 7am ward timetable",
        "category": "FAQ",
        "icon": "fa-circle-question",
    },
    {
        "path": "/report",
        "title": "How do I report a missed service?",
        "description": "Use the report page to file a complaint with your address, GPS coordinates and optional photo. No account needed. Resolution within 24 hours.",
        "keywords": "report missed service complaint how file address gps photo no account 24 hours",
        "category": "FAQ",
        "icon": "fa-circle-question",
    },
    {
        "path": "/schedule",
        "title": "How should I segregate waste before collection?",
        "description": "Separate dry recyclables (paper, plastic, metal) from wet food waste. Place each type in a separate bag before morning pickup.",
        "keywords": "segregate waste separation dry wet recyclable plastic paper food compost bin two bags",
        "category": "FAQ",
        "icon": "fa-circle-question",
    },
    {
        "path": "/report",
        "title": "Can I track my complaint after filing?",
        "description": "Yes. You receive a tracking link via SMS. Register an account to view all complaints on your citizen dashboard with real-time status updates.",
        "keywords": "track complaint status tracking link sms dashboard real time follow progress",
        "category": "FAQ",
        "icon": "fa-circle-question",
    },
    {
        "path": "/register",
        "title": "What are Green Points and how do I earn them?",
        "description": "Green Points reward residents for filing reports and declaring daily segregation. Earn 15 points per report. Redeem for vouchers and tax discounts.",
        "keywords": "green points earn redeem voucher tax discount points reward declare segregation",
        "category": "FAQ",
        "icon": "fa-circle-question",
    },
    {
        "path": "/schedule",
        "title": "Which wards are covered by the service?",
        "description": "All 5 wards: MVGR College Area, Chintalavalasa Junction, RTC Colony, Ramalayam Street, and Sai Nagar. Serving 12,000+ residents.",
        "keywords": "wards covered service mvgr junction rtc ramalayam sai nagar 5 areas neighborhoods",
        "category": "FAQ",
        "icon": "fa-circle-question",
    },
    {
        "path": "/about",
        "title": "Is there a fee for using this portal?",
        "description": "No. The portal is free for all residents. Checking schedules, reporting issues, and tracking complaints require no payment or login.",
        "keywords": "free fee cost charge payment price portal subscription",
        "category": "FAQ",
        "icon": "fa-circle-question",
    },
    {
        "path": "/transparency",
        "title": "How do I check ward transparency and bin status?",
        "description": "Visit the transparency page to see live fill levels, complaint resolution rates, and segregation percentages for your ward.",
        "keywords": "transparency bin status fill level resolution rate segregation ward dashboard live",
        "category": "FAQ",
        "icon": "fa-circle-question",
    },

    # ── Contact & Support ──────────────────────────────────────────
    {
        "path": "/contact",
        "title": "Grievance Hotline — 1800-119-9111",
        "description": "Call the toll-free grievance hotline 1800-119-9111 for urgent sanitation issues. Available 24/7.",
        "keywords": "phone hotline 1800 119 9111 call grievance help urgent emergency toll free",
        "category": "Support",
        "icon": "fa-headset",
    },
    {
        "path": "/contact",
        "title": "Gram Panchayat Office Address",
        "description": "Chintalavalasa Gram Panchayat Office, Denkada Mandal, Vizianagaram District, Andhra Pradesh — 535005.",
        "keywords": "address office gram panchayat denkada vizianagaram andhra pradesh 535005 location",
        "category": "Support",
        "icon": "fa-building",
    },

    # ── Legal & Compliance ─────────────────────────────────────────
    {
        "path": "/privacy",
        "title": "Data Collected by This Portal",
        "description": "Contact details, addresses, report descriptions, GPS location, photos, and PAYT billing records. Only what is needed for waste collection.",
        "keywords": "data collected personal information contact address gps photo billing what data",
        "category": "Information",
        "icon": "fa-database",
    },
    {
        "path": "/terms",
        "title": "Green Points Redemption Rules",
        "description": "Points are redeemable for local vouchers and municipal tax discounts. The Gram Panchayat reserves the right to modify point values.",
        "keywords": "green points rules redemption voucher tax discount terms conditions program",
        "category": "Information",
        "icon": "fa-coins",
    },
    {
        "path": "/terms",
        "title": "Pay-As-You-Throw (PAYT) Billing",
        "description": "Weight-based waste disposal billing for bulk waste generators. View invoices and payment history in your dashboard.",
        "keywords": "payt pay as you throw billing weight invoice payment bulk waste generator",
        "category": "Information",
        "icon": "fa-receipt",
    },
]


def search_pages(query: str) -> list[dict]:
    """Search the index and return matching results ranked by relevance.

    Matching is keyword-based: the query is tokenized into lowercase words
    and each index entry is scored by how many query tokens match its
    keywords, title, or description.  Results with zero matches are
    excluded.
    """
    if not query or not query.strip():
        return []

    tokens = [t.lower() for t in query.split() if len(t) >= 2]
    if not tokens:
        return []

    scored = []
    seen_paths = set()
    for entry in SEARCH_INDEX:
        haystack = (
            entry["title"].lower()
            + " "
            + entry["description"].lower()
            + " "
            + entry["keywords"].lower()
        )
        hits = sum(1 for t in tokens if t in haystack)
        if hits == 0:
            continue
        # Deduplicate: keep the highest-scoring entry per unique
        # (path + title) pair so ward-specific results don't collapse.
        key = (entry["path"], entry["title"])
        if key in seen_paths:
            continue
        seen_paths.add(key)
        scored.append((hits, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored[:20]]
