# Copyright (c) 2026, MUBTKIR and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

# The six indicators, in a fixed order. Field name on the session <-> the
# per-option effect field on Question Option <-> the per-answer impact field.
INDICATORS = (
    ("cash_flow", "cash_effect", "cash_impact"),
    ("profitability", "profit_effect", "profit_impact"),
    ("inventory", "inventory_effect", "inventory_impact"),
    ("collection", "collection_effect", "collection_impact"),
    ("control", "control_effect", "control_impact"),
    ("compliance", "compliance_effect", "compliance_impact"),
)


def clamp(value, low=0, high=100):
    """Keep an indicator within [low, high]."""
    return max(low, min(high, value))


class ChallengeSession(Document):
    """A single player's run through a challenge.

    Holds the state-machine status, the six live indicators, every answer, and
    the final scores. All mutation goes through the engine; the methods here are
    the low-level primitives it calls.
    """

    def apply_option(self, question, option):
        """Apply one chosen option to the indicators and record the answer.

        Adds each indicator effect (clamped 0-100) and appends a Challenge
        Answer row. Does not save; the caller commits.
        """
        impact = {}
        for field, effect_field, impact_field in INDICATORS:
            effect = option.get(effect_field) or 0
            setattr(self, field, clamp((self.get(field) or 0) + effect))
            impact[impact_field] = effect

        self.append(
            "answers",
            {
                "question": question.name,
                "question_number": question.question_number,
                "selected_option_id": option.get("option_id"),
                "score": option.get("score") or 0,
                "answered_at": frappe.utils.now_datetime(),
                **impact,
            },
        )

    def compute_total(self):
        """Set total_score/challenge_score to the simple average of the six."""
        values = [self.get(field) or 0 for field, _, _ in INDICATORS]
        total = round(sum(values) / len(values))
        self.total_score = total
        self.challenge_score = total
        return total

    def lowest_indicators(self, count=2):
        """Return the `count` weakest indicators as (label, field, value)."""
        labels = {
            "cash_flow": "Cash Flow",
            "profitability": "Profitability",
            "inventory": "Inventory",
            "collection": "Collection",
            "control": "Control",
            "compliance": "Compliance",
        }
        ordered = sorted(
            ((labels[f], f, self.get(f) or 0) for f, _, _ in INDICATORS),
            key=lambda row: row[2],
        )
        return ordered[:count]
