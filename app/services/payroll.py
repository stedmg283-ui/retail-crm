"""Attendance hours and payroll calculations with deductions."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Iterable

from flask import current_app

from app.extensions import db
from app.models.attendance import (
    Attendance,
    Employee,
    PayrollDeduction,
    PayrollRun,
    PayrollRunLine,
)


@dataclass
class DayPay:
    work_date: date
    hours: float
    regular_hours: float
    ot_hours: float
    regular_pay: Decimal
    ot_pay: Decimal
    total_pay: Decimal
    late_minutes: int = 0
    status: str = "present"


@dataclass
class EmployeePayroll:
    employee: Employee
    days: list[DayPay]
    total_hours: float
    total_regular_hours: float
    total_ot_hours: float
    gross_pay: Decimal
    deductions: Decimal
    net_pay: Decimal
    deduction_details: list = field(default_factory=list)

    # Back-compat alias used by older callers/tests
    @property
    def total_pay(self) -> Decimal:
        return self.net_pay


def compute_day_pay(
    employee: Employee,
    hours: float,
    *,
    shift_hours: float | None = None,
    ot_multiplier: float | None = None,
) -> tuple[float, float, Decimal, Decimal, Decimal]:
    """Return (regular_h, ot_h, regular_pay, ot_pay, total)."""
    try:
        default_shift = float(current_app.config["DEFAULT_SHIFT_HOURS"])
        default_mult = float(current_app.config["OT_MULTIPLIER"])
    except RuntimeError:
        default_shift, default_mult = 9.0, 1.5
    shift = shift_hours if shift_hours is not None else default_shift
    mult = ot_multiplier if ot_multiplier is not None else default_mult
    hours = max(0.0, float(hours))
    regular_h = min(hours, shift)
    ot_h = max(0.0, hours - shift)
    rate = Decimal(str(employee.rate_amount))

    if employee.rate_type == "hourly":
        regular_pay = (Decimal(str(regular_h)) * rate).quantize(Decimal("0.01"))
        ot_pay = (Decimal(str(ot_h)) * rate * Decimal(str(mult))).quantize(Decimal("0.01"))
    else:
        if hours <= 0:
            regular_pay = Decimal("0")
        else:
            if hours < shift:
                regular_pay = (rate * Decimal(str(hours / shift))).quantize(Decimal("0.01"))
            else:
                regular_pay = rate
        hourly_equiv = rate / Decimal(str(shift)) if shift else Decimal("0")
        ot_pay = (Decimal(str(ot_h)) * hourly_equiv * Decimal(str(mult))).quantize(Decimal("0.01"))

    return regular_h, ot_h, regular_pay, ot_pay, regular_pay + ot_pay


def deductions_for_period(
    employee: Employee,
    start: date,
    end: date,
    gross: Decimal,
) -> tuple[Decimal, list]:
    """Sum PayrollDeduction rows + optional PF/ESI % of gross."""
    details = []
    total = Decimal("0")
    rows = (
        PayrollDeduction.query.filter(
            PayrollDeduction.employee_id == employee.id,
            PayrollDeduction.period_start <= end,
            PayrollDeduction.period_end >= start,
        ).all()
    )
    for r in rows:
        amt = Decimal(str(r.amount))
        total += amt
        details.append({"type": r.deduction_type, "amount": amt, "notes": r.notes})

    pf = Decimal(str(employee.pf_percent or 0))
    if pf > 0 and gross > 0:
        amt = (gross * pf / Decimal("100")).quantize(Decimal("0.01"))
        total += amt
        details.append({"type": "pf", "amount": amt, "notes": f"{pf}%"})

    esi = Decimal(str(employee.esi_percent or 0))
    if esi > 0 and gross > 0:
        amt = (gross * esi / Decimal("100")).quantize(Decimal("0.01"))
        total += amt
        details.append({"type": "esi", "amount": amt, "notes": f"{esi}%"})

    return total, details


def payroll_for_employee(
    employee: Employee,
    records: Iterable[Attendance],
    *,
    shift_hours: float | None = None,
    ot_multiplier: float | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> EmployeePayroll:
    days: list[DayPay] = []
    th = tr = to = 0.0
    gross = Decimal("0")
    dates = []
    for att in records:
        h = att.hours_worked
        rh, oh, rp, op, tot = compute_day_pay(
            employee, h, shift_hours=shift_hours, ot_multiplier=ot_multiplier
        )
        days.append(
            DayPay(
                work_date=att.work_date,
                hours=h,
                regular_hours=rh,
                ot_hours=oh,
                regular_pay=rp,
                ot_pay=op,
                total_pay=tot,
                late_minutes=att.late_minutes or 0,
                status=att.status or "present",
            )
        )
        th += h
        tr += rh
        to += oh
        gross += tot
        dates.append(att.work_date)

    start = period_start or (min(dates) if dates else date.today())
    end = period_end or (max(dates) if dates else date.today())
    ded, details = deductions_for_period(employee, start, end, gross)
    net = gross - ded
    if net < 0:
        net = Decimal("0")

    return EmployeePayroll(
        employee=employee,
        days=days,
        total_hours=round(th, 2),
        total_regular_hours=round(tr, 2),
        total_ot_hours=round(to, 2),
        gross_pay=gross,
        deductions=ded,
        net_pay=net,
        deduction_details=details,
    )


def monthly_payroll(
    year: int,
    month: int,
    *,
    shift_hours: float | None = None,
    ot_multiplier: float | None = None,
) -> list[EmployeePayroll]:
    from calendar import monthrange

    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    return payroll_for_range(start, end, shift_hours=shift_hours, ot_multiplier=ot_multiplier)


def payroll_for_range(
    start: date,
    end: date,
    *,
    shift_hours: float | None = None,
    ot_multiplier: float | None = None,
) -> list[EmployeePayroll]:
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()
    result = []
    for emp in employees:
        recs = (
            Attendance.query.filter(
                Attendance.employee_id == emp.id,
                Attendance.work_date >= start,
                Attendance.work_date <= end,
            )
            .order_by(Attendance.work_date)
            .all()
        )
        result.append(
            payroll_for_employee(
                emp,
                recs,
                shift_hours=shift_hours,
                ot_multiplier=ot_multiplier,
                period_start=start,
                period_end=end,
            )
        )
    return result


def create_payroll_run(
    period_type: str,
    start: date,
    end: date,
) -> PayrollRun:
    rows = payroll_for_range(start, end)
    run = PayrollRun(
        period_type=period_type,
        period_start=start,
        period_end=end,
        status="draft",
    )
    gross_t = ded_t = net_t = Decimal("0")
    for ep in rows:
        line = PayrollRunLine(
            employee_id=ep.employee.id,
            days_worked=len([d for d in ep.days if d.hours > 0 or d.status == "present"]),
            regular_hours=Decimal(str(ep.total_regular_hours)),
            ot_hours=Decimal(str(ep.total_ot_hours)),
            gross_pay=ep.gross_pay,
            deductions=ep.deductions,
            net_pay=ep.net_pay,
        )
        run.lines.append(line)
        gross_t += ep.gross_pay
        ded_t += ep.deductions
        net_t += ep.net_pay
    run.gross_total = gross_t
    run.deductions_total = ded_t
    run.net_total = net_t
    db.session.add(run)
    db.session.commit()
    return run
