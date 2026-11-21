"""
Management command: backfill_attendance_sessions
------------------------------------------------
Creates an AttendanceSession (session_number=1) for every Attendance record
that satisfies ALL of the following:
  1. Has a time_in value (employee actually checked in)
  2. Has zero existing AttendanceSession rows

This is a safe, idempotent back-fill – running it multiple times will not
create duplicate sessions because of the `has_sessions` filter.

Usage:
    python manage.py backfill_attendance_sessions
    python manage.py backfill_attendance_sessions --dry-run
    python manage.py backfill_attendance_sessions --start-date 2025-01-01
    python manage.py backfill_attendance_sessions --end-date   2025-12-31
"""

from django.core.management.base import BaseCommand
from django.db.models import Count
from api.models import Attendance, AttendanceSession


class Command(BaseCommand):
    help = (
        "Back-fill AttendanceSession records for Attendance rows that have "
        "time_in set but no associated sessions."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be created without touching the database.",
        )
        parser.add_argument(
            "--start-date",
            type=str,
            default=None,
            help="Only process attendance records on or after this date (YYYY-MM-DD).",
        )
        parser.add_argument(
            "--end-date",
            type=str,
            default=None,
            help="Only process attendance records on or before this date (YYYY-MM-DD).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        start_date = options["start_date"]
        end_date = options["end_date"]

        # ------------------------------------------------------------------ #
        # Build queryset: Attendance with time_in but no sessions             #
        # ------------------------------------------------------------------ #
        qs = (
            Attendance.objects
            .filter(time_in__isnull=False)          # must have checked in
            .annotate(session_count=Count("sessions"))
            .filter(session_count=0)                # no sessions yet
            .select_related("user")
            .order_by("date", "user__username")
        )

        if start_date:
            qs = qs.filter(date__gte=start_date)
        if end_date:
            qs = qs.filter(date__lte=end_date)

        total = qs.count()

        if total == 0:
            self.stdout.write(self.style.SUCCESS(
                "Nothing to do — no Attendance records without sessions found."
            ))
            return

        self.stdout.write(
            f"Found {total} Attendance record(s) missing a session."
            + (" (DRY RUN – no changes will be saved)" if dry_run else "")
        )

        # ------------------------------------------------------------------ #
        # Create sessions                                                      #
        # ------------------------------------------------------------------ #
        sessions_to_create = []

        for attendance in qs.iterator():
            # Duration: only calculable when time_out is available
            duration = 0
            if attendance.time_out:
                from datetime import datetime, date as date_type
                dummy_date = date_type.today()
                t_in  = datetime.combine(dummy_date, attendance.time_in)
                t_out = datetime.combine(dummy_date, attendance.time_out)
                diff  = t_out - t_in
                # Handle overnight shifts gracefully
                if diff.total_seconds() < 0:
                    from datetime import timedelta
                    diff += timedelta(days=1)
                duration = max(0, int(diff.total_seconds() // 60))

            session = AttendanceSession(
                attendance=attendance,
                session_number=1,
                time_in=attendance.time_in,
                time_out=attendance.time_out,      # may be None — that's fine
                duration_minutes=duration,
                check_in_mode=attendance.check_in_mode,
            )

            if dry_run:
                self.stdout.write(
                    f"  [DRY RUN] Would create Session 1 for "
                    f"{attendance.user.username} on {attendance.date} "
                    f"(in={attendance.time_in}, out={attendance.time_out}, "
                    f"duration={duration} min)"
                )
            else:
                sessions_to_create.append(session)

        if not dry_run:
            created = AttendanceSession.objects.bulk_create(sessions_to_create)
            self.stdout.write(self.style.SUCCESS(
                f"Successfully created {len(created)} AttendanceSession record(s)."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"Dry run complete. {total} session(s) would have been created."
            ))
