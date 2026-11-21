"""
SIO-132: freeze the salary basis on each Attendance record.

Fines and overtime used to be priced from the employee's *live* salary, and a
post_save signal swept every historical record whenever that salary changed. A
raise silently repriced payroll months that had already been closed, while
Payroll.base_salary stayed frozen at the old figure — so the two halves of the
same payroll row no longer reconciled.

Each record now carries the salary it was priced at.

Backfill note: existing rows are stamped with the employee's CURRENT effective
salary. That is not a guess about the past — it is the figure those rows are
already priced at today, because the old sweep kept rewriting them to match the
current salary. api_salarychangelog is empty, so genuine historical salaries are
not recoverable; this freezes the data at its present, self-consistent state.
"""
from django.db import migrations, models

DAYS_IN_MONTH = 30


def backfill_snapshots(apps, schema_editor):
    Attendance = apps.get_model('api', 'Attendance')
    User = apps.get_model('api', 'User')

    rates = {
        u.pk: (float(u.salary_per_month or 0)
               - float(u.esi_amount or 0)
               - float(u.epf_amount or 0))
        for u in User.objects.all()
    }

    to_update = []
    for att in Attendance.objects.filter(salary_snapshot__isnull=True).iterator(chunk_size=2000):
        effective = rates.get(att.user_id)
        if effective is None:
            continue
        att.salary_snapshot = round(effective, 2)
        to_update.append(att)
        if len(to_update) >= 2000:
            Attendance.objects.bulk_update(to_update, ['salary_snapshot'])
            to_update.clear()
    if to_update:
        Attendance.objects.bulk_update(to_update, ['salary_snapshot'])


def clear_snapshots(apps, schema_editor):
    apps.get_model('api', 'Attendance').objects.update(salary_snapshot=None)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0017_payroll_float_field_types'),
    ]

    operations = [
        migrations.AddField(
            model_name='attendance',
            name='salary_snapshot',
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=10, null=True,
                help_text='Effective monthly salary (base - ESI - EPF) in effect when this '
                          'record was created. Left null only for rows created before this '
                          'field existed.',
            ),
        ),
        migrations.RunPython(backfill_snapshots, clear_snapshots),
    ]
