app_name = "mu_smart_challenge"
app_title = "MU Smart Challenge"
app_publisher = "MUBTKIR"
app_description = "WhatsApp business-simulation challenge engine that generates qualified ERPNext Leads."
app_email = "info@mubtkir.com"
app_license = "MIT"

# ---------------------------------------------------------------------------
# Document Events
# ---------------------------------------------------------------------------
# The channel app (frappe_whatsapp / "mu-wats-api") saves every inbound message
# as a "WhatsApp Message" (type=Incoming). We listen for that insert and hand it
# to the challenge engine. We never touch the channel app's webhook or talk to
# WhatsApp directly — replies are created as Outgoing "WhatsApp Message" records,
# which the channel app sends automatically. This works for both Meta Cloud API
# and Evolution, since both terminate in a "WhatsApp Message".
doc_events = {
    "WhatsApp Message": {
        "after_insert": "mu_smart_challenge.mu_smart_challenge.engine.handle_incoming_message",
    }
}

# ---------------------------------------------------------------------------
# Install / Migrate hooks — seed the one sample Retail challenge + question
# ---------------------------------------------------------------------------
after_install = "mu_smart_challenge.mu_smart_challenge.bootstrap.create_sample_data"
after_migrate = "mu_smart_challenge.mu_smart_challenge.bootstrap.create_sample_data"

# ---------------------------------------------------------------------------
# Scheduled Tasks
# ---------------------------------------------------------------------------
# Mark long-idle sessions as ABANDONED so follow-up logic can pick them up.
scheduler_events = {
    "hourly": [
        "mu_smart_challenge.mu_smart_challenge.engine.mark_abandoned_sessions",
    ]
}
