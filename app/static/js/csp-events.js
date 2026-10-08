/* ================================================================
   CSP event delegation for SmartGarbage
   ================================================================
   The Content-Security-Policy authorises inline <script> blocks with a
   per-request nonce and no longer allows 'unsafe-inline'. Inline event
   handler attributes (onclick="...", onchange="...", onsubmit="...") are NOT
   covered by a nonce and would be blocked, so templates declare the same
   intent with data-sg-* attributes and this file wires the listeners.

   Supported attributes:
     data-sg-click="fnA fnB"   run each window.fn on click
     data-sg-change="fn"       run on change
     data-sg-input="fn"        run on input
     data-sg-submit="fn"       run on submit
     data-sg-args='[..]'       JSON args passed to each handler (this = element)
     data-sg-confirm="text"    window.confirm() gate for click/submit
     data-sg-navigate="/x?q="  on change, navigate to prefix + encodeURIComponent(value)
     data-sg-reset             reset select.selectedIndex after change
   ================================================================ */
(function () {
  'use strict';

  function parseArgs(el) {
    var raw = el.getAttribute('data-sg-args');
    if (!raw) return [];
    try { return JSON.parse(raw); } catch (e) {
      console.warn('[csp-events] invalid data-sg-args:', raw);
      return [];
    }
  }

  function run(el, attr) {
    var names = (el.getAttribute(attr) || '').split(/\s+/).filter(Boolean);
    var args = parseArgs(el);
    names.forEach(function (name) {
      var fn = window[name];
      if (typeof fn === 'function') { fn.apply(el, args); }
      else { console.warn('[csp-events] unknown handler:', name); }
    });
  }

  function closest(event, attr) {
    var t = event.target;
    return t && t.closest ? t.closest('[' + attr + ']') : null;
  }

  document.addEventListener('click', function (event) {
    var el = closest(event, 'data-sg-click') || closest(event, 'data-sg-confirm');
    if (!el) return;
    if (el.hasAttribute('data-sg-confirm') && !window.confirm(el.getAttribute('data-sg-confirm'))) {
      event.preventDefault();
      return;
    }
    if (el.hasAttribute('data-sg-click')) run(el, 'data-sg-click');
  });

  document.addEventListener('change', function (event) {
    var el = closest(event, 'data-sg-change');
    if (!el) {
      var nav = closest(event, 'data-sg-navigate');
      if (nav) window.location.href = nav.getAttribute('data-sg-navigate') + encodeURIComponent(nav.value);
      return;
    }
    run(el, 'data-sg-change');
    if (el.hasAttribute('data-sg-reset')) el.selectedIndex = 0;
  });

  document.addEventListener('input', function (event) {
    var el = closest(event, 'data-sg-input');
    if (el) run(el, 'data-sg-input');
  });

  document.addEventListener('submit', function (event) {
    var el = closest(event, 'data-sg-confirm');
    if (el && !window.confirm(el.getAttribute('data-sg-confirm'))) {
      event.preventDefault();
      return;
    }
    var s = closest(event, 'data-sg-submit');
    if (s) run(s, 'data-sg-submit');
  });

  /* ---- named helpers for the few complex inline handlers ---- */

  // Account-menu "Notifications" toggle (was a long inline ternary).
  window.sgTogglePush = function (el) {
    if (!window.SGPush) return;
    if (window.SGPush.isEnabled()) {
      window.SGPush.unsubscribe().then(function () { el.textContent = '🔔 Enable notifications'; });
    } else {
      window.SGPush.subscribe().then(function () { el.textContent = '🔕 Disable notifications'; });
    }
  };

  // Homepage push prompt: subscribe, then hide the prompt.
  window.sgPushPromptSubscribe = function () {
    if (!window.SGPush) return;
    window.SGPush.subscribe().then(function () {
      var p = document.getElementById('sgPushPrompt');
      if (p) p.classList.add('d-none');
    });
  };

  window.sgPushPromptDismiss = function () {
    try { localStorage.setItem('sgPushPromptDismissed', '1'); } catch (e) { /* ignore */ }
    var p = document.getElementById('sgPushPrompt');
    if (p) p.classList.add('d-none');
  };

  // Notification-preferences subscribe/unsubscribe, then refresh the status UI.
  window.sgPushSubscribe = function () {
    if (!window.SGPush) return;
    window.SGPush.subscribe().then(function () {
      if (typeof window.updatePushStatus === 'function') window.updatePushStatus();
    });
  };

  window.sgPushUnsubscribe = function () {
    if (!window.SGPush) return;
    window.SGPush.unsubscribe().then(function () {
      if (typeof window.updatePushStatus === 'function') window.updatePushStatus();
    });
  };
})();
