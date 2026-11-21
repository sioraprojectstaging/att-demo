from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import Location, User, Attendance, AttendanceSession, Payroll, Holiday, Shift, Leave, ActivityLog, SalaryChangeLog, AttendanceEditLog


# ==============================
# LOCATION ADMIN
# ==============================
@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active', 'user_count', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('code', 'name', 'address')
    ordering = ('code',)
    
    fieldsets = (
        (None, {'fields': ('code', 'name')}),
        ('Details', {'fields': ('address', 'is_active')}),
    )

    def user_count(self, obj):
        count = obj.users.count()
        return format_html('<b>{}</b>', count)
    user_count.short_description = 'Users'


# ==============================
# SHIFT ADMIN
# ==============================
from django import forms

class ShiftAdminForm(forms.ModelForm):
    """Custom form to ensure buffer_minutes is a whole number"""
    buffer_minutes = forms.IntegerField(
        min_value=0,
        max_value=120,
        help_text="Grace period in minutes (whole numbers only, 0-120)",
        widget=forms.NumberInput(attrs={'step': '1'})
    )
    
    class Meta:
        model = Shift
        fields = '__all__'


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    form = ShiftAdminForm
    list_display = ('name', 'start_time', 'end_time', 'buffer_minutes', 'employee_count', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)
    ordering = ('start_time',)
    list_editable = ('buffer_minutes', 'is_active')

    def employee_count(self, obj):
        count = obj.employees.count()
        return format_html('<b>{}</b>', count)
    employee_count.short_description = 'Employees'


# ==============================
# LEAVE ADMIN
# ==============================
@admin.register(Leave)
class LeaveAdmin(admin.ModelAdmin):
    list_display = ('user', 'date', 'leave_type', 'approved', 'reason', 'created_at')
    list_filter = ('leave_type', 'approved', 'date', 'user__location')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'reason')
    date_hierarchy = 'date'
    ordering = ('-date',)
    list_editable = ('approved',)
    
    @admin.display(description='Location')
    def get_location(self, obj):
        return obj.user.location.code if obj.user.location else '-'


# ==============================
# USER ADMIN
# ==============================
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Work Details', {'fields': ('role', 'location', 'shift', 'department', 'designation', 'contact')}),
        ('Salary & Benefits', {'fields': ('salary_per_month', 'esi_amount', 'epf_amount', 'paid_leaves_per_month')}),
        ('Status', {'fields': ('is_approved',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Work Details', {'fields': ('role', 'location', 'shift', 'department', 'designation', 'contact')}),
    )
    list_display = ('username', 'email', 'role', 'get_location', 'get_shift', 'department', 'paid_leaves_per_month', 'is_approved', 'is_active')
    list_filter = ('role', 'location', 'is_approved', 'is_active', 'is_staff')
    search_fields = ('username', 'email', 'contact', 'first_name', 'last_name')
    list_editable = ('is_approved',)  # Quick approve/disapprove
    ordering = ('-date_joined',)
    
    actions = ['approve_users', 'disapprove_users', 'activate_users', 'deactivate_users']

    @admin.display(description='Location')
    def get_location(self, obj):
        return obj.location.code if obj.location else '-'

    @admin.display(description='Shift')
    def get_shift(self, obj):
        return obj.shift.name if obj.shift else '-'

    @admin.action(description='Approve selected users')
    def approve_users(self, request, queryset):
        count = queryset.update(is_approved=True)
        self.message_user(request, f'{count} user(s) approved.')

    @admin.action(description='Disapprove selected users')
    def disapprove_users(self, request, queryset):
        count = queryset.update(is_approved=False)
        self.message_user(request, f'{count} user(s) disapproved.')

    @admin.action(description='Activate selected users')
    def activate_users(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f'{count} user(s) activated.')

    @admin.action(description='Deactivate selected users')
    def deactivate_users(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f'{count} user(s) deactivated.')

    def save_model(self, request, obj, form, change):
        """
        Auto-log salary changes when an admin edits a user via Django Admin.
        Compares old vs new for salary_per_month, esi_amount, epf_amount.
        """
        if change:  # Only log on edits, not on creation
            try:
                old_obj = User.objects.get(pk=obj.pk)
                for field in SalaryChangeLog.TRACKED_FIELDS:
                    old_val = getattr(old_obj, field)
                    new_val = getattr(obj, field)
                    if old_val != new_val:
                        SalaryChangeLog.objects.create(
                            employee=obj,
                            changed_by=request.user,
                            field_name=field,
                            old_value=old_val,
                            new_value=new_val,
                        )
            except User.DoesNotExist:
                pass
        super().save_model(request, obj, form, change)


@admin.register(User)
class UserAdminConfig(CustomUserAdmin):
    pass


# ==============================
# ATTENDANCE SESSION INLINE
# ==============================
class AttendanceSessionInline(admin.TabularInline):
    model = AttendanceSession
    extra = 0
    readonly_fields = ('session_number', 'time_in', 'time_out', 'duration_minutes', 'check_in_mode')
    can_delete = False
    ordering = ('session_number',)


@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    list_display = ('get_employee', 'get_date', 'session_number', 'time_in', 'time_out', 'duration_minutes', 'check_in_mode')
    list_filter = ('check_in_mode', 'attendance__date')
    search_fields = ('attendance__user__username', 'attendance__user__first_name', 'attendance__user__last_name')
    ordering = ('-attendance__date', 'session_number')

    @admin.display(description='Employee')
    def get_employee(self, obj):
        return f"{obj.attendance.user.first_name} {obj.attendance.user.last_name}"

    @admin.display(description='Date')
    def get_date(self, obj):
        return obj.attendance.date


# ==============================
# ATTENDANCE ADMIN
# ==============================
@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_location', 'date', 'time_in', 'time_out', 'status', 'status_edited', 'late_minutes', 'fine_amount', 'early_checkout_minutes', 'early_checkout_fine', 'early_checkin_minutes', 'overtime_minutes', 'overtime_amount', 'total_worked_minutes', 'gap_deduction', 'check_in_mode', "fine_edited", 'salary_snapshot',)
    list_filter = ('date', 'status', 'check_in_mode', 'user__location')
    search_fields = ('user__username', 'user__contact', 'user__first_name', 'user__last_name')
    date_hierarchy = 'date'
    ordering = ('-date', '-time_in')
    readonly_fields = ('salary_snapshot',)
    list_editable = ('status', 'fine_amount', 'early_checkout_fine', 'overtime_amount')  # Quick edit fines and overtime
    inlines = [AttendanceSessionInline]
    
    fieldsets = (
        (None, {'fields': ('user', 'date', 'shift', 'status', 'status_edited', 'check_in_mode')}),
        ('Time', {'fields': ('time_in', 'time_out')}),
        ('Late Entry Fine', {
            'fields': ('late_minutes', 'fine_amount', 'fine_edited', 'salary_snapshot'),
            'description': 'salary_snapshot is the effective monthly salary (base - ESI - EPF) '
                           'frozen when this record was created. Fines are priced from it, so a '
                           'later salary change cannot reprice this record (SIO-132). Read-only.',
        }),
        ('Early Checkout Fine', {'fields': ('early_checkout_minutes', 'early_checkout_fine')}),
        ('Overtime', {'fields': ('early_checkin_minutes', 'overtime_minutes', 'overtime_amount')}),
        ('Multi-Session', {'fields': ('total_worked_minutes', 'gap_deduction')}),
    )
    
    actions = ['mark_present', 'mark_absent', 'clear_fines', 'clear_early_checkout_fines']

    @admin.display(description='Location')
    def get_location(self, obj):
        return obj.user.location.code if obj.user.location else '-'

    @admin.action(description='Mark selected as PRESENT')
    def mark_present(self, request, queryset):
        count = queryset.update(status='PRESENT')
        self.message_user(request, f'{count} record(s) marked as present.')

    @admin.action(description='Mark selected as ABSENT')
    def mark_absent(self, request, queryset):
        count = queryset.update(status='ABSENT')
        self.message_user(request, f'{count} record(s) marked as absent.')

    @admin.action(description='Clear fines for selected')
    def clear_fines(self, request, queryset):
        count = queryset.update(fine_amount=0, late_minutes=0)
        self.message_user(request, f'Fines cleared for {count} record(s).')

    @admin.action(description='Clear early checkout fines for selected')
    def clear_early_checkout_fines(self, request, queryset):
        count = queryset.update(early_checkout_fine=0, early_checkout_minutes=0)
        self.message_user(request, f'Early checkout fines cleared for {count} record(s).')

    def save_model(self, request, obj, form, change):
        """
        Auto-log attendance edits (status, fines, overtime) when admin edits via Django Admin.
        Also sets fine_edited/status_edited flags so the pre_save signal doesn't overwrite admin edits.
        """

        if change:
            try:
                old_obj = Attendance.objects.get(pk=obj.pk)

                # Detect which fields changed and log them
                for field in AttendanceEditLog.TRACKED_FIELDS:
                    old_raw = getattr(old_obj, field)
                    new_raw = getattr(obj, field)
                    old_val = '' if old_raw is None else str(old_raw)
                    new_val = '' if new_raw is None else str(new_raw)
                    if old_val != new_val:
                        AttendanceEditLog.objects.create(
                            attendance=obj,
                            employee=obj.user,
                            changed_by=request.user,
                            field_name=field,
                            old_value=old_val,
                            new_value=new_val,
                            attendance_date=obj.date,
                            source='ADMIN_PANEL',
                        )

                # Auto-set edited flags so the pre_save signal preserves admin edits
                if getattr(old_obj, 'fine_amount') != getattr(obj, 'fine_amount'):
                    obj.fine_edited = True
                if getattr(old_obj, 'early_checkout_fine') != getattr(obj, 'early_checkout_fine'):
                    obj.fine_edited = True
                if getattr(old_obj, 'status') != getattr(obj, 'status'):
                    obj.status_edited = True

            except Attendance.DoesNotExist:
                pass
            except Exception as e:
                print(f"[EDIT LOG] ERROR: {e}")
                import traceback
                traceback.print_exc()
        super().save_model(request, obj, form, change)


# ==============================
# PAYROLL ADMIN
# ==============================
@admin.register(Payroll)
class PayrollAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_location', 'month', 'total_present_days', 'working_days', 'base_salary', 'fine_deductions', 'overtime_pay', 'paid_leaves_taken', 'unpaid_leaves_taken', 'calculated_salary', 'status')
    list_filter = ('month', 'status', 'user__location')
    search_fields = ('user__username', 'user__contact')
    ordering = ('-month', 'user__username')
    list_editable = ('status', 'paid_leaves_taken')  # Quick edit status and paid leaves
    
    fieldsets = (
        (None, {'fields': ('user', 'month', 'status')}),
        ('Working Days', {'fields': ('working_days', 'total_present_days')}),
        ('Salary Calculation', {'fields': ('base_salary', 'calculated_salary')}),
        ('Deductions', {'fields': ('fine_deductions', 'esi_deductions', 'epf_deductions', 'leave_deductions')}),
        ('Leaves & Overtime', {'fields': ('paid_leaves_taken', 'unpaid_leaves_taken', 'overtime_pay')}),
    )
    
    # readonly_fields = ('calculated_salary',)  # Removed to allow manual override

    @admin.display(description='Location')
    def get_location(self, obj):
        return obj.user.location.code if obj.user.location else '-'

    @admin.action(description='Mark selected as PAID')
    def mark_paid(self, request, queryset):
        count = queryset.update(status='PAID')
        self.message_user(request, f'{count} payroll(s) marked as paid.')

    @admin.action(description='Mark selected as PENDING')
    def mark_pending(self, request, queryset):
        count = queryset.update(status='PENDING')
        self.message_user(request, f'{count} payroll(s) marked as pending.')


# ==============================
# HOLIDAY ADMIN
# ==============================
@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ('date', 'name', 'get_location', 'is_weekend')
    list_filter = ('location', 'is_weekend', 'date')
    search_fields = ('name',)
    date_hierarchy = 'date'
    ordering = ('-date',)
    list_editable = ('name',)  # Quick name edit
    
    actions = ['delete_weekends', 'copy_to_all_locations']

    @admin.display(description='Location')
    def get_location(self, obj):
        return obj.location.code if obj.location else '-'

    @admin.action(description='Delete weekend holidays only')
    def delete_weekends(self, request, queryset):
        count = queryset.filter(is_weekend=True).delete()[0]
        self.message_user(request, f'{count} weekend holiday(s) deleted.')

    @admin.action(description='Copy selected to ALL locations')
    def copy_to_all_locations(self, request, queryset):
        locations = Location.objects.filter(is_active=True)
        created = 0
        for holiday in queryset:
            for loc in locations:
                if loc != holiday.location:
                    _, was_created = Holiday.objects.get_or_create(
                        date=holiday.date,
                        location=loc,
                        defaults={'name': holiday.name, 'is_weekend': holiday.is_weekend}
                    )
                    if was_created:
                        created += 1
        self.message_user(request, f'{created} holiday(s) copied to other locations.')


# ==============================
# ACTIVITY LOG ADMIN
# ==============================
@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    """
    Comprehensive activity log viewer for tracking all attendance operations.
    Read-only to maintain log integrity.
    """
    list_display = (
        'timestamp', 
        'action_badge', 
        'status_badge', 
        'get_user_display', 
        'get_location', 
        'message_short',
    )
    list_filter = (
        'action', 
        'status', 
        'location', 
        ('timestamp', admin.DateFieldListFilter),
    )
    search_fields = (
        'user__username', 
        'user__first_name', 
        'user__last_name',
        'user__contact',
        'contact_attempted',
        'name_attempted',
        'message',
    )
    date_hierarchy = 'timestamp'
    ordering = ('-timestamp',)
    
    readonly_fields = (
        'action', 'status', 'timestamp', 'user', 'contact_attempted',
        'name_attempted', 'location', 'message', 'error_details',
        'activity_data', 'ip_address', 'user_agent',
    )
    
    fieldsets = (
        ('Activity Info', {
            'fields': ('action', 'status', 'timestamp')
        }),
        ('User/Employee', {
            'fields': ('user', 'contact_attempted', 'name_attempted')
        }),
        ('Location', {
            'fields': ('location',)
        }),
        ('Details', {
            'fields': ('message', 'error_details', 'activity_data'),
            'classes': ('wide',)
        }),
        ('Request Info', {
            'fields': ('ip_address', 'user_agent'),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        """Logs should only be created programmatically"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Logs should be read-only"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Allow superusers to delete old logs for cleanup"""
        return request.user.is_superuser
    
    @admin.display(description='Action')
    def action_badge(self, obj):
        colors = {
            'REGISTER': '#28a745',      # Green
            'CHECK_IN': '#17a2b8',      # Blue
            'CHECK_OUT': '#6c757d',     # Gray
            'ADMIN_REGISTER': '#ffc107', # Yellow
            'FACE_MATCH': '#6f42c1',    # Purple
            'SPOOF_DETECT': '#dc3545',  # Red
        }
        color = colors.get(obj.action, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.get_action_display()
        )
    
    @admin.display(description='Status')
    def status_badge(self, obj):
        colors = {
            'SUCCESS': '#28a745',
            'FAILED': '#dc3545',
            'WARNING': '#ffc107',
        }
        text_colors = {
            'SUCCESS': 'white',
            'FAILED': 'white',
            'WARNING': 'black',
        }
        color = colors.get(obj.status, '#6c757d')
        text_color = text_colors.get(obj.status, 'white')
        return format_html(
            '<span style="background-color: {}; color: {}; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            text_color,
            obj.status
        )
    
    @admin.display(description='User/Contact')
    def get_user_display(self, obj):
        if obj.user:
            return format_html(
                '<strong>{}</strong><br><small>{}</small>',
                f"{obj.user.first_name} {obj.user.last_name}",
                obj.user.contact or obj.user.email
            )
        elif obj.contact_attempted:
            return format_html(
                '<span style="color: #dc3545;">{}</span><br><small>{}</small>',
                obj.name_attempted or 'Unknown',
                obj.contact_attempted
            )
        return '-'
    
    @admin.display(description='Location')
    def get_location(self, obj):
        return obj.location.code if obj.location else '-'
    
    @admin.display(description='Message')
    def message_short(self, obj):
        if len(obj.message) > 60:
            return obj.message[:60] + '...'
        return obj.message


# ==============================
# SALARY CHANGE LOG ADMIN
# ==============================
@admin.register(SalaryChangeLog)
class SalaryChangeLogAdmin(admin.ModelAdmin):
    """
    Read-only audit trail of all salary edits made via Django Admin.
    """
    list_display = (
        'changed_at',
        'get_employee_name',
        'field_badge',
        'old_value',
        'arrow_display',
        'new_value',
        'get_changed_by',
    )
    list_filter = (
        'field_name',
        'employee__location',
        ('changed_at', admin.DateFieldListFilter),
    )
    search_fields = (
        'employee__username',
        'employee__first_name',
        'employee__last_name',
        'employee__contact',
        'changed_by__username',
        'changed_by__first_name',
    )
    date_hierarchy = 'changed_at'
    ordering = ('-changed_at',)

    readonly_fields = (
        'employee', 'changed_by', 'field_name',
        'old_value', 'new_value', 'changed_at', 'notes',
    )

    fieldsets = (
        ('Change Details', {
            'fields': ('employee', 'changed_by', 'changed_at')
        }),
        ('Values', {
            'fields': ('field_name', 'old_value', 'new_value')
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request):
        return False  # Logs are auto-created, not manually added

    def has_change_permission(self, request, obj=None):
        return False  # Read-only

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser  # Only superusers can cleanup

    @admin.display(description='Employee')
    def get_employee_name(self, obj):
        name = f"{obj.employee.first_name} {obj.employee.last_name or ''}".strip()
        loc = obj.employee.location.code if obj.employee.location else ''
        return format_html(
            '<strong>{}</strong> <small style="color:#888">({})</small>',
            name, loc
        )

    @admin.display(description='Field')
    def field_badge(self, obj):
        colors = {
            'salary_per_month': '#007bff',
            'esi_amount': '#17a2b8',
            'epf_amount': '#6f42c1',
        }
        label = SalaryChangeLog.FIELD_LABELS.get(obj.field_name, obj.field_name)
        color = colors.get(obj.field_name, '#6c757d')
        return format_html(
            '<span style="background-color:{}; color:white; padding:3px 8px; border-radius:4px; font-size:11px;">{}</span>',
            color, label
        )

    @admin.display(description='')
    def arrow_display(self, obj):
        # The arrow is passed as an argument rather than baked into the format
        # string: format_html() with no args/kwargs was removed in Django 5.0
        # and raises TypeError, which 500'd both log changelists.
        return format_html('<span style="font-size:16px;">{}</span>', '→')

    @admin.display(description='Changed By')
    def get_changed_by(self, obj):
        if obj.changed_by:
            return format_html(
                '<strong>{}</strong>',
                f"{obj.changed_by.first_name} {obj.changed_by.last_name or ''}".strip() or obj.changed_by.username
            )
        return '-'


# ==============================
# ATTENDANCE EDIT LOG ADMIN
# ==============================
@admin.register(AttendanceEditLog)
class AttendanceEditLogAdmin(admin.ModelAdmin):
    """
    Read-only audit trail of attendance record edits made via Django Admin.
    """
    list_display = (
        'changed_at',
        'get_employee_name',
        'attendance_date',
        'source_badge',
        'field_badge',
        'old_value',
        'arrow_display',
        'new_value',
        'get_changed_by',
    )
    list_filter = (
        'source',
        'field_name',
        'employee__location',
        ('changed_at', admin.DateFieldListFilter),
        ('attendance_date', admin.DateFieldListFilter),
    )
    search_fields = (
        'employee__username',
        'employee__first_name',
        'employee__last_name',
        'employee__contact',
        'changed_by__username',
    )
    date_hierarchy = 'changed_at'
    ordering = ('-changed_at',)

    readonly_fields = (
        'attendance', 'employee', 'changed_by', 'field_name',
        'old_value', 'new_value', 'attendance_date', 'changed_at', 'source',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    @admin.display(description='Employee')
    def get_employee_name(self, obj):
        name = f"{obj.employee.first_name} {obj.employee.last_name or ''}".strip()
        return format_html('<strong>{}</strong>', name)

    @admin.display(description='Field')
    def field_badge(self, obj):
        colors = {
            'status': '#dc3545',
            'fine_amount': '#fd7e14',
            'early_checkout_fine': '#ffc107',
            'overtime_amount': '#28a745',
            'overtime_minutes': '#20c997',
            'late_minutes': '#e83e8c',
        }
        label = AttendanceEditLog.FIELD_LABELS.get(obj.field_name, obj.field_name)
        color = colors.get(obj.field_name, '#6c757d')
        text_color = 'black' if obj.field_name == 'early_checkout_fine' else 'white'
        return format_html(
            '<span style="background-color:{}; color:{}; padding:3px 8px; border-radius:4px; font-size:11px;">{}</span>',
            color, text_color, label
        )


    @admin.display(description='Source')
    def source_badge(self, obj):
        colors = {
            'ADMIN_PANEL': '#6f42c1',
            'FRONTEND': '#007bff',
            'PAYROLL_GEN': '#28a745',
        }
        color = colors.get(obj.source, '#6c757d')
        return format_html(
            '<span style="background-color:{}; color:white; padding:3px 8px; border-radius:4px; font-size:11px;">{}</span>',
            color, obj.get_source_display()
        )

    @admin.display(description='')
    def arrow_display(self, obj):
        # The arrow is passed as an argument rather than baked into the format
        # string: format_html() with no args/kwargs was removed in Django 5.0
        # and raises TypeError, which 500'd both log changelists.
        return format_html('<span style="font-size:16px;">{}</span>', '→')

    @admin.display(description='Changed By')
    def get_changed_by(self, obj):
        if obj.changed_by:
            return f"{obj.changed_by.first_name} {obj.changed_by.last_name or ''}".strip() or obj.changed_by.username
        return '-'


# ==============================
# ADMIN SITE CUSTOMIZATION
# ==============================
admin.site.site_header = "Siora One Admin"
admin.site.site_title = "Siora One Admin"
admin.site.index_title = "System Management"
