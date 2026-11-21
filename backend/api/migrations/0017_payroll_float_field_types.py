"""
Resolves pre-existing model/migration drift on Payroll.

These three fields were already declared as FloatField on the model but no
migration recorded the change, so `makemigrations` reported drift on every run.
The database columns are already `double precision`, so this migration is a
no-op against existing environments — it only brings migration state in line
with models.py. Unrelated to SIO-132; split out to keep that change reviewable.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0016_merge_20260308_2359'),
    ]

    operations = [
        migrations.AlterField(
            model_name='payroll',
            name='paid_leaves_taken',
            field=models.FloatField(default=0.0, help_text='Number of paid leaves taken this month'),
        ),
        migrations.AlterField(
            model_name='payroll',
            name='total_present_days',
            field=models.FloatField(default=0.0),
        ),
        migrations.AlterField(
            model_name='payroll',
            name='unpaid_leaves_taken',
            field=models.FloatField(default=0.0, help_text='Number of unpaid leaves (deducted from salary)'),
        ),
    ]
