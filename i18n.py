"""Langues de l'interface : français, English, العربية (RTL). Traduction des pages à la volée."""
import html
import re

from flask import g, redirect, request, session, url_for

import translations as T

LANGS = {"fr": "Français", "en": "English", "ar": "العربية"}
LLM_NAMES = {"fr": "français", "en": "English", "ar": "العربية (arabe)"}
SKIP = re.compile(r"(<script\b.*?</script>|<style\b.*?</style>|<textarea\b.*?</textarea>|<!--nt-->.*?<!--/nt-->)", re.S | re.I)
_cache = {}


def current_lang():
    try:
        return g.lang
    except (AttributeError, RuntimeError):
        return "fr"


def tr(key, **kw):
    s = T.DICT.get(current_lang(), {}).get(key, key)
    return s.format(**kw) if kw else s


def _tables(lang):
    if lang not in _cache:
        exact, pats = {}, []
        for k, v in T.DICT[lang].items():
            if "{}" in k:
                rx = re.compile("^" + re.escape(k).replace(r"\{\}", "(.+?)") + "$", re.S)
                pats.append((rx, v))
            else:
                exact[k] = v
        _cache[lang] = (exact, pats)
    return _cache[lang]


def lookup(core, lang, depth=0):
    exact, pats = _tables(lang)
    if core in exact:
        return exact[core]
    for rx, tpl in pats:
        m = rx.match(core)
        if m:
            return tpl.format(*[exact.get(x, x) for x in m.groups()])
    if depth == 0 and " · " in core:
        parts = core.split(" · ")
        out = [lookup(p, lang, 1) or p for p in parts]
        if out != parts:
            return " · ".join(out)
    return None


def _text(m, lang):
    raw = m.group(1)
    core = re.sub(r"\s+", " ", html.unescape(raw)).strip()
    if not core:
        return m.group(0)
    out = lookup(core, lang)
    if out is None:
        return m.group(0)
    lead = raw[:len(raw) - len(raw.lstrip())]
    trail = raw[len(raw.rstrip()):]
    return ">" + lead + html.escape(out, quote=False) + trail + "<"


def _attr(m, lang):
    core = html.unescape(m.group(2)).strip()
    out = lookup(core, lang) if core else None
    return m.group(0) if out is None else f'{m.group(1)}="{html.escape(out, quote=True)}"'


def translate_html(doc, lang):
    parts = SKIP.split(doc)
    for i in range(0, len(parts), 2):
        p = re.sub(r'\b(placeholder|title|alt|aria-label)="([^"]*)"', lambda m: _attr(m, lang), parts[i])
        parts[i] = re.sub(r">([^<>]+)<", lambda m: _text(m, lang), p)
    return "".join(parts)


def init(app, get_db):
    @app.before_request
    def pick_lang():
        lang = session.get("lang")
        if lang not in LANGS:
            lang = request.accept_languages.best_match(list(LANGS)) or "fr"
        g.lang = lang

    @app.after_request
    def translate(resp):
        lang = current_lang()
        if lang != "fr" and resp.mimetype == "text/html" and not resp.direct_passthrough:
            resp.set_data(translate_html(resp.get_data(as_text=True), lang))
        return resp

    @app.context_processor
    def inject():
        lang = current_lang()
        exact = _tables(lang)[0] if lang != "fr" else {}
        return {"lang": lang, "dir": "rtl" if lang == "ar" else "ltr", "langs": LANGS,
                "tr_js": exact, "tr": tr, "here": request.full_path.rstrip("?") if request else "/"}

    @app.post("/lang")
    def set_lang():
        lang = request.form.get("lang")
        if lang in LANGS:
            session["lang"] = lang
            if g.get("uid"):
                get_db().execute("UPDATE users SET lang=? WHERE id=?", (lang, g.uid))
                get_db().commit()
        nxt = request.form.get("next", "/")
        if not nxt.startswith("/") or nxt.startswith("//") or "\\" in nxt:
            nxt = url_for("dashboard")
        return redirect(nxt)
