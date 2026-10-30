"""Employee, shifts, attendance, payroll runs, deductions."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from app.extensions import db


class Employee(db.Model):
    __tablename__ = "employees"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(80), nullable=False, default="Sales Associate")
    phone = db.Column(db.String(20), nullable=True)
    shift = db.Column(db.String(40), nullable=False, default="Day")  # Day / Evening
    shift_start = db.Column(db.Time, nullable=True)  # e.g. 10:00
    shift_end = db.Column(db.Time, nullable=True)    # e.g. 19:00
    rate_type = db.Column(db.String(20), nullable=False, default="daily")  # hourly | daily
    rate_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    # Optional statutory deductions % of gross
    pf_percent = db.Column(db.Numeric(5, 2), nullable=True, default=0)
    esi_percent = db.Column(db.Numeric(5, 2), nullable=True, default=0)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    attendance = db.relationship("Attendance", back_populates="employee", lazy="dynamic")
    deductions = db.relationship("PayrollDeduction", back_populates="employee", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Employee {self.name}>"


class Attendance(db.Model):
    __tablename__ = "attendance"
    __table_args__ = (
        db.UniqueConstraint("employee_id", "work_date", name="uq_attendance_emp_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    work_date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    check_in = db.Column(db.Time, nullable=True)
    check_out = db.Column(db.Time, nullable=True)
    # present | absent | half | leave
    status = db.Column(db.String(20), nullable=False, default="present")
    late_minutes = db.Column(db.Integer, nullable=False, default=0)
    notes = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship("Employee", back_populates="attendance")

    @property
    def hours_worked(self) -> float:
        if self.status == "absent":
            return 0.0
        if not self.check_in or not self.check_out:
            return 0.0
        start = datetime.combine(self.work_date, self.check_in)
        end = datetime.combine(self.work_date, self.check_out)
        if end < start:
            end += timedelta(days=1)
        return round((end - start).total_seconds() / 3600.0, 2)

    def __repr__(self) -> str:
        return f"<Attendance emp={self.employee_id} {self.work_date}>"


class PayrollDeduction(db.Model):
    """Manual or auto deductions: absence, late, advances, PF, ESI, other."""
    __tablename__ = "payroll_deductions"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    # absence | late | advance | pf | esi | other
    deduction_type = db.Column(db.String(40), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    notes = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship("Employee", back_populates="deductions")


class PayrollRun(db.Model):
    """Snapshot of a payroll calculation for a period (daily/weekly/monthly)."""
    __tablename__ = "payroll_runs"

    id = db.Column(db.Integer, primary_key=True)
    # daily | weekly | monthly
    period_type = db.Column(db.String(20), nullable=False, default="monthly")
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    # draft | finalized | paid
    status = db.Column(db.String(20), nullable=False, default="draft")
    gross_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    deductions_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    net_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    finalized_at = db.Column(db.DateTime, nullable=True)

    lines = db.relationship(
        "PayrollRunLine",
        back_populates="payroll_run",
        cascade="all, delete-orphan",
        lazy="joined",
    )


class PayrollRunLine(db.Model):
    __tablename__ = "payroll_run_lines"

    id = db.Column(db.Integer, primary_key=True)
    payroll_run_id = db.Column(db.Integer, db.ForeignKey("payroll_runs.id"), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    days_worked = db.Column(db.Numeric(8, 2), nullable=False, default=0)
    regular_hours = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    ot_hours = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    gross_pay = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    deductions = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    net_pay = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    payroll_run = db.relationship("PayrollRun", back_populates="lines")
    employee = db.relationship("Employee")
