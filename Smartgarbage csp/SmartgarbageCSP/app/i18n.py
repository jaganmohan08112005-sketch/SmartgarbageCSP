"""Lightweight i18n for SmartGarbage.

Citizens in Chintalavalasa (Andhra Pradesh) are predominantly Telugu-speaking,
so English-only is a real adoption barrier. We use a tiny server-side translation
table (no Flask-Babel / Babel compile toolchain needed) selected via
`?lang=te` / `?lang=en` or a sticky session value, exposed in templates as `_()`.

Only the highest-traffic UI strings are translated first; unknown strings fall
back to the original text so the app never breaks.
"""

SUPPORTED = ['en', 'te']
DEFAULT_LANG = 'en'

EN = {
    'Report Issue': 'ఫిర్యాదు నమోదు చేయండి',
    'My Dashboard': 'నా డాష్‌బోర్డ్',
    'Schedules': 'సేకరణ షెడ్యూల్',
    'Home': 'హోమ్',
    'Login': 'లాగిన్',
    'Sign Up': 'నమోదు చేసుకోండి',
    'Logout': 'లాగౌట్',
    'Ward Transparency': 'వార్డ్ పారదర్శకత',
    'Picker Sign-up': 'కలెక్టర్ నమోదు',
    'Admin Console': 'అడ్మిన్ కన్సోల్',
    'Worker Portal': 'వర్కర్ పోర్టల్',
    'Waste Report': 'చెత్త ఫిర్యాదు',
    'Submit': 'సమర్పించు',
    'Name': 'పేరు',
    'Phone': 'ఫోన్',
    'Ward': 'వార్డ్',
    'Address': 'చిరునామా',
    'Description': 'వివరణ',
    'Success': 'విజయం',
    'Error': 'లోపం',
    'You are offline': 'మీరు ఆఫ్‌లైన్‌లో ఉన్నారు',
    'SmartGarbage Chintalavalasa': 'స్మార్ట్ జాబితా చింతలవలస',
}

TE = EN  # alias for clarity; translations live in EN keyed by English text.

_TRANSLATIONS = {'en': {}, 'te': EN}


def get_translations(lang):
    return _TRANSLATIONS.get(lang, _TRANSLATIONS[DEFAULT_LANG])


def translate(text, lang):
    if lang == 'en':
        return text
    table = _TRANSLATIONS.get(lang, {})
    return table.get(text, text)
