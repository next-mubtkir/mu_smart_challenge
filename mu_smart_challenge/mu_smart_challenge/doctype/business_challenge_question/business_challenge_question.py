# Copyright (c) 2026, MUBTKIR and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class BusinessChallengeQuestion(Document):
    """One scenario within a challenge, plus its selectable options.

    The engine reads active questions in question_number order and renders the
    options as WhatsApp buttons or a list depending on option_format / count.
    """

    def resolved_format(self):
        """Return the effective option format: buttons or list.

        When option_format is 'auto', <=3 options render as buttons and more
        render as a list (WhatsApp allows up to 3 reply buttons, up to 10 list
        rows).
        """
        fmt = self.option_format or "auto"
        if fmt in ("buttons", "list"):
            return fmt
        return "buttons" if len(self.options or []) <= 3 else "list"
