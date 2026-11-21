"""
Management command: recalculate_attendance_fines
-------------------------------------------------
Recalculates late_minutes, early_checkout_minutes, total_worked_minutes,
overtime_minutes, overtime_amount, early_checkout_fine, gap_deduction, and
fine_amount for every Attendance record in the ongoing month that has NOT
been manually edited (fine_edited=False, status_edited=False).

Mirrors the same logic run by the payroll generator (PayrollViewSet.generate):

  Step 0 – Pre-pass: records with no checkout AND status not admin-edited are
            marked ABSENT and their gap_deduction / overtime fields are zeroed.
  Step 1 – For each remaining eligible record (PRESENT / LATE / HALF_DAY,
            has check-in, not admin-edited), call recalculate_attendance_record
            which re-derives all minute fields and triggers the pre_save signal
            for fine_amount / overtime_amount / early_checkout_fine.

Records are EXCLUDED from Step 1 when:
  • status_edited = True  (admin locked the status)
  • fine_edited   = True  (admin locked the fine)
  • status in ABSENT / LEAVE / HOLIDAY  (no worked time to recalculate)
  • date >= today          (today is still ongoing)
  • No time_in and no sessions (nothing to compute)

Usage:
    python manage.py recalculate_attendance_fines
    python manage.py recalculate_attendance_fines --dry-run
    python manage.py recalculate_attendance_fines --month 2026-02
    python manage.py recalculate_attendance_fines --location HYD
    python manage.py recalculate_attendance_fines --user-id 42
"""

from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand

from api.models import Attendance, AttendanceEditLog
from api.views import recalculate_attendance_record


class Command(BaseCommand):
    help = (
        "Recalculate fines, overtime, and deductions for non-edited attendance "
        "records in the current (or specified) month. Mirrors payroll generation logic."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without touching the database.",
        )
        parser.add_argument(
            "--month",
            type=str,
            default=None,
            help=(
                "Month to process in YYYY-MM format. "
                "Defaults to the current calendar month."
            ),
        )
        parser.add_argument(
            "--location",
            type=str,
            default=None,
            help="Filter by location code (e.g. HYD). Processes all locations if omitted.",
        )
        parser.add_argument(
            "--user-id",
            type=int,
            default=None,
            dest="user_id",
            help="Process only a specific employee (by user ID).",
        )

    # ------------------------------------------------------------------ #

    def handle(self, *args, **options):
        dry_run   = options["dry_run"]
        month_str = options["month"]
        location  = options["location"]
        user_id   = options["user_id"]

        today = date.today()

        # ── Resolve month ──────────────────────────────────────────────────
        if month_str:
            try:
                target_month = datetime.strptime(month_str, "%Y-%m").date().replace(day=1)
            except ValueError:
                self.stderr.write(self.style.ERROR(
                    f"Invalid --month value '{month_str}'. Use YYYY-MM format."
                ))
                return
        else:
            target_month = today.replace(day=1)

        month_end = (target_month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

        self.stdout.write(
            f"Processing month: {target_month.strftime('%B %Y')}  "
            f"(up to {min(today - timedelta(days=1), month_end)})"
            + (" [DRY RUN]" if dry_run else "")
        )

        # ── Common filters ─────────────────────────────────────────────────
        base_filter = dict(
            date__year=target_month.year,
            date__month=target_month.month,
            date__lt=today,          # exclude today (ongoing)
        )
        if location:
            base_filter["user__location__code__iexact"] = location
        if user_id:
            base_filter["user_id"] = user_id

        # ==================================================================
        # STEP 0 — Pre-pass: missing-checkout records → ABSENT,
        #          zero out gap_deduction / overtime fields.
        #          (Same as payroll generator Step 1 cleanup.)
        # ==================================================================
        missing_checkout_qs = Attendance.objects.filter(
            **base_filter,
            status__in=["PRESENT", "LATE", "HALF_DAY"],
            time_out__isnull=True,
            status_edited=False,
        )

        absent_count = missing_checkout_qs.count()

        if not dry_run and absent_count:
            # Audit log before bulk update
            for att in missing_checkout_qs.select_related("user"):
                AttendanceEditLog.objects.create(
                    attendance=att,
                    employee=att.user,
                    changed_by=None,
                    field_name="status",
                    old_value=att.status,
                    new_value="ABSENT",
                    attendance_date=att.date,
                    source="SCRIPT",
                )
            missing_checkout_qs.update(
                status="ABSENT",
                gap_deduction=0,
                overtime_minutes=0,
                overtime_amount=0,
            )
            self.stdout.write(
                f"  Pre-pass: marked {absent_count} missing-checkout record(s) as ABSENT "
                f"and zeroed their gap/overtime fields."
            )
        elif dry_run and absent_count:
            self.stdout.write(
                f"  [DRY RUN] Pre-pass would mark {absent_count} missing-checkout "
                f"record(s) as ABSENT and zero gap/overtime."
            )

        # Also zero gap/overtime for ALREADY-ABSENT records that still carry
        # non-zero values (e.g. from before this fix was deployed).
        already_absent_qs = Attendance.objects.filter(
            **base_filter,
            status="ABSENT",
            status_edited=False,
        ).filter(
            # Only touch records that actually have something to zero
            gap_deduction__gt=0,
        )
        already_absent_count = already_absent_qs.count()

        if not dry_run and already_absent_count:
            already_absent_qs.update(
                gap_deduction=0,
                overtime_minutes=0,
                overtime_amount=0,
            )
            self.stdout.write(
                f"  Pre-pass: zeroed gap/overtime on {already_absent_count} "
                f"existing ABSENT record(s) that had stale non-zero values."
            )
        elif dry_run and already_absent_count:
            self.stdout.write(
                f"  [DRY RUN] Pre-pass would zero gap/overtime on "
                f"{already_absent_count} existing ABSENT record(s)."
            )

        # ==================================================================
        # STEP 1 — Recalculate all eligible working-day records.
        #
        # Eligible = has check-in, not ABSENT/LEAVE/HOLIDAY,
        #            not admin-status-edited, not admin-fine-edited.
        # ==================================================================
        qs = (
            Attendance.objects
            .filter(
                **base_filter,
                time_in__isnull=False,            # must have checked in
                fine_edited=False,                # skip manual fine overrides
                status_edited=False,              # skip admin-pinned statuses
            )
            .exclude(status__in=["ABSENT", "LEAVE", "HOLIDAY"])
            .select_related("user", "user__shift", "shift")
            .prefetch_related("sessions")
            .order_by("date", "user__username")
        )

        total = qs.count()

        if total == 0:
            self.stdout.write(self.style.SUCCESS(
                "Step 1: No eligible working-day records to recalculate."
            ))
        else:
            self.stdout.write(f"Step 1: Found {total} eligible record(s) to recalculate.")

        TRACKED = AttendanceEditLog.TRACKED_FIELDS

        updated = 0
        skipped = 0
        errors  = 0

        for att in qs:
            # Snapshot current values before recalculation
            old_vals = {
                f: ('' if getattr(att, f) is None else str(getattr(att, f)))
                for f in TRACKED
            }

            # Skip records with no session data AND no time_out
            # (check-in only with no sessions — can't compute worked minutes)
            has_sessions = att.sessions.exists()
            if not att.time_out and not has_sessions:
                skipped += 1
                if dry_run:
                    name = att.user.get_full_name() or att.user.username
                    self.stdout.write(
                        f"  [SKIP] {name} | {att.date} — check-in only, no checkout, no sessions"
                    )
                continue

            if dry_run:
                self._dry_run_preview(att, old_vals)
                updated += 1
                continue

            try:
                # recalculate_attendance_record recalculates:
                # late_minutes, status, early_checkout_minutes,
                # total_worked_minutes, overtime_minutes, gap_deduction,
                # then calls att.save() which fires the pre_save signal to
                # recompute fine_amount, overtime_amount, early_checkout_fine.
                recalculate_attendance_record(
                    att,
                    changed_by=None,   # system — no specific user
                    old_vals=old_vals,
                )

                att.refresh_from_db()
                new_vals = {
                    f: ('' if getattr(att, f) is None else str(getattr(att, f)))
                    for f in TRACKED
                }
                changed_fields = [f for f in TRACKED if old_vals[f] != new_vals[f]]

                if changed_fields:
                    name = att.user.get_full_name() or att.user.username
                    self.stdout.write(
                        f"  ✓ {name} on {att.date} — updated: {', '.join(changed_fields)}"
                    )
                updated += 1

            except Exception as exc:
                errors += 1
                self.stderr.write(self.style.ERROR(
                    f"  ✗ ERROR for {att.user.username} on {att.date}: {exc}"
                ))

        # ── Summary ────────────────────────────────────────────────────────
        self.stdout.write("")
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"Dry run complete. "
                f"{absent_count} record(s) would be marked ABSENT, "
                f"{already_absent_count} ABSENT record(s) would have gap/OT zeroed, "
                f"{updated} record(s) would be recalculated, "
                f"{skipped} skipped (check-in only, no sessions)."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Done. "
                f"{absent_count} marked ABSENT (missing checkout), "
                f"{already_absent_count} ABSENT records cleaned up, "
                f"{updated} record(s) recalculated, "
                f"{skipped} skipped, "
                f"{errors} error(s)."
            ))

    # ------------------------------------------------------------------ #

    def _dry_run_preview(self, att, old_vals):
        """Print a short preview line without saving anything."""
        name = att.user.get_full_name() or att.user.username
        has_out = "✓" if att.time_out else "–"
        self.stdout.write(
            f"  [DRY RUN] {name} | {att.date} | "
            f"in={att.time_in} out={att.time_out} {has_out} | "
            f"late={old_vals['late_minutes']}min "
            f"fine={old_vals['fine_amount']} "
            f"OT={old_vals['overtime_amount']} "
            f"early_fine={old_vals['early_checkout_fine']} "
            f"gap={old_vals['gap_deduction']}"
        )
