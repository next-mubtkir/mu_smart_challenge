# Copyright (c) 2026, MUBTKIR and contributors
# For license information, please see license.txt
"""Challenge engine.

This module is the "brain". It is deliberately channel-agnostic: it never talks
to WhatsApp directly. Instead it listens for inbound "WhatsApp Message" records
(saved by the channel app frappe_whatsapp / "mu-wats-api") via a doc_events
hook, and it replies by *inserting* outbound "WhatsApp Message" records, which
the channel app sends automatically over whichever transport is configured
(Meta Cloud API or Evolution).

Everything here is deterministic. There is no AI in the MVP scoring path.

State machine
-------------
NEW -> WAITING_START -> WAITING_BUSINESS_TYPE -> WAITING_COMPANY_SIZE
    -> PLAYING/WAITING_ANSWER (loop over scenarios)
    -> CALCULATING -> COMPLETED
Any state, idle 24h -> ABANDONED
"""

import json

import frappe
from frappe.utils import now_datetime, add_to_date

# Language used for the MVP. Kept in one place so a later phase can switch on the
# player's locale.
LANG = "ar"

# Business-size options offered before gameplay.
COMPANY_SIZES = ["1-3", "4-10", "11-50", "50+"]


# ---------------------------------------------------------------------------
# Small helpers for reading fields in the active language
# ---------------------------------------------------------------------------
def _t(doc, base):
    """Return doc.<base>_<LANG>, falling back to the English/other variant."""
    value = doc.get(f"{base}_{LANG}")
    if value:
        return value
    other = "en" if LANG == "ar" else "ar"
    return doc.get(f"{base}_{other}") or ""


def _label(option):
    """Return an option's label in the active language."""
    return option.get(f"label_{LANG}") or option.get("label_en") or option.get("option_id")


def _feedback(option):
    """Return an option's feedback in the active language."""
    return option.get(f"feedback_{LANG}") or option.get("feedback_en") or ""


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------
def _already_processed(message_id):
    """True if this WhatsApp message id was already logged (idempotency)."""
    if not message_id:
        return False
    return bool(
        frappe.db.exists("Challenge Message Log", {"whatsapp_message_id": message_id})
    )


def _log_message(message_id, direction, session=None, payload=None):
    """Record a message id so it is never processed twice. Best-effort."""
    if not message_id:
        return
    try:
        frappe.get_doc(
            {
                "doctype": "Challenge Message Log",
                "whatsapp_message_id": message_id,
                "direction": direction,
                "session": session,
                "timestamp": now_datetime(),
                "payload": (payload or "")[:1000],
            }
        ).insert(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        # Another worker logged the same id first — that's fine.
        pass


# ---------------------------------------------------------------------------
# Sending (create an Outgoing WhatsApp Message; the channel app sends it)
# ---------------------------------------------------------------------------
def _send_text(to, body):
    """Send a plain text message via the channel app."""
    frappe.get_doc(
        {
            "doctype": "WhatsApp Message",
            "type": "Outgoing",
            "to": to,
            "content_type": "text",
            "message": body,
        }
    ).insert(ignore_permissions=True)


def _send_options(to, body, options, fmt):
    """Send a decision prompt.

    We render options as a numbered text prompt: it works identically on Meta
    and on Evolution, and the inbound parser accepts either the number the user
    types or the option label/id they tap. `fmt` (buttons/list) is recorded for
    a later phase that emits native interactive payloads; the MVP keeps one
    portable format so the engine behaves the same on both transports.
    """
    lines = [body, ""]
    for index, option in enumerate(options, start=1):
        lines.append(f"{index}. {_label(option)}")
    lines.append("")
    lines.append(_("Reply with the option number."))
    _send_text(to, "\n".join(lines))


def _(text):
    """Tiny wrapper so user-facing strings stay translatable later."""
    # In the MVP we ship Arabic copy inline where it matters; generic prompts
    # are short and localised here.
    ar = {
        "Reply with the option number.": "أرسل رقم الخيار.",
    }
    return ar.get(text, text) if LANG == "ar" else text


# ---------------------------------------------------------------------------
# Session lookup / creation
# ---------------------------------------------------------------------------
def _get_or_create_session(mobile, profile_name=None):
    """Return the active session for a mobile number, creating one if needed.

    An "active" session is any that is not in a terminal state. A brand-new
    session starts in NEW.
    """
    name = frappe.db.get_value(
        "Challenge Session",
        {
            "mobile_number": mobile,
            "status": ["not in", ["COMPLETED", "REPORT_SENT", "CONVERTED", "ABANDONED"]],
        },
        "name",
    )
    if name:
        return frappe.get_doc("Challenge Session", name)

    session = frappe.get_doc(
        {
            "doctype": "Challenge Session",
            "session_id": f"CS-{frappe.generate_hash(length=10)}",
            "status": "NEW",
            "mobile_number": mobile,
            "whatsapp_id": mobile,
            "customer_name": profile_name,
            "started_at": now_datetime(),
            "last_interaction_at": now_datetime(),
        }
    )
    session.insert(ignore_permissions=True)
    return session


def _active_challenge():
    """Return the single active challenge for the MVP (first active by name)."""
    name = frappe.db.get_value("Business Challenge", {"is_active": 1}, "name")
    return frappe.get_doc("Business Challenge", name) if name else None


def _questions(challenge):
    """Return active questions for a challenge, in play order."""
    names = frappe.get_all(
        "Business Challenge Question",
        filters={"challenge": challenge.name, "is_active": 1},
        order_by="question_number asc",
        pluck="name",
    )
    return [frappe.get_doc("Business Challenge Question", n) for n in names]


# ---------------------------------------------------------------------------
# The doc_events entry point
# ---------------------------------------------------------------------------
def handle_incoming_message(doc, method=None):
    """after_insert hook on WhatsApp Message.

    Only acts on inbound messages. Everything is wrapped so a failure here can
    never break the channel app's own insert.
    """
    try:
        if (doc.get("type") or "").lower() != "incoming":
            return

        message_id = doc.get("message_id")
        if _already_processed(message_id):
            return

        mobile = (doc.get("from") or "").strip()
        if not mobile:
            return

        text = _extract_text(doc)
        session = _get_or_create_session(mobile, doc.get("profile_name"))
        _log_message(message_id, "in", session.name, text)

        _advance(session, text)

        session.last_interaction_at = now_datetime()
        session.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(
            title="MU Smart Challenge — incoming handler failed",
            message=frappe.get_traceback(),
        )


def _extract_text(doc):
    """Get a usable text/selection out of an inbound WhatsApp Message.

    Handles plain text, tapped button text, and interactive replies (the
    channel app stores an interactive reply as a JSON string).
    """
    content_type = (doc.get("content_type") or "text").lower()
    raw = doc.get("message") or ""

    if content_type in ("text", "button"):
        return raw.strip()

    # interactive / flow: the channel app stored a JSON payload; try to pull an
    # id or title out of it.
    try:
        data = json.loads(raw)
        for key in ("id", "title", "selected_id", "button_reply", "list_reply"):
            value = data.get(key) if isinstance(data, dict) else None
            if isinstance(value, dict):
                value = value.get("id") or value.get("title")
            if value:
                return str(value).strip()
    except (ValueError, TypeError):
        pass
    return raw.strip()


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------
def _advance(session, text):
    """Drive the session forward based on its status and the player's message."""
    status = session.status or "NEW"

    if status in ("NEW", "WAITING_START"):
        _begin(session)
    elif status == "WAITING_BUSINESS_TYPE":
        session.business_type = text
        _ask_company_size(session)
    elif status == "WAITING_COMPANY_SIZE":
        session.company_size = text
        _start_gameplay(session)
    elif status in ("PLAYING", "WAITING_ANSWER"):
        _handle_answer(session, text)
    else:
        # Terminal or unexpected — do nothing further.
        pass


def _begin(session):
    """NEW -> ask for business type (first onboarding step)."""
    challenge = _active_challenge()
    if not challenge:
        _send_text(session.mobile_number, "لا يوجد تحدٍ مفعّل حالياً. تواصل معنا لاحقاً 🙏")
        return

    session.challenge = challenge.name
    session.challenge_version = challenge.version
    start = _t(challenge, "start_message") or "أهلاً بك في تحدي إدارة البزنس 👋"
    _send_text(session.mobile_number, start)
    _ask_business_type(session)


def _ask_business_type(session):
    """Onboarding step 1 — business type (separate step, before gameplay)."""
    session.status = "WAITING_BUSINESS_TYPE"
    _send_text(session.mobile_number, "ما نوع نشاطك التجاري؟ (مثال: تجزئة، مطعم، خدمات)")


def _ask_company_size(session):
    """Onboarding step 2 — company size (separate step, before gameplay)."""
    session.status = "WAITING_COMPANY_SIZE"
    sizes = " / ".join(COMPANY_SIZES)
    _send_text(session.mobile_number, f"كم عدد موظفيك تقريباً؟\n{sizes}")


def _start_gameplay(session):
    """Move into the scenario loop and send the first question."""
    session.status = "PLAYING"
    session.current_question = 0
    _send_next_question(session)


def _send_next_question(session):
    """Send the next unplayed question, or finish if none remain."""
    questions = _questions(frappe.get_doc("Business Challenge", session.challenge))
    upcoming = [q for q in questions if (q.question_number or 0) > (session.current_question or 0)]

    if not upcoming:
        _finish(session)
        return

    question = upcoming[0]
    session.current_question = question.question_number
    session.status = "WAITING_ANSWER"

    header = _t(question, "scenario_title")
    body = _t(question, "scenario_text")
    prompt = f"📅 {header}\n\n{body}" if header else body
    _send_options(
        session.mobile_number,
        prompt,
        question.options,
        question.resolved_format(),
    )


def _handle_answer(session, text):
    """Match the player's message to an option, apply it, send feedback, advance."""
    questions = _questions(frappe.get_doc("Business Challenge", session.challenge))
    current = next(
        (q for q in questions if q.question_number == session.current_question),
        None,
    )
    if not current:
        _finish(session)
        return

    option = _match_option(current.options, text)
    if not option:
        # Unexpected input: re-show the same options, keep the state.
        _send_text(session.mobile_number, "😄 هذا هو التحدي! اختر الأقرب لما ستفعله:")
        _send_options(
            session.mobile_number,
            _t(current, "scenario_text"),
            current.options,
            current.resolved_format(),
        )
        return

    session.apply_option(current, option)

    feedback = _feedback(option)
    if feedback:
        _send_text(session.mobile_number, feedback)

    session.status = "PLAYING"
    _send_next_question(session)


def _match_option(options, text):
    """Resolve a player's message to one option.

    Accepts: the 1-based option number, the exact option_id, or a label match.
    """
    text = (text or "").strip()
    if not text:
        return None

    # by number
    if text.isdigit():
        index = int(text) - 1
        if 0 <= index < len(options):
            return options[index]

    lowered = text.lower()
    for option in options:
        if (option.get("option_id") or "").lower() == lowered:
            return option
    for option in options:
        for key in (f"label_{LANG}", "label_en", "label_ar"):
            label = (option.get(key) or "").strip().lower()
            if label and label == lowered:
                return option
    return None


# ---------------------------------------------------------------------------
# Finishing: score, diagnosis, lead
# ---------------------------------------------------------------------------
def _finish(session):
    """Compute totals, send the result + diagnosis, create the Lead."""
    session.status = "CALCULATING"
    total = session.compute_total()
    session.completed_at = now_datetime()

    _send_result(session, total)
    _send_diagnosis(session)

    challenge = frappe.get_doc("Business Challenge", session.challenge)
    completion = _t(challenge, "completion_message")
    if completion:
        _send_text(session.mobile_number, completion)

    _create_lead(session)
    session.status = "COMPLETED"


def _send_result(session, total):
    """Send the headline score and the six indicators."""
    lines = [
        f"🧠 نتيجة تحدي إدارة المشروع",
        f"{total} / 100",
        "",
        f"💰 السيولة: {session.cash_flow}/100",
        f"📦 المخزون: {session.inventory}/100",
        f"💵 الربحية: {session.profitability}/100",
        f"🧾 التحصيل: {session.collection}/100",
        f"📊 الرقابة: {session.control}/100",
        f"🧾 الامتثال: {session.compliance}/100",
    ]
    _send_text(session.mobile_number, "\n".join(lines))


def _send_diagnosis(session):
    """Send the two weakest areas as the key risks."""
    weakest = session.lowest_indicators(2)
    names_ar = {
        "Cash Flow": "التدفق النقدي",
        "Profitability": "الربحية",
        "Inventory": "المخزون",
        "Collection": "تحصيل العملاء",
        "Control": "الرقابة",
        "Compliance": "الامتثال",
    }
    risks = "\n".join(f"• {names_ar.get(label, label)}" for label, _f, _v in weakest)
    _send_text(session.mobile_number, f"🔍 أكبر خطرين على مشروعك:\n{risks}")


# ---------------------------------------------------------------------------
# Lead scoring + creation + sales alert
# ---------------------------------------------------------------------------
def _compute_lead_score(session):
    """Deterministic lead score from qualification signals. Returns (score, band)."""
    score = 20  # assume a business owner completed the challenge
    size = (session.company_size or "")
    if size in ("11-50", "50+"):
        score += 15
    if size == "50+":
        score += 15

    # Completing the challenge at all is a warm signal.
    score += 10

    score = max(0, min(100, score))
    if score <= 30:
        band = "Cold"
    elif score <= 60:
        band = "Warm"
    elif score <= 80:
        band = "Hot"
    else:
        band = "Sales Priority"
    return score, band


def _create_lead(session):
    """Create an ERPNext Lead, store the split scores, alert sales if hot."""
    lead_score, band = _compute_lead_score(session)
    session.lead_score = lead_score
    session.lead_quality = band

    weakest = session.lowest_indicators(2)
    main_problem = weakest[0][0] if weakest else ""
    second_problem = weakest[1][0] if len(weakest) > 1 else ""

    try:
        lead = frappe.get_doc(
            {
                "doctype": "Lead",
                "lead_name": session.customer_name or session.mobile_number,
                "mobile_no": session.mobile_number,
                "source": "Business Simulator",
                "notes": (
                    f"Business Type: {session.business_type}\n"
                    f"Company Size: {session.company_size}\n"
                    f"Challenge Score: {session.challenge_score}\n"
                    f"Lead Score: {lead_score} ({band})\n"
                    f"Main Problem: {main_problem}\n"
                    f"Secondary Problem: {second_problem}\n"
                    f"Campaign: {session.campaign or ''} | Source: {session.source or ''}"
                ),
            }
        )
        lead.insert(ignore_permissions=True)
        session.lead = lead.name
    except Exception:
        frappe.log_error(
            title="MU Smart Challenge — lead creation failed",
            message=frappe.get_traceback(),
        )
        return

    if lead_score >= 70:
        _alert_sales(session, lead, band, main_problem, second_problem)


def _alert_sales(session, lead, band, main_problem, second_problem):
    """Raise an in-ERPNext ToDo for the sales team on a high-quality lead."""
    try:
        frappe.get_doc(
            {
                "doctype": "ToDo",
                "reference_type": "Lead",
                "reference_name": lead.name,
                "priority": "High",
                "description": (
                    f"🔥 High-priority Lead from Business Simulator\n"
                    f"Business Type: {session.business_type} | Size: {session.company_size}\n"
                    f"Lead Score: {session.lead_score} ({band})\n"
                    f"Main Problem: {main_problem} | Secondary: {second_problem}\n"
                    f"Challenge Score: {session.challenge_score}\n"
                    f"Mobile: {session.mobile_number}"
                ),
            }
        ).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(
            title="MU Smart Challenge — sales ToDo failed",
            message=frappe.get_traceback(),
        )


# ---------------------------------------------------------------------------
# Scheduled: abandon idle sessions
# ---------------------------------------------------------------------------
def mark_abandoned_sessions():
    """Hourly job: mark sessions idle for 24h+ as ABANDONED."""
    cutoff = add_to_date(now_datetime(), hours=-24)
    stale = frappe.get_all(
        "Challenge Session",
        filters={
            "status": ["not in", ["COMPLETED", "REPORT_SENT", "CONVERTED", "ABANDONED"]],
            "last_interaction_at": ["<", cutoff],
        },
        pluck="name",
    )
    for name in stale:
        frappe.db.set_value("Challenge Session", name, "status", "ABANDONED")
    if stale:
        frappe.db.commit()
