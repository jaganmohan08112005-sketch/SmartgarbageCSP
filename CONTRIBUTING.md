# Contributing to SmartGarbage

Thank you for your interest in contributing to SmartGarbage! This guide will help you get started.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Style Guidelines](#style-guidelines)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)

---

## Code of Conduct

This project adheres to the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). By participating, you are expected to uphold this code. Please report unacceptable behavior to the project maintainers.

---

## How Can I Contribute?

### Reporting Bugs

Before creating a bug report, please check existing issues to avoid duplicates. When you create a bug report, include:

- **Clear title** — describe the issue concisely
- **Steps to reproduce** — what you did, what you expected, what happened
- **Environment** — OS, Python version, browser (if frontend issue)
- **Screenshots** — if applicable
- **Error logs** — from console or terminal

### Suggesting Features

Open an issue with the `feature-request` label. Include:

- **Problem statement** — what problem does this solve?
- **Proposed solution** — how should it work?
- **Alternatives considered** — other approaches you thought about
- **Use case** — who benefits and how?

### Contributing Code

1. **Good first issues** — look for issues labeled `good first issue`
2. **Documentation** — improve docs, add examples, fix typos
3. **Tests** — add missing tests, improve coverage
4. **Translations** — help translate the portal to more Indian languages
5. **Accessibility** — improve WCAG compliance

---

## Getting Started

### Prerequisites

- **Python 3.11+** — `python --version`
- **PostgreSQL** — or use Supabase (recommended)
- **Git** — `git --version`
- **pip** — Python package manager

### Optional

- **Redis** — for shared rate limits (needed for multi-worker setups)
- **Docker** — for containerised development
- **Node.js** — only if modifying frontend build tools

---

## Development Setup

### 1. Fork and Clone

```bash
# Fork on GitHub, then:
git clone https://github.com/YOUR_USERNAME/SmartGarbage.git
cd SmartGarbage
git remote add upstream https://github.com/jaganmohan08112005-sketch/SmartGarbage.git
```

### 2. Create Virtual Environment

```bash
# Linux/macOS
python -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
# Production dependencies
pip install -r requirements.txt

# Development/test dependencies (includes pytest, flake8, etc.)
pip install -r requirements-dev.txt
```

### 4. Set Up Database

**Option A: Local PostgreSQL**

```bash
# Create database
createdb smartgarbage_dev

# Set environment variable
export DATABASE_URL="postgresql://localhost/smartgarbage_dev"

# Run migrations
flask db upgrade
```

**Option B: Supabase (Recommended)**

1. Create a free Supabase project at [supabase.com](https://supabase.com)
2. Copy the connection string from Settings → Database → Connection pooling
3. Set environment variable:
   ```bash
   export DATABASE_URL="postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:5432/postgres"
   ```
4. Run migrations:
   ```bash
   flask db upgrade
   ```

### 5. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your settings (at minimum, set DATABASE_URL)
```

Key variables:

```bash
DATABASE_URL=postgresql://...        # Required
SECRET_KEY=your-secret-key-here      # Auto-generated if missing
FLASK_ENV=development                # Enables debug mode
SEED_DEMO=true                       # Seeds demo data (dev only!)
```

### 6. Seed Demo Data (Optional)

```bash
python seed_db.py
```

This creates demo accounts:

| Role | Username | Password | Notes |
|------|----------|----------|-------|
| Admin | `admin` | `admin123` | Requires MFA (OTP shown in console) |
| Worker | `worker` | `worker123` | Requires MFA |
| Citizen | `user` | `user123` | Direct login |

> ⚠️ **Never set `SEED_DEMO=true` in production.**

### 7. Run Development Server

```bash
python run.py
```

Visit [http://localhost:5000](http://localhost:5000)

---

## Project Structure

```
SmartGarbage/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── models.py            # SQLAlchemy models
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py          # Login, register, MFA
│   │   ├── admin.py         # Admin console
│   │   ├── public.py        # Public pages (home, schedule, etc.)
│   │   ├── citizen.py       # Citizen dashboard, reports
│   │   └── worker.py        # Worker dashboard
│   ├── templates/           # Jinja2 HTML templates
│   ├── static/              # CSS, JS, images
│   └── ml/                  # ML models (missed collection prediction)
├── migrations/              # Alembic database migrations
├── tests/                   # Pytest test suite
├── scripts/                 # Utility scripts
├── wiki/                    # Wikipedia and brand authority docs
├── .github/workflows/       # CI/CD pipelines
├── Dockerfile               # Container build
├── render.yaml              # Render deployment config
├── fly.toml                 # Fly.io deployment config
└── requirements.txt         # Python dependencies
```

---

## Making Changes

### Branch Naming

Use descriptive branch names:

```bash
git checkout -b feature/add-email-notifications
git checkout -b fix/complaint-status-update
git checkout -b docs/update-deployment-guide
git checkout -b test/add-auth-tests
```

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add email notification for complaint resolution
fix: prevent duplicate complaint submissions
docs: update deployment guide for Fly.io
test: add tests for MFA verification flow
refactor: extract phone validation to utils module
chore: update dependencies
```

### Code Style

- **Python**: Follow PEP 8 (enforced by flake8)
- **Templates**: 4-space indentation, semantic HTML
- **CSS**: Follow existing naming conventions (`sg-*` prefix for custom classes)
- **JavaScript**: ES6+, no jQuery (use vanilla JS)

---

## Testing

### Running Tests

```bash
# Run all tests (parallel by default)
pytest tests/ -v

# Run specific test file
pytest tests/test_auth.py -v

# Run with coverage report
pytest tests/ --cov=app --cov-report=html

# Open coverage report
open htmlcov/index.html
```

### Writing Tests

Tests live in `tests/`. Each test file should focus on a feature area:

```python
# tests/test_my_feature.py
import pytest
from app import create_app


@pytest.fixture
def app():
    """Create test application."""
    app = create_app(test_config={'TESTING': True, 'DATABASE_URL': '...'})
    yield app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


def test_my_feature(client):
    """Test description."""
    response = client.get('/my-route')
    assert response.status_code == 200
    assert b'expected content' in response.data
```

### Test Requirements

- **Every new feature** must include tests
- **Bug fixes** must include a regression test
- **Tests must pass** before submitting a PR
- **Maintain or improve coverage** — check with `--cov-report=html`

### CI Checks

All PRs run these checks automatically:

- `pytest tests/ -v` — all tests must pass
- `flake8 app/` — no lint errors
- `python -c "from app import create_app"` — app imports correctly

---

## Pull Request Process

### Before Submitting

1. **Sync with upstream:**
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Run tests:**
   ```bash
   pytest tests/ -v
   ```

3. **Check linting:**
   ```bash
   flake8 app/
   ```

4. **Verify app starts:**
   ```bash
   python -c "from app import create_app; app = create_app(); print('OK')"
   ```

### Submitting

1. Push your branch:
   ```bash
   git push origin feature/my-feature
   ```

2. Open a Pull Request on GitHub with:
   - **Clear title** describing the change
   - **Description** explaining what and why (not how — the code shows how)
   - **Related issues** — reference with `Closes #123`
   - **Screenshots** — for UI changes
   - **Testing notes** — how you verified the change

### Review Process

1. Maintainers will review your PR within 1 week
2. They may request changes — please respond to feedback
3. Once approved, a maintainer will merge your PR
4. Your contribution will be included in the next release

---

## Style Guidelines

### Python

```python
# Good
def calculate_green_points(waste_type: str, weight_kg: float) -> int:
    """Calculate Green Points based on waste type and weight."""
    multipliers = {"organic": 2, "recyclable": 3, "hazardous": 5}
    return int(weight_kg * multipliers.get(waste_type, 1))


# Bad
def calc(w, wt):
    m = {"o": 2, "r": 3, "h": 5}
    return int(wt * m.get(w, 1))
```

### HTML Templates

```html
<!-- Good: semantic, accessible -->
<div class="card border-0 shadow-sm" role="region" aria-labelledby="heading-1">
    <h2 id="heading-1" class="h5 fw-bold">Section Title</h2>
    <p class="text-muted">Content here.</p>
</div>

<!-- Bad: no semantics, no accessibility -->
<div style="border: 1px solid #ddd; padding: 10px;">
    <b>Section Title</b>
    <p>Content here.</p>
</div>
```

### CSS

```css
/* Good: BEM-like, prefixed */
.sg-card { ... }
.sg-card__title { ... }
.sg-card--highlighted { ... }

/* Bad: generic, unprefixed */
.card { ... }
.card-title { ... }
```

---

## Reporting Bugs

### Bug Report Template

```markdown
**Describe the bug**
A clear description of what the bug is.

**To reproduce**
1. Go to '...'
2. Click on '...'
3. Scroll down to '...'
4. See error

**Expected behavior**
What you expected to happen.

**Screenshots**
If applicable, add screenshots.

**Environment:**
- OS: [e.g., Windows 11]
- Python: [e.g., 3.12]
- Browser: [e.g., Chrome 120]
- Database: [e.g., Supabase]

**Additional context**
Any other information about the problem.
```

---

## Suggesting Features

### Feature Request Template

```markdown
**Is your feature request related to a problem?**
A clear description of the problem. Ex. "I'm always frustrated when..."

**Describe the solution you'd like**
A clear description of what you want to happen.

**Describe alternatives you've considered**
Other solutions or features you've considered.

**Additional context**
Mockups, examples, or references from other projects.
```

---

## Labels

We use these labels for issues:

| Label | Description |
|-------|-------------|
| `good first issue` | Perfect for newcomers |
| `bug` | Something isn't working |
| `enhancement` | New feature or improvement |
| `documentation` | Docs need updating |
| `testing` | Tests need adding/fixing |
| `accessibility` | WCAG compliance issues |
| `help wanted` | Extra attention needed |
| `priority: high` | Critical issue |
| `priority: low` | Nice to have |

---

## Questions?

- **GitHub Discussions** — for general questions
- **GitHub Issues** — for bugs and feature requests
- **Email** — for security concerns (see SECURITY.md)

Thank you for contributing to SmartGarbage! 🗑️♻️
