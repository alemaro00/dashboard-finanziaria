import copy
import unittest

from bank_allocations import cents, validate_bank_allocations


class BankAllocationTests(unittest.TestCase):
    def setUp(self):
        self.record = {"id": "test-bank", "amount": 1000, "currency": "EUR", "recordType": "expense",
                       "date": "2026-10-01", "description": "Originale fixture"}
        self.state = {"monthName": "Ottobre", "year": 2026, "notes": [
            {"id": identifier, "bankTransactionId": "test-bank", "bankOriginalAmount": 1000,
             "bankSplitVersion": 1, "bankRecordType": "expense", "transactionDate": "2026-10-01",
             "originalBankDescription": "Originale fixture", "label": label, "category": category, "amount": amount}
            for identifier, label, category, amount in [("a", "Affitto", "Costo Fisso", 200), ("b", "Spesa", "Costo Variabile", 800)]]}

    def validate(self):
        validate_bank_allocations(self.state, [self.record])

    def test_valid_split_partial_and_removal(self):
        self.validate()
        self.state["notes"].pop()
        self.validate()
        self.state["notes"].clear()
        self.validate()

    def test_excess_is_rejected_without_mutation(self):
        self.state["notes"][0]["amount"] = 210
        original = copy.deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "superano"):
            self.validate()
        self.assertEqual(self.state, original)

    def test_cents_do_not_use_float_tolerance(self):
        self.assertEqual(cents(0.1), 10)
        self.assertEqual(cents("0.20"), 20)
        for invalid in [0, -1, 0.001, True, None, "bad", float("nan"), float("inf"), 1000000000]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                cents(invalid)

    def test_original_amount_cannot_be_inflated_against_archive(self):
        for note in self.state["notes"]:
            note["bankOriginalAmount"] = 1200
        with self.assertRaisesRegex(ValueError, "originale diverso"):
            self.validate()

    def test_duplicate_id_bad_name_direction_date_or_reference_rejected(self):
        for field, value in [("id", "b"), ("label", ""), ("category", "Stipendio"),
                             ("transactionDate", "2026-09-01"), ("originalBankDescription", "Alterato"),
                             ("bankOriginalAmount", 1100), ("bankRecordType", "income")]:
            state = copy.deepcopy(self.state)
            state["notes"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_bank_allocations(state, [self.record])

    def test_income_splits_allow_emoluments_and_extra(self):
        self.record["recordType"] = "income"
        for note, category in zip(self.state["notes"], ["Stipendio", "Entrate aggiuntive"]):
            note.update(bankRecordType="income", category=category)
        self.validate()
        for note in self.state["notes"]:
            note["category"] = "Entrate aggiuntive"
        self.validate()

    def test_current_draft_and_saved_month_are_validated_independently(self):
        self.state["monthlyHistory"] = [copy.deepcopy(self.state)]
        self.state["monthDrafts"] = {"2026-ottobre": {"notes": copy.deepcopy(self.state["notes"])}}
        self.validate()
        self.state["monthDrafts"]["2026-ottobre"]["notes"][0]["amount"] = 210
        with self.assertRaises(ValueError):
            self.validate()

    def test_portable_backup_keeps_split_without_bank_session(self):
        validate_bank_allocations(self.state)
        self.state["notes"][0]["amount"] = 210
        with self.assertRaises(ValueError):
            validate_bank_allocations(self.state)

    def test_legacy_notes_remain_compatible(self):
        validate_bank_allocations({"notes": [{"bankTransactionId": "legacy", "amount": 1}]})


if __name__ == "__main__":
    unittest.main()
