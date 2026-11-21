from rest_framework import serializers
from .models import Location, User, Attendance, AttendanceSession, Payroll, Holiday, Shift, Leave


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ['id', 'code', 'name', 'is_active']


class ShiftSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Shift
        fields = ['id', 'name', 'start_time', 'end_time', 'buffer_minutes', 'is_active', 'display_name']
    
    def get_display_name(self, obj):
        return f"{obj.start_time.strftime('%I:%M %p')} - {obj.end_time.strftime('%I:%M %p')}"


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    location_code = serializers.CharField(source='location.code', read_only=True)
    location_display = serializers.CharField(source='location.name', read_only=True)
    shift_details = ShiftSerializer(source='shift', read_only=True)
    leaves_taken_this_month = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'first_name', 'last_name', 'email', 'password',
            'role', 'location', 'location_code', 'location_display', 'department', 'designation',
            'contact', 'salary_per_month', 'esi_amount', 'epf_amount', 'is_approved',
            'shift', 'shift_details', 'paid_leaves_per_month', 'profile_picture',
            'leaves_taken_this_month'
        ]

        read_only_fields = ['is_approved']

    def get_leaves_taken_this_month(self, obj):
        from datetime import date
        today = date.today()
        quota = obj.paid_leaves_per_month or 0

        # Count days already explicitly marked as LEAVE (by admin or a prior payroll run)
        explicit_leave_count = obj.attendances.filter(
            date__year=today.year,
            date__month=today.month,
            status='LEAVE'
        ).count()

        remaining_quota = max(quota - explicit_leave_count, 0)

        # Count pure-absent days (genuine no-shows: no check-in, no check-out,
        # not admin-overridden) that would be auto-converted to paid leave.
        # This mirrors the exact filter used in PayrollViewSet.generate().
        auto_convert_count = 0
        if remaining_quota > 0:
            pure_absent_count = obj.attendances.filter(
                date__year=today.year,
                date__month=today.month,
                status='ABSENT',
                status_edited=False,
                time_in__isnull=True,
                time_out__isnull=True,
            ).count()
            auto_convert_count = min(pure_absent_count, remaining_quota)

        return explicit_leave_count + auto_convert_count

    def validate(self, data):
        import re
        name_re = re.compile(r"^[a-zA-Z\s\-']+$")

        # First name is required (2–50 chars)
        for field_label, field_key in [('First name', 'first_name')]:
            value = data.get(field_key, getattr(self.instance, field_key, '') if self.instance else '')
            if value is not None:
                value = value.strip()
                if len(value) < 2 or len(value) > 50:
                    raise serializers.ValidationError(
                        {field_key: f"{field_label} must be between 2 and 50 characters."}
                    )
                if not name_re.match(value):
                    raise serializers.ValidationError(
                        {field_key: f"{field_label} can only contain letters, spaces, hyphens, or apostrophes."}
                    )

        # Last name is optional — only validate format/length when provided
        ln = data.get('last_name', getattr(self.instance, 'last_name', '') if self.instance else '')
        if ln:
            ln = ln.strip()
            if len(ln) > 50:
                raise serializers.ValidationError(
                    {'last_name': "Last name must be 50 characters or fewer."}
                )
            if not name_re.match(ln):
                raise serializers.ValidationError(
                    {'last_name': "Last name can only contain letters, spaces, hyphens, or apostrophes."}
                )

        return data

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        instance = self.Meta.model(**validated_data)
        if password is not None:
            instance.set_password(password)
        instance.save()
        return instance


class AttendanceSessionSerializer(serializers.ModelSerializer):
    """Serializer for individual check-in/check-out sessions within a day."""
    class Meta:
        model = AttendanceSession
        fields = ['id', 'session_number', 'time_in', 'time_out', 'duration_minutes', 'check_in_mode']
        read_only_fields = ['id', 'session_number', 'time_in', 'time_out', 'duration_minutes', 'check_in_mode']


class AttendanceSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    shift_details = ShiftSerializer(source='shift', read_only=True)
    sessions = AttendanceSessionSerializer(many=True, read_only=True)
    gap_minutes = serializers.SerializerMethodField()

    def get_gap_minutes(self, obj):
        """Compute actual gap minutes = effective_shift - total_worked.
        Shows the real gap even when it is within the buffer (fine is 0 but minutes > 0)."""
        from datetime import datetime, timedelta
        total_worked = obj.total_worked_minutes or 0
        if total_worked <= 0:
            return 0
        shift = obj.shift or (obj.user.shift if obj.user else None)
        if not shift:
            return 0
        ref_date = obj.date
        s_start = datetime.combine(ref_date, shift.start_time)
        s_end = datetime.combine(ref_date, shift.end_time)
        if s_end <= s_start:
            s_end += timedelta(days=1)
        shift_dur = int((s_end - s_start).total_seconds() / 60)
        if shift_dur <= 0:
            return 0
        # Effective shift = shift_duration minus late and early-checkout minutes
        # (mirrors the same formula used in views.py and signals.py)
        late_mins = obj.late_minutes or 0
        early_checkout_mins = obj.early_checkout_minutes or 0
        effective_shift = max(0, shift_dur - late_mins - early_checkout_mins)
        gap = effective_shift - total_worked
        return max(0, gap)

    class Meta:
        model = Attendance
        fields = '__all__'
        read_only_fields = [
            'id', 'user', 'date',                          # Identity — set at check-in
            'fine_amount', 'fine_edited',                   # Computed by signal / admin edit endpoint
            'status_edited',                                # Set by admin edit endpoint
            'overtime_minutes', 'overtime_amount',          # Computed at check-out
            'early_checkin_minutes',                         # Computed at check-in
            'early_checkout_minutes', 'early_checkout_fine', # Computed at check-out
            'total_worked_minutes', 'gap_deduction',        # Computed from sessions
            'check_in_mode',                                # System-set (FACE/MANUAL)
        ]


class LeaveSerializer(serializers.ModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)

    class Meta:
        model = Leave
        fields = '__all__'
        read_only_fields = [
            'id',
            'created_at',   # Auto-set by Django
        ]


class PayrollSerializer(serializers.ModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)

    class Meta:
        model = Payroll
        fields = '__all__'
        read_only_fields = [
            'id', 'user', 'month',                          # Identity — set at generation
            'total_present_days', 'working_days',            # Computed from attendance
            'calculated_salary',                             # Computed net salary
            'paid_leaves_taken', 'unpaid_leaves_taken',      # Computed from attendance
            'leave_deductions',                              # Computed
            'num_holidays',                                  # Computed from holiday calendar
            'fine_edited', 'overtime_edited',                # System flags
        ]



class HolidaySerializer(serializers.ModelSerializer):
    location_code = serializers.CharField(source='location.code', read_only=True)
    location_display = serializers.CharField(source='location.name', read_only=True)

    class Meta:
        model = Holiday
        fields = '__all__'
        read_only_fields = [
            'id',
            'is_weekend',   # System-generated for Sat/Sun
        ]
