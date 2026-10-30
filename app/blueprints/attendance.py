"""Daily employee attendance registration."""
from __future__ import annotations

from datetime import date, datetime, time

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.extensions import db
from app.models.attendance import Attendance, Employee

bp = Blueprint("attendance", __name__)


def _parse_time(s: str | None) -> time | None:
    if not s:
        return None
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(s.strip(), fmt).time()
        except ValueError:
            continue
    return None


@bp.route("/")
def index():
    day_str = request.args.get("date")
    day = date.today()
    if day_str:
        try:
            day = datetime.strptime(day_str, "%Y-%m-%d").date()
        except ValueError:
            pass
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()
    records = {
        a.employee_id: a
        for a in Attendance.query.filter_by(work_date=day).all()
    }
    return render_template(
        "attendance/index.html",
        day=day,
        employees=employees,
        records=records,
    )


@bp.route("/check", methods=["POST"])
def check():
    emp_id = int(request.form["employee_id"])
    day = datetime.strptime(request.form.get("work_date") or str(date.today()), "%Y-%m-%d").date()
    check_in = _parse_time(request.form.get("check_in"))
    check_out = _parse_time(request.form.get("check_out"))
    status = request.form.get("status") or "present"
    notes = request.form.get("notes") or None
    late = int(request.form.get("late_minutes") or 0)

    att = Attendance.query.filter_by(employee_id=emp_id, work_date=day).first()
    if not att:
        att = Attendance(employee_id=emp_id, work_date=day)
        db.session.add(att)
    att.check_in = check_in
    att.check_out = check_out
    att.status = status
    att.notes = notes
    att.late_minutes = late

    # Auto late minutes vs employee shift_start
    emp = Employee.query.get(emp_id)
    if emp and emp.shift_start and check_in and late == 0:
        start_dt = datetime.combine(day, emp.shift_start)
        in_dt = datetime.combine(day, check_in)
        if in_dt > start_dt:
            att.late_minutes = int((in_dt - start_dt).total_seconds() // 60)

    db.session.commit()
    flash(f"Attendance saved for {emp.name if emp else emp_id} on {day}.", "success")
    return redirect(url_for("attendance.index", date=day.isoformat()))


@bp.route("/employees", methods=["GET", "POST"])
def employees():
    if request.method == "POST":
        emp = Employee(
            name=request.form["name"].strip(),
            role=request.form.get("role") or "Sales Associate",
            phone=request.form.get("phone") or None,
            shift=request.form.get("shift") or "Day",
            shift_start=_parse_time(request.form.get("shift_start")),
            shift_end=_parse_time(request.form.get("shift_end")),
            rate_type=request.form.get("rate_type") or "daily",
            rate_amount=request.form.get("rate_amount") or 0,
            pf_percent=request.form.get("pf_percent") or 0,
            esi_percent=request.form.get("esi_percent") or 0,
        )
        db.session.add(emp)
        db.session.commit()
        flash(f"Employee {emp.name} added.", "success")
        return redirect(url_for("attendance.employees"))
    emps = Employee.query.order_by(Employee.name).all()
    return render_template("attendance/employees.html", employees=emps)
