"""Moteur IA de Masar : Gemini API + NLP local de secours. Multilingue."""
import json
import os
import re
import time
import unicodedata
import urllib.error
from urllib.parse import quote
import urllib.request

from i18n import LLM_NAMES, current_lang, tr

MODEL = os.environ.get("MASAR_MODEL", "gemini-3.8-flash")


def gemini_key():
    return (os.environ.get("GEMINI_API_KEY", "").strip()
            or os.environ.get("GOOGLE_API_KEY", "").strip())


def llm_enabled():
    return bool(gemini_key())


def ask_llm(system, messages, max_tokens=900):
    """Appelle le LLM. Retourne (texte, erreur). texte=None si pas de clé ou en cas d'erreur."""
    key = gemini_key()
    if not key:
        return None, "no_key"
    contents = [
        {"role": "model" if m["role"] == "assistant" else "user",
         "parts": [{"text": m["content"]}]}
        for m in messages
    ]
    body = json.dumps({
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": max_tokens},
    }).encode()
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{quote(MODEL, safe='-._')}:generateContent")
    req = urllib.request.Request(
        url, data=body,
        headers={"content-type": "application/json", "x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
        candidates = data.get("candidates", [])
        parts = (candidates[0].get("content", {}).get("parts", [])
                 if candidates else [])
        txt = "".join(
            part.get("text", "") for part in parts if isinstance(part, dict)
        ).strip()
        return (txt or None), ("" if txt else tr("Réponse vide"))
    except urllib.error.HTTPError as e:
        try:
            detail = json.load(e).get("error", {}).get("message", "")
        except Exception:
            detail = ""
        hints = {
            400: tr("Clé API invalide ou mal copiée"),
            401: tr("Clé API invalide ou mal copiée"),
            403: tr("Accès refusé pour cette clé"),
            404: tr("Modèle introuvable ({model}) : change MASAR_MODEL", model=MODEL),
            429: tr("Trop de requêtes, réessaie dans un instant"),
        }
        hint = hints.get(e.code, tr("Erreur HTTP {code}", code=e.code))
        return None, f"{hint} ({detail[:160]})" if detail else hint
    except Exception as e:
        return None, tr(
            "Connexion impossible à l'API Gemini ({err}). Vérifie Internet.",
            err=type(e).__name__)


_status = {}


def llm_status():
    """Teste la clé (cache 60 s par langue). Retourne {'mode': 'llm'|'local'|'error', 'detail': str}."""
    if not llm_enabled():
        return {
            "mode": "local",
            "detail": tr("Aucune clé GEMINI_API_KEY détectée"),
        }
    lang = current_lang()
    t, v = _status.get(lang, (0, None))
    if time.time() - t < 60 and v:
        return v
    txt, err = ask_llm(
        "Réponds seulement : ok", [{"role": "user", "content": "test"}], 64)
    v = ({"mode": "llm", "detail": MODEL} if txt
         else {"mode": "error", "detail": err})
    _status[lang] = (time.time(), v)
    return v


def norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def skills_of(p):
    return [x.strip() for x in (p.get("competences") or "").split(",") if x.strip()]


def prenom(p):
    return (p.get("nom") or "").split(" ")[0] or "toi"


def mail_lang():
    """Langue des emails de candidature : l'interface si EN, sinon français."""
    return "en" if current_lang() == "en" else "fr"


# ------------------------------------------------------------------ BIO
def parse_projets(p):
    out = []
    for line in (p.get("projets") or "").splitlines():
        if line.strip():
            parts = re.split(r"\s[—–-]\s|:\s", line, maxsplit=1)
            out.append({"nom": parts[0].strip(), "description": parts[1].strip() if len(parts) > 1 else ""})
    return out


def gen_bio(p):
    lang = LLM_NAMES[current_lang()]
    out, _ = ask_llm(
        "Tu écris des bios professionnelles pour des étudiants et jeunes diplômés au Maroc. Réponds uniquement avec la bio : "
        f"3 phrases, première personne, ton professionnel et simple, en {lang}, sans inventer de faits absents des données.",
        [{"role": "user", "content": "Données du profil : " + json.dumps(p, ensure_ascii=False)}], 350)
    if out:
        return out
    sk = ", ".join(skills_of(p)[:4]) or "Data"
    projets = [x["nom"] for x in parse_projets(p)]
    titre = p.get("titre") or tr("Étudiante en intelligence artificielle")
    s2 = tr("Je travaille avec {sk}", sk=sk) + (tr(" et j'ai réalisé des projets concrets comme {projets}.", projets=", ".join(projets[:2])) if projets else ".")
    return " ".join([tr("{titre}, basée à {ville}.", titre=titre, ville=p.get("ville") or "Marrakech"), s2,
                     tr("Je cherche un stage ou un premier poste en data et IA pour transformer mes compétences en résultats utiles.")])


# ------------------------------------------------------------------- CV
def gen_cv(p, poste="", lang="fr"):
    """Retourne {resume, competences, projets} dans la langue du CV (fr/en). LLM si dispo, sinon local."""
    base = {"resume": p.get("bio") or gen_bio(p), "competences": skills_of(p), "projets": parse_projets(p)}
    system = ("Tu es un expert en rédaction de CV. À partir du profil JSON, produis un CV adapté au poste visé. "
              "N'invente AUCUN fait (diplôme, entreprise, chiffre) absent du profil. "
              f"Langue : {'français' if lang == 'fr' else 'anglais'}. "
              'Réponds uniquement avec du JSON : {"resume": "2-3 phrases", "competences": ["max 10, triées par pertinence"], '
              '"projets": [{"nom": "...", "description": "1 phrase orientée résultat"}]}')
    out, _ = ask_llm(system, [{"role": "user", "content": json.dumps({"profil": p, "poste_vise": poste}, ensure_ascii=False)}], 900)
    if out:
        try:
            d = json.loads(re.search(r"\{.*\}", out, re.S).group(0))
            return {"resume": d.get("resume") or base["resume"], "competences": d.get("competences") or base["competences"],
                    "projets": d.get("projets") or base["projets"]}
        except Exception:
            pass
    if poste:
        pn = norm(poste)
        base["competences"].sort(key=lambda s: 0 if norm(s) in pn else 1)
        base["resume"] = base["resume"].rstrip(".") + (f". Objectif : {poste}." if lang == "fr" else f". Goal: {poste}.")
    return base


# ----------------------------------------------------------- CHATBOT (NLP)
INTENTS = [
    ("greet", ["salam", "bonjour", "bonsoir", "salut", "hello", "hi", "ahlan", "mrhba", "marhba", "مرحبا", "سلام", "اهلا"]),
    ("bio", ["bio", "presentation", "presente", "about", "profil", "نبذة", "نبذتي"]),
    ("lettre", ["lettre", "motivation", "cover", "letter", "رسالة"]),
    ("cv", ["cv", "curriculum", "resume", "سيرة", "السيرة"]),
    ("entretien", ["entretien", "interview", "mulaqat", "question", "prepar", "prepare", "مقابلة"]),
    ("relance", ["relanc", "follow", "rappel", "متابعة"]),
    ("candidatures", ["candidat", "postul", "statut", "applic", "ترشيح", "ترشيحات"]),
    ("offres", ["offre", "stage", "emploi", "travail", "khdma", "khedma", "job", "poste", "match", "correspond", "offers", "عروض", "عمل", "وظيفة"]),
    ("villes", ["ville", "city", "casablanca", "rabat", "marrakech", "tanger", "agadir", "entrepris", "secteur", "societe", "cities", "مدينة", "مدن", "شركات"]),
    ("competences", ["competence", "skill", "skills", "apprendre", "formation", "niveau", "ameliorer", "learn", "مهارات"]),
]


def detect_intent(msg):
    toks = re.findall(r"[a-z0-9\u0600-\u06FF]+", norm(msg))
    best, score = "default", 0
    for name, kws in INTENTS:
        s = sum(1 for t in toks if any(t == k or (len(k) >= 4 and t.startswith(k)) for k in kws))
        if s > score:
            best, score = name, s
    return best


def chat_system(ctx):
    return ("Tu es Masar AI, un assistant polyvalent intégré à l'application Masar (carrière et emploi au Maroc). "
            "Tu réponds à TOUTE question de l'utilisateur : culture générale, études, programmation, maths, rédaction, "
            "traduction, conseils de vie ou de carrière, etc., sans refuser un sujet sans raison valable. "
            f"Langue par défaut : {LLM_NAMES[current_lang()]} (la langue choisie dans l'interface). Si l'utilisateur écrit clairement "
            "dans une autre langue (français, anglais, arabe, darija en lettres latines), réponds dans cette langue. "
            "Quand c'est utile pour l'emploi, aide pour : bio, CV, lettre de motivation, entretiens, relances, choix d'offres. "
            "Utilise le contexte ci-dessous seulement s'il est pertinent, sans inventer de faits sur l'utilisateur. "
            "Contexte (JSON) : " + json.dumps(ctx, ensure_ascii=False))


def local_reply(msg, ctx):
    p, intent = ctx["profil"], detect_intent(msg)
    nom = prenom(p)
    if intent == "greet":
        return tr("Salam {nom} ! Je suis Masar AI. Je peux écrire ta bio, améliorer ton CV, rédiger une lettre de motivation, te préparer aux entretiens, te rappeler tes relances et te proposer les meilleures offres. Par quoi on commence ?", nom=nom)
    if intent == "bio":
        return gen_bio(p) + "\n\n" + tr("Tu peux l'enregistrer depuis la page « Mon profil ».")
    if intent == "lettre":
        sk = ", ".join(skills_of(p)[:3]) or "Data"
        ent = next((o["entreprise"] for o in ctx["top_offres"] if norm(o["entreprise"]) in norm(msg)), tr("[Entreprise]"))
        titre = (p.get("titre") or tr("Étudiante en intelligence artificielle"))
        titre = titre[0].lower() + titre[1:]
        return tr("Madame, Monsieur,\n\nActuellement {titre}, je souhaite rejoindre {ent} pour un poste de [Poste]. Je travaille avec {sk} et j'ai déjà appliqué ces outils dans des projets concrets. Motivée et rigoureuse, je serais heureuse de contribuer à vos équipes et d'apprendre à vos côtés.\n\nJe reste disponible pour un entretien à votre convenance.\n\nCordialement,\n{nom}",
                  titre=titre, ent=ent, sk=sk, nom=p.get("nom") or "")
    if intent == "cv":
        return tr("Ouvre « Créer mon CV », écris le poste visé et clique sur Générer : je réorganise tes compétences et tes projets pour ce poste, puis tu peux l'enregistrer en PDF. Je n'ajoute jamais d'information que tu n'as pas saisie.")
    if intent == "entretien":
        return tr("Questions fréquentes pour un poste data / IA :\n1. Présente-toi en 1 minute.\n2. Explique un projet dont tu es fière (problème, méthode, résultat).\n3. Comment nettoies-tu un jeu de données avec des valeurs manquantes ?\n4. Quelle différence entre surapprentissage et sous-apprentissage ?\n5. Pourquoi cette entreprise ?\nEntraîne-toi à voix haute avec la structure Situation → Action → Résultat.")
    if intent == "relance":
        if not ctx["relances"]:
            return tr("Aucune candidature à relancer pour le moment. Je te le dirai dès qu'une candidature dépasse 7 jours sans réponse.")
        return (tr("À relancer aujourd'hui :") + "\n" + "\n".join(f"• {r}" for r in ctx["relances"]) + "\n\n" +
                tr("Modèle : « Bonjour, je me permets de revenir vers vous au sujet de ma candidature envoyée il y a quelques jours. Je reste très motivée et disponible pour un échange. Cordialement. »"))
    if intent == "candidatures":
        liste = ", ".join(tr("{n} {statut}", n=n, statut=tr(s)) for s, n in ctx["stats"].items() if n)
        return tr("Tes candidatures : {liste}. Va dans « Candidatures » pour changer un statut ou ajouter une note.", liste=liste)
    if intent == "offres":
        if not ctx["top_offres"]:
            return tr("Complète d'abord tes compétences dans « Mon profil » pour que je puisse calculer ton matching.")
        lignes = "\n".join(f"• {o['titre']} · {o['entreprise']} ({tr(o['ville'])}) : {o['score']} %" for o in ctx["top_offres"][:3])
        return tr("Les offres qui te correspondent le mieux :") + "\n" + lignes + "\n\n" + tr("Détails dans « Offres » et « CV & Matching ».")
    if intent == "villes":
        v = "\n".join(f"• {tr(n)} ({c})" for n, c in ctx["top_villes"][:3])
        return tr("Villes avec le plus d'entreprises dans l'analyse :") + "\n" + v + "\n\n" + tr("Affine par type d'entreprise dans « Analyse des entreprises ».")
    if intent == "competences":
        if ctx["manquantes"]:
            return tr("Compétences très demandées dans les offres qui te manquent : {liste}. Commence par une, avec un mini-projet à mettre dans ton CV.", liste=", ".join(ctx["manquantes"][:4]))
        return tr("Ton profil couvre déjà les compétences les plus demandées dans les offres. Ajoute des projets concrets pour le prouver.")
    return tr("Je n'ai pas bien compris. Essaie par exemple : « écris ma bio », « prépare-moi à un entretien », « lettre de motivation », « quelles offres me correspondent ? » ou « qui dois-je relancer ? ».")


def chat_reply(msg, history, ctx):
    """Retourne (réponse, mode, erreur)."""
    msgs = [{"role": h["role"], "content": h["content"]} for h in history[-12:]
            if h.get("role") in ("user", "assistant") and h.get("content")]
    msgs.append({"role": "user", "content": msg})
    out, err = ask_llm(chat_system(ctx), msgs, 1500)
    if out:
        return out, "llm", ""
    local = local_reply(msg, ctx)
    if err == "no_key":
        return local + "\n\n" + tr("(Mode local : pour que je réponde à toutes les questions, ajoute ta clé GEMINI_API_KEY.)"), "local", ""
    return tr("⚠️ L'IA n'a pas pu répondre : {err}", err=err) + "\n\n" + local, "error", err
