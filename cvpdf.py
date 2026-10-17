"""Génération du CV en vrai PDF (reportlab), avec photo ronde."""
import io
from html import escape

from PIL import Image, ImageDraw
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

GREEN, MINT, MUTED = colors.HexColor("#1b4332"), colors.HexColor("#b7e4c7"), colors.HexColor("#5b6a62")


def clean(s):
    """Texte compatible avec les polices PDF standard (Latin-1 / cp1252)."""
    s = (s or "").replace("→", "->").replace("•", "-")
    return escape(s.encode("cp1252", "replace").decode("cp1252"))


def round_photo(path, px=360):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    m = min(w, h)
    im = im.crop(((w - m) // 2, (h - m) // 2, (w + m) // 2, (h + m) // 2)).resize((px, px))
    mask = Image.new("L", (px, px), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, px, px), fill=255)
    im.putalpha(mask)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    buf.seek(0)
    return buf


def build_pdf(p, cv, poste, labels, photo_path=None):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=f"CV {p.get('nom', '')}", author=p.get("nom", ""))
    name = ParagraphStyle("n", fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=GREEN)
    sub = ParagraphStyle("s", fontName="Helvetica", fontSize=12, leading=16, textColor=colors.HexColor("#2d6a4f"))
    small = ParagraphStyle("c", fontName="Helvetica", fontSize=9.5, leading=13, textColor=MUTED)
    h = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=GREEN, spaceBefore=12, spaceAfter=3)
    body = ParagraphStyle("b", fontName="Helvetica", fontSize=10, leading=14.5, alignment=TA_LEFT)
    story = []
    head = [Paragraph(clean(p.get("nom")), name), Paragraph(clean(poste or p.get("titre")), sub),
            Paragraph(clean(" | ".join(x for x in (p.get("ville"), p.get("email"), p.get("tel")) if x)), small)]
    if photo_path:
        t = Table([[head, RLImage(round_photo(photo_path), 28 * mm, 28 * mm)]], colWidths=[144 * mm, 30 * mm], hAlign="LEFT")
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        story.append(t)
    else:
        story += head

    def section(title):
        t = Table([[Paragraph(clean(title.upper()), h)]], colWidths=[174 * mm], hAlign="LEFT")
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 1.2, MINT), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
        story.append(t)
        story.append(Spacer(1, 3))

    if cv.get("resume"):
        section(labels["resume"]); story.append(Paragraph(clean(cv["resume"]), body))
    if cv.get("competences"):
        section(labels["skills"]); story.append(Paragraph(clean("  -  ".join(cv["competences"])), body))
    if cv.get("projets"):
        section(labels["projects"])
        for pr in cv["projets"]:
            d = f" - {clean(pr.get('description'))}" if pr.get("description") else ""
            story.append(Paragraph(f"<b>{clean(pr.get('nom'))}</b>{d}", body))
    for key, title in (("experience", labels["exp"]), ("formation", labels["edu"])):
        if p.get(key):
            section(title)
            for line in p[key].splitlines():
                if line.strip():
                    story.append(Paragraph(clean(line), body))
    if p.get("langues"):
        section(labels["lang"]); story.append(Paragraph(clean(p["langues"]), body))
    doc.build(story)
    return buf.getvalue()


def build_letter_pdf(p, offer, letter):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm,
        topMargin=22 * mm, bottomMargin=22 * mm,
        title=f"Lettre de motivation - {offer.get('titre', '')}",
        author=p.get("nom", ""),
    )
    name = ParagraphStyle(
        "letter_name", fontName="Helvetica-Bold", fontSize=16, leading=20,
        textColor=GREEN, spaceAfter=5,
    )
    contact = ParagraphStyle(
        "letter_contact", fontName="Helvetica", fontSize=9, leading=13,
        textColor=MUTED, spaceAfter=20,
    )
    heading = ParagraphStyle(
        "letter_heading", fontName="Helvetica-Bold", fontSize=11, leading=15,
        textColor=GREEN, spaceAfter=12,
    )
    body = ParagraphStyle(
        "letter_body", fontName="Helvetica", fontSize=10.5, leading=16,
        spaceAfter=12,
    )
    story = [
        Paragraph(clean(p.get("nom")), name),
        Paragraph(clean(" | ".join(
            value for value in (p.get("email"), p.get("tel"), p.get("ville"))
            if value
        )), contact),
        Paragraph(clean(offer.get("entreprise", "")), heading),
        Paragraph(clean(f"Candidature : {offer.get('titre', '')}"), heading),
    ]
    normalized_letter = (letter or "").replace("\r\n", "\n").strip()
    for paragraph in normalized_letter.split("\n\n"):
        text = "<br/>".join(clean(line) for line in paragraph.splitlines())
        if text:
            story.append(Paragraph(text, body))
    doc.build(story)
    return buf.getvalue()
