from django.db import models
from django.contrib.auth.models import AbstractUser

class Location(models.Model):
    """Dynamic location model - can add new locations via Django admin"""
    code = models.CharField(max_length=10, unique=True, help_text="Short code like HO, BR1")
    name = models.CharField(max_length=100, help_text="Full name like 'Head Office'")
    address = models.TextField(blank=True, null=True, help_text="Physical address of the location")
    is_active = models.BooleanField(default=True, help_text="Uncheck to disable this location")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class Shift(models.Model):
    """Work shift timings - chosen by employee at registration, editable by admin"""
    name = models.CharField(max_length=50, help_text="e.g., 'Morning Standard', '10AM-6:30PM'")
    start_time = models.TimeField(help_text="Shift start time")
    end_time = models.TimeField(help_text="Shift end time")
    buffer_minutes = models.IntegerField(default=10, help_text="Grace period in minutes (no fine)")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['start_time']

    def __str__(self):
        return f"{self.name} ({self.start_time.strftime('%I:%M %p')} - {self.end_time.strftime('%I:%M %p')})"


from django.contrib.auth.models import BaseUserManager


class CustomUserManager(BaseUserManager):
    """
    Custom user manager to ensure superusers are created with ADMIN role.
    """
    def create_user(self, username, email=None, password=None, **extra_fields):
        if not username:
            raise ValueError('The Username field must be set')
        email = self.normalize_email(email) if email else None
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', 'ADMIN')  # Superusers should be ADMIN
        extra_fields.setdefault('is_approved', True)  # Auto-approve superusers

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(username, email, password, **extra_fields)


class User(AbstractUser):
    ROLE_CHOICES = (
        ('ADMIN', 'Admin'),
        ('EMPLOYEE', 'Employee'),
    )
    role = models.CharField(max_length=15, choices=ROLE_CHOICES, default='EMPLOYEE')
    location = models.ForeignKey(
        Location, 
        on_delete=models.PROTECT,  # Prevent deleting location if users exist
        related_name='users',
        null=True,
        blank=True,
        help_text="Assigned work location"
    )
    shift = models.ForeignKey(
        Shift,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees',
        help_text="Assigned work shift (chosen at registration)"
    )
    department = models.CharField(max_length=100, blank=True, null=True)
    designation = models.CharField(max_length=100, blank=True, null=True)
    salary_per_month = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # Face recognition fields
    face_encoding = models.TextField(blank=True, null=True)  # JSON-encoded face embedding
    contact = models.CharField(max_length=15, unique=True, null=True, blank=True, help_text="Unique phone number for identification")
    esi_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    epf_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # Leave settings
    paid_leaves_per_month = models.IntegerField(default=1, help_text="Number of paid leaves per month")
    # Admin approval workflow
    is_approved = models.BooleanField(default=True, help_text="Uncheck to disable login")
    # Password reset
    password_reset_token = models.CharField(max_length=100, blank=True, null=True)
    password_reset_expires = models.DateTimeField(blank=True, null=True)

    # Registration photograph. Stored via the default storage: Vercel Blob in
    # production (see core/storage.py), backend/media/ locally.
    profile_picture = models.ImageField(
        upload_to='profile_pictures/',
        null=True,
        blank=True
    )

    objects = CustomUserManager()

    def __str__(self):
        loc = self.location.code if self.location else 'No Location'
        return f"{self.username} ({loc})"


class Attendance(models.Model):
    STATUS_CHOICES = (
        ('PRESENT', 'Present'),
        ('ABSENT', 'Absent'),
        ('LATE', 'Late'),
        ('HALF_DAY', 'Half Day'),
        ('LEAVE', 'Leave'),
        ('HOLIDAY', 'Holiday'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='attendances')
    date = models.DateField()
    time_in = models.TimeField(null=True, blank=True)
    time_out = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ABSENT')
    late_minutes = models.IntegerField(default=0)
    fine_amount = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    check_in_mode = models.CharField(max_length=10, default='FACE', choices=[('FACE', 'Face'), ('MANUAL', 'Manual')])
    # Shift captured at check-in time
    shift = models.ForeignKey(
        Shift,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Shift for this day (captured at check-in)"
    )
    # Editable fields
    fine_edited = models.BooleanField(default=False, help_text="True if admin manually edited the fine")
    status_edited = models.BooleanField(default=False, help_text="True if admin manually edited the status")
    # Overtime tracking
    overtime_minutes = models.IntegerField(default=0, help_text="Total overtime = early checkin + late checkout")
    overtime_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0.00, help_text="Overtime pay based on salary")
    early_checkin_minutes = models.IntegerField(default=0, help_text="Minutes checked in before shift start")
    overtime_edited = models.BooleanField(default=False, help_text="True if admin manually edited the overtime amount")
    # Early checkout tracking
    early_checkout_minutes = models.IntegerField(default=0, help_text="Minutes left before shift end - buffer")
    early_checkout_fine = models.DecimalField(max_digits=8, decimal_places=2, default=0.00, help_text="Fine for early checkout")
    # Multi-session tracking
    total_worked_minutes = models.IntegerField(default=0, help_text="Total minutes worked across all sessions")
    gap_deduction = models.DecimalField(max_digits=8, decimal_places=2, default=0.00, help_text="Salary deduction for gaps between sessions")
    early_checkout_fine_edited = models.BooleanField(default=False, help_text="True if admin manually edited the early checkout fine")
    # Salary basis frozen at creation (SIO-132). Fines/overtime are priced from this,
    # so changing an employee's salary can never rewrite historical records.
    salary_snapshot = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Effective monthly salary (base - ESI - EPF) in effect when this record "
                  "was created. Left null only for rows created before this field existed."
    )
    esi_snapshot = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="ESI amount in effect when this record was created. Together with "
                  "epf_snapshot this lets payroll reconstruct the gross salary of the day: "
                  "base = salary_snapshot + esi_snapshot + epf_snapshot."
    )
    epf_snapshot = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="EPF amount in effect when this record was created."
    )

    class Meta:
        unique_together = ['user', 'date']
        ordering = ['-date', '-time_in']

    def __str__(self):
        return f"{self.user.username} - {self.date}"


class AttendanceSession(models.Model):
    """Individual check-in/check-out session within a day's attendance."""
    attendance = models.ForeignKey(
        Attendance, on_delete=models.CASCADE,
        related_name='sessions',
        help_text="The daily attendance record this session belongs to"
    )
    session_number = models.IntegerField(default=1, help_text="Session order within the day (1, 2, 3...)")
    time_in = models.TimeField(help_text="Check-in time for this session")
    time_out = models.TimeField(null=True, blank=True, help_text="Check-out time for this session")
    duration_minutes = models.IntegerField(default=0, help_text="Duration of this session in minutes")
    check_in_mode = models.CharField(
        max_length=10, default='FACE',
        choices=[('FACE', 'Face'), ('MANUAL', 'Manual')],
        help_text="How the employee checked in for this session"
    )

    class Meta:
        ordering = ['session_number']
        unique_together = ['attendance', 'session_number']

    def __str__(self):
        return f"{self.attendance.user.username} - {self.attendance.date} - Session {self.session_number}"


class Leave(models.Model):
    """Track employee leaves - 1 paid leave per month by default"""
    LEAVE_TYPE_CHOICES = (
        ('PAID', 'Paid Leave'),
        ('UNPAID', 'Unpaid Leave'),
        ('SICK', 'Sick Leave'),
        ('CASUAL', 'Casual Leave'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='leaves')
    date = models.DateField()
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPE_CHOICES, default='PAID')
    reason = models.TextField(blank=True, null=True)
    approved = models.BooleanField(default=True, help_text="Whether leave is approved by admin")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'date']
        ordering = ['-date']

    def __str__(self):
        return f"{self.user.username} - {self.date} ({self.leave_type})"


class Payroll(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PAID', 'Paid'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payrolls')
    month = models.DateField(help_text="Store as 1st of the month")
    total_present_days = models.FloatField(default=0.0)
    calculated_salary = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    base_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    fine_deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    esi_deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    epf_deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    working_days = models.IntegerField(default=30)
    # Leave tracking
    paid_leaves_taken = models.FloatField(default=0.0, help_text="Number of paid leaves taken this month")
    unpaid_leaves_taken = models.FloatField(default=0.0, help_text="Number of unpaid leaves (deducted from salary)")
    leave_deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Salary deducted for unpaid leaves")
    # Overtime tracking
    overtime_pay = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Total overtime pay for the month")
    # Holiday tracking
    num_holidays = models.IntegerField(default=0, help_text="Number of paid holidays in this month")
    # Track manual edits to preserve them during regeneration
    fine_edited = models.BooleanField(default=False, help_text="True if admin manually edited the fine deductions")
    overtime_edited = models.BooleanField(default=False, help_text="True if admin manually edited the overtime pay")

    class Meta:
        unique_together = ['user', 'month']
        ordering = ['-month']

    def __str__(self):
        return f"{self.user.username} - {self.month}"


class Holiday(models.Model):
    date = models.DateField()
    name = models.CharField(max_length=100, default='Holiday')
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name='holidays',
        help_text="Location this holiday applies to"
    )
    is_weekend = models.BooleanField(default=False, help_text="Auto-generated Sat/Sun")

    class Meta:
        ordering = ['date']
        unique_together = ['date', 'location']

    def __str__(self):
        return f"{self.date} - {self.name} ({self.location.code})"


class ActivityLog(models.Model):
    """
    Comprehensive activity log for all attendance-related operations.
    Tracks registration, check-in, check-out attempts with success/failure status.
    Replaces the need for log file lookup.
    """
    ACTION_CHOICES = (
        ('REGISTER', 'Employee Registration'),
        ('CHECK_IN', 'Check In'),
        ('CHECK_OUT', 'Check Out'),
        ('ADMIN_REGISTER', 'Admin Registration'),
        ('FACE_MATCH', 'Face Recognition'),
        ('SPOOF_DETECT', 'Spoof Detection'),
    )
    
    STATUS_CHOICES = (
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
        ('WARNING', 'Warning'),
    )
    
    # Core fields
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, help_text="Type of activity")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SUCCESS')
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # User/Employee identification (may be null for failed registrations)
    user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='activity_logs',
        help_text="User associated with this activity (null for failed registration attempts)"
    )
    
    # For failed registration attempts, store identifying info
    contact_attempted = models.CharField(max_length=20, blank=True, null=True, help_text="Contact number attempted (for failed registrations)")
    name_attempted = models.CharField(max_length=200, blank=True, null=True, help_text="Name attempted (for failed registrations)")
    
    # Location tracking
    location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activity_logs',
        help_text="Location where activity occurred"
    )
    
    # Result details
    message = models.TextField(help_text="Human-readable message describing the result")
    error_details = models.TextField(blank=True, null=True, help_text="Error details for failed attempts")
    
    # Activity-specific data (JSON)
    activity_data = models.JSONField(
        default=dict, 
        blank=True,
        help_text="Additional activity data (shift, similarity score, late minutes, etc.)"
    )
    
    # IP/Device tracking (optional)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Activity Log'
        verbose_name_plural = 'Activity Logs'
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['action', 'status']),
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['location', '-timestamp']),
        ]
    
    def __str__(self):
        user_str = self.user.username if self.user else (self.contact_attempted or 'Unknown')
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] {self.get_action_display()} - {user_str} - {self.status}"
    
    @classmethod
    def log_activity(cls, action, status, message, user=None, location=None, 
                     contact_attempted=None, name_attempted=None, error_details=None,
                     activity_data=None, ip_address=None, user_agent=None):
        """
        Helper method to create activity log entries.
        """
        return cls.objects.create(
            action=action,
            status=status,
            message=message,
            user=user,
            location=location,
            contact_attempted=contact_attempted,
            name_attempted=name_attempted,
            error_details=error_details,
            activity_data=activity_data or {},
            ip_address=ip_address,
            user_agent=user_agent
        )


# ==============================
# SALARY CHANGE LOG
# ==============================
class SalaryChangeLog(models.Model):
    """
    Audit trail for salary-related field edits made via Django Admin.
    Tracks who changed what, old vs new values, and when.
    """
    employee = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='salary_changes',
        help_text="Employee whose salary was changed"
    )
    changed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='salary_edits_made',
        help_text="Admin who made the change"
    )
    field_name = models.CharField(
        max_length=50,
        help_text="Which field was changed (salary_per_month, esi_amount, epf_amount)"
    )
    old_value = models.DecimalField(max_digits=10, decimal_places=2)
    new_value = models.DecimalField(max_digits=10, decimal_places=2)
    changed_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, default='', help_text="Optional notes about the change")

    class Meta:
        ordering = ['-changed_at']
        verbose_name = 'Salary Change Log'
        verbose_name_plural = 'Salary Change Logs'

    def __str__(self):
        return f"{self.employee.first_name} | {self.field_name}: {self.old_value} → {self.new_value} | by {self.changed_by} | {self.changed_at.strftime('%Y-%m-%d %H:%M')}"

    TRACKED_FIELDS = ['salary_per_month', 'esi_amount', 'epf_amount']

    FIELD_LABELS = {
        'salary_per_month': 'Base Salary',
        'esi_amount': 'ESI Amount',
        'epf_amount': 'EPF Amount',
    }


# ==============================
# ATTENDANCE EDIT LOG
# ==============================
class AttendanceEditLog(models.Model):
    """
    Audit trail for attendance record edits made via Django Admin.
    Tracks fine, status, and overtime changes.
    """
    attendance = models.ForeignKey(
        'Attendance', on_delete=models.CASCADE,
        related_name='edit_logs',
        help_text="The attendance record that was edited"
    )
    employee = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='attendance_edits',
        help_text="Employee whose attendance was edited"
    )
    changed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='attendance_edits_made',
        help_text="Admin who made the change"
    )
    field_name = models.CharField(max_length=50)
    old_value = models.CharField(max_length=100)
    new_value = models.CharField(max_length=100)
    attendance_date = models.DateField(help_text="Date of the attendance record")
    changed_at = models.DateTimeField(auto_now_add=True)
    
    SOURCE_CHOICES = [
        ('ADMIN_PANEL', 'Django Admin'),
        ('FRONTEND', 'Frontend Edit'),
        ('PAYROLL_GEN', 'Payroll Generation'),
    ]
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='FRONTEND')

    class Meta:
        ordering = ['-changed_at']
        verbose_name = 'Attendance Edit Log'
        verbose_name_plural = 'Attendance Edit Logs'

    def __str__(self):
        return f"{self.employee.first_name} | {self.attendance_date} | {self.field_name}: {self.old_value} → {self.new_value} [{self.source}]"

    TRACKED_FIELDS = ['status', 'time_in', 'time_out', 'fine_amount', 'early_checkout_fine', 'overtime_amount', 'overtime_minutes', 'late_minutes']

    FIELD_LABELS = {
        'status': 'Status',
        'time_in': 'Check In Time',
        'time_out': 'Check Out Time',
        'fine_amount': 'Late Fine',
        'early_checkout_fine': 'Early Checkout Fine',
        'overtime_amount': 'Overtime Pay',
        'overtime_minutes': 'Overtime Minutes',
        'late_minutes': 'Late Minutes',
    }


