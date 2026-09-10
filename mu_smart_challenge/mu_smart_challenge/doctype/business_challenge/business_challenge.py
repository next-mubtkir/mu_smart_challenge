# Copyright (c) 2026, MUBTKIR and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class BusinessChallenge(Document):
    """Definition of one challenge (a sector scenario set).

    A generic container so new sectors/challenges can be added from the UI
    without touching the engine.
    """

    pass
