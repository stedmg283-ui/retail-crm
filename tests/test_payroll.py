"""Payroll OT math tests."""
from decimal import Decimal

from app.models.attendance import Employee
from app.services.payroll import compute_day_pay


def test_hourly_ot_beyond_9_hours(app):
    emp = Employee(name="A", role="S", shift="Day", rate_type="hourly", rate_amount=100)
    rh, oh, rp, op, tot = compute_day_pay(emp, 11, shift_hours=9, ot_multiplier=1.5)
    assert rh == 9
    assert oh == 2
    assert rp == Decimal("900.00")
    assert op == Decimal("300.00")
    assert tot == Decimal("1200.00")


def test_daily_rate_full_day_plus_ot(app):
    emp = Employee(name="B", role="S", shift="Day", rate_type="daily", rate_amount=900)
    rh, oh, rp, op, tot = compute_day_pay(emp, 11, shift_hours=9, ot_multiplier=1.5)
    assert rh == 9
    assert oh == 2
    assert rp == Decimal("900")
    assert op == Decimal("300.00")
    assert tot == Decimal("1200.00")


def test_daily_prorate_under_shift(app):
    emp = Employee(name="C", role="S", shift="Day", rate_type="daily", rate_amount=900)
    rh, oh, rp, op, tot = compute_day_pay(emp, 4.5, shift_hours=9, ot_multiplier=1.5)
    assert rh == 4.5
    assert oh == 0
    assert rp == Decimal("450.00")
    assert op == Decimal("0.00")
