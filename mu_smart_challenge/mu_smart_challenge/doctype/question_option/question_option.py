# Copyright (c) 2026, MUBTKIR and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class QuestionOption(Document):
    """A single selectable option inside a Business Challenge Question.

    Child table. Each option carries its per-indicator effects and the feedback
    shown to the user immediately after they pick it.
    """

    pass
