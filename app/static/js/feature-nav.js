/* feature-nav.js — "open one feature at a time".
   Any card tagged with data-feature="<id>" (and a matching id) becomes an
   independently openable feature. Navigating to #<id> — from the navbar
   Features menu or a shared link — shows that card only and offers a way
   back to the full page. */
"use strict";

(function () {
    function cards() {
        return Array.from(document.querySelectorAll('[data-feature]'));
    }

    function bar() {
        let el = document.getElementById('feature-focus-bar');
        if (!el) {
            el = document.createElement('div');
            el.id = 'feature-focus-bar';
            el.className = 'alert alert-success d-none align-items-center justify-content-between gap-3 shadow-sm';
            el.style.borderRadius = '12px';
            el.innerHTML =
                '<div class="fw-semibold" id="feature-focus-label"></div>' +
                '<a href="#" class="btn btn-sm btn-outline-success rounded-pill" id="feature-focus-clear"></a>';
            const host = document.querySelector('main .container, .container');
            if (host) host.insertBefore(el, host.firstChild);
            el.querySelector('#feature-focus-clear').addEventListener('click', (e) => {
                e.preventDefault();
                history.pushState(null, '', window.location.pathname);
                apply();
            });
        }
        return el;
    }

    function apply() {
        const all = cards();
        if (!all.length) return;
        const hash = (window.location.hash || '').replace('#', '');
        const target = all.find(c => c.dataset.feature === hash);

        all.forEach(c => c.classList.toggle('d-none', !!target && c !== target));

        const focusBar = bar();
        if (target) {
            const name = target.dataset.featureName || hash;
            focusBar.classList.remove('d-none');
            focusBar.classList.add('d-flex');
            focusBar.querySelector('#feature-focus-label').textContent = 'Showing: ' + name;
            focusBar.querySelector('#feature-focus-clear').textContent = 'Show all features';
            window.dispatchEvent(new CustomEvent('feature:shown', { detail: { id: hash } }));
        } else {
            focusBar.classList.add('d-none');
            focusBar.classList.remove('d-flex');
        }
        // Leaflet maps sized while hidden render blank; its resize handler
        // re-measures them once they are back on screen.
        window.dispatchEvent(new Event('resize'));
    }

    document.addEventListener('DOMContentLoaded', apply);
    window.addEventListener('hashchange', apply);
    window.addEventListener('popstate', apply);
})();
