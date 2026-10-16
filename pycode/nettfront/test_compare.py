"""Regression tests for invoice fronts without a handedness label."""

import unittest

from nettfront.engine import FIELDNAMES, compare_invoice_rows, compare_rows


def order(code, qty=5, price=10, net=None):
    return [None, None, None, code, None, qty, None, None, price, qty * price if net is None else net]


def invoice(code="NFA_ZI_BGAS_718x297", qty=5, price=10, net=None):
    return dict(kod=code, db=str(qty), egyseg_ar=str(price),
                netto_ar=str(qty * price if net is None else net), termek="ZILLE/P", meret="718x297")


class HandedComparisonTests(unittest.TestCase):
    def reports(self, orders, invoices):
        rows = [["header"] * 10, *orders]
        return (compare_rows(rows, invoices, FIELDNAMES),
                compare_invoice_rows(rows, invoices, FIELDNAMES))

    def test_reversed_quantities_match_both_directions(self):
        orders = [order("NFAIF_ZI_BGAS_718x297_B_KA_NO_U", 4),
                  order("NFAIF_ZI_BGAS_718x297_J_KA_NO_U", 6)]
        forward, reverse = self.reports(orders, [invoice(qty=6), invoice(qty=4)])
        self.assertEqual(forward[1], [True, True, True])
        self.assertEqual(reverse[1], [True, True, True])
        self.assertEqual(forward[0][1][-3], "NFAIF_ZI_BGAS_718x297_B")

    def test_plain_order_has_priority_and_invoice_is_used_once(self):
        orders = [order("NFAIF_ZI_BGAS_718x297_B"), order("NFA_ZI_BGAS_718x297_KA_NO_U")]
        forward, reverse = self.reports(orders, [invoice()])
        self.assertEqual(forward[1], [True, False, True])
        self.assertEqual(reverse[1], [True, True])

    def test_equal_handed_rows_need_two_invoice_rows(self):
        orders = [order("NFAIF_ZI_BGAS_718x297_B"), order("NFAIF_ZI_BGAS_718x297_J")]
        self.assertEqual(self.reports(orders, [invoice(), invoice()])[0][1], [True, True, True])
        self.assertEqual(self.reports(orders, [invoice()])[0][1], [True, True, False])

    def test_fallback_requires_all_values_and_same_model_color_size(self):
        for changed in [dict(db="4"), dict(egyseg_ar="11"), dict(netto_ar="51"),
                        dict(db=""), dict(kod="NFA_LU_BGAS_718x297"),
                        dict(kod="NFA_ZI_WTF_718x297"), dict(kod="NFA_ZI_BGAS_718x397"),
                        dict(termek="ZILLE/P jobbos")]:
            with self.subTest(changed=changed):
                forward, reverse = self.reports([order("NFAIF_ZI_BGAS_718x297_B")], [{**invoice(), **changed}])
                self.assertEqual(forward[1], [True, False])
                self.assertEqual(reverse[1], [True, False])

    def test_explicit_opposite_side_does_not_match(self):
        forward, _ = self.reports([order("NFAIF_ZI_BGAS_718x297_B")],
                                  [invoice(code="NFAIF_ZI_BGAS_718x297_J")])
        self.assertEqual(forward[1], [True, False])

    def test_exact_code_still_reports_numeric_mismatch(self):
        forward, reverse = self.reports([order("NFA_ZI_BGAS_718x297", qty=4)], [invoice()])
        self.assertEqual(forward[0][1][-1], "db, netto_ar")
        self.assertEqual(reverse[0][1][-1], "db, netto_ar")

    def test_color_normalization_is_preserved(self):
        forward, _ = self.reports([order("NFAIF_ZI_PRA_718x297_B")],
                                  [invoice(code="NFA_ZI_PRAS_718x297")])
        self.assertEqual(forward[1], [True, True])


if __name__ == "__main__":
    unittest.main()
