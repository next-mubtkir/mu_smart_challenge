# Copyright (c) 2026, MUBTKIR and contributors
# For license information, please see license.txt
"""One-time sample data.

Creates a single Retail challenge with ONE sample scenario (the supplier
discount decision) so the flow can be tested end-to-end immediately after
install. The rest of the questions are added from the ERPNext UI.

Safe to run repeatedly: it only creates records that don't already exist.
"""

import frappe

SAMPLE_CHALLENGE_CODE = "RETAIL-001"


def create_sample_data():
    """Create the sample challenge + question if they are not there yet."""
    if not frappe.db.exists("Business Challenge", SAMPLE_CHALLENGE_CODE):
        frappe.get_doc(
            {
                "doctype": "Business Challenge",
                "challenge_name": "Retail Store Management",
                "challenge_code": SAMPLE_CHALLENGE_CODE,
                "business_type": "Retail",
                "is_active": 1,
                "version": "v1",
                "number_of_questions": 1,
                "estimated_duration": "4 minutes",
                "title_ar": "إدارة متجر تجزئة",
                "title_en": "Retail Store Management",
                "description": "MVP sample challenge with one scenario.",
                "start_message_ar": (
                    "أهلاً بك في تحدي إدارة البزنس 👋\n"
                    "ستدير متجراً افتراضياً وتتخذ قرارات واقعية. جاهز؟"
                ),
                "start_message_en": "Welcome to the business challenge 👋",
                "completion_message_ar": (
                    "شكراً لإكمالك التحدي 🙏\n"
                    "هل تريد تحليل مشروعك الحقيقي؟ فريقنا جاهز لمساعدتك."
                ),
                "completion_message_en": "Thanks for completing the challenge 🙏",
            }
        ).insert(ignore_permissions=True)

    existing = frappe.db.get_value(
        "Business Challenge Question",
        {"challenge": SAMPLE_CHALLENGE_CODE, "question_number": 1},
        "name",
    )
    if not existing:
        frappe.get_doc(
            {
                "doctype": "Business Challenge Question",
                "challenge": SAMPLE_CHALLENGE_CODE,
                "question_number": 1,
                "category": "Cash Flow",
                "option_format": "auto",
                "is_active": 1,
                "scenario_title_ar": "اليوم 12",
                "scenario_text_ar": (
                    "المبيعات ممتازة، لكن ظهرت مشكلة جديدة...\n"
                    "المورد الرئيسي عرض عليك خصم 10% إذا دفعت 70,000 ريال اليوم.\n"
                    "رصيد البنك لديك 95,000 ريال، والرواتب بعد أسبوع 45,000 ريال.\n"
                    "ماذا ستفعل؟"
                ),
                "scenario_title_en": "Day 12",
                "scenario_text_en": (
                    "Sales are great, but a new problem appears...\n"
                    "Your main supplier offers a 10% discount if you pay SAR 70,000 today.\n"
                    "Your bank balance is SAR 95,000, and payroll of SAR 45,000 is due in a week.\n"
                    "What will you do?"
                ),
                "options": [
                    {
                        "option_id": "opt_a",
                        "label_ar": "أقبل العرض",
                        "label_en": "Accept the offer",
                        "score": 4,
                        "cash_effect": -15,
                        "profit_effect": 8,
                        "inventory_effect": 5,
                        "collection_effect": 0,
                        "control_effect": -3,
                        "compliance_effect": 0,
                        "feedback_ar": (
                            "اخترت قبول العرض.\n"
                            "💰 السيولة -15 | 📈 الربحية +8\n"
                            "حصلت على الخصم لكن ضغطت السيولة قبل الرواتب."
                        ),
                        "feedback_en": "You took the discount but strained cash before payroll.",
                    },
                    {
                        "option_id": "opt_b",
                        "label_ar": "أرفض العرض",
                        "label_en": "Decline the offer",
                        "score": 5,
                        "cash_effect": 5,
                        "profit_effect": -3,
                        "inventory_effect": 0,
                        "collection_effect": 0,
                        "control_effect": 5,
                        "compliance_effect": 0,
                        "feedback_ar": (
                            "اخترت رفض العرض.\n"
                            "💰 السيولة +5 | 📈 الربحية -3\n"
                            "حافظت على السيولة لكنك فوّت وفراً محتملاً."
                        ),
                        "feedback_en": "You protected cash but missed a saving.",
                    },
                    {
                        "option_id": "opt_c",
                        "label_ar": "أتفاوض على دفع جزء",
                        "label_en": "Negotiate a partial payment",
                        "score": 9,
                        "cash_effect": 8,
                        "profit_effect": 4,
                        "inventory_effect": 3,
                        "collection_effect": 0,
                        "control_effect": 6,
                        "compliance_effect": 0,
                        "feedback_ar": (
                            "اخترت التفاوض مع المورد.\n"
                            "💰 السيولة +8 | 📈 الربحية +4\n"
                            "حافظت على جزء من الخصم بدون استنزاف السيولة. لكن الشهر لم ينتهِ 👀"
                        ),
                        "feedback_en": "You captured part of the discount without draining cash.",
                    },
                ],
            }
        ).insert(ignore_permissions=True)

    frappe.db.commit()
