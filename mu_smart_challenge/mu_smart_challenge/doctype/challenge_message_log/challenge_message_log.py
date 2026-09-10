# Copyright (c) 2026, MUBTKIR and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ChallengeMessageLog(Document):
    """Dedup + audit log of every inbound/outbound WhatsApp message id.

    The unique whatsapp_message_id is what makes processing idempotent: a
    redelivered webhook for the same id is ignored.
    """

    pass
