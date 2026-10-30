"""Payroll daily / weekly / monthly views + deductions."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.extensions import db
from app.models.attendance import Employee, PayrollDeduction, PayrollRun
from app.services.payroll import create_payroll_run, monthly_payroll, payroll_for_range

bp = Blueprint("payroll", __name__)


@bp.route("/")
def index():
    view = request.args.get("view", "monthly")  # daily|weekly|monthly
    today = date.today()

    if view == "daily":
        day_str = request.args.get("date")
        day = datetime.strptime(day_str, "%Y-%m-%d").date() if day_str else today
        rows = payroll_for_range(day, day)
        period_label = day.isoformat()
        start, end = day, day
    elif view == "weekly":
        day_str = request.args.get("date")
        day = datetime.strptime(day_str, "%Y-%m-%d").date() if day_str else today
        start = day - timedelta(days=day.weekday())  # Monday
        end = start + timedelta(days=6)
        rows = payroll_for_range(start, end)
        period_label = f"{start.isoformat()} → {end.isoformat()}"
    else:
        year = int(request.args.get("year") or today.year)
        month = int(request.args.get("month") or today.month)
        rows = monthly_payroll(year, month)
        from calendar import monthrange

        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
        period_label = f"{start.strftime('%B %Y')}"

    return render_template(
        "payroll/index.html",
        view=view,
        rows=rows,
        period_label=period_label,
        start=start,
        end=end,
        today=today,
    )


@bp.route("/deductions", methods=["GET", "POST"])
def deductions():
    if request.method == "POST":
        d = PayrollDeduction(
            employee_id=int(request.form["employee_id"]),
            deduction_type=request.form["deduction_type"],
            amount=Decimal(request.form["amount"]),
            period_start=datetime.strptime(request.form["period_start"], "%Y-%m-%d").date(),
            period_end=datetime.strptime(request.form["period_end"], "%Y-%m-%d").date(),
            notes=request.form.get("notes") or None,
        )
        db.session.add(d)
        db.session.commit()
        flash("Deduction recorded.", "success")
        return redirect(url_for("payroll.deductions"))
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()
    rows = PayrollDeduction.query.order_by(PayrollDeduction.id.desc()).limit(50).all()
    return render_template("payroll/deductions.html", employees=employees, deductions=rows)


@bp.route("/run", methods=["POST"])
def run():
    period_type = request.form.get("period_type", "monthly")
    start = datetime.strptime(request.form["period_start"], "%Y-%m-%d").date()
    end = datetime.strptime(request.form["period_end"], "%Y-%m-%d").date()
    run = create_payroll_run(period_type, start, end)
    flash(f"Payroll run #{run.id} created — net ₹{run.net_total}.", "success")
    return redirect(url_for("payroll.view_run", run_id=run.id))


@bp.route("/runs/<int:run_id>")
def view_run(run_id: int):
    run = PayrollRun.query.get_or_404(run_id)
    return render_template("payroll/run.html", run=run)


@bp.route("/runs")
def list_runs():
    runs = PayrollRun.query.order_by(PayrollRun.id.desc()).limit(50).all()
    return render_template("payroll/runs.html", runs=runs)


@bp.route("/export.csv")
def export_csv():
    import csv
    from io import StringIO
    from flask import Response

    today = date.today()
    year = int(request.args.get("year", today.year))
    month = int(request.args.get("month", today.month))
    summaries = monthly_payroll(year, month)
    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(["Employee", "Role", "Hours", "Regular", "OT", "Gross", "Deductions", "Net"])
    for s in summaries:
        w.writerow([
            s.employee.name,
            s.employee.role,
            s.total_hours,
            s.total_regular_hours,
            s.total_ot_hours,
            float(s.gross_pay),
            float(s.deductions),
            float(s.net_pay),
        ])
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=payroll_{year}_{month:02d}.csv"},
    )


@bp.route("/export.pdf")
def export_pdf():
    from flask import Response
    from app.services.pdfs import generate_payroll_pdf

    today = date.today()
    year = int(request.args.get("year", today.year))
    month = int(request.args.get("month", today.month))
    summaries = monthly_payroll(year, month)
    pdf = generate_payroll_pdf(year, month, summaries)
    return Response(
        pdf,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=payroll_{year}_{month:02d}.pdf"},
    )
