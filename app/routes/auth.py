import random

from datetime import datetime, timedelta, timezone

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from flask import (current_app, flash, redirect, render_template, request, session, url_for)

from flask_login import login_user, logout_user

from werkzeug.security import generate_password_hash, check_password_hash

from ..models import (User, WorkerProfile, utcnow)

from .. import db, limiter

from . import (_clear_login_failures, _hash_otp, _is_account_locked, _locked_until_utc, _record_failed_login, _send_otp_with_fallback, fit_length, logger, main, send_reset_email, send_verification_email, validate_indian_phone, write_audit)

import app.routes as _routes  # call-time: honors test monkeypatches


@main.route('/register', methods=['GET', 'POST'])
@limiter.limit("10/hour")
def register():
    if 'user_id' in session and not session.get('mfa_pending'):
        return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password')
        role = request.form.get('role', 'citizen')
        if role not in ['citizen', 'worker', 'admin']:
            role = 'citizen'
        raw_phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip().lower()
        # ── Phone Validation ──────────────────────────────────────────
        if not raw_phone:
            flash('Phone number is required.', 'error')
            return redirect(url_for('main.register'))
        phone = validate_indian_phone(raw_phone)
        if not phone:
            flash('Enter a valid Indian mobile number (10 digits starting with 6–9, e.g. +91 98765 43210). Fake or sequential numbers are not accepted.', 'error')
            return redirect(url_for('main.register'))
        if not email or '@' not in email:
            flash('A valid email address is required.', 'error')
            return redirect(url_for('main.register'))
        # ─────────────────────────────────────────────────────────────
        if not username or not password:
            flash('Username and password are required.', 'error')
            return redirect(url_for('main.register'))
        # VARCHAR(100) on Postgres — reject overlong instead of truncating identity fields.
        if len(username) > 100:
            flash('Username must be 100 characters or fewer.', 'error')
            return redirect(url_for('main.register'))
        if len(email) > 120:
            flash('Email must be 120 characters or fewer.', 'error')
            return redirect(url_for('main.register'))
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return redirect(url_for('main.register'))
        if password.lower() == username.lower():
            flash('Password must be different from your username.', 'error')
            return redirect(url_for('main.register'))
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'error')
            return redirect(url_for('main.register'))
        if User.query.filter_by(phone=phone).first():
            flash('This phone number is already registered with another account.', 'error')
            return redirect(url_for('main.register'))
        if User.query.filter_by(email=email).first():
            flash('This email address is already registered.', 'error')
            return redirect(url_for('main.register'))
        new_user = User(username=username, email=email, password_hash=generate_password_hash(password),
                        role=role, phone=phone, is_approved=(role != 'admin'))
        db.session.add(new_user)
        db.session.commit()
        if role == 'worker':
            wp = WorkerProfile(user_id=new_user.id, vehicle_id=f"CV-{random.randint(10, 99)}",
                               status="Idle", performance_rating=5.0)
            db.session.add(wp)
            db.session.commit()
        elif role == 'admin':
            flash('Admin account registered! Your account is pending super-admin approval before you can log in.', 'success')
            write_audit("REGISTER_ADMIN_PENDING", target=username, detail=f"New admin account pending approval. Phone: {phone}")
            return redirect(url_for('main.login'))
        write_audit("REGISTER", target=username, detail=f"New {role} account created. Phone: {phone}, Email: {email}")
        logger.info("registration_success", username=username, role=role, phone=phone, email=email)
        # Send email verification link (non-blocking: a mail failure must not
        # block registration — the citizen can log in after verifying via phone MFA).
        try:
            send_verification_email(email, new_user.id)
        except Exception as e:
            logger.warning("verification_email_send_error", error=str(e))
        flash('Registration successful! Please verify your email and log in.', 'success')
        return redirect(url_for('main.login'))
    return render_template('register.html')


@main.route('/register/picker', methods=['GET', 'POST'])
@limiter.limit("10/hour")
def register_picker():
    """Lightweight informal waste-picker recognition registration
    (SBM Grameen Phase II) — separate from formal fleet drivers."""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        raw_phone = request.form.get('phone', '').strip()
        area = request.form.get('area', '').strip()
        if not username or not password or not raw_phone:
            flash('Name, password and phone are required.', 'error')
            return redirect(url_for('main.register_picker'))
        if len(username) > 100:
            flash('Name must be 100 characters or fewer.', 'error')
            return redirect(url_for('main.register_picker'))
        phone = validate_indian_phone(raw_phone)
        if not phone:
            flash('Enter a valid Indian mobile number.', 'error')
            return redirect(url_for('main.register_picker'))
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return redirect(url_for('main.register_picker'))
        if password.lower() == username.lower():
            flash('Password must be different from your username.', 'error')
            return redirect(url_for('main.register_picker'))
        if User.query.filter_by(username=username).first():
            flash('Name already registered.', 'error')
            return redirect(url_for('main.register_picker'))
        if User.query.filter_by(phone=phone).first():
            flash('This phone is already registered.', 'error')
            return redirect(url_for('main.register_picker'))
        picker = User(username=username, password_hash=generate_password_hash(password),
                      role='worker', phone=phone)
        db.session.add(picker)
        db.session.commit()
        wp = WorkerProfile(user_id=picker.id, status='Active',
                           is_informal_picker=True, picker_area=fit_length(area, 100))
        db.session.add(wp)
        db.session.commit()
        write_audit("PICKER_REGISTER", target=username,
                    detail=f"Informal waste-picker recognised, area={area}")
        flash('Waste-picker registered & recognised. Welcome!', 'success')
        return redirect(url_for('main.login'))
    return render_template('register_picker.html')


@main.route('/login', methods=['GET', 'POST'])
@limiter.limit("30/minute")
def login():
    if 'user_id' in session and not session.get('mfa_pending'):
        if session.get('role') == 'admin': return redirect(url_for('main.admin'))
        elif session.get('role') == 'worker': return redirect(url_for('main.worker'))
        return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        # Account lockout (brute-force defense): reject before any password work
        # while the account sits inside its cooling window.
        if _is_account_locked(user):
            mins_left = max(1, int((_locked_until_utc(user) - datetime.now(timezone.utc)).total_seconds() // 60))
            logger.warning("login_locked", username=username, ip=request.remote_addr)
            flash(f'Account temporarily locked after repeated failed attempts. Try again in ~{mins_left} min.', 'error')
            return redirect(url_for('main.login'))

        if not user or not check_password_hash(user.password_hash, password):
            if user:
                _record_failed_login(user)
            logger.warning("login_failed", username=username, ip=request.remote_addr)
            flash('Invalid username or password.', 'error')
            return redirect(url_for('main.login'))
        # Successful login — clear any previous lockout state.
        _clear_login_failures(user)
        if user.role == 'admin' and not user.is_approved:
            flash('Your admin account is pending super-admin approval. You cannot log in until approved.', 'error')
            return redirect(url_for('main.login'))
        # Email verification gate: citizens with an email must verify before
        # first login. Accounts without an email (pre-verification, workers)
        # are allowed through so legacy accounts are not locked out.
        if (user.role == 'citizen' and user.email
                and not getattr(user, 'email_verified', False)):
            flash('Please verify your email address before logging in. Check your inbox for the verification link.', 'error')
            return redirect(url_for('main.login'))
        # Session-fixation defense: start each login with a fresh session
        # (preserving the user's language preference).
        _lang = session.get('lang')
        session.clear()
        if _lang:
            session['lang'] = _lang
        session['user_id'] = user.id
        session['username'] = user.username
        session['role'] = user.role
        if user.role in ['admin', 'worker']:
            otp_val = str(random.randint(100000, 999999))
            # Store only a one-way hash of the OTP at rest, never plaintext.
            user.otp = _hash_otp(otp_val)
            user.otp_expiry = utcnow() + timedelta(minutes=5)
            db.session.commit()
            logger.info("mfa_otp_generated", username=user.username)
            _send_otp_with_fallback(user.phone or '+919876543210', otp_val)
            if _routes._is_local_request():
                session['dev_otp'] = otp_val
            session['mfa_pending'] = True
            return redirect(url_for('main.mfa_verify'))
        session['mfa_pending'] = False
        login_user(user)
        logger.info("login_success", username=user.username, role=user.role, ip=request.remote_addr)
        write_audit("LOGIN", target=username, detail="Citizen login successful.")
        flash(f'Welcome back, {user.username}!', 'success')
        return redirect(url_for('main.dashboard'))
    return render_template('login.html')


@main.route('/mfa-verify', methods=['GET', 'POST'])
@limiter.limit("30/minute")
def mfa_verify():
    if 'user_id' not in session:
        return redirect(url_for('main.login'))
    user = User.query.get(session['user_id'])
    if user is None:
        flash('Account not found. Please log in again.', 'error')
        return redirect(url_for('main.logout'))
    if request.method == 'POST':
        entered_otp = request.form.get('otp', '').strip()
        if user.otp and user.otp_expiry:
            expiry = user.otp_expiry if user.otp_expiry.tzinfo else user.otp_expiry.replace(tzinfo=timezone.utc)
            if expiry > datetime.now(timezone.utc) and user.otp == _hash_otp(entered_otp):
                user.otp = None; user.otp_expiry = None
                _clear_login_failures(user)
                db.session.commit()
                session['mfa_pending'] = False
                session.pop('dev_otp', None)
                login_user(user)
                write_audit("MFA_SUCCESS", target=user.username, detail="MFA verified successfully.")
                flash(f'MFA Verified. Welcome, {user.username}!', 'success')
                if user.role == 'admin': return redirect(url_for('main.admin'))
                elif user.role == 'worker': return redirect(url_for('main.worker'))
                return redirect(url_for('main.dashboard'))
            else:
                # OTP brute-force defense: count wrong OTPs against the same
                # lockout counter so the MFA step can't be hammered indefinitely.
                _record_failed_login(user)
                flash('Invalid or expired OTP.', 'error')
        else:
            flash('OTP not found. Please log in again.', 'error')
            return redirect(url_for('main.login'))
    dev_otp = session.get('dev_otp')
    return render_template('mfa_verify.html', dev_otp=dev_otp)


@main.route('/auth/phone-login', methods=['POST'])
@limiter.limit("10/hour")
def auth_phone_login():
    raw_phone = request.form.get('phone_number', '').strip()
    if not raw_phone:
        flash("Phone number is required.", "error")
        return redirect(url_for('main.login'))
    # ── Validate real Indian mobile format ────────────────────────────
    phone_number = validate_indian_phone(raw_phone)
    if not phone_number:
        flash("Enter a valid Indian mobile number (10 digits starting with 6–9). Fake or sequential numbers like 1234567890 are not accepted.", "error")
        return redirect(url_for('main.login'))
    # ─────────────────────────────────────────────────────────────────
    user = User.query.filter_by(phone=phone_number).first()
    if not user:
        # Auto-create a citizen account for the verified phone number
        last4 = phone_number[-4:]
        username = f"citizen_{last4}_{random.randint(10, 99)}"
        # Ensure unique username
        while User.query.filter_by(username=username).first():
            username = f"citizen_{last4}_{random.randint(10, 99)}"
        user = User(username=username, password_hash=generate_password_hash("phone_otp_user"),
                    role="citizen", phone=phone_number)
        db.session.add(user); db.session.commit()
    # Lockout applies to phone-login too: an attacker with the victim's number
    # must not be able to spam OTP generation while the account is cooling down.
    if _is_account_locked(user):
        mins_left = max(1, int((_locked_until_utc(user) - datetime.now(timezone.utc)).total_seconds() // 60))
        flash(f'Account temporarily locked after repeated failed attempts. Try again in ~{mins_left} min.', 'error')
        return redirect(url_for('main.login'))
    otp_val = str(random.randint(100000, 999999))
    # Store only a one-way hash of the OTP at rest, never plaintext.
    user.otp = _hash_otp(otp_val)
    user.otp_expiry = utcnow() + timedelta(minutes=5)
    db.session.commit()
    logger.info("phone_otp_generated", phone=phone_number)
    _send_otp_with_fallback(phone_number, otp_val)
    _lang = session.get('lang')
    session.clear()  # session-fixation defense (preserve lang preference)
    if _lang:
        session['lang'] = _lang
    session_data = {'user_id': user.id, 'mfa_pending': True,
                    'username': user.username, 'role': user.role}
    if _routes._is_local_request():
        session_data['dev_otp'] = otp_val
    session.update(session_data)
    return redirect(url_for('main.mfa_verify'))


@main.route('/verify-email/<token>')
def verify_email(token):
    """Email verification link handler.

    The token is a URLSafeTimedSerializer signature (salt='email-verify-salt')
    that expires after 24 hours. On success, the user's email_verified flag
    is set to True and they can log in.
    """
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        user_id = serializer.loads(token, salt='email-verify-salt', max_age=86400)
    except SignatureExpired:
        flash('Verification link has expired. Please register again or request a new link.', 'error')
        return redirect(url_for('main.login'))
    except BadSignature:
        flash('Invalid verification link.', 'error')
        return redirect(url_for('main.login'))
    user = User.query.get(int(user_id))
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('main.login'))
    if user.email_verified:
        flash('Your email is already verified. Please log in.', 'success')
    else:
        user.email_verified = True
        db.session.commit()
        write_audit("EMAIL_VERIFIED", target=user.username, detail=f"Email {user.email} verified.")
        logger.info("email_verified", username=user.username, email=user.email)
        flash('Email verified successfully! You can now log in.', 'success')
    return redirect(url_for('main.login'))


@main.route('/resend-verification', methods=['GET', 'POST'])
def resend_verification():
    """Let an unverified user request a new email-verification link."""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if not email or '@' not in email:
            flash('Please enter a valid email address.', 'error')
            return redirect(url_for('main.resend_verification'))
        user = User.query.filter_by(email=email).first()
        if user and not getattr(user, 'email_verified', False):
            try:
                send_verification_email(email, user.id)
            except Exception as e:
                logger.warning("resend_verification_error", error=str(e))
        # Always show success to prevent email enumeration.
        flash('If an unverified account exists with that email, a new verification link has been sent.', 'success')
        return redirect(url_for('main.login'))
    return render_template('resend_verification.html')


@main.route('/logout')
def logout():
    write_audit("LOGOUT", target=session.get('username'))
    logout_user()
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('main.login'))


@main.route('/reset-password-request', methods=['GET', 'POST'])
@limiter.limit("10/hour")
def reset_password_request():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        user = User.query.filter_by(username=username).first()
        if user and user.email:
            send_reset_email(user.email, user.id)
            write_audit("PASSWORD_RESET_REQUEST", target=username, detail="Reset email dispatched.")
        flash('If an account exists, a password reset link has been sent.', 'success')
        return redirect(url_for('main.login'))
    return render_template('reset_password_request.html')


@main.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        user_id = serializer.loads(token, salt='password-reset-salt', max_age=1800)
    except SignatureExpired:
        flash('Password reset link has expired. Please request a new one.', 'error')
        return redirect(url_for('main.reset_password_request'))
    except BadSignature:
        flash('Invalid password reset link.', 'error')
        return redirect(url_for('main.reset_password_request'))
    user = User.query.get(int(user_id))
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('main.login'))
    if request.method == 'POST':
        password = request.form.get('password', '')
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return redirect(url_for('main.reset_password', token=token))
        user.password_hash = generate_password_hash(password)
        db.session.commit()
        write_audit("PASSWORD_RESET_COMPLETE", target=user.username, detail="Password updated via reset link.")
        flash('Password updated. Please log in.', 'success')
        return redirect(url_for('main.login'))
    return render_template('reset_password.html', token=token)
