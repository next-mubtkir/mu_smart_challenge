# Copyright (c) 2026, MUBTKIR and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ChallengeAnswer(Document):
    """One recorded answer inside a Challenge Session.

    Child table. Every answer is stored (not just the final score) so answers
    can be analysed later.
    """

    pass
