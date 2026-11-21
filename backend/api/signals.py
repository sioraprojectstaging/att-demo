"""
Django signals for the Attendance Management System.

This module contains signals to automatically calculate fine and overtime amounts
based on late/overtime minutes, shift duration, and daily wage.
"""

import calendar
import logging
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from datetime import datetime, timedelta, date as _date

# Configure logger for this module
logger = logging.getLogger(__name__)


# SIO-132 takes effect from this date onward. Governs two separate things for any
# given attendance record, both keyed off the record's own date:
#   1. which late-arrival bands apply       (see resolve_late_penalty)
#   2. how many days a month is treated as having, for turning a monthly salary
#      into a daily rate                    (see days_in_month_for / get_salary_data)
# Before this date, both keep reproducing exactly what was live in production —
# a flat 30-day month — so a settled month never recomputes differently from what
# was actually paid, no matter when it is regenerated.
NEW_FINE_RULES_FROM = _date(2026, 8, 1)

LEGACY_DAYS_IN_MONTH = 30  # what every path used before the fix — kept for old records


def days_in_month_for(on_date):
    """
    Real length of on_date's calendar month (28-31), matching how payroll
    generation and the check-in preview already compute a daily rate — the two
    paths mentioned as already being "on dynamic days". Attendance fines were the
    odd one out, always dividing by a flat 30 regardless of the month; this is
    what makes them match.

    Records dated before NEW_FINE_RULES_FROM keep the flat 30 that was actually
    used when they were priced, so re-saving an old record can never change what
    it was paid.
    """
    if on_date is not None and on_date < NEW_FINE_RULES_FROM:
        return LEGACY_DAYS_IN_MONTH
    if on_date is None:
        on_date = _date.today()
    return calendar.monthrange(on_date.year, on_date.month)[1]


def effective_monthly_salary(user):
    """Base salary minus ESI and EPF — the figure every rate is derived from."""
    if not user:
        return None
    return (float(user.salary_per_month or 0)
            - float(user.esi_amount or 0)
            - float(user.epf_amount or 0))


def get_salary_data(user, attendance=None):
    """
    Daily rate used to price fines and overtime.

    When `attendance` carries a salary_snapshot, that frozen figure wins: the record
    keeps the salary that was in effect when it was created, so a later salary change
    cannot retroactively reprice history (SIO-132).

    Falls back to the user's live salary only for rows predating the snapshot field.

    The monthly-to-daily divisor comes from days_in_month_for(attendance.date): the
    real length of that record's own month from August 2026 onward, a flat 30 for
    anything before it. See days_in_month_for() for why.

    Returns daily_rate (float), or None when it cannot be computed.
    """
    on_date = attendance.date if attendance is not None else None
    divisor = days_in_month_for(on_date)

    if attendance is not None and attendance.salary_snapshot is not None:
        return float(attendance.salary_snapshot) / divisor

    effective_salary = effective_monthly_salary(user)
    if effective_salary is None:
        return None

    return effective_salary / divisor


def get_shift_data(attendance, user):
    """
    Helper to get shift duration in minutes for an attendance record.
    """
    shift = attendance.shift or (user.shift if user else None)
    
    if not shift:
        return None, None
    
    # Calculate shift duration in minutes
    attendance_date = attendance.date or datetime.now().date()
    shift_start = datetime.combine(attendance_date, shift.start_time)
    shift_end = datetime.combine(attendance_date, shift.end_time)
    
    # Handle overnight shifts
    if shift_end <= shift_start:
        shift_end += timedelta(days=1)
    
    shift_duration_mins = (shift_end - shift_start).total_seconds() / 60
    buffer_minutes = shift.buffer_minutes or 0
    
    return shift_duration_mins, buffer_minutes


# ── LATE-ARRIVAL PENALTY BANDS (SIO-132) ────────────────────────────────────
# Every boundary is derived from the employee's OWN shift — nothing here is a
# hardcoded clock value. On a standard 8-hour shift with a 10-minute grace period
# these resolve to exactly the figures written in the ticket:
#
#     grace          = shift.buffer_minutes            → 10 min
#     per-minute end = buffer x 2                      → 20 min
#     flat-fine end  = shift_duration / 4              → 120 min  ("2 hours")
#     half-day end   = shift_duration / 2              → 240 min  ("4 hours")
#
# A shift of any other length scales the same way, so a 5-hour shift is not
# penalised on an 8-hour shift's clock.
PER_MINUTE_BUFFER_MULTIPLE = 2   # per-minute band runs to N x the shift's own grace period
FLAT_FINE_DIVISOR = 4            # flat-fine band ends at shift/4, and costs a quarter day
HALF_DAY_DIVISOR = 2             # half-day escalation begins at shift/2

# Kept for backwards compatibility with older imports.
HALF_DAY_THRESHOLD = 20


def _legacy_late_penalty(late_mins, shift_duration_mins, buffer_minutes, daily_rate):
    """
    The rules as they stood before NEW_FINE_RULES_FROM. Kept verbatim (including the
    absent fine cap) so recomputing a settled month reproduces exactly what was paid.

        late <= buffer          → PRESENT,  no fine
        buffer < late <= 20     → LATE,     late x minute_rate, capped at daily_rate
        late >= shift/2         → HALF_DAY, (late - shift/2) x minute_rate
        20 < late < shift/2     → HALF_DAY, no cash fine
    """
    if late_mins <= 0 or late_mins <= buffer_minutes:
        return 'PRESENT', 0.0

    can_price = shift_duration_mins > 0 and daily_rate > 0
    minute_rate = (daily_rate / shift_duration_mins) if can_price else 0.0
    half_shift = (shift_duration_mins / 2) if shift_duration_mins > 0 else None

    if late_mins <= 20:
        if not can_price:
            return 'LATE', 0.0
        return 'LATE', round(min(late_mins * minute_rate, daily_rate), 2)

    if half_shift is not None and late_mins >= half_shift:
        if not can_price:
            return 'HALF_DAY', 0.0
        return 'HALF_DAY', round((late_mins - half_shift) * minute_rate, 2)

    return 'HALF_DAY', 0.0


def resolve_late_penalty(late_mins, shift_duration_mins, buffer_minutes=0, daily_rate=0.0, on_date=None):
    """
    Single source of truth for late-arrival penalties.

    Bands, all proportional to the employee's own shift:

        late <= buffer                  → PRESENT,  no fine
        buffer < late <= 2 x buffer     → LATE,     fine = late x minute_rate
        2 x buffer < late <= shift/4    → LATE,     fine = a quarter day's pay
        shift/4 < late < shift/2        → HALF_DAY, no cash fine
        late >= shift/2                 → HALF_DAY, fine on minutes beyond shift/2

    PRESENT and LATE both count as a full present day in payroll; HALF_DAY counts
    as 0.5. That is why the flat-fine band stays LATE and carries a cash fine
    rather than being downgraded — the employee loses exactly a quarter day.

    The flat fine is quarter_shift x minute_rate, which is identically
    daily_rate / 4, so it stays a quarter of a day's pay on any shift length.

    Returns (status, fine_amount). fine_amount is 0.0 when salary or shift data is
    missing, so callers that only need the status can ignore it.
    """
    late_mins = int(late_mins or 0)
    buffer_minutes = int(buffer_minutes or 0)
    shift_duration_mins = float(shift_duration_mins or 0)
    daily_rate = float(daily_rate or 0)

    # Attendance worked before the policy change keeps the old rules.
    if on_date is not None and on_date < NEW_FINE_RULES_FROM:
        return _legacy_late_penalty(late_mins, shift_duration_mins,
                                    buffer_minutes, daily_rate)

    can_price = shift_duration_mins > 0 and daily_rate > 0
    minute_rate = (daily_rate / shift_duration_mins) if can_price else 0.0

    # Within the grace period (or not late at all)
    if late_mins <= 0 or late_mins <= buffer_minutes:
        return 'PRESENT', 0.0

    # No shift data — we can still say they were late, but not price any band.
    if shift_duration_mins <= 0:
        return 'LATE', 0.0

    half_shift = shift_duration_mins / HALF_DAY_DIVISOR
    quarter_shift = shift_duration_mins / FLAT_FINE_DIVISOR
    # Clamp so the ladder stays ordered even if an admin sets a grace period
    # that is large relative to the shift length.
    per_minute_end = min(buffer_minutes * PER_MINUTE_BUFFER_MULTIPLE, quarter_shift)

    # Band 1: per-minute fine, still a full working day
    if late_mins <= per_minute_end:
        if not can_price:
            return 'LATE', 0.0
        return 'LATE', round(min(late_mins * minute_rate, daily_rate), 2)

    # Band 4: past half their own shift — half day plus the excess minutes.
    # Capped at half the daily rate so the half-day loss plus this fine can never
    # exceed one full day's pay (reachable when late_mins > shift_duration_mins).
    if late_mins >= half_shift:
        if not can_price:
            return 'HALF_DAY', 0.0
        excess_fine = (late_mins - half_shift) * minute_rate
        return 'HALF_DAY', round(min(excess_fine, daily_rate * 0.5), 2)

    # Band 2: flat quarter-day fine, still a full working day
    if late_mins <= quarter_shift:
        if not can_price:
            return 'LATE', 0.0
        return 'LATE', round(quarter_shift * minute_rate, 2)

    # Band 3: half day, no cash fine on top
    return 'HALF_DAY', 0.0


def compute_fine_amount(attendance, user=None, is_half_day=False):
    """
    Compute fine_amount for an attendance record.

    Thin wrapper over resolve_late_penalty() so the band logic lives in one place.

    Args:
        is_half_day: accepted for backwards compatibility and ignored -
                     resolve_late_penalty() derives the band from late_minutes.

    Returns None when shift/user data is missing, meaning "leave the stored value
    alone"; callers rely on that distinction.
    """
    user = user or attendance.user
    late_mins = attendance.late_minutes or 0

    # No late minutes means no fine
    if late_mins <= 0:
        return 0.00

    # Get shift (prefer attendance.shift, fallback to user.shift)
    shift = attendance.shift or (user.shift if user else None)

    if not shift or not user:
        return None  # Cannot compute without shift/user

    daily_rate = get_salary_data(user, attendance)
    if daily_rate is None or daily_rate <= 0:
        return 0.00

    shift_duration_mins, buffer = get_shift_data(attendance, user)
    if shift_duration_mins is None or shift_duration_mins <= 0:
        return 0.00

    _status, fine = resolve_late_penalty(
        late_mins, shift_duration_mins, buffer, daily_rate, on_date=attendance.date
    )
    return fine


def compute_overtime_amount(attendance, user=None):
    """
    Helper function to compute overtime_amount for an attendance record.
    
    Formula:
        Overtime = overtime_minutes × (daily_rate / shift_duration_minutes)
        
    Note: Overtime is typically paid at same rate as regular work (can be adjusted for 1.5x/2x if needed)
    """
    user = user or attendance.user
    overtime_mins = attendance.overtime_minutes or 0
    
    # No overtime minutes means no overtime pay
    if overtime_mins <= 0:
        return 0.00
    
    # Get shift (prefer attendance.shift, fallback to user.shift)
    shift = attendance.shift or (user.shift if user else None)
    
    if not shift or not user:
        return None  # Cannot compute without shift/user
    
    daily_rate = get_salary_data(user, attendance)
    if daily_rate is None or daily_rate <= 0:
        return 0.00
    
    shift_duration_mins, _ = get_shift_data(attendance, user)
    if shift_duration_mins is None or shift_duration_mins <= 0:
        return 0.00
    
    # Overtime per minute = daily_rate / shift_duration_mins
    minute_rate = daily_rate / shift_duration_mins
    
    # Compute overtime pay (at 1x rate - adjust multiplier if needed for 1.5x/2x)
    overtime_pay = overtime_mins * minute_rate
    
    return round(overtime_pay, 2)


def compute_early_checkout_fine(attendance, user=None):
    """
    Helper function to compute fine for early checkout.

    Formula:
        Fine = early_checkout_minutes × (daily_rate / shift_duration_minutes)
        Capped at daily_rate

    Grace period: if early_checkout_minutes ≤ shift.buffer_minutes, the employee
    left within the allowed grace window — no fine is charged (just like how
    arriving within buffer = no late fine). The minutes are still stored for
    display purposes.
    """
    user = user or attendance.user
    early_mins = attendance.early_checkout_minutes or 0

    # No early checkout means no fine
    if early_mins <= 0:
        return 0.00

    # Get shift (prefer attendance.shift, fallback to user.shift)
    shift = attendance.shift or (user.shift if user else None)

    if not shift or not user:
        return None  # Cannot compute without shift/user

    # Grace period check — same logic as late check-in buffer
    buffer = shift.buffer_minutes or 0
    if early_mins <= buffer:
        return 0.00  # Within checkout grace period — show minutes, no fine

    daily_rate = get_salary_data(user, attendance)
    if daily_rate is None or daily_rate <= 0:
        return 0.00

    shift_duration_mins, _ = get_shift_data(attendance, user)
    if shift_duration_mins is None or shift_duration_mins <= 0:
        return 0.00

    # Fine per minute = daily_rate / shift_duration_mins
    minute_rate = daily_rate / shift_duration_mins

    # Fine for minutes BEYOND the buffer
    computed_fine = early_mins * minute_rate

    # Cap fine at daily salary (logical limit - can't fine more than a day's wage)
    if computed_fine > daily_rate:
        computed_fine = daily_rate

    return round(computed_fine, 2)


@receiver(pre_save, sender='api.Attendance')
def calculate_attendance_amounts(sender, instance, **kwargs):
    """
    Pre-save signal to calculate fine_amount, overtime_amount, early_checkout_fine,
    and auto-set the status for Attendance records.

    Late bands (applied when fine_edited is False) — see resolve_late_penalty().
    All boundaries scale with the employee's own shift; nothing is hardcoded.
    """
    late_mins = instance.late_minutes or 0

    # Freeze the salary basis the first time this record is saved. Never overwritten,
    # so a later salary change cannot reprice history (SIO-132).
    if instance.salary_snapshot is None and instance.user:
        effective = effective_monthly_salary(instance.user)
        if effective is not None:
            instance.salary_snapshot = round(effective, 2)
            instance.esi_snapshot = round(float(instance.user.esi_amount or 0), 2)
            instance.epf_snapshot = round(float(instance.user.epf_amount or 0), 2)

    # Guard: only auto-set status/fine if the admin has not manually locked them.
    if not instance.fine_edited:
        shift_duration_mins, buffer = get_shift_data(instance, instance.user)
        daily_rate = get_salary_data(instance.user, instance) if instance.user else 0.0

        resolved_status, resolved_fine = resolve_late_penalty(
            late_mins, shift_duration_mins, buffer, daily_rate, on_date=instance.date
        )

        # Only overwrite the fine when the record has enough data to price it.
        # Mirrors compute_fine_amount()'s None contract ("leave the stored value alone").
        shift = instance.shift or (instance.user.shift if instance.user else None)
        if late_mins <= 0 or (shift and instance.user):
            instance.fine_amount = resolved_fine

        # ABSENT / LEAVE / HOLIDAY are terminal — a late-arrival band must never
        # overwrite them. status_edited means the admin pinned the status by hand.
        if not instance.status_edited and instance.status not in ['ABSENT', 'LEAVE', 'HOLIDAY']:
            instance.status = resolved_status

    # Compute overtime — skip if admin has manually locked the value (overtime_edited).
    if not getattr(instance, 'overtime_edited', False):
        computed_overtime = compute_overtime_amount(instance)
        if computed_overtime is not None:
            instance.overtime_amount = computed_overtime

    # Compute early checkout fine — skip if admin has manually locked it.
    if not getattr(instance, 'early_checkout_fine_edited', False):
        computed_early_fine = compute_early_checkout_fine(instance)
        if computed_early_fine is not None:
            instance.early_checkout_fine = computed_early_fine


@receiver(post_save, sender='api.User')
def recalculate_amounts_on_salary_change(sender, instance, created, **kwargs):
    """
    Post_save on User: apply a salary change to the CURRENT month onward.

    This is the original behaviour, with one change (SIO-132): the sweep used to run
    over every attendance record the employee had ever had, with no date filter, so a
    raise silently repriced closed months that had already been paid. It is now bounded
    to the current month and later.

    Months before the current one keep the salary that was in effect then, held on each
    record's salary_snapshot. The current month is re-stamped so a raise applies to the
    whole of it, exactly as before.
    """
    if created:
        return

    from api.models import Attendance
    from datetime import date as _d

    effective = effective_monthly_salary(instance)
    if effective is None:
        return
    effective = round(effective, 2)
    esi = round(float(instance.esi_amount or 0), 2)
    epf = round(float(instance.epf_amount or 0), 2)

    current_month_start = _d.today().replace(day=1)
    stale = Attendance.objects.filter(
        user=instance, date__gte=current_month_start
    ).exclude(salary_snapshot=effective)

    if not stale.exists():
        return  # nothing to do (this fires on every User.save(), not just salary edits)

    pks = list(stale.values_list('pk', flat=True))
    Attendance.objects.filter(pk__in=pks).update(
        salary_snapshot=effective, esi_snapshot=esi, epf_snapshot=epf
    )
    # Re-save so the pre_save signal recomputes fine / overtime / early-checkout
    # from the newly stamped salary.
    for att in Attendance.objects.filter(pk__in=pks).select_related('user', 'shift', 'user__shift'):
        att.save()

    logger.info(
        f"Salary change for {instance.username}: re-priced {len(pks)} attendance "
        f"records from {current_month_start} onward. Earlier months left untouched."
    )


@receiver(post_save, sender='api.Shift')
def recalculate_on_shift_change(sender, instance, created, **kwargs):
    """
    Post-save signal for Shift model.

    When a shift's start_time, end_time, or buffer_minutes changes,
    recalculate late_minutes, early_checkout_minutes, overtime_minutes,
    and all derived fines for every attendance record using this shift.
    """
    if created:
        return  # New shift — no attendance records exist yet

    from api.models import Attendance

    # Find all attendance records that reference this shift
    # (either directly on the attendance or via the user's current shift)
    attendances = Attendance.objects.filter(
        shift=instance,
        time_in__isnull=False,
    ).select_related('user')

    recalc_count = 0
    for att in attendances:
        user = att.user
        shift = instance  # The updated shift

        # --- Recalculate LATE MINUTES from time_in vs new shift start ---
        old_late = att.late_minutes or 0
        shift_start_dt = datetime.combine(att.date, shift.start_time)
        checkin_dt = datetime.combine(att.date, att.time_in)
        buffer = shift.buffer_minutes or 0

        if checkin_dt > shift_start_dt:
            raw_late = int((checkin_dt - shift_start_dt).total_seconds() / 60)
            new_late = raw_late  # Always store actual late minutes for display
            new_early_checkin = 0
        elif checkin_dt < shift_start_dt:
            new_late = 0
            new_early_checkin = int((shift_start_dt - checkin_dt).total_seconds() / 60)
        else:
            new_late = 0
            new_early_checkin = 0

        att.late_minutes = new_late
        att.early_checkin_minutes = new_early_checkin

        # --- Update status based on new late_minutes and buffer ---
        shift_start_dt2 = datetime.combine(att.date, shift.start_time)
        shift_end_dt2 = datetime.combine(att.date, shift.end_time)
        if shift_end_dt2 <= shift_start_dt2:
            shift_end_dt2 += timedelta(days=1)
        shift_dur_for_status = int((shift_end_dt2 - shift_start_dt2).total_seconds() / 60)

        att.status, _ = resolve_late_penalty(new_late, shift_dur_for_status, buffer,
                                            on_date=att.date)

        # --- Recalculate total_worked_minutes from sessions ---
        from api.models import AttendanceSession
        sessions = att.sessions.all()
        total_worked = sum(s.duration_minutes for s in sessions) if sessions.exists() else 0
        if not sessions.exists() and att.time_in and att.time_out:
            tin = datetime.combine(att.date, att.time_in)
            tout = datetime.combine(att.date, att.time_out)
            total_worked = max(0, int((tout - tin).total_seconds() / 60))
        att.total_worked_minutes = total_worked

        # --- Shift duration ---
        shift_end_dt = datetime.combine(att.date, shift.end_time)
        if shift_end_dt <= shift_start_dt:
            shift_end_dt += timedelta(days=1)
        shift_duration_mins = int((shift_end_dt - shift_start_dt).total_seconds() / 60)

        # --- Early checkout detection (for fine) ---
        att.early_checkout_minutes = 0
        if att.time_out:
            checkout_dt = datetime.combine(att.date, att.time_out)
            shift_end_minus_buffer = shift_end_dt - timedelta(minutes=buffer)
            if checkout_dt < shift_end_minus_buffer:
                att.early_checkout_minutes = int((shift_end_dt - checkout_dt).total_seconds() / 60)

        # --- Effective shift = benchmark for OT & gap ---
        effective_shift = max(0, shift_duration_mins - new_late - att.early_checkout_minutes)

        daily_rate = get_salary_data(att.user, att)
        if daily_rate and shift_duration_mins > 0:
            minute_rate = daily_rate / shift_duration_mins
        else:
            minute_rate = 0

        # OT = total_worked - effective_shift
        if total_worked > effective_shift:
            att.overtime_minutes = total_worked - effective_shift
        else:
            att.overtime_minutes = 0

        # Gap = effective_shift - total_worked.
        # Only charge if gap exceeds shift buffer (10-min client relief).
        if total_worked < effective_shift:
            gap_minutes = effective_shift - total_worked
            if gap_minutes > buffer:
                att.gap_deduction = round(gap_minutes * minute_rate, 2) if minute_rate else 0
            else:
                att.gap_deduction = 0
        else:
            att.gap_deduction = 0

        # Save triggers pre_save signal → recalculates fine_amount, overtime_amount, early_checkout_fine
        att.save()
        recalc_count += 1

    if recalc_count > 0:
        logger.info(f"Shift '{instance.name}' changed → recalculated {recalc_count} attendance records.")
