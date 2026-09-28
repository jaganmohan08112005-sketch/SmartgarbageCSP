#!/usr/bin/env python3
"""Generate 3 missing diagrams for the SmartGarbage report."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import os, numpy as np

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_diagrams')
os.makedirs(OUT, exist_ok=True)

# Color palette
C = {
    'bg': '#FAFBFC', 'blue': '#2563EB', 'blue_l': '#DBEAFE',
    'green': '#059669', 'green_l': '#D1FAE5', 'orange': '#D97706',
    'orange_l': '#FEF3C7', 'red': '#DC2626', 'red_l': '#FEE2E2',
    'purple': '#7C3AED', 'purple_l': '#EDE9FE', 'gray': '#6B7280',
    'gray_l': '#F3F4F6', 'dark': '#1F2937', 'white': '#FFFFFF',
    'teal': '#0891B2', 'teal_l': '#CFFAFE',
}

def box(ax, x, y, w, h, text, fc, ec, fs=9, fw='bold', ta='center'):
    r = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05",
                        facecolor=fc, edgecolor=ec, linewidth=1.5, zorder=2)
    ax.add_patch(r)
    ax.text(x + w/2, y + h/2, text, ha='center', va='center',
            fontsize=fs, fontweight=fw, color=C['dark'], zorder=3, wrap=True)

def arrow(ax, x1, y1, x2, y2, color='#6B7280', style='->', lw=1.5):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, color=color, lw=lw), zorder=1)

# ════════════════════════════════════════════════════════════════════
# DIAGRAM 1: SECURITY ARCHITECTURE
# ════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(10, 8))
ax.set_xlim(0, 10); ax.set_ylim(0, 10)
ax.axis('off'); ax.set_facecolor(C['bg'])
fig.patch.set_facecolor(C['bg'])
ax.set_title('Security Architecture', fontsize=16, fontweight='bold', color=C['dark'], pad=20)

# Layer 1: Transport Security (top)
box(ax, 0.5, 8.5, 9, 1.0, '', C['blue_l'], C['blue'], fs=1)
ax.text(5, 9.25, 'TRANSPORT SECURITY', ha='center', va='center', fontsize=11, fontweight='bold', color=C['blue'])
items = ['HTTPS (HSTS)', 'TLS 1.3', 'Cloudflare CDN']
for i, t in enumerate(items):
    ax.text(1.8 + i*2.8, 8.75, f'● {t}', ha='center', va='center', fontsize=9, color=C['dark'])

# Layer 2: HTTP Security Headers
box(ax, 0.5, 7.0, 9, 1.2, '', C['green_l'], C['green'], fs=1)
ax.text(5, 7.9, 'HTTP SECURITY HEADERS (Flask-Talisman)', ha='center', va='center', fontsize=10, fontweight='bold', color=C['green'])
headers_l1 = ['CSP', 'X-Frame-Options', 'X-Content-Type', 'X-XSS-Protection']
headers_l2 = ['Referrer-Policy', 'Permissions-Policy', 'COOP', 'COEP']
for i, h in enumerate(headers_l1):
    ax.text(1.5 + i*2.2, 7.5, f'✓ {h}', ha='center', va='center', fontsize=8, color=C['dark'])
for i, h in enumerate(headers_l2):
    ax.text(1.5 + i*2.2, 7.2, f'✓ {h}', ha='center', va='center', fontsize=8, color=C['dark'])

# Layer 3: Authentication & Authorization
box(ax, 0.5, 5.2, 9, 1.5, '', C['orange_l'], C['orange'], fs=1)
ax.text(5, 6.4, 'AUTHENTICATION & AUTHORIZATION', ha='center', va='center', fontsize=10, fontweight='bold', color=C['orange'])
auth_items = [
    ('Flask-Login', 'Session Management'),
    ('bcrypt', 'Password Hashing'),
    ('OTP/MFA', 'Multi-Factor Auth'),
    ('RBAC', 'Role-Based Access'),
]
for i, (name, desc) in enumerate(auth_items):
    x = 1.0 + i * 2.3
    box(ax, x, 5.4, 2.0, 0.7, '', C['white'], C['orange'], fs=1)
    ax.text(x+1.0, 5.85, name, ha='center', va='center', fontsize=9, fontweight='bold', color=C['orange'])
    ax.text(x+1.0, 5.55, desc, ha='center', va='center', fontsize=7, color=C['gray'])

# Layer 4: Application Security
box(ax, 0.5, 3.5, 9, 1.4, '', C['purple_l'], C['purple'], fs=1)
ax.text(5, 4.6, 'APPLICATION SECURITY', ha='center', va='center', fontsize=10, fontweight='bold', color=C['purple'])
app_items = ['SQLAlchemy\nParameterized Queries', 'CSRF Protection\n(Flask-WTF)', 'Input Validation\n& Sanitization', 'File Upload\nSize Limits']
for i, t in enumerate(app_items):
    x = 0.8 + i * 2.3
    box(ax, x, 3.7, 2.0, 0.7, '', C['white'], C['purple'], fs=1)
    ax.text(x+1.0, 4.05, t, ha='center', va='center', fontsize=7, color=C['dark'])

# Layer 5: Infrastructure Security (bottom)
box(ax, 0.5, 1.8, 9, 1.4, '', C['red_l'], C['red'], fs=1)
ax.text(5, 2.9, 'INFRASTRUCTURE & MONITORING', ha='center', va='center', fontsize=10, fontweight='bold', color=C['red'])
infra_items = ['Docker\nContainerization', 'Environment\nVariable Secrets', 'Audit Logging\n& Monitoring', 'Sentry\nError Tracking']
for i, t in enumerate(infra_items):
    x = 0.8 + i * 2.3
    box(ax, x, 2.0, 2.0, 0.7, '', C['white'], C['red'], fs=1)
    ax.text(x+1.0, 2.35, t, ha='center', va='center', fontsize=7, color=C['dark'])

# Users at top
box(ax, 3.0, 0.2, 4.0, 0.8, 'Users (Citizen / Admin / Worker)', C['teal_l'], C['teal'], fs=10)

# Arrows
arrow(ax, 5, 1.0, 5, 1.8, C['teal'])
arrow(ax, 5, 3.2, 5, 3.5, C['red'])
arrow(ax, 5, 4.9, 5, 5.2, C['purple'])
arrow(ax, 5, 6.7, 5, 7.0, C['orange'])
arrow(ax, 5, 8.2, 5, 8.5, C['green'])

plt.tight_layout()
plt.savefig(os.path.join(OUT, 'security_architecture.png'), dpi=200, bbox_inches='tight',
            facecolor=C['bg'], edgecolor='none')
plt.close()
print("Created: security_architecture.png")


# ════════════════════════════════════════════════════════════════════
# DIAGRAM 2: DATA FLOW DIAGRAM
# ════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(11, 7))
ax.set_xlim(0, 11); ax.set_ylim(0, 7)
ax.axis('off'); ax.set_facecolor(C['bg'])
fig.patch.set_facecolor(C['bg'])
ax.set_title('Data Flow Diagram — SmartGarbage', fontsize=16, fontweight='bold', color=C['dark'], pad=20)

# External Entities (left)
entities = [('Citizen\n(User)', 0.3, 5.5), ('Worker\n(Field)', 0.3, 3.5), ('Admin\n(Office)', 0.3, 1.5)]
for name, x, y in entities:
    box(ax, x, y, 1.5, 1.0, name, C['teal_l'], C['teal'], fs=9)

# Processes (middle)
processes = [
    ('P1: Complaint\nProcessing', 3.5, 5.3, C['blue_l'], C['blue']),
    ('P2: Schedule\nManagement', 3.5, 3.3, C['green_l'], C['green']),
    ('P3: Admin\nDashboard', 3.5, 1.3, C['orange_l'], C['orange']),
    ('P4: IoT\nProcessing', 7.0, 5.3, C['purple_l'], C['purple']),
    ('P5: ML\nPrediction', 7.0, 3.3, C['red_l'], C['red']),
    ('P6: Notification\n& Jobs', 7.0, 1.3, C['gray_l'], C['gray']),
]
for name, x, y, fc, ec in processes:
    box(ax, x, y, 1.8, 1.0, name, fc, ec, fs=9)

# Data Stores (right)
stores = [('Complaints\nDB', 9.5, 5.5, C['blue_l']),
          ('Schedules\nDB', 9.5, 3.5, C['green_l']),
          ('ML Model\n+ Data', 9.5, 1.5, C['red_l'])]
for name, x, y, fc in stores:
    # Data store as cylinder-like shape
    r = FancyBboxPatch((x, y), 1.3, 0.8, boxstyle="round,pad=0.05",
                        facecolor=fc, edgecolor=C['dark'], linewidth=1.5, zorder=2)
    ax.add_patch(r)
    ax.text(x+0.65, y+0.4, name, ha='center', va='center', fontsize=8, fontweight='bold', color=C['dark'], zorder=3)

# Arrows: Entities → Processes
arrow(ax, 1.8, 6.0, 3.5, 5.8, C['teal'])
arrow(ax, 1.8, 4.0, 3.5, 3.8, C['teal'])
arrow(ax, 1.8, 2.0, 3.5, 1.8, C['teal'])

# Arrows: Processes → Processes
arrow(ax, 5.3, 5.8, 7.0, 5.8, C['blue'])
arrow(ax, 5.3, 3.8, 7.0, 3.8, C['green'])
arrow(ax, 5.3, 1.8, 7.0, 1.8, C['orange'])

# Arrows: Processes → Data Stores
arrow(ax, 8.8, 5.8, 9.5, 5.9, C['purple'])
arrow(ax, 8.8, 3.8, 9.5, 3.9, C['red'])
arrow(ax, 8.8, 1.8, 9.5, 1.9, C['gray'])

# Arrow: ML → DB
arrow(ax, 10.15, 2.3, 10.15, 3.5, C['red'], style='->', lw=1)

# Labels
ax.text(5.5, 6.7, 'EXTERNAL\nENTITIES', ha='center', va='center', fontsize=9, fontweight='bold', color=C['gray'], style='italic')
ax.text(8.0, 6.7, 'PROCESSES', ha='center', va='center', fontsize=9, fontweight='bold', color=C['gray'], style='italic')
ax.text(10.15, 6.7, 'DATA\nSTORES', ha='center', va='center', fontsize=9, fontweight='bold', color=C['gray'], style='italic')

plt.tight_layout()
plt.savefig(os.path.join(OUT, 'data_flow_diagram.png'), dpi=200, bbox_inches='tight',
            facecolor=C['bg'], edgecolor='none')
plt.close()
print("Created: data_flow_diagram.png")


# ════════════════════════════════════════════════════════════════════
# DIAGRAM 3: DATABASE ER DIAGRAM
# ════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(12, 8))
ax.set_xlim(0, 12); ax.set_ylim(0, 8)
ax.axis('off'); ax.set_facecolor(C['bg'])
fig.patch.set_facecolor(C['bg'])
ax.set_title('Database Entity-Relationship Diagram', fontsize=16, fontweight='bold', color=C['dark'], pad=20)

# Entity definitions: (name, x, y, fields, color)
entities_db = [
    ('User', 0.3, 6.0, ['id (PK)', 'username', 'email', 'password_hash', 'role', 'phone', 'language', 'created_at'], C['blue_l'], C['blue']),
    ('Complaint', 0.3, 3.0, ['id (PK)', 'user_id (FK)', 'ward', 'description', 'photo_url', 'latitude', 'longitude', 'status', 'priority', 'created_at'], C['green_l'], C['green']),
    ('WasteDeclaration', 0.3, 0.2, ['id (PK)', 'user_id (FK)', 'wet_kg', 'dry_kg', 'month', 'year', 'created_at'], C['teal_l'], C['teal']),
    ('SmartBin', 4.5, 6.0, ['id (PK)', 'bin_id', 'ward', 'latitude', 'longitude', 'installed_date'], C['purple_l'], C['purple']),
    ('Telemetry', 4.5, 3.5, ['id (PK)', 'bin_id (FK)', 'fill_level', 'temperature', 'battery', 'methane', 'timestamp'], C['orange_l'], C['orange']),
    ('PAYTInvoice', 4.5, 1.0, ['id (PK)', 'user_id (FK)', 'month', 'year', 'wet_charged', 'dry_charged', 'total', 'status', 'razorpay_id'], C['red_l'], C['red']),
    ('GreenPoint', 8.5, 6.0, ['id (PK)', 'user_id (FK)', 'points', 'reason', 'created_at'], C['green_l'], C['green']),
    ('PushSubscription', 8.5, 4.0, ['id (PK)', 'user_id (FK)', 'endpoint', 'p256dh', 'auth', 'created_at'], C['gray_l'], C['gray']),
    ('WorkerProfile', 8.5, 2.0, ['id (PK)', 'user_id (FK)', 'vehicle_type', 'assigned_wards', 'is_active'], C['teal_l'], C['teal']),
]

for name, x, y, fields, fc, ec in entities_db:
    h = 0.3 + len(fields) * 0.28
    w = 2.8
    # Header
    r = FancyBboxPatch((x, y + h - 0.35), w, 0.35, boxstyle="round,pad=0.02",
                        facecolor=ec, edgecolor=ec, linewidth=1.5, zorder=2)
    ax.add_patch(r)
    ax.text(x + w/2, y + h - 0.17, name, ha='center', va='center', fontsize=9, fontweight='bold', color=C['white'], zorder=3)
    # Body
    r2 = FancyBboxPatch((x, y), w, h - 0.35, boxstyle="round,pad=0.02",
                         facecolor=fc, edgecolor=ec, linewidth=1.5, zorder=2)
    ax.add_patch(r2)
    for i, f in enumerate(fields):
        prefix = '[PK] ' if 'PK' in f else '[FK] ' if 'FK' in f else '      '
        ax.text(x + 0.15, y + h - 0.55 - i*0.28, f'{prefix}{f}', ha='left', va='center',
                fontsize=7, color=C['dark'], zorder=3, family='monospace')

# Relationships
rels = [
    (3.1, 6.5, 4.5, 6.5, 'has bins'),
    (3.1, 3.5, 4.5, 4.0, 'records'),
    (3.1, 0.7, 4.5, 1.3, 'generates'),
    (7.3, 6.5, 8.5, 6.5, 'earns'),
    (3.1, 6.2, 8.5, 4.3, 'subscribes'),
    (7.3, 3.8, 8.5, 2.3, 'managed by'),
]
for x1, y1, x2, y2, label in rels:
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=C['gray'], lw=1.2, connectionstyle='arc3,rad=0.1'),
                zorder=1)
    mx, my = (x1+x2)/2, (y1+y2)/2
    ax.text(mx, my+0.12, label, ha='center', va='center', fontsize=6, color=C['gray'], style='italic', zorder=1)

plt.tight_layout()
plt.savefig(os.path.join(OUT, 'database_er_diagram.png'), dpi=200, bbox_inches='tight',
            facecolor=C['bg'], edgecolor='none')
plt.close()
print("Created: database_er_diagram.png")

print("\nAll 3 diagrams created successfully!")
