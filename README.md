# MU Smart Challenge (`mu_smart_challenge`)

WhatsApp business-simulation challenge engine for ERPNext/Frappe. A player runs
a simulated business through a series of decision scenarios, receives a 0–100
score across six indicators, and is converted into a qualified ERPNext **Lead**.

This app is the **"brain"**: all logic and data live here. It does **not** talk
to WhatsApp directly. It relies on the channel app **`frappe_whatsapp`
("mu-wats-api")** for sending and receiving, so it works over **both** Meta
Cloud API and Evolution with no changes.

## How the integration works (no n8n)

```
Player ──▶ Meta Cloud API / Evolution ──▶ frappe_whatsapp webhook
                                              │ saves "WhatsApp Message" (Incoming)
                                              ▼
                    doc_events after_insert ──▶ mu_smart_challenge.engine
                                              │ runs the state machine + scoring
                                              ▼
                    inserts "WhatsApp Message" (Outgoing)
                                              │
                    frappe_whatsapp sends it ─▶ Player
```

- Inbound: the engine listens via a `doc_events` hook on **WhatsApp Message**
  (`after_insert`). No change to the channel app's webhook.
- Outbound: the engine **creates** an Outgoing WhatsApp Message; the channel app
  sends it automatically.

## Requirements

- A Frappe/ERPNext site.
- The channel app `frappe_whatsapp` ("mu-wats-api") installed and connected on
  the same site (Meta Cloud API and/or Evolution).

## Install

```bash
cd frappe-bench
bench get-app mu_smart_challenge /path/to/mu_smart_challenge
bench --site YOUR_SITE install-app mu_smart_challenge
bench --site YOUR_SITE migrate
```

Installing seeds one sample challenge (`RETAIL-001`) with a single scenario so
you can test immediately. Add the rest of the questions from the ERPNext UI:
**Business Challenge Question**.

## DocTypes

- **Business Challenge** — a challenge/sector definition (bilingual messages).
- **Business Challenge Question** — one scenario + its options (child table).
- **Question Option** — one option, with per-indicator effects and feedback.
- **Challenge Session** — a player's run: state machine, six live indicators,
  answers, and split scores (`challenge_score` vs `lead_score`).
- **Challenge Answer** — every answer recorded (child of session).
- **Challenge Message Log** — dedup + audit by WhatsApp message id.

## State machine

```
NEW → WAITING_START → WAITING_BUSINESS_TYPE → WAITING_COMPANY_SIZE
    → PLAYING / WAITING_ANSWER (scenario loop)
    → CALCULATING → COMPLETED
any state, idle 24h → ABANDONED
```

## Scoring

- Six indicators start at 50, each option adds/subtracts, clamped to 0–100.
- `total_score` / `challenge_score` = **simple average** of the six.
- `lead_score` is separate (qualification-based) and drives the sales alert.
- On `lead_score >= 70` a **High-priority ToDo** is raised in ERPNext against
  the Lead.

## Notes / next phases

- Options are sent as a portable numbered text prompt so behaviour is identical
  on Meta and Evolution. Native interactive buttons/lists (Cloud API) and Poll
  (Evolution) can be emitted in a later phase; `option_format` is already stored.
- Deferred: PDF report, AI analysis, branching, random events, referral,
  campaign analytics.
