# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| Latest  | ✅ Yes             |
| < Latest | ❌ No (please upgrade) |

## Reporting a Vulnerability

The SmartGarbage team takes security seriously. If you discover a security vulnerability, please report it responsibly.

### DO NOT

- **Do not** open a public GitHub issue for security vulnerabilities
- **Do not** post about it on social media
- **Do not** exploit the vulnerability beyond what's necessary to demonstrate it

### DO

- **Email** the maintainers at: [INSERT SECURITY EMAIL]
- **Include** the following in your report:
  - Description of the vulnerability
  - Steps to reproduce
  - Potential impact
  - Suggested fix (if any)

### What to Expect

- **Acknowledgment** within 48 hours
- **Assessment** within 1 week
- **Fix timeline** communicated based on severity
- **Credit** in the release notes (unless you prefer anonymity)

## Security Measures

SmartGarbage implements these security measures:

### Authentication & Authorization

- Password hashing with Werkzeug (PBKDF2)
- Multi-factor authentication (OTP) for admin/worker roles
- Role-based access control (citizen, worker, admin, superadmin)
- Session management with secure cookies
- CSRF protection on all forms

### Data Protection

- HTTPS enforced in production
- HSTS headers (1-year max-age)
- Content Security Policy (CSP) headers
- SQL injection prevention via SQLAlchemy ORM
- XSS prevention via Jinja2 auto-escaping
- File upload validation (type, size, randomised filenames)

### Infrastructure

- Environment variables for all secrets (no hardcoded credentials)
- Rate limiting on authentication routes
- Debug mode disabled in production
- Secure cookie flags (HttpOnly, Secure, SameSite)

### Compliance

- DPDP Act 2023 compliant privacy policy
- Solid Waste Management Rules, 2026 compliant
- WCAG 2.1 Level AA accessibility

## Known Security Considerations

### Demo Accounts

The `seed_db.py` script creates demo accounts with known passwords:

| Role | Username | Password |
|------|----------|----------|
| Admin | `admin` | `admin123` |
| Worker | `worker` | `worker123` |
| Citizen | `user` | `user123` |

⚠️ **These are for development only.** Never set `SEED_DEMO=true` in production.

### Environment Variables

Never commit these to version control:

```
SECRET_KEY
DATABASE_URL
SUPABASE_SERVICE_ROLE_KEY
TWILIO_AUTH_TOKEN
RAZORPAY_KEY_SECRET
RAZORPAY_WEBHOOK_SECRET
```

Use `.env` files locally (already in `.gitignore`) and environment variables in production.

## Dependencies

We regularly update dependencies to patch known vulnerabilities:

```bash
# Check for known vulnerabilities
pip install safety
safety check -r requirements.txt

# Update dependencies
pip install --upgrade -r requirements.txt
```

## Contact

For security concerns, contact the maintainers at:

- **Email**: [INSERT SECURITY EMAIL]
- **GitHub**: Open a private security advisory at https://github.com/jaganmohan08112005-sketch/SmartGarbage/security/advisories/new

Thank you for helping keep SmartGarbage and its users safe!
