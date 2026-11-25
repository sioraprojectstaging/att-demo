import json
import math 
import secrets
import calendar
import time as time_module
from datetime import time, datetime, timedelta, date


from django.utils import timezone
from django.utils.timezone import now
from django.utils.dateparse import parse_date
from rest_framework import viewsets, generics, permissions, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response

from .models import User, Attendance, Payroll, Holiday, ActivityLog, Location
from .serializers import AttendanceSerializer, PayrollSerializer, UserSerializer, HolidaySerializer
from .face_recognition import FaceHandler
import logging

logger = logging.getLogger(__name__)

def debug_log(payload):
    """Debug logging - disabled in production"""
    pass


def get_request_metadata(request):
    """Extract IP address and user agent from request for activity logging"""
    if request is None:
        return None, None
    
    # Get IP address (handle proxies)
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip_address = x_forwarded_for.split(',')[0].strip()
    else:
        ip_address = request.META.get('REMOTE_ADDR')
    
    # Get user agent
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    return ip_address, user_agent


# ==========================
# CONFIG
# ==========================
# buffalo_l (ArcFace) scores: same person ~0.6+, different people usually < 0.3,
# but poor lighting / distance can push different people to ~0.5 (e.g. 0.5137
# seen for two different workers). Block only clear duplicates; flag the grey
# zone for admin review instead of rejecting it.
REGISTRATION_DUPLICATE_THRESHOLD = 0.60
REGISTRATION_REVIEW_THRESHOLD = 0.40
ATTENDANCE_MATCH_THRESHOLD = 0.5


# ==========================
# UTILS
# ==========================
def normalize(vec):
    """L2 normalize a vector"""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


def cosine_similarity(v1, v2):
    """Cosine similarity for normalized vectors.

    Vectors of different lengths come from different models and cannot be
    compared (zip would silently truncate), so they score 0.
    """
    if len(v1) != len(v2):
        return 0.0
    return sum(a * b for a, b in zip(v1, v2))


# ==========================
# CLEAN RESPONSE HELPERS
# ==========================
def error_response(message, status_code=status.HTTP_400_BAD_REQUEST, details=None):
    """Return a clean error response with just a message field for toast display"""
    response = {"message": message}
    if details:
        response["details"] = details
    return Response(response, status=status_code)


def success_response(message, data=None, status_code=status.HTTP_200_OK):
    """Return a clean success response"""
    response = {"message": message}
    if data:
        response.update(data)
    return Response(response, status=status_code)

# ==========================
# ATTENDANCE HELPER
# ==========================
def handle_attendance_logic(data, files=None, request=None):
    import time as time_module
    request_start = time_module.time()
    
    # Get request metadata for logging
    ip_address, user_agent = get_request_metadata(request) if request else (None, None)
    
    # Check for image file first (Backend-side recognition)
    image_file = files.get('image') if files else None
    
    # Check for pre-calculated embedding (Legacy/Test support)
    embedding_str = data.get("embedding") 
    
    user_id = data.get("user_id")
    attendance_type = data.get("type", "IN").upper() # IN or OUT
    
    incoming_embedding = None
    
    # 1. Try Image
    if image_file:
        logger.debug("Processing uploaded image for attendance...")
        handler = FaceHandler.get_instance()
        
        # ANTI-SPOOFING CHECK
        spoof_start = time_module.time()
        is_live, liveness_score, spoof_reason = handler.detect_spoof_single_image(image_file)
        spoof_time = time_module.time() - spoof_start
        logger.debug(f"Spoof check time: {spoof_time:.3f}s")
        
        if not is_live:
            logger.warning(f"Spoof detected: {spoof_reason} (score={liveness_score})")
            # Log spoof detection
            ActivityLog.log_activity(
                action='SPOOF_DETECT',
                status='FAILED',
                message=f"Spoof detected: {spoof_reason}",
                activity_data={
                    'liveness_score': float(liveness_score) if liveness_score else None,
                    'reason': spoof_reason,
                    'attendance_type': attendance_type
                },
                ip_address=ip_address,
                user_agent=user_agent
            )
            return error_response(
                spoof_reason,  # Now contains user-friendly message from detect_spoof_single_image
                status_code=status.HTTP_403_FORBIDDEN
            )
        
        logger.debug(f"Liveness check passed (score={liveness_score:.2f})")
        
        process_start = time_module.time()
        raw_embedding = handler.process_image(image_file)
        process_time = time_module.time() - process_start
        logger.debug(f"Face embedding extraction time: {process_time:.3f}s")
        
        if raw_embedding is None:
            # Log no face detected
            ActivityLog.log_activity(
                action='FACE_MATCH',
                status='FAILED',
                message="No face detected in attendance image",
                activity_data={'attendance_type': attendance_type},
                ip_address=ip_address,
                user_agent=user_agent
            )
            return error_response("Full face not visible, retry")
        incoming_embedding = normalize(raw_embedding)
    # 2. Try Embedding (Legacy)
    elif embedding_str:
        try:
            # If it's a list already
            if isinstance(embedding_str, list):
                 incoming_embedding = normalize(list(map(float, embedding_str)))
            # If it's a string representation
            elif isinstance(embedding_str, str):
                 incoming_embedding = normalize(json.loads(embedding_str))
        except (ValueError, TypeError, json.JSONDecodeError):
             return error_response("Invalid face data format")

    user = None
    best_similarity = 0.0
    
    if incoming_embedding:
        best_match = None
        users_with_face = User.objects.exclude(face_encoding__isnull=True).exclude(face_encoding='')
        user_count = users_with_face.count()
        logger.debug(f"Comparing against {user_count} registered users...")
        
        compare_start = time_module.time()
        for u in users_with_face:
            try:
                stored_embedding = normalize(json.loads(u.face_encoding))
                similarity = cosine_similarity(incoming_embedding, stored_embedding)

                # print(f"[ATTENDANCE] {u.email} similarity={similarity:.4f}")

                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = u
            except Exception:
                continue
        
        compare_time = time_module.time() - compare_start
        total_time = time_module.time() - request_start
        logger.debug(f"User comparison time: {compare_time:.3f}s for {user_count} users")
        logger.info(f"Total attendance request time: {total_time:.3f}s")

        if best_match and best_similarity >= ATTENDANCE_MATCH_THRESHOLD:
            user = best_match
            logger.info(f"Matched {user.email} with score {best_similarity:.4f}")
        else:
            # Log face not recognized
            ActivityLog.log_activity(
                action='FACE_MATCH',
                status='FAILED',
                message=f"Face not recognized (best similarity: {best_similarity:.4f})",
                activity_data={
                    'attendance_type': attendance_type,
                    'best_similarity': round(best_similarity, 4),
                    'threshold': ATTENDANCE_MATCH_THRESHOLD,
                    'users_compared': user_count
                },
                ip_address=ip_address,
                user_agent=user_agent
            )
            return error_response(
                "Face not recognized. Please register first or try again.",
                status_code=status.HTTP_401_UNAUTHORIZED
            )
    elif user_id:
            user = User.objects.filter(id=user_id).first()
            if not user:
                return error_response("User not found", status_code=status.HTTP_404_NOT_FOUND)
    else:
        return error_response("Please capture your face to mark attendance")

    today = timezone.localtime().date()
    current_time = timezone.localtime().time() # Aware time if USE_TZ=True
    
    # Get current datetime for calculation
    now = timezone.localtime()

    if attendance_type == 'IN':
        # CHECK IN LOGIC (Multi-Session)
        # Capture the user's assigned shift at check-in time
        user_shift = user.shift
        from .models import AttendanceSession
        
        attendance, created = Attendance.objects.get_or_create(
            user=user,
            date=today,
            defaults={
                'time_in': current_time,
                'status': 'PRESENT',
                'check_in_mode': 'FACE' if incoming_embedding else 'MANUAL',
                'shift': user_shift  # Store the shift for this attendance record
            }
        )
        
        if not created:
            # MULTI-SESSION: Attendance record already exists — this is a subsequent check-in
            # 1. Verify last session is closed (has time_out)
            last_session = attendance.sessions.order_by('-session_number').first()
            if last_session and not last_session.time_out:
                return Response({
                    "status": "failed",
                    "message": "Please check out first before checking in again",
                    "employee_name": f"{user.first_name} {user.last_name}",
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # 2. Enforce 5-minute gap from last checkout
            MIN_GAP_MINUTES = 5
            if last_session and last_session.time_out:
                last_checkout_dt = datetime.combine(today, last_session.time_out)
                if timezone.is_aware(now):
                    last_checkout_dt = timezone.make_aware(last_checkout_dt)
                minutes_since_checkout = (now - last_checkout_dt).total_seconds() / 60
                if minutes_since_checkout < MIN_GAP_MINUTES:
                    remaining = int(MIN_GAP_MINUTES - minutes_since_checkout)
                    return Response({
                        "status": "failed",
                        "message": f"Please wait {remaining} more minute(s) before checking in again",
                        "employee_name": f"{user.first_name} {user.last_name}",
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # 3. Create new session (no late recalculation)
            new_session_number = (last_session.session_number + 1) if last_session else 1
            AttendanceSession.objects.create(
                attendance=attendance,
                session_number=new_session_number,
                time_in=current_time,
                check_in_mode='FACE' if incoming_embedding else 'MANUAL',
            )
            
            # Log subsequent check-in
            ActivityLog.log_activity(
                action='CHECK_IN',
                status='SUCCESS',
                message=f"Session {new_session_number} check-in at {current_time}",
                user=user,
                location=user.location,
                activity_data={
                    'time_in': str(current_time),
                    'session_number': new_session_number,
                    'similarity_score': round(best_similarity, 4) if best_similarity else None
                },
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            return Response({
                "status": "success",
                "employee_name": f"{user.first_name} {user.last_name}",
                "message": f"Session {new_session_number} check-in successful",
                "time_in": str(current_time),
                "session_number": new_session_number,
            }, status=status.HTTP_201_CREATED)

        # FIRST CHECK-IN OF THE DAY — create Session #1 and calculate late minutes
        # Also create the first AttendanceSession
        AttendanceSession.objects.create(
            attendance=attendance,
            session_number=1,
            time_in=current_time,
            check_in_mode='FACE' if incoming_embedding else 'MANUAL',
        )

        # SHIFT-BASED LATE FINE CALCULATION (unchanged logic)
        # Get shift timing (default to 10:00 AM if no shift assigned)
        if user_shift:
            expected_start = now.replace(
                hour=user_shift.start_time.hour,
                minute=user_shift.start_time.minute,
                second=0,
                microsecond=0
            )
            buffer_minutes = user_shift.buffer_minutes  # Default 10 minutes
        else:
            logger.debug("No shift assigned, falling back to default (10:00 AM)")
            # Fallback to 10:00 AM default with 10-min buffer
            expected_start = now.replace(hour=10, minute=0, second=0, microsecond=0)
            buffer_minutes = 10
        
        late_minutes = 0
        fine_amount = 0.0
        early_checkin_minutes = 0
        
        if now > expected_start:
            delta = now - expected_start
            late_minutes = int(delta.total_seconds() / 60)
            
            # Calculate effective salary for rates (Base - ESI - EPF)
            salary_base = float(user.salary_per_month)
            esi = float(user.esi_amount)
            epf = float(user.epf_amount)
            effective_salary = salary_base - esi - epf
            
            # Use dynamic days for current month
            import calendar
            _, DAYS_IN_MONTH = calendar.monthrange(today.year, today.month)
            
            daily_salary = effective_salary / DAYS_IN_MONTH
            # Use actual shift duration for minute rate (not hardcoded 9 hours)
            if user_shift:
                from datetime import datetime as dt_class
                shift_start_dt = dt_class.combine(today, user_shift.start_time)
                shift_end_dt = dt_class.combine(today, user_shift.end_time)
                if shift_end_dt <= shift_start_dt:
                    shift_end_dt += timedelta(days=1)
                shift_duration_mins = (shift_end_dt - shift_start_dt).total_seconds() / 60
            else:
                shift_duration_mins = 9 * 60  # Default 9 hours
            minute_rate = daily_salary / shift_duration_mins
            
            # Single source of truth for the late bands lives in signals.py.
            # The pre_save signal recomputes fine_amount on save anyway; resolving
            # here keeps the status and the check-in response consistent with it.
            from .signals import resolve_late_penalty
            resolved_status, fine_amount = resolve_late_penalty(
                late_minutes, shift_duration_mins, buffer_minutes, daily_salary,
                on_date=attendance.date
            )
            attendance.status = resolved_status
        elif now < expected_start:
            # EARLY CHECK-IN → counts as overtime
            early_delta = expected_start - now
            early_checkin_minutes = int(early_delta.total_seconds() / 60)
            logger.debug(f"Early check-in: {early_checkin_minutes} minutes before shift start")
        
        attendance.late_minutes = late_minutes
        attendance.fine_amount = round(fine_amount, 2)
        attendance.early_checkin_minutes = early_checkin_minutes
        attendance.gap_deduction = 0.0  # Reset at check-in; only computed at checkout
        attendance.save()

        # Log successful check-in
        ActivityLog.log_activity(
            action='CHECK_IN',
            status='SUCCESS',
            message=f"Check-in successful at {current_time}",
            user=user,
            location=user.location,
            activity_data={
                'time_in': str(attendance.time_in),
                'shift': user_shift.name if user_shift else 'Default',
                'late_minutes': late_minutes,
                'fine_amount': float(attendance.fine_amount),
                'status': attendance.status,
                'session_number': 1,
                'similarity_score': round(best_similarity, 4) if best_similarity else None
            },
            ip_address=ip_address,
            user_agent=user_agent
        )

        return Response(
            {
                "status": "success",
                "employee_name": f"{user.first_name} {user.last_name}",
                "message": "Check-in successful",
                "time_in": str(attendance.time_in),
                "shift": user_shift.name if user_shift else "Default (10:00 AM)",
                "late_minutes": late_minutes,
                "fine_amount": attendance.fine_amount,
                "session_number": 1,
            },
            status=status.HTTP_201_CREATED
        )

    elif attendance_type == 'OUT':
        # CHECK OUT LOGIC (Multi-Session)
        from .models import AttendanceSession
        try:
            attendance = Attendance.objects.get(user=user, date=today)
        except Attendance.DoesNotExist:
            # Log check-out without check-in
            ActivityLog.log_activity(
                action='CHECK_OUT',
                status='FAILED',
                message="No check-in record found for today",
                user=user,
                location=user.location,
                activity_data={'date': str(today)},
                ip_address=ip_address,
                user_agent=user_agent
            )
            return Response({"error": "No check-in record found for today"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Find the open session (no time_out)
        open_session = attendance.sessions.filter(time_out__isnull=True).order_by('-session_number').first()
        
        if not open_session:
            # No open session — all sessions are already closed
            ActivityLog.log_activity(
                action='CHECK_OUT',
                status='WARNING',
                message="No open session to check out from",
                user=user,
                location=user.location,
                activity_data={
                    'last_time_out': str(attendance.time_out),
                    'attempt_time': str(current_time)
                },
                ip_address=ip_address,
                user_agent=user_agent
            )
            return Response({
                "status": "failed",
                "message": "No open session. Please check in first.",
                "employee_name": f"{user.first_name} {user.last_name}",
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Minimum 5 minutes between session check-in and check-out
        MIN_CHECKOUT_DELAY_MINUTES = 5
        session_checkin_dt = datetime.combine(today, open_session.time_in)
        # Make timezone-aware if USE_TZ is enabled
        if timezone.is_aware(now):
            session_checkin_dt = timezone.make_aware(session_checkin_dt)
        minutes_since_checkin = (now - session_checkin_dt).total_seconds() / 60

        if minutes_since_checkin < MIN_CHECKOUT_DELAY_MINUTES:
            remaining_minutes = int(MIN_CHECKOUT_DELAY_MINUTES - minutes_since_checkin)
            ActivityLog.log_activity(
                action='CHECK_OUT',
                status='WARNING',
                message=f"Check-out too soon. Wait {remaining_minutes} more minute(s)",
                user=user,
                location=user.location,
                activity_data={
                    'session_time_in': str(open_session.time_in),
                    'session_number': open_session.session_number,
                    'attempt_time': str(current_time),
                    'minutes_since_checkin': round(minutes_since_checkin, 1)
                },
                ip_address=ip_address,
                user_agent=user_agent
            )
            return Response({
                "status": "failed",
                "message": f"Cannot check-out within {MIN_CHECKOUT_DELAY_MINUTES} minutes of check-in. Please wait {remaining_minutes} more minute(s).",
                "employee_name": f"{user.first_name} {user.last_name}",
                "time_in": str(open_session.time_in)
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Close the session
        open_session.time_out = current_time
        session_duration = int((now - session_checkin_dt).total_seconds() / 60)
        open_session.duration_minutes = session_duration
        open_session.save()
        
        # Update attendance.time_out to latest check-out
        attendance.time_out = current_time
        
        # Recalculate total_worked_minutes from ALL sessions
        all_sessions = attendance.sessions.all()
        total_worked = sum(s.duration_minutes for s in all_sessions)
        attendance.total_worked_minutes = total_worked
        
        # ──────────────────────────────────────────────────────────
        # SIMPLIFIED OT / GAP MODEL
        # OT  = max(0, total_worked - shift_duration)
        # Gap = max(0, effective_shift - total_worked)  [only when total_worked < shift]
        # Early checkout detection is separate (for fine only)
        # ──────────────────────────────────────────────────────────
        overtime_minutes = 0
        overtime_amount = 0.0
        early_checkout_minutes = 0
        gap_deduction = 0.0
        user_shift = attendance.shift or user.shift
        
        if user_shift:
            from datetime import datetime as dt_class
            shift_start_dt = dt_class.combine(today, user_shift.start_time)
            shift_end_dt = dt_class.combine(today, user_shift.end_time)
            if shift_end_dt <= shift_start_dt:
                shift_end_dt += timedelta(days=1)
            shift_duration_mins = int((shift_end_dt - shift_start_dt).total_seconds() / 60)
            buffer_minutes = user_shift.buffer_minutes or 0
            
            # Salary data for minute_rate
            payroll = Payroll.objects.filter(user=user, month=now.replace(day=1)).first()
            salary_base = float(payroll.base_salary if payroll else user.salary_per_month)
            esi_val = float(payroll.esi_deductions if payroll else user.esi_amount)
            epf_val = float(payroll.epf_deductions if payroll else user.epf_amount)
            effective_salary = salary_base - esi_val - epf_val
            import calendar
            _, DAYS_IN_MONTH = calendar.monthrange(today.year, today.month)
            daily_salary = effective_salary / DAYS_IN_MONTH
            minute_rate = daily_salary / shift_duration_mins if shift_duration_mins > 0 else 0
            
            # ─── EARLY CHECKOUT DETECTION (for fine only) ───
            expected_end = now.replace(
                hour=user_shift.end_time.hour,
                minute=user_shift.end_time.minute,
                second=0, microsecond=0
            )
            expected_end_minus_buffer = expected_end - timedelta(minutes=buffer_minutes)
            
            if now < expected_end_minus_buffer:
                delta = expected_end - now
                early_checkout_minutes = int(delta.total_seconds() / 60)
                logger.debug(f"Early checkout detected: {early_checkout_minutes} min before shift end")
            
            # ─── EFFECTIVE SHIFT (benchmark for OT & gap) ───
            # Clamp to 0: if early_checkout_minutes alone exceeds shift_duration,
            # effective_shift must not go negative (would cause fake OT)
            effective_shift = max(0, shift_duration_mins - (attendance.late_minutes or 0) - early_checkout_minutes)
            
            # ─── OVERTIME ───
            # OT = total_worked minus effective_shift (what was expected)
            if total_worked > effective_shift:
                overtime_minutes = total_worked - effective_shift
                overtime_amount = round(overtime_minutes * minute_rate, 2)
            
            # ─── GAP DEDUCTION ───
            # Gap = effective_shift minus total_worked (what was missing)
            # Apply same buffer tolerance as late/early fines: gaps within the
            # shift buffer (10 min client requirement) are forgiven.
            if total_worked < effective_shift:
                gap_minutes = effective_shift - total_worked
                if gap_minutes > buffer_minutes:
                    gap_deduction = round(gap_minutes * minute_rate, 2)
        
        attendance.overtime_minutes = overtime_minutes
        attendance.overtime_amount = overtime_amount
        attendance.early_checkout_minutes = early_checkout_minutes
        attendance.gap_deduction = gap_deduction
        # early_checkout_fine will be computed by the pre_save signal
        attendance.save()
        
        # Log successful check-out
        session_num = open_session.session_number
        ActivityLog.log_activity(
            action='CHECK_OUT',
            status='SUCCESS',
            message=f"Session {session_num} check-out at {current_time}",
            user=user,
            location=user.location,
            activity_data={
                'time_in': str(attendance.time_in),
                'time_out': str(attendance.time_out),
                'session_number': session_num,
                'session_duration': session_duration,
                'total_worked_minutes': total_worked,
                'gap_deduction': float(gap_deduction),
                'shift': user_shift.name if user_shift else 'Default',
                'overtime_minutes': overtime_minutes,
                'overtime_amount': float(overtime_amount),
                'early_checkout_minutes': early_checkout_minutes,
                'early_checkout_fine': float(attendance.early_checkout_fine),
                'similarity_score': round(best_similarity, 4) if best_similarity else None
            },
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        response_data = {
            "status": "success",
            "message": f"Session {session_num} check-out successful",
            "employee_name": f"{user.first_name} {user.last_name}",
            "time_out": str(attendance.time_out),
            "session_number": session_num,
            "session_duration": session_duration,
            "total_worked_minutes": total_worked,
            "gap_deduction": float(gap_deduction),
            "overtime_minutes": overtime_minutes,
            "overtime_amount": round(overtime_amount, 2)
        }
        
        # Add early checkout info if applicable
        if early_checkout_minutes > 0:
            response_data["early_checkout_minutes"] = early_checkout_minutes
            response_data["early_checkout_fine"] = float(attendance.early_checkout_fine)
            response_data["message"] = f"Session {session_num} check-out (early by {early_checkout_minutes} mins)"
        
        return Response(response_data)
    
    return Response({"error": "Invalid attendance type"}, status=status.HTTP_400_BAD_REQUEST)


# ==========================
# REGISTER EMPLOYEE (MOBILE APP)
# ==========================
@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def register_employee(request):
    # Get request metadata for logging
    ip_address, user_agent = get_request_metadata(request)
    
    # Extract fields early for logging even if registration fails
    name = request.data.get("name") or request.data.get("full_name") or request.data.get("fullName")
    contact = request.data.get("contact") or request.data.get("phone") or request.data.get("mobile")
    department = request.data.get("department") or request.data.get("dept")
    location_code = request.data.get("location")  # Location code, e.g. "HO"; required
    
    try:
        # Debug Logging - log ALL received data for debugging
        logger.info(f"=== REGISTRATION REQUEST DEBUG ===")
        logger.info(f"Data Keys: {list(request.data.keys())}")
        logger.info(f"Files Keys: {list(request.FILES.keys())}")
        logger.info(f"Data: name={name}, contact={contact}, department={department}, location={location_code}")
        
        # Log all files received with details
        for key, file in request.FILES.items():
            logger.info(f"File '{key}': name={file.name}, size={file.size}, content_type={file.content_type}")
        
        # Accept alternate field names for flexibility (Android apps may use different names)
        email = request.data.get("email", "")
        
        # Check multiple possible field names for the image
        image_field_names = ["image", "photo", "face_image", "file", "picture", "img", "faceImage", "profileImage"]
        image_file = None
        for field_name in image_field_names:
            if field_name in request.FILES:
                image_file = request.FILES[field_name]
                logger.info(f"Found image in field: '{field_name}'")
                break
        
        if not image_file and request.FILES:
            # Take the first file if none of the expected names match
            first_key = list(request.FILES.keys())[0]
            image_file = request.FILES[first_key]
            logger.info(f"Using first available file: '{first_key}'")
        
        embedding_str = request.data.get("embedding")  # Legacy support

        if not all([name, department, contact]):
            ActivityLog.log_activity(
                action='REGISTER',
                status='FAILED',
                message="Missing required fields",
                contact_attempted=contact,
                name_attempted=name,
                activity_data={
                    'department': department,
                    'location_code': location_code,
                    'missing_fields': [f for f in ['name', 'department', 'contact'] if not locals().get(f)]
                },
                ip_address=ip_address,
                user_agent=user_agent
            )
            return error_response("Please fill in all required fields: Name, Department, and Contact number")

        # Lookup location from database
        try:
            location = Location.objects.get(code=location_code, is_active=True)
        except Location.DoesNotExist:
            ActivityLog.log_activity(
                action='REGISTER',
                status='FAILED',
                message=f"Invalid location code: {location_code}",
                contact_attempted=contact,
                name_attempted=name,
                activity_data={'location_code': location_code},
                ip_address=ip_address,
                user_agent=user_agent
            )
            if not location_code:
                return error_response("Location is required")
            return error_response(f"Invalid location code: {location_code}")

        if User.objects.filter(contact=contact).exists():
            ActivityLog.log_activity(
                action='REGISTER',
                status='FAILED',
                message="Phone number already registered",
                contact_attempted=contact,
                name_attempted=name,
                location=location,
                activity_data={'duplicate_contact': contact},
                ip_address=ip_address,
                user_agent=user_agent
            )
            return error_response("This phone number is already registered. Please use a different number.")
            
        incoming_embedding = None
        
        # 1. Try Image Processing
        if image_file:
            # Log image details for debugging
            try:
                image_file.seek(0, 2)  # Seek to end
                file_size = image_file.tell()
                image_file.seek(0)  # Reset
                content_type = getattr(image_file, 'content_type', 'unknown')
                file_name = getattr(image_file, 'name', 'unknown')
                logger.info(f"Registration image received: name={file_name}, size={file_size} bytes, content_type={content_type}")
                
                # Read first few bytes to check format
                first_bytes = image_file.read(16)
                image_file.seek(0)
                logger.debug(f"Image first bytes (hex): {first_bytes.hex()}")
            except Exception as e:
                logger.warning(f"Could not log image details: {e}")
            
            logger.debug("Processing uploaded image for registration...")
            handler = FaceHandler.get_instance()
            raw_embedding = handler.process_image(image_file)
            if raw_embedding is None:
                logger.warning(f"No face detected in registration image for {name} ({contact})")
                ActivityLog.log_activity(
                    action='REGISTER',
                    status='FAILED',
                    message="No face detected in registration image",
                    contact_attempted=contact,
                    name_attempted=name,
                    location=location,
                    ip_address=ip_address,
                    user_agent=user_agent
                )
                return error_response("Full face not visible, retry")
            incoming_embedding = normalize(raw_embedding)
        
        # 2. Try Legacy Embedding
        elif embedding_str:
            try:
                incoming_embedding = normalize(list(map(float, embedding_str)))
            except (ValueError, TypeError):
                return error_response("Invalid face data format")
        
        else:
            ActivityLog.log_activity(
                action='REGISTER',
                status='FAILED',
                message="No face image provided",
                contact_attempted=contact,
                name_attempted=name,
                location=location,
                ip_address=ip_address,
                user_agent=user_agent
            )
            return error_response("Please capture your face photo to register")


        # ---- DUPLICATE FACE CHECK (across ALL locations) ----
        # Check against ALL users with face encodings to prevent duplicate registrations
        existing_users = User.objects.exclude(face_encoding__isnull=True).exclude(face_encoding='')
        
        best_match_user = None
        best_match_similarity = 0.0
        
        for user in existing_users:
            try:
                stored_embedding = json.loads(user.face_encoding)
                stored_embedding = normalize(stored_embedding)
                
                similarity = cosine_similarity(incoming_embedding, stored_embedding)
                logger.debug(f"Comparing with {user.contact} | similarity={similarity:.4f}")

                # Track the best match
                if similarity > best_match_similarity:
                    best_match_similarity = similarity
                    best_match_user = user
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"Error comparing with user {user.id}: {e}")
                continue

        # Block on the CLOSEST match (not the first one over the threshold),
        # so the error and log name the most likely duplicate.
        if best_match_user and best_match_similarity > REGISTRATION_DUPLICATE_THRESHOLD:
            existing_location = best_match_user.location.name if best_match_user.location else 'Unknown'
            logger.warning(f"DUPLICATE DETECTED! {best_match_user.contact} at {existing_location} with similarity={best_match_similarity:.4f}")
            ActivityLog.log_activity(
                action='REGISTER',
                status='FAILED',
                message=f"Duplicate face detected - matches {best_match_user.contact} at {existing_location}",
                contact_attempted=contact,
                name_attempted=name,
                location=location,
                activity_data={
                    'matched_user_id': best_match_user.id,
                    'matched_contact': best_match_user.contact,
                    'matched_location': existing_location,
                    'similarity': round(best_match_similarity, 4),
                    'threshold': REGISTRATION_DUPLICATE_THRESHOLD
                },
                ip_address=ip_address,
                user_agent=user_agent
            )
            return error_response(
                f"This face is already registered at {existing_location}. Contact admin if this is an error.",
                status_code=status.HTTP_409_CONFLICT
            )

        # Log the best match even if below threshold (for debugging)
        suspicious_match = None
        if best_match_user:
            logger.debug(f"Best match was {best_match_user.contact} with similarity={best_match_similarity:.4f} (threshold={REGISTRATION_DUPLICATE_THRESHOLD})")
            # Flag suspicious matches for admin review
            if best_match_similarity >= REGISTRATION_REVIEW_THRESHOLD:
                suspicious_match = {
                    "contact": best_match_user.contact,
                    "similarity": round(best_match_similarity, 4),
                    "location": best_match_user.location.name if best_match_user.location else 'Unknown'
                }
                logger.warning("Suspicious match detected but below threshold!")

        # ---- SAVE EMPLOYEE (USER) ----
        random_password = secrets.token_urlsafe(16)
        
        name_parts = name.split()
        first_name = name_parts[0] if name_parts else ""
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

        # Use contact as username for uniqueness
        username = contact

        # Get shift from request (sent from mobile app dropdown)
        from .models import Shift
        shift_value = request.data.get("shift_id") or request.data.get("shift")
        shift = None
        logger.debug(f"Shift value received: {shift_value} (type: {type(shift_value).__name__})")
        
        if shift_value:
            try:
                # Try as ID first
                shift = Shift.objects.get(id=int(shift_value), is_active=True)
                logger.debug(f"Found shift by ID: {shift.name}")
            except (Shift.DoesNotExist, ValueError, TypeError):
                # Try as exact name match
                try:
                    shift = Shift.objects.get(name__iexact=str(shift_value), is_active=True)
                    logger.debug(f"Found shift by exact name: {shift.name}")
                except Shift.DoesNotExist:
                    # Try fuzzy matching - extract times and compare
                    import re
                    shift_str = str(shift_value).lower()
                    # Extract times like "10:00" or "10" from the string
                    time_pattern = r'(\d{1,2}):?(\d{2})?\s*(am|pm)?'
                    matches = re.findall(time_pattern, shift_str, re.IGNORECASE)
                    
                    if len(matches) >= 2:
                        # Try to match by start time
                        start_hour = int(matches[0][0])
                        end_hour = int(matches[1][0])
                        
                        for s in Shift.objects.filter(is_active=True):
                            s_start = s.start_time.hour
                            s_end = s.end_time.hour
                            # Handle AM/PM conversion
                            if 'pm' in shift_str and start_hour < 12 and start_hour != 12:
                                start_hour += 12
                            if s_start == start_hour or (s_start == start_hour % 12) or (s_start % 12 == start_hour):
                                shift = s
                                logger.debug(f"Found shift by time match: {shift.name}")
                                break
                    
                    if not shift:
                        # Last resort: use first active shift as default
                        shift = Shift.objects.filter(is_active=True).first()
                        if shift:
                            logger.debug(f"Using default shift: {shift.name}")
                        else:
                            logger.warning("No shifts found in database")

        # Reset file pointer before saving to S3
        if image_file:
            image_file.seek(0)
        
        user = User.objects.create_user(
            username=username,
            email=email if email else None,

            password=random_password,
            first_name=first_name,
            last_name=last_name,
            role='EMPLOYEE',
            location=location,
            shift=shift,
            department=department,
            contact=contact,
            face_encoding=json.dumps(incoming_embedding),
            profile_picture=image_file
        )



        # Log successful registration
        activity_data = {
            'department': department,
            'shift': shift.name if shift else None,
            'email': email if email else None,
            'best_match_similarity': round(best_match_similarity, 4) if best_match_similarity else None
        }
        
        if suspicious_match:
            activity_data['suspicious_match'] = suspicious_match
            ActivityLog.log_activity(
                action='REGISTER',
                status='WARNING',
                message=f"Registration successful with suspicious match (similarity: {suspicious_match['similarity']})",
                user=user,
                location=location,
                activity_data=activity_data,
                ip_address=ip_address,
                user_agent=user_agent
            )
        else:
            ActivityLog.log_activity(
                action='REGISTER',
                status='SUCCESS',
                message=f"Employee registered successfully",
                user=user,
                location=location,
                activity_data=activity_data,
                ip_address=ip_address,
                user_agent=user_agent
            )

        response_data = {
            "status": "success",
            "employee_name": f"{user.first_name} {user.last_name}",
            "location": user.location.name if user.location else '',
            "message": "Employee registered successfully",
            "user_id": user.id
        }
        
        # Add warning if suspicious match found
        if suspicious_match:
            response_data["warning"] = "Suspicious match detected - please verify this is not a duplicate"
            response_data["suspicious_match"] = suspicious_match
        
        return Response(response_data, status=status.HTTP_201_CREATED)

    except Exception as e:
        logger.exception(f"Register error: {e}")
        # Log the exception
        ActivityLog.log_activity(
            action='REGISTER',
            status='FAILED',
            message="Registration failed due to unexpected error",
            contact_attempted=contact,
            name_attempted=name,
            error_details=str(e),
            ip_address=ip_address,
            user_agent=user_agent
        )
        # fallback if race condition happens
        if "unique" in str(e).lower():
            return error_response("This phone number is already registered")
        return error_response("Registration failed. Please try again.", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==========================
# FACE-BASED ATTENDANCE
# ==========================
@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def mark_attendance(request):
    try:
        return handle_attendance_logic(request.data, request.FILES, request)
    except Exception as e:
        logger.exception(f"Attendance error: {e}")
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def mark_attendance_face(request):
    try:
        return handle_attendance_logic(request.data, request.FILES, request)
    except Exception as e:
        logger.exception(f"Attendance error: {e}")
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ==========================
# WEB DASHBOARD VIEWS
# ==========================

class RegisterView(generics.GenericAPIView):
    """Web registration for Admin accounts (location-specific)"""
    permission_classes = [permissions.AllowAny]
    serializer_class = UserSerializer

    def post(self, request, *args, **kwargs):
        logger.debug(f"Web register request - Data keys: {list(request.data.keys())}")
        
        email = request.data.get('email')
        password = request.data.get('password')
        role = request.data.get('role', 'ADMIN').upper()
        # region agent log
        debug_log({
            "sessionId": "debug-session",
            "runId": "run1",
            "hypothesisId": "A",
            "location": "views.py:RegisterView.post.entry",
            "message": "register_entry",
            "data": {
                "has_email": bool(email),
                "has_password": bool(password),
                "role": role,
                "location_input": request.data.get('location')
            },
            "timestamp": int(time_module.time() * 1000)
        })
        # endregion
        
        if not email or not password:
            return Response({"error": "Email and Password are required"}, status=status.HTTP_400_BAD_REQUEST)

        # Lookup location from database (accepts ID or code)
        from .models import Location
        location_input = request.data.get('location')
        try:
            # Try by ID first if numeric
            if str(location_input).isdigit():
                location = Location.objects.get(id=int(location_input), is_active=True)
            else:
                # Otherwise try by code
                location = Location.objects.get(code=location_input, is_active=True)
        except Location.DoesNotExist:
            valid_codes = list(Location.objects.filter(is_active=True).values_list('code', flat=True))
            return Response({"error": f"Invalid location '{location_input}'. Valid: {valid_codes}"}, status=status.HTTP_400_BAD_REQUEST)

        # Only ADMIN registration via web
        if role not in ['ADMIN']:
            return Response({"error": "Only ADMIN role can be registered via web. Employees are registered via mobile app."}, status=status.HTTP_400_BAD_REQUEST)

        # Check if user exists
        if User.objects.filter(email=email).exists():
            return Response({"error": "User with this email already exists"}, status=status.HTTP_400_BAD_REQUEST)

        # Create admin user (pending approval)
        logger.info(f"Creating new admin {email} for location {location.name}")
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            user.set_password(password)
            user.role = 'ADMIN'
            user.location = location
            user.is_approved = False  # Requires Django admin approval
            user.save()
            # region agent log
            debug_log({
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "B",
                "location": "views.py:RegisterView.post.success",
                "message": "register_success",
                "data": {
                    "user_id": user.id,
                    "location_id": location.id
                },
                "timestamp": int(time_module.time() * 1000)
            })
            # endregion
            
            return Response({
                "message": "Admin registration submitted. Awaiting approval from system administrator.",
                "user_id": user.id,
                "location": location.name,
                "pending_approval": True
            }, status=status.HTTP_201_CREATED)
        # region agent log
        debug_log({
            "sessionId": "debug-session",
            "runId": "run1",
            "hypothesisId": "C",
            "location": "views.py:RegisterView.post.invalid",
            "message": "register_invalid",
            "data": {
                "error_fields": list(serializer.errors.keys())
            },
            "timestamp": int(time_module.time() * 1000)
        })
        # endregion
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class DashboardView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # Security Check: Only ADMIN can view the dashboard stats
        logger.debug(f"Dashboard request from user with role: {request.user.role}")
        if request.user.role != 'ADMIN':
            return Response({"error": "Unauthorized. Only Admins can view this dashboard."}, status=status.HTTP_403_FORBIDDEN)
        
        # Filter by admin's location
        admin_location = request.user.location
        
        logger.debug(f"Dashboard - Admin: {request.user.email}, Location: {admin_location.code if admin_location else 'NONE'}")
        
        today = timezone.localtime().date()
        
        total_employees = User.objects.filter(role='EMPLOYEE', location=admin_location).count()
        logger.debug(f"Dashboard - Total employees: {total_employees}, Today: {today}")
        
        present_today = Attendance.objects.filter(
            date=today, 
            status__in=['PRESENT', 'HALF_DAY', 'LATE'],
            user__location=admin_location
        ).count()
        logger.debug(f"Dashboard - Present today: {present_today}")
        
        # Recent Attendance Logs (filtered by location)
        recent_attendance_qs = Attendance.objects.filter(
            user__location=admin_location
        ).select_related('user').order_by('-date', '-time_in')[:10]
        recent_attendance = []
        for att in recent_attendance_qs:
            recent_attendance.append({
                "id": att.id,
                "employee_name": f"{att.user.first_name} {att.user.last_name}",
                "contact": att.user.contact,
                "date": att.date,
                "time_in": att.time_in,
                "time_out": att.time_out,
                "status": att.status
            })

        # Recent Registrations (filtered by location)
        recent_employees_qs = User.objects.filter(
            role='EMPLOYEE', 
            location=admin_location
        ).order_by('-date_joined')[:5]
        recent_employees = []
        for emp in recent_employees_qs:
            recent_employees.append({
                "id": emp.id,
                "name": f"{emp.first_name} {emp.last_name}",
                "contact": emp.contact,
                "department": emp.department,
                "joined_at": emp.date_joined
            })

        data = {
            "location": admin_location.id if admin_location else None,
            "location_display": admin_location.name if admin_location else '',
            "total_employees": total_employees,
            "present_today": present_today,
            "pending_payroll": Payroll.objects.filter(status='PENDING', user__location=admin_location).count(),
            "recent_attendance": recent_attendance,
            "recent_registrations": recent_employees
        }
        return Response(data)

class UserViewSet(viewsets.ModelViewSet):
    """User ViewSet - filtered by admin's location"""
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'ADMIN':
            # Admin sees only employees in their location
            return User.objects.filter(location=user.location, role='EMPLOYEE')
        # Django admin sees all
        return User.objects.all()

    def partial_update(self, request, *args, **kwargs):
        """
        PATCH an employee.

        Salary/ESI/EPF edits deliberately do NOT touch existing attendance records
        (SIO-132). Each record carries the salary_snapshot frozen when it was created,
        so the new figure applies only to records created from now on. This method
        previously re-saved the current month's records to reprice them, which - on top
        of the global sweep in the User post_save signal - rewrote closed payroll months.
        """
        return super().partial_update(request, *args, **kwargs)


class AttendanceViewSet(viewsets.ModelViewSet):
    """Attendance ViewSet - filtered by admin's location"""
    queryset = Attendance.objects.all()
    serializer_class = AttendanceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = Attendance.objects.all()
        
        # Filter by admin's location
        if user.role == 'ADMIN':
            queryset = queryset.filter(user__location=user.location)
        
        # Date filter
        date_str = self.request.query_params.get('date', None)
        if date_str is not None:
            queryset = queryset.filter(date=date_str)
        
        # Filter by specific employee (for employee detail page)
        user_id = self.request.query_params.get('user', None)
        if user_id is not None:
            queryset = queryset.filter(user_id=user_id)
        
        # Filter by month (YYYY-MM format, for monthly attendance view)
        month_str = self.request.query_params.get('month', None)
        if month_str is not None:
            try:
                year, month = month_str.split('-')
                queryset = queryset.filter(date__year=int(year), date__month=int(month))
            except (ValueError, IndexError):
                pass  # Invalid format, skip filter
        
        return queryset.select_related('user', 'shift').prefetch_related('sessions')

    @action(detail=True, methods=['patch'])
    def edit(self, request, pk=None):
        """
        Admin can edit: status, fine_amount, early_checkout_fine, overtime_amount,
        overtime_minutes, late_minutes, shift, time_in, time_out.

        When time_in or time_out is changed, the record is fully recalculated
        (late_minutes, status, early_checkout_minutes, overtime_minutes, gap_deduction,
        fine_amount, overtime_amount, early_checkout_fine) — unless individual fields
        have been manually flagged as edited (fine_edited = True).
        """
        attendance = self.get_object()

        from .models import AttendanceEditLog
        # Capture old values BEFORE any changes for audit logging
        old_values = {}
        for field in AttendanceEditLog.TRACKED_FIELDS:
            raw = getattr(attendance, field)
            old_values[field] = '' if raw is None else str(raw)

        # ── time_in / time_out ─────────────────────────────────────────────────
        time_changed = False
        if 'time_in' in request.data:
            val = request.data['time_in']
            if val in (None, '', 'null'):
                attendance.time_in = None
            else:
                try:
                    from datetime import time as dt_time
                    attendance.time_in = dt_time.fromisoformat(str(val))
                except ValueError:
                    return Response({"error": "Invalid time_in format. Use HH:MM or HH:MM:SS"}, status=status.HTTP_400_BAD_REQUEST)
            time_changed = True

        if 'time_out' in request.data:
            val = request.data['time_out']
            if val in (None, '', 'null'):
                attendance.time_out = None
            else:
                try:
                    from datetime import time as dt_time
                    attendance.time_out = dt_time.fromisoformat(str(val))
                except ValueError:
                    return Response({"error": "Invalid time_out format. Use HH:MM or HH:MM:SS"}, status=status.HTTP_400_BAD_REQUEST)
            time_changed = True

        # ── Validate time order ────────────────────────────────────────────────
        # Both must be set (or the update omits one of them) before we compare.
        if attendance.time_in and attendance.time_out:
            from datetime import datetime as _dt_check
            tin_cmp  = _dt_check.combine(attendance.date, attendance.time_in)
            tout_cmp = _dt_check.combine(attendance.date, attendance.time_out)
            if tout_cmp <= tin_cmp:
                return Response(
                    {"error": "Check-out time must be after check-in time."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # ── Sync session records when time_in / time_out is edited ────────────
        # total_worked_minutes is the SUM of session durations. If we only update
        # attendance.time_in / time_out without touching the sessions, the worked
        # total stays stale. So we mirror the changes into the actual sessions.
        from .models import AttendanceSession
        if time_changed:
            sessions_qs = attendance.sessions.order_by('session_number', 'time_in')
            sessions_list = list(sessions_qs)

            if sessions_list:
                from datetime import datetime as _dt
                att_date = attendance.date

                if len(sessions_list) == 1:
                    only = sessions_list[0]
                    if 'time_in' in request.data and attendance.time_in is not None:
                        only.time_in = attendance.time_in
                    if 'time_out' in request.data and attendance.time_out is not None:
                        only.time_out = attendance.time_out
                    
                    # Sanity check: start vs end
                    if only.time_in and only.time_out and only.time_in > only.time_out:
                        only.time_out = None
                        
                    # Recompute duration
                    if only.time_out:
                        tin_dt  = _dt.combine(att_date, only.time_in)
                        tout_dt = _dt.combine(att_date, only.time_out)
                        only.duration_minutes = max(0, int((tout_dt - tin_dt).total_seconds() / 60))
                    else:
                        only.duration_minutes = 0
                    only.save()
                else:
                    # time_in edit → update Session #1 (first check-in of the day)
                    if 'time_in' in request.data and attendance.time_in is not None:
                        first_session = sessions_list[0]
                        first_session.time_in = attendance.time_in
                        # If session now starts AFTER its end, clear the end time
                        if first_session.time_out and first_session.time_in > first_session.time_out:
                            first_session.time_out = None
                        # Recompute duration_minutes from the new times
                        if first_session.time_out:
                            tin_dt  = _dt.combine(att_date, first_session.time_in)
                            tout_dt = _dt.combine(att_date, first_session.time_out)
                            first_session.duration_minutes = max(0, int((tout_dt - tin_dt).total_seconds() / 60))
                        else:
                            first_session.duration_minutes = 0
                        first_session.save()

                    # time_out edit → update last session (last checkout of the day)
                    if 'time_out' in request.data and attendance.time_out is not None:
                        last_session = sessions_list[-1]
                        last_session.time_out = attendance.time_out
                        # If session now ends BEFORE it starts, clear time_out
                        if last_session.time_in and last_session.time_out < last_session.time_in:
                            last_session.time_out = None
                        # Recompute duration_minutes from the new times
                        if last_session.time_out:
                            tin_dt  = _dt.combine(att_date, last_session.time_in)
                            tout_dt = _dt.combine(att_date, last_session.time_out)
                            last_session.duration_minutes = max(0, int((tout_dt - tin_dt).total_seconds() / 60))
                        else:
                            last_session.duration_minutes = 0
                        last_session.save()

            # ── Clear Django's prefetch cache ─────────────────────────────────
            # get_object() uses prefetch_related('sessions'), so attendance has a
            # stale session cache. After updating sessions in DB, we must clear it
            # so that att.sessions.all() inside recalculate_attendance_record
            # fetches the fresh rows (with updated duration_minutes).
            try:
                del attendance._prefetched_objects_cache
            except AttributeError:
                pass

        # ── fine_amount ────────────────────────────────────────────────────────
        # Only flag as explicitly changed if the submitted value DIFFERS from what
        # is already stored. Sending the same value (e.g. no-op save) must NOT
        # lock fine_edited=True — mirrors the same-value guard on status above.
        fine_explicitly_changed = False
        early_checkout_fine_explicitly_changed = False
        overtime_explicitly_changed = False
        if 'fine_amount' in request.data:
            try:
                new_fine = round(float(request.data['fine_amount']), 2)
                current_fine = round(float(attendance.fine_amount or 0), 2)
                attendance.fine_amount = new_fine
                if abs(new_fine - current_fine) > 0.001:
                    fine_explicitly_changed = True
            except (ValueError, TypeError):
                return Response({"error": "Invalid fine_amount"}, status=status.HTTP_400_BAD_REQUEST)

        # ── status ────────────────────────────────────────────────────────────
        # Track whether admin explicitly CHANGED the status (not just sent the same value).
        # Sending the current status unchanged should not lock status_edited=True.
        status_explicitly_changed = False
        if 'status' in request.data:
            valid_statuses = ['PRESENT', 'ABSENT', 'LATE', 'HALF_DAY', 'LEAVE', 'HOLIDAY']
            if request.data['status'] in valid_statuses:
                if request.data['status'] != attendance.status:
                    # Admin actually picked a different status
                    status_explicitly_changed = True
                attendance.status = request.data['status']
            else:
                return Response({"error": f"Invalid status. Must be one of: {valid_statuses}"}, status=status.HTTP_400_BAD_REQUEST)

        # ── late_minutes ──────────────────────────────────────────────────────
        if 'late_minutes' in request.data:
            try:
                attendance.late_minutes = int(request.data['late_minutes'])
            except (ValueError, TypeError):
                return Response({"error": "Invalid late_minutes"}, status=status.HTTP_400_BAD_REQUEST)

        # ── overtime fields ───────────────────────────────────────────────────
        if 'overtime_minutes' in request.data:
            try:
                attendance.overtime_minutes = int(request.data['overtime_minutes'])
            except (ValueError, TypeError):
                return Response({"error": "Invalid overtime_minutes"}, status=status.HTTP_400_BAD_REQUEST)

        if 'overtime_amount' in request.data:
            try:
                new_overtime = round(float(request.data['overtime_amount']), 2)
                current_overtime = round(float(attendance.overtime_amount or 0), 2)
                attendance.overtime_amount = new_overtime
                if abs(new_overtime - current_overtime) > 0.001:
                    overtime_explicitly_changed = True
            except (ValueError, TypeError):
                return Response({"error": "Invalid overtime_amount"}, status=status.HTTP_400_BAD_REQUEST)

        # ── early checkout fields ─────────────────────────────────────────────
        if 'early_checkout_minutes' in request.data:
            try:
                attendance.early_checkout_minutes = int(request.data['early_checkout_minutes'])
            except (ValueError, TypeError):
                return Response({"error": "Invalid early_checkout_minutes"}, status=status.HTTP_400_BAD_REQUEST)

        if 'early_checkout_fine' in request.data:
            try:
                new_ecf = round(float(request.data['early_checkout_fine']), 2)
                current_ecf = round(float(attendance.early_checkout_fine or 0), 2)
                attendance.early_checkout_fine = new_ecf
                # If the early checkout fine changed without a time edit, it's a
                # manual override — treat as fine_explicitly_changed so fine_edited is locked.
                if abs(new_ecf - current_ecf) > 0.001:
                    early_checkout_fine_explicitly_changed = True
            except (ValueError, TypeError):
                return Response({"error": "Invalid early_checkout_fine"}, status=status.HTTP_400_BAD_REQUEST)

        # ── shift ─────────────────────────────────────────────────────────────
        if 'shift_id' in request.data or 'shift' in request.data:
            from .models import Shift
            shift_id = request.data.get('shift_id') or request.data.get('shift')
            if shift_id:
                try:
                    attendance.shift = Shift.objects.get(id=int(shift_id))
                except (Shift.DoesNotExist, ValueError):
                    return Response({"error": "Invalid shift_id"}, status=status.HTTP_400_BAD_REQUEST)
            else:
                attendance.shift = None

        # ── Apply fine_edited flag ─────────────────────────────────────────────
        # Time changes always take priority: when the admin edits time_in/time_out
        # the intent is for the system to RECALCULATE all derived amounts from the
        # new times. Any fine_amount sent in the same payload is just the stale
        # displayed value, NOT a manual override — so we must clear fine_edited.
        # Only a pure fine edit (no time change) locks fine_edited=True.
        if time_changed:
            # Time edit — recalculation will derive the correct fine from new times
            attendance.fine_edited = False
        elif fine_explicitly_changed:
            # Pure fine edit (no time change) — admin intentionally set a custom fine
            attendance.fine_edited = True

        # Same pattern for status_edited:
        # Only lock it when admin explicitly chose a DIFFERENT status.
        if status_explicitly_changed:
            attendance.status_edited = True
        elif time_changed:
            # Time edit — let recalculate derive the correct status from late_minutes
            attendance.status_edited = False
        if early_checkout_fine_explicitly_changed:
            attendance.early_checkout_fine_edited = True
        elif time_changed:
            # Time edit — let recalculate derive the correct early checkout fine from late_minutes
            attendance.early_checkout_fine_edited = False
        if overtime_explicitly_changed:
            attendance.overtime_edited = True
        elif time_changed:
            # Time edit — let recalculate derive the correct overtime from late_minutes
            attendance.overtime_edited = False

        # ── If time changed, recalculate before saving ────────────────────────
        if time_changed:
            recalculate_attendance_record(attendance, changed_by=request.user, old_vals=old_values)
            # recalculate_attendance_record calls att.save() internally
            # Re-fetch from DB to get the fresh computed values
            attendance.refresh_from_db()
        else:
            # Log all changed fields BEFORE saving (only when NOT doing a time-triggered recalc,
            # because recalculate_attendance_record logs its own field changes)
            for field in AttendanceEditLog.TRACKED_FIELDS:
                new_raw = getattr(attendance, field)
                new_val = '' if new_raw is None else str(new_raw)
                old_val = old_values[field]

                # Numeric fields (fine, OT, gap amounts) can have trailing-zero
                # differences between the DB decimal ('96.30') and the float we just
                # set ('96.3'). Compare as floats with tolerance to avoid false positives.
                try:
                    actually_changed = abs(float(old_val or 0) - float(new_val or 0)) > 0.001
                except (ValueError, TypeError):
                    actually_changed = (old_val != new_val)

                if actually_changed:
                    AttendanceEditLog.objects.create(
                        attendance=attendance,
                        employee=attendance.user,
                        changed_by=request.user,
                        field_name=field,
                        old_value=old_val,
                        new_value=new_val,
                        attendance_date=attendance.date,
                        source='FRONTEND',
                    )
            attendance.save()

        return Response(self.get_serializer(attendance).data)

    @action(detail=False, methods=['post'])
    def create_record(self, request):
        """Create an attendance record for a date where none exists.

        Required: user_id, date
        Optional: time_in (HH:MM:SS), time_out (HH:MM:SS)

        When time_in and time_out are provided the record is fully recalculated
        (late_minutes, status, early checkout, overtime, fines) and a single
        AttendanceSession is created automatically.
        """
        user_id = request.data.get('user_id')
        date_str = request.data.get('date')

        if not user_id or not date_str:
            return Response({"error": "user_id and date are required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            record_date = parse_date(date_str)
            if not record_date:
                raise ValueError
        except ValueError:
            return Response({"error": "Invalid date format (expected YYYY-MM-DD)"}, status=status.HTTP_400_BAD_REQUEST)

        # Don't create duplicate records
        if Attendance.objects.filter(user=target_user, date=record_date).exists():
            return Response({"error": "Attendance record already exists for this date"}, status=status.HTTP_409_CONFLICT)

        # ── Parse optional time_in / time_out ─────────────────────────────────
        from datetime import time as dt_time
        time_in_val = None
        time_out_val = None

        if 'time_in' in request.data and request.data['time_in'] not in (None, '', 'null'):
            try:
                time_in_val = dt_time.fromisoformat(str(request.data['time_in']))
            except ValueError:
                return Response({"error": "Invalid time_in format. Use HH:MM or HH:MM:SS"}, status=status.HTTP_400_BAD_REQUEST)

        if 'time_out' in request.data and request.data['time_out'] not in (None, '', 'null'):
            try:
                time_out_val = dt_time.fromisoformat(str(request.data['time_out']))
            except ValueError:
                return Response({"error": "Invalid time_out format. Use HH:MM or HH:MM:SS"}, status=status.HTTP_400_BAD_REQUEST)

        # ── Validate time order ─────────────────────────────────────────────
        if time_in_val and time_out_val:
            from datetime import datetime as _dt
            tin_cmp  = _dt.combine(record_date, time_in_val)
            tout_cmp = _dt.combine(record_date, time_out_val)
            if tout_cmp <= tin_cmp:
                return Response(
                    {"error": "Check-out time must be after check-in time."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # ── Create the attendance record ───────────────────────────────────
        # Start with ABSENT; recalculate_attendance_record will set the real status
        attendance = Attendance.objects.create(
            user=target_user,
            date=record_date,
            shift=target_user.shift,
            status='ABSENT',
            time_in=time_in_val,
            time_out=time_out_val,
        )

        # ── Create a session when both times are given ───────────────────────
        if time_in_val and time_out_val:
            from .models import AttendanceSession
            from datetime import datetime as _dt2
            tin_dt  = _dt2.combine(record_date, time_in_val)
            tout_dt = _dt2.combine(record_date, time_out_val)
            duration = max(0, int((tout_dt - tin_dt).total_seconds() / 60))
            AttendanceSession.objects.create(
                attendance=attendance,
                session_number=1,
                time_in=time_in_val,
                time_out=time_out_val,
                duration_minutes=duration,
                check_in_mode='MANUAL',
            )
            # Recalculate all derived fields (status, late/early mins, fines, OT, gap)
            recalculate_attendance_record(attendance, changed_by=request.user)
            attendance.refresh_from_db()

        # Audit log
        from .models import AttendanceEditLog
        AttendanceEditLog.objects.create(
            attendance=attendance,
            employee=target_user,
            changed_by=request.user,
            field_name='status',
            old_value='(no record)',
            new_value=attendance.status,
            attendance_date=record_date,
            source='FRONTEND',
        )

        return Response(self.get_serializer(attendance).data, status=status.HTTP_201_CREATED)


def recalculate_attendance_record(att, changed_by=None, old_vals=None):
    """
    Recalculate all derived fields for a single Attendance record after
    time_in or time_out is edited by an admin.

    Recomputes (in order):
      1. late_minutes, early_checkin_minutes  (from time_in vs shift start)
      2. status                                (PRESENT / LATE / HALF_DAY)
      3. early_checkout_minutes               (from time_out vs shift end)
      4. total_worked_minutes                 (from sessions or time_in–time_out)
      5. overtime_minutes, gap_deduction      (total_worked vs effective_shift)

    Then calls att.save() which triggers the pre_save signal to recompute:
      • fine_amount        (unless fine_edited = True)
      • overtime_amount
      • early_checkout_fine

    All field changes are logged to AttendanceEditLog.
    """
    from .models import AttendanceEditLog, AttendanceSession
    from datetime import datetime as dt_class

    user = att.user
    user_shift = att.shift or user.shift

    # If old_vals wasn't provided, snapshot now (though this is risky if edits 
    # were already made to `att` memory object before calling this function)
    if old_vals is None:
        old_vals = {}
        for field in AttendanceEditLog.TRACKED_FIELDS:
            raw = getattr(att, field)
            old_vals[field] = '' if raw is None else str(raw)

    # ── 1 & 2. late_minutes / status from time_in ─────────────────────────
    if att.time_in and user_shift:
        shift_start_dt = dt_class.combine(att.date, user_shift.start_time)
        shift_end_dt   = dt_class.combine(att.date, user_shift.end_time)
        if shift_end_dt <= shift_start_dt:
            shift_end_dt += timedelta(days=1)
        shift_dur   = int((shift_end_dt - shift_start_dt).total_seconds() / 60)
        half_shift  = shift_dur / 2
        buf         = user_shift.buffer_minutes or 0

        check_in_dt = dt_class.combine(att.date, att.time_in)

        if check_in_dt > shift_start_dt:
            raw_late = int((check_in_dt - shift_start_dt).total_seconds() / 60)
            att.late_minutes        = raw_late
            att.early_checkin_minutes = 0
            if not att.status_edited:
                from .signals import resolve_late_penalty
                att.status, _ = resolve_late_penalty(raw_late, shift_dur, buf,
                                                     on_date=att.date)
        elif check_in_dt < shift_start_dt:
            att.late_minutes          = 0
            att.early_checkin_minutes = int((shift_start_dt - check_in_dt).total_seconds() / 60)
            if not att.status_edited:
                att.status = 'PRESENT'
        else:
            att.late_minutes          = 0
            att.early_checkin_minutes = 0
            if not att.status_edited:
                att.status = 'PRESENT'
    elif not att.time_in:
        att.late_minutes          = 0
        att.early_checkin_minutes = 0

    # ── 3. early_checkout_minutes from time_out ────────────────────────────
    # Always store actual minutes (for display), but the fine is suppressed
    # when early_checkout_minutes ≤ buffer (handled by compute_early_checkout_fine
    # in signals.py and by the explicit check in step 5 below).
    if att.time_out and user_shift:
        shift_start_dt2 = dt_class.combine(att.date, user_shift.start_time)
        shift_end_dt2   = dt_class.combine(att.date, user_shift.end_time)
        if shift_end_dt2 <= shift_start_dt2:
            shift_end_dt2 += timedelta(days=1)
        check_out_dt = dt_class.combine(att.date, att.time_out)
        if check_out_dt < shift_end_dt2:
            att.early_checkout_minutes = int((shift_end_dt2 - check_out_dt).total_seconds() / 60)
        else:
            att.early_checkout_minutes = 0
    elif not att.time_out:
        att.early_checkout_minutes = 0

    # ── 4. total_worked_minutes ───────────────────────────────────────────
    sessions = att.sessions.all()
    if sessions.exists():
        total_worked = sum(s.duration_minutes for s in sessions)
        att.total_worked_minutes = total_worked
    elif att.time_in and att.time_out:
        tin  = dt_class.combine(att.date, att.time_in)
        tout = dt_class.combine(att.date, att.time_out)
        att.total_worked_minutes = max(0, int((tout - tin).total_seconds() / 60))
        total_worked = att.total_worked_minutes
    else:
        # No sessions and no time range — treat as 0 worked minutes
        att.total_worked_minutes = 0
        total_worked = 0

    # ── 5. overtime_minutes, overtime_amount, gap_deduction, early_checkout_fine ──
    if user_shift:
        from .signals import get_salary_data
        s_start = dt_class.combine(att.date, user_shift.start_time)
        s_end   = dt_class.combine(att.date, user_shift.end_time)
        if s_end <= s_start:
            s_end += timedelta(days=1)
        shift_dur2 = int((s_end - s_start).total_seconds() / 60)

        # effective_shift = expected work time (shift minus late entry and early checkout)
        # Since early_checkout_minutes now always reflects actual minutes, the
        # effective_shift formula naturally zeroes out the gap for buffer departures.
        effective_shift = max(0, shift_dur2 - (att.late_minutes or 0) - (att.early_checkout_minutes or 0))
        daily_rate  = get_salary_data(user, att)
        min_rate    = (daily_rate / shift_dur2) if (daily_rate and shift_dur2 > 0) else 0

        buf = user_shift.buffer_minutes or 0

        if total_worked > effective_shift:
            att.overtime_minutes = total_worked - effective_shift
            att.overtime_amount  = round(att.overtime_minutes * min_rate, 2) if min_rate else 0
            att.gap_deduction    = 0
        elif total_worked < effective_shift:
            att.overtime_minutes = 0
            att.overtime_amount  = 0
            gap_mins = effective_shift - total_worked
            # Only charge gap if it exceeds the shift buffer (10-min client relief).
            # This also eliminates integer-rounding noise on sessions.
            if gap_mins > buf:
                att.gap_deduction = round(gap_mins * min_rate, 2) if min_rate else 0
            else:
                att.gap_deduction = 0
        else:
            att.overtime_minutes = 0
            att.overtime_amount  = 0
            att.gap_deduction    = 0

        # ── Early checkout fine (buffer-aware) ────────────────────────────────
        # Fine is only for departures BEYOND the buffer window.
        early_checkout_mins = att.early_checkout_minutes or 0
        buf_co = user_shift.buffer_minutes or 0
        if early_checkout_mins > buf_co and min_rate:
            ecf = round(early_checkout_mins * min_rate, 2)
            att.early_checkout_fine = min(ecf, round(daily_rate, 2)) if daily_rate else ecf
        else:
            att.early_checkout_fine = 0

    # ── Save (pre_save signal will also recompute fine_amount, overtime_amount,
    #         early_checkout_fine — the values we set above act as the primary
    #         source; the signal is a safety net for other save paths) ────────
    att.save()

    # ── Audit log: record every field that changed ────────────────────────
    att.refresh_from_db()  # pick up signal-computed values
    for field in AttendanceEditLog.TRACKED_FIELDS:
        new_raw = getattr(att, field)
        new_val = '' if new_raw is None else str(new_raw)
        if old_vals[field] != new_val:
            AttendanceEditLog.objects.create(
                attendance=att,
                employee=att.user,
                changed_by=changed_by,
                field_name=field,
                old_value=old_vals[field],
                new_value=new_val,
                attendance_date=att.date,
                source='FRONTEND',
            )


def calculate_net_salary(
    base_salary,
    esi,
    epf,
    total_fines,
    total_overtime,
    present_days,
    days_in_month,
    num_holidays=0,
    paid_leaves_taken=0,
    shift_hours=8
):
    """
    Single source of truth for salary calculation.
    """
    DAYS_IN_MONTH = days_in_month
    
    effective_salary = base_salary - esi - epf
    daily_rate = effective_salary / DAYS_IN_MONTH

    # Pay for days worked + holidays + paid leaves
    earned_days = present_days + num_holidays + paid_leaves_taken
    # Cap at 30 to enforce strict 30-day month (prevents overpay in 31-day months)
    earned_days = min(earned_days, DAYS_IN_MONTH)
    earned_salary = earned_days * daily_rate

    net_salary = (
        earned_salary
        - total_fines
        + total_overtime
    )

    return max(round(net_salary, 2), 0)


class PayrollViewSet(viewsets.ModelViewSet):
    """Payroll ViewSet - filtered by admin's location"""
    queryset = Payroll.objects.all()
    serializer_class = PayrollSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'ADMIN':
            return Payroll.objects.filter(user__location=user.location).select_related('user')
        return Payroll.objects.all().select_related('user')

    @action(detail=False, methods=['get'])
    def fetch(self, request):
        """Fetch existing payroll records for a given month without regenerating."""
        month_str = request.query_params.get('month')
        if not month_str:
            return Response({"error": "Month is required (YYYY-MM-01)"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            month = parse_date(month_str)
            if not month:
                raise ValueError
        except ValueError:
            return Response({"error": "Invalid date format"}, status=status.HTTP_400_BAD_REQUEST)

        # Filter by location
        admin_location = request.user.location
        payrolls = Payroll.objects.filter(
            month=month, 
            user__location=admin_location
        ).select_related('user')
        serializer = self.get_serializer(payrolls, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def generate(self, request):
        month_str = request.data.get('month')
        if not month_str:
            return Response({"error": "Month is required (YYYY-MM-01)"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            month = parse_date(month_str)
            if not month:
                raise ValueError
        except ValueError as e:
            logger.exception("Invalid date format",e)
            return Response({"error": "Invalid date format"}, status=status.HTTP_400_BAD_REQUEST)

        admin_location = request.user.location
        # Get calendar days for reference but use 30 for everything (user request)
        _, calendar_days = calendar.monthrange(month.year, month.month)

        # Get holidays for this month at this location
        holidays = Holiday.objects.filter(
            date__year=month.year,
            date__month=month.month,
            location=admin_location
        )
        holiday_dates = set(h.date for h in holidays)
        # Only count holidays up to today for earned salary calculation
        today = date.today()
        holidays_upto_today = set(d for d in holiday_dates if d <= today)
        # num_holidays is computed PER USER inside the loop (based on date_joined)
        # holidays_upto_today is kept as a shared set for per-user filtering below
        
        working_days = calendar_days
        DAYS_IN_MONTH = calendar_days

        users = User.objects.filter(role='EMPLOYEE', location=admin_location)
        logger.debug(f"Generating payroll for {users.count()} users at location {admin_location}")
        payrolls = []

        # ==================================================================================
        # 1. CLEANUP: Mark missing checkouts as ABSENT (User Request)
        # ==================================================================================
        missing_checkout_qs = Attendance.objects.filter(
            user__location=admin_location,
            date__year=month.year,
            date__month=month.month,
            date__lt=today,  # Don't touch today's records — day isn't over
            status__in=['PRESENT', 'LATE', 'HALF_DAY'],  # Any attendance without checkout
            time_out__isnull=True,
            status_edited=False  # Don't overwrite admin-edited records
        )
        # Log before bulk update
        from .models import AttendanceEditLog
        for att in missing_checkout_qs:
            AttendanceEditLog.objects.create(
                attendance=att, employee=att.user, changed_by=request.user,
                field_name='status', old_value='PRESENT', new_value='ABSENT',
                attendance_date=att.date, source='PAYROLL_GEN',
            )
        updated_count = missing_checkout_qs.update(
            status='ABSENT',
            gap_deduction=0,
            overtime_minutes=0,
            overtime_amount=0,
        )
        if updated_count > 0:
            logger.info(f"Marked {updated_count} incomplete attendance records as ABSENT for {month_str}")

        # 1a-ii. Fix contradictory LEAVE records that have a check-in
        # A genuine leave has NO check-in. If check-in exists, it's incomplete attendance → ABSENT
        leave_with_checkin = Attendance.objects.filter(
            user__location=admin_location,
            date__year=month.year,
            date__month=month.month,
            date__lt=today,
            status='LEAVE',
            time_in__isnull=False,
            time_out__isnull=True,
            status_edited=False
        )
        # Log before bulk update
        for att in leave_with_checkin:
            AttendanceEditLog.objects.create(
                attendance=att, employee=att.user, changed_by=request.user,
                field_name='status', old_value='LEAVE', new_value='ABSENT',
                attendance_date=att.date, source='PAYROLL_GEN',
            )
        fixed_leave_count = leave_with_checkin.update(
            status='ABSENT',
            gap_deduction=0,
            overtime_minutes=0,
            overtime_amount=0,
        )
        if fixed_leave_count > 0:
            logger.info(f"Fixed {fixed_leave_count} LEAVE records that had check-in but no checkout → ABSENT")

        # ==================================================================================
        # 1b. Mark ABSENT records on holiday dates as HOLIDAY
        # ==================================================================================
        if holiday_dates:
            holiday_to_holiday_qs = Attendance.objects.filter(
                user__location=admin_location,
                date__in=holiday_dates,
                status='ABSENT',
                status_edited=False  # Don't overwrite admin-edited records
            )
            # Log before bulk update
            for att in holiday_to_holiday_qs:
                AttendanceEditLog.objects.create(
                    attendance=att, employee=att.user, changed_by=request.user,
                    field_name='status', old_value='ABSENT', new_value='HOLIDAY',
                    attendance_date=att.date, source='PAYROLL_GEN',
                )
            holiday_to_holiday = holiday_to_holiday_qs.update(status='HOLIDAY')
            if holiday_to_holiday > 0:
                logger.info(f"Marked {holiday_to_holiday} ABSENT records as HOLIDAY for holiday dates")


        for user in users:
            existing_payroll = Payroll.objects.filter(user=user, month=month).first()

            # ✅ HOLIDAY COUNT: Only count holidays on/after the employee's join date
            # An employee who joined on the 15th should not be paid for holidays on the 1st, 4th etc.
            user_join_date = user.date_joined.date() if user.date_joined else date.min
            num_holidays = len([d for d in holidays_upto_today if d >= user_join_date])

            # ── SALARY BASIS FOR THIS MONTH (SIO-132) ────────────────────────
            # A closed month must be priced at the salary that applied THEN, not at
            # whatever the employee earns today. Regenerating January after a raise
            # used to silently reprice January.
            #
            # Current month and future  -> the employee's live salary (original behaviour).
            # Months already past         -> frozen, in this order:
            #   1. the snapshots stamped on that month's attendance (historical truth)
            #   2. the salary already stored on an existing payroll row
            #   3. the live salary, only if that month has neither
            monthly_salary = esi = epf = None
            is_past_month = month < today.replace(day=1)
            snap = None if not is_past_month else (Attendance.objects
                    .filter(user=user, date__year=month.year, date__month=month.month,
                            date__lt=today,   # only days this payroll actually counts
                            salary_snapshot__isnull=False)
                    .order_by('-date')
                    .values('salary_snapshot', 'esi_snapshot', 'epf_snapshot')
                    .first())
            if not is_past_month:
                # Current and future months follow the employee's live salary — the
                # original behaviour, deliberately unchanged.
                monthly_salary = float(user.salary_per_month)
                esi = float(user.esi_amount)
                epf = float(user.epf_amount)
            elif snap:
                esi = float(snap['esi_snapshot'] or 0)
                epf = float(snap['epf_snapshot'] or 0)
                # salary_snapshot is the EFFECTIVE salary; rebuild the gross figure
                monthly_salary = float(snap['salary_snapshot']) + esi + epf
            elif existing_payroll:
                monthly_salary = float(existing_payroll.base_salary)
                esi = float(existing_payroll.esi_deductions)
                epf = float(existing_payroll.epf_deductions)
            else:
                monthly_salary = float(user.salary_per_month)
                esi = float(user.esi_amount)
                epf = float(user.epf_amount)

            # ✅ EFFECTIVE SALARY (single deduction point)
            effective_salary = monthly_salary - esi - epf

            # ✅ FLAT DAILY RATE: effective_salary / 30
            # Shift duration is only used for minute-rate fine calculations (in signals.py)
            daily_rate = effective_salary / DAYS_IN_MONTH if DAYS_IN_MONTH > 0 else 0

            # ✅ FORCE RECALCULATION of Time & Fines
            # This ensures "logic changes" (e.g. Shift buffer change) are applied to history.
            attendances = list(Attendance.objects.filter(
                user=user,
                date__year=month.year,
                date__month=month.month,
                date__lt=today  # Only completed days
            ))
            
            for att in attendances:
                # SKIP recalculation for admin-edited or non-working statuses
                if att.status_edited or att.status in ['ABSENT', 'LEAVE', 'HOLIDAY']:
                    continue
                
                # Capture old values for logging
                old_vals = {f: ('' if getattr(att, f) is None else str(getattr(att, f))) for f in ['late_minutes', 'overtime_minutes', 'early_checkout_minutes', 'total_worked_minutes', 'gap_deduction']}
                
                # Use assigned shift or user default
                user_shift = att.shift or user.shift
                
                # Check-in time available? Recalculate LATE MINUTES & EARLY CHECKIN
                if att.time_in and user_shift:
                    from datetime import datetime as dt_class
                    check_in_dt = dt_class.combine(att.date, att.time_in)
                    shift_start_dt = dt_class.combine(att.date, user_shift.start_time)
                    shift_end_dt2 = dt_class.combine(att.date, user_shift.end_time)
                    if shift_end_dt2 <= shift_start_dt:
                        shift_end_dt2 += timedelta(days=1)
                    shift_dur_status = int((shift_end_dt2 - shift_start_dt).total_seconds() / 60)
                    half_shift = shift_dur_status / 2
                    buf = user_shift.buffer_minutes or 0

                    if check_in_dt > shift_start_dt:
                        raw_late = int((check_in_dt - shift_start_dt).total_seconds() / 60)
                        att.late_minutes = raw_late  # Always show actual minutes
                        att.early_checkin_minutes = 0
                        # Recalculate status with buffer awareness
                        if not att.status_edited:
                            from .signals import resolve_late_penalty
                            att.status, _ = resolve_late_penalty(
                                raw_late, shift_dur_status, buf, on_date=att.date
                            )
                    elif check_in_dt < shift_start_dt:
                        att.late_minutes = 0
                        att.early_checkin_minutes = int((shift_start_dt - check_in_dt).total_seconds() / 60)
                        if not att.status_edited:
                            att.status = 'PRESENT'
                    else:
                        att.late_minutes = 0
                        att.early_checkin_minutes = 0
                        if not att.status_edited:
                            att.status = 'PRESENT'

                
                # Check-out time available? Recalculate EARLY CHECKOUT
                # Always store actual early checkout minutes (for display).
                # Fine and gap suppression for buffer departures is handled below.
                if att.time_out and user_shift:
                     from datetime import datetime as dt_class
                     check_out_dt = dt_class.combine(att.date, att.time_out)
                     shift_start_dt = dt_class.combine(att.date, user_shift.start_time)
                     shift_end_dt = dt_class.combine(att.date, user_shift.end_time)
                     if shift_end_dt <= shift_start_dt:
                         shift_end_dt += timedelta(days=1)

                     att.early_checkout_minutes = 0
                     if check_out_dt < shift_end_dt:
                         att.early_checkout_minutes = int((shift_end_dt - check_out_dt).total_seconds() / 60)

                # Recalculate total_worked_minutes from sessions
                from .models import AttendanceSession
                sessions = att.sessions.all()
                if sessions.exists():
                    total_worked = sum(s.duration_minutes for s in sessions)
                    att.total_worked_minutes = total_worked
                elif att.time_in and att.time_out:
                    # Legacy records without sessions — compute from time_in/time_out
                    from datetime import datetime as dt_class
                    tin = dt_class.combine(att.date, att.time_in)
                    tout = dt_class.combine(att.date, att.time_out)
                    att.total_worked_minutes = max(0, int((tout - tin).total_seconds() / 60))
                    total_worked = att.total_worked_minutes
                else:
                    total_worked = att.total_worked_minutes
                
                # Simplified OT & Gap deduction
                if user_shift:
                    from datetime import datetime as dt_class
                    s_start = dt_class.combine(att.date, user_shift.start_time)
                    s_end = dt_class.combine(att.date, user_shift.end_time)
                    if s_end <= s_start:
                        s_end += timedelta(days=1)
                    shift_dur = int((s_end - s_start).total_seconds() / 60)

                    # effective_shift accounts for late entry and early checkout minutes.
                    # early_checkout_minutes now includes buffer departures, so the
                    # effective_shift formula naturally keeps gap = 0 for within-buffer exits.
                    effective_shift = max(0, shift_dur - (att.late_minutes or 0) - (att.early_checkout_minutes or 0))
                    min_rate = daily_rate / shift_dur if shift_dur > 0 else 0

                    buf = user_shift.buffer_minutes or 0

                    # OT = total_worked - effective_shift
                    if total_worked > effective_shift:
                        att.overtime_minutes = total_worked - effective_shift
                    else:
                        att.overtime_minutes = 0

                    # Gap = effective_shift - total_worked.
                    # Only charge if gap exceeds shift buffer (10-min client relief).
                    if total_worked < effective_shift:
                        gap_mins = effective_shift - total_worked
                        if gap_mins > buf:
                            att.gap_deduction = round(gap_mins * min_rate, 2) if min_rate else 0
                        else:
                            att.gap_deduction = 0
                    else:
                        att.gap_deduction = 0
                
                # Log any recalculation changes
                for field in ['late_minutes', 'overtime_minutes', 'early_checkout_minutes', 'total_worked_minutes', 'gap_deduction']:
                    new_val = '' if getattr(att, field) is None else str(getattr(att, field))
                    if old_vals[field] != new_val:
                        AttendanceEditLog.objects.create(
                            attendance=att, employee=att.user, changed_by=request.user,
                            field_name=field, old_value=old_vals[field], new_value=new_val,
                            attendance_date=att.date, source='PAYROLL_GEN',
                        )

                # ✅ IMPORTANT: Do NOT reset `fine_edited`.
                # If fine_edited is True, the pre_save signal will SKIP overwriting fine_amount.
                # If fine_edited is False, the pre_save signal will RECALCULATE fine_amount using new late_minutes.
                att.save() 
            
            # Re-fetch after recalculation to get updated values
            attendances = list(Attendance.objects.filter(
                user=user,
                date__year=month.year,
                date__month=month.month,
                date__lt=today  # Only completed days
            ))

            # Calculate present days — correctly weighted. Each half day works 0.5 present days.
            full_present_days = sum(
                1 for att in attendances
                if att.status in ['PRESENT', 'LATE']
            )
            half_present_days = sum(
                1 for att in attendances
                if att.status == 'HALF_DAY'
            )
            # The decimal count for display/billing
            present_days = full_present_days + (half_present_days * 0.5)

            # Sum fines only from working-day records (PRESENT / LATE / HALF_DAY / HOLIDAY).
            # ABSENT and LEAVE employees already lose a full day's salary — stacking their
            # late/gap/early-checkout fines on top would double-penalise them.
            # This matches the "Total Fines" card logic on the employee detail page.
            fine_attendances = [
                att for att in attendances
                if att.status not in ('ABSENT', 'LEAVE')
            ]
            late_fines = sum(float(att.fine_amount) for att in fine_attendances)
            early_checkout_fines = sum(float(att.early_checkout_fine) for att in fine_attendances)
            gap_deductions = sum(float(att.gap_deduction) for att in fine_attendances)
            total_fines = late_fines + early_checkout_fines + gap_deductions

            total_overtime = sum(float(att.overtime_amount) for att in attendances)
            
            # ✅ HOLIDAY PAY LOGIC
            # 1. Everyone is paid for holidays (holidays don't count as absent)
            # 2. If someone works on a holiday, they get extra overtime (1 day's pay)
            
            # Count how many days the user worked on holidays
            holiday_work_count = 0
            for att in attendances:
                if att.date in holiday_dates and att.status in ['PRESENT', 'HALF_DAY', 'LATE']:
                    holiday_work_count += 1
            
            # Holiday work bonus = number of holiday work days × daily_rate
            holiday_work_bonus = holiday_work_count * daily_rate
            
            # Add holiday work bonus to total overtime
            total_overtime += holiday_work_bonus

            # ✅ FIRST-PRINCIPLES: Pay for days worked + holidays + paid leaves
            # Full days (PRESENT/LATE) on non-holiday dates
            full_on_non_holidays = sum(
                1 for att in attendances
                if att.date not in holiday_dates and att.status in ['PRESENT', 'LATE']
            )
            # Half days (HALF_DAY) on non-holiday dates → earn 0.5 × daily_rate
            half_on_non_holidays = sum(
                1 for att in attendances
                if att.date not in holiday_dates and att.status == 'HALF_DAY'
            )

            # ✅ PAID LEAVE LOGIC (refactored)
            # 1. Count days already marked as LEAVE (by admin or auto)
            existing_leave_list = [
                att for att in attendances
                if att.date not in holiday_dates and att.status == 'LEAVE'
            ]
            existing_leave_days = len(existing_leave_list)
            
            # 1b. REVERT excess LEAVE → ABSENT when paid_leaves_per_month decreases
            # Only revert auto-converted leaves (not admin-edited, no check-in/out = genuine no-show)
            if existing_leave_days > user.paid_leaves_per_month:
                excess = existing_leave_days - user.paid_leaves_per_month
                # Find auto-converted leaves (not admin-edited, no check-in)
                revertible = [
                    att for att in existing_leave_list
                    if not att.status_edited and att.time_in is None and att.time_out is None
                ]
                # Revert the most recent ones first (reverse chronological)
                revertible.sort(key=lambda a: a.date, reverse=True)
                reverted = 0
                for att in revertible[:excess]:
                    att.status = 'ABSENT'
                    att.save(update_fields=['status'])
                    reverted += 1
                existing_leave_days -= reverted
            
            # 2. Count ALL ABSENT and HALF_DAY days (whether manual or auto) for auto-conversion
            final_absent_days = sum(1 for att in attendances if att.date not in holiday_dates and att.status == 'ABSENT')
            final_half_days = sum(1 for att in attendances if att.date not in holiday_dates and att.status == 'HALF_DAY')
            
            # The frontend creates synthetic ABSENT days for any missed day (excluding Sundays & Holidays).
            # We must count these empty days here in the backend so their pay is correctly deducted!
            attended_dates = set(att.date for att in attendances)
            
            month_start_date = date(month.year, month.month, 1)
            limit_date = min(date(month.year, month.month, calendar_days), today - timedelta(days=1))
            
            empty_absent_days = 0
            if limit_date >= month_start_date:
                for d_int in range(1, limit_date.day + 1):
                    current_d = date(month.year, month.month, d_int)
                    if current_d < user_join_date:
                        continue
                    if current_d.isoweekday() == 7:  # Skip Sundays
                        continue
                    if current_d in holiday_dates:
                        continue
                    if current_d not in attended_dates:
                        empty_absent_days += 1
            
            total_missing = final_absent_days + (final_half_days * 0.5) + empty_absent_days

            # 3. Calculate Paid vs Unpaid strictly based on Quota
            # All absences (whether marked "LEAVE", "ABSENT", or missing) go into total_unworked.
            total_unworked = existing_leave_days + total_missing
            
            quota = user.paid_leaves_per_month
            paid_leaves_used = min(total_unworked, quota)
            unpaid_absent_days = total_unworked - paid_leaves_used

            # ✅ STRICT BOTTOM-UP (ALL EMPLOYEES)
            
            month_start_date = date(month.year, month.month, 1)

            # Ensure they get paid for Sundays they were enrolled for (but didn't explicitly work on)
            enrolled_sundays = 0
            if limit_date >= month_start_date:
                for d_int in range(1, limit_date.day + 1):
                    current_d = date(month.year, month.month, d_int)
                    if current_d >= user_join_date and current_d.isoweekday() == 7 and current_d not in holiday_dates:
                        enrolled_sundays += 1
            earned_days = full_on_non_holidays + (half_on_non_holidays * 0.5) + num_holidays + paid_leaves_used + enrolled_sundays

            # Secure clamps — ceiling is reduced by unpaid days so they always cost pay
            earned_days = max(0, min(earned_days, DAYS_IN_MONTH - unpaid_absent_days))
            earned_salary = earned_days * daily_rate

            # ✅ Preserve payroll-level fine edits, otherwise use freshly calculated fines
            if existing_payroll and existing_payroll.fine_edited:
                # Admin manually edited the payroll fine — preserve it
                final_fines = float(existing_payroll.fine_deductions)
                fine_edited_flag = True
            else:
                # Use freshly calculated fines from attendance data
                final_fines = round(total_fines, 2)
                fine_edited_flag = False

            # ✅ Preserve payroll-level overtime edits, otherwise use freshly calculated overtime
            if existing_payroll and existing_payroll.overtime_edited:
                final_overtime = float(existing_payroll.overtime_pay)
                overtime_edited_flag = True
            else:
                final_overtime = round(total_overtime, 2)
                overtime_edited_flag = False

            # ✅ NET SALARY = Earned Salary - Fines + Overtime
            gross_payout = (
                earned_salary
                - final_fines
                + final_overtime
            )

            if gross_payout < 0:
                gross_payout = 0

            payroll, created = Payroll.objects.update_or_create(
                user=user,
                month=month,
                defaults={
                    'base_salary': monthly_salary,
                    'total_present_days': present_days,
                    'working_days': working_days,
                    'fine_deductions': final_fines,
                    'fine_edited': fine_edited_flag,
                    'esi_deductions': round(esi, 2),
                    'epf_deductions': round(epf, 2),
                    'paid_leaves_taken': paid_leaves_used,
                    'unpaid_leaves_taken': unpaid_absent_days,
                    'leave_deductions': 0,
                    'overtime_pay': round(final_overtime, 2),
                    'overtime_edited': overtime_edited_flag,
                    'num_holidays': num_holidays,
                    'calculated_salary': round(gross_payout, 2),
                    'status': 'PENDING'
                }
            )

            payrolls.append(payroll)

        serializer = self.get_serializer(payrolls, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['patch'])
    def update_base_salary(self, request, pk=None):
        payroll = self.get_object()

        new_base = request.data.get('base_salary', payroll.base_salary)
        new_esi = request.data.get('esi_deductions', payroll.esi_deductions)
        new_epf = request.data.get('epf_deductions', payroll.epf_deductions)
        new_fines = request.data.get('fine_deductions', payroll.fine_deductions)
        new_overtime = request.data.get('overtime_pay', payroll.overtime_pay)
        
        # Track if fine/overtime are being manually edited
        fine_being_edited = 'fine_deductions' in request.data and float(request.data['fine_deductions']) != float(payroll.fine_deductions)
        overtime_being_edited = 'overtime_pay' in request.data and float(request.data['overtime_pay']) != float(payroll.overtime_pay)

        try:
            monthly_salary = float(new_base)
            esi = float(new_esi)
            epf = float(new_epf)
            total_fines = float(new_fines)
            overtime_pay = float(new_overtime)
        except (ValueError, TypeError):
            return Response({"error": "Invalid amount. Please enter valid numbers only."}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Validate non-negative values
        if monthly_salary < 0:
            return Response({"error": "Base salary cannot be negative"}, status=status.HTTP_400_BAD_REQUEST)
        if esi < 0:
            return Response({"error": "ESI amount cannot be negative"}, status=status.HTTP_400_BAD_REQUEST)
        if epf < 0:
            return Response({"error": "EPF amount cannot be negative"}, status=status.HTTP_400_BAD_REQUEST)
        if total_fines < 0:
            return Response({"error": "Fines cannot be negative"}, status=status.HTTP_400_BAD_REQUEST)
        if overtime_pay < 0:
            return Response({"error": "Overtime pay cannot be negative"}, status=status.HTTP_400_BAD_REQUEST)
        
        # ✅ Validate reasonable limits
        if monthly_salary > 9999999:
            return Response({"error": "Base salary exceeds maximum allowed value"}, status=status.HTTP_400_BAD_REQUEST)

        import calendar
        _, DAYS_IN_MONTH = calendar.monthrange(payroll.month.year, payroll.month.month)

        # ✅ FLAT DAILY RATE
        effective_salary = monthly_salary - esi - epf
        daily_rate = effective_salary / DAYS_IN_MONTH

        # ✅ STRICT BOTTOM-UP (ALL EMPLOYEES)
        
        month_start_date = date(payroll.month.year, payroll.month.month, 1)
        join_date = payroll.user.date_joined.date() if payroll.user.date_joined else date.min
        
        month_attendances = Attendance.objects.filter(
            user=payroll.user,
            date__year=payroll.month.year,
            date__month=payroll.month.month,
            date__lt=date.today()
        )
        holiday_dates = set(
            Holiday.objects.filter(
                date__year=payroll.month.year,
                date__month=payroll.month.month,
                location=payroll.user.location
            ).values_list('date', flat=True)
        )

        full_on_non_holidays = sum(1 for att in month_attendances if att.date not in holiday_dates and att.status in ['PRESENT', 'LATE'])
        half_on_non_holidays = sum(1 for att in month_attendances if att.date not in holiday_dates and att.status == 'HALF_DAY')
        explicit_leave_days = sum(1 for att in month_attendances if att.status == 'LEAVE')
        
        today = date.today()
        limit_date = min(date(payroll.month.year, payroll.month.month, DAYS_IN_MONTH), today - timedelta(days=1))

        # Recompute missing/empty days (no attendance record on workable days)
        attended_dates = set(att.date for att in month_attendances)
        empty_absent_days = 0
        if limit_date >= month_start_date:
            for d_int in range(1, limit_date.day + 1):
                current_d = date(payroll.month.year, payroll.month.month, d_int)
                if current_d < join_date:
                    continue
                if current_d.isoweekday() == 7:
                    continue
                if current_d in holiday_dates:
                    continue
                if current_d not in attended_dates:
                    empty_absent_days += 1

        final_absent_days = sum(1 for att in month_attendances if att.status == 'ABSENT')
        final_half_days = sum(1 for att in month_attendances if att.status == 'HALF_DAY')
        total_missing = final_absent_days + (final_half_days * 0.5) + empty_absent_days
        total_unworked = explicit_leave_days + total_missing
        quota = payroll.user.paid_leaves_per_month
        paid_leaves_used = min(total_unworked, quota)
        unpaid_absent_days = total_unworked - paid_leaves_used

        enrolled_sundays = 0
        if limit_date >= month_start_date:
            for d_int in range(1, limit_date.day + 1):
                current_d = date(payroll.month.year, payroll.month.month, d_int)
                if current_d >= join_date and current_d.isoweekday() == 7 and current_d not in holiday_dates:
                    enrolled_sundays += 1
        
        earned_days = full_on_non_holidays + (half_on_non_holidays * 0.5) + payroll.num_holidays + paid_leaves_used + enrolled_sundays

        # Ceiling is reduced by unpaid days so they always cost pay
        earned_days = max(0, min(earned_days, DAYS_IN_MONTH - unpaid_absent_days))
        earned_salary = earned_days * daily_rate

        # ✅ NET SALARY = Earned Salary - Fines + Overtime
        gross_payout = (
            earned_salary
            - total_fines
            + overtime_pay
        )

        if gross_payout < 0:
            gross_payout = 0

        # ✅ UPDATE USER MASTER RECORD TO PERSIST CHANGES
        # This ensures future regenerations use the updated salary
        user = payroll.user
        user.salary_per_month = monthly_salary
        user.esi_amount = esi
        user.epf_amount = epf
        user.save()

        payroll.base_salary = monthly_salary
        payroll.esi_deductions = esi
        payroll.epf_deductions = epf
        payroll.fine_deductions = total_fines
        payroll.overtime_pay = overtime_pay
        payroll.leave_deductions = 0
        payroll.calculated_salary = round(gross_payout, 2)
        
        # Mark fine as manually edited if it was changed
        if fine_being_edited:
            payroll.fine_edited = True
        
        # Mark overtime as manually edited if it was changed
        if overtime_being_edited:
            payroll.overtime_edited = True

        payroll.save()

        # An explicit correction must also re-stamp that month's attendance snapshots
        # (SIO-132). Without this the payroll row and the attendance rows disagree, and
        # the next regeneration — which prices a month from its snapshots — would quietly
        # revert this edit. Re-saving recomputes each day's fine at the corrected salary.
        effective = round(monthly_salary - esi - epf, 2)
        month_attendance = Attendance.objects.filter(
            user=user, date__year=payroll.month.year, date__month=payroll.month.month,
        )
        month_attendance.update(salary_snapshot=effective,
                                esi_snapshot=round(esi, 2),
                                epf_snapshot=round(epf, 2))
        for att in month_attendance.select_related('user', 'shift', 'user__shift'):
            att.save()

        return Response(self.get_serializer(payroll).data)

    @action(detail=False, methods=['get'])
    def export_excel(self, request):
        """Export payroll data to Excel format (raw, editable)"""
        import io
        try:
            import openpyxl
            from openpyxl.utils import get_column_letter
        except ImportError:
            return Response({"error": "openpyxl not installed. Run: pip install openpyxl"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        from django.http import HttpResponse
        
        month_str = request.query_params.get('month')
        if not month_str:
            return Response({"error": "Month is required (YYYY-MM-01)"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            month = parse_date(month_str)
            if not month:
                raise ValueError
        except ValueError:
            return Response({"error": "Invalid date format"}, status=status.HTTP_400_BAD_REQUEST)
        
        admin_location = request.user.location
        payrolls = Payroll.objects.filter(
            month=month, 
            user__location=admin_location
        ).select_related('user')

        # Create workbook
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"Payroll {month.strftime('%b %Y')}"
        
        # Headers (EPF removed, Overtime added)
        headers = ['Sr.', 'Name', 'Contact', 'Department', 'Present Days', 'Working Days',
                   'Base Salary', 'Fine Deductions', 'Paid Leaves', 'Unpaid Leaves', 
                   'Leave Deductions', 'ESI', 'Overtime Pay', 'Net Salary', 'Status']
        ws.append(headers)
        
        # Data rows
        for idx, p in enumerate(payrolls, 1):
            ws.append([
                idx,
                f"{p.user.first_name} {p.user.last_name}".strip() or p.user.username,
                p.user.contact or '',
                p.user.department or '',
                p.total_present_days,
                p.working_days,
                float(p.base_salary),
                float(p.fine_deductions),
                p.paid_leaves_taken,
                p.unpaid_leaves_taken,
                float(p.leave_deductions),
                float(p.esi_deductions),
                float(p.overtime_pay),
                float(p.calculated_salary),
                p.status
            ])
        
        # Auto-adjust column widths
        for col in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(col)].width = 15
        
        # Save to bytes
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="payroll_{month.strftime("%Y_%m")}.xlsx"'
        return response


# ==========================
# PASSWORD RESET VIEWS
# ==========================

class ForgotPasswordView(generics.GenericAPIView):
    """Generate password reset token"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        user = User.objects.filter(email=email).first()
        if not user:
            # Don't reveal if email exists
            return Response({"message": "If this email exists, a reset link has been generated."})
        
        # Generate token
        token = secrets.token_urlsafe(32)
        user.password_reset_token = token
        user.password_reset_expires = timezone.now() + timedelta(hours=1)
        user.save()
        
        logger.info(f"Password reset token generated for user id {user.id}")

        # No email delivery yet. Returning the token to the caller would let
        # anyone reset any account by knowing its email, so it is only exposed
        # in local development (DEBUG). In production an admin resets passwords.
        from django.conf import settings
        if settings.DEBUG:
            return Response({
                "message": "Password reset token generated (development only).",
                "reset_token": token,
                "expires_in": "1 hour"
            })
        return Response({"message": "If this email exists, a reset link has been generated."})


class ResetPasswordView(generics.GenericAPIView):
    """Reset password using token"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        token = request.data.get('token')
        new_password = request.data.get('password')
        
        if not token or not new_password:
            return Response({"error": "Token and new password are required"}, status=status.HTTP_400_BAD_REQUEST)
        
        user = User.objects.filter(
            password_reset_token=token,
            password_reset_expires__gt=timezone.now()
        ).first()
        
        if not user:
            return Response({"error": "Invalid or expired token"}, status=status.HTTP_400_BAD_REQUEST)
        
        user.set_password(new_password)
        user.password_reset_token = None
        user.password_reset_expires = None
        user.save()
        
        return Response({"message": "Password reset successfully. You can now login."})


# ==========================
# EMPLOYEE PERSONAL DATA VIEWS
# ==========================

class MyProfileView(generics.RetrieveAPIView):
    """Get current user's profile"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get(self, request):
        user = request.user
        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "designation": user.designation,
            "contact": user.contact,
            "salary_per_month": str(user.salary_per_month),
            "date_joined": user.date_joined
        })


class MyAttendanceView(generics.ListAPIView):
    """Get current user's attendance records"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AttendanceSerializer

    def get(self, request):
        user = request.user
        month_str = request.query_params.get('month')
        
        queryset = Attendance.objects.filter(user=user).order_by('-date')
        
        if month_str:
            try:
                month = parse_date(month_str)
                if month:
                    queryset = queryset.filter(date__year=month.year, date__month=month.month)
            except:
                pass
        
        serializer = self.get_serializer(queryset[:50], many=True)
        return Response(serializer.data)


class MyPayrollView(generics.ListAPIView):
    """Get current user's payroll records"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PayrollSerializer

    def get(self, request):
        user = request.user
        payrolls = Payroll.objects.filter(user=user).order_by('-month')
        serializer = self.get_serializer(payrolls, many=True)
        return Response(serializer.data)


class HolidayViewSet(viewsets.ModelViewSet):
    """CRUD for holidays - Admin only, filtered by location"""
    queryset = Holiday.objects.all()
    serializer_class = HolidaySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Filter by admin's location and month if provided"""
        user = self.request.user
        queryset = Holiday.objects.filter(location=user.location)
        
        month_str = self.request.query_params.get('month')
        if month_str:
            try:
                month = parse_date(month_str)
                if month:
                    queryset = queryset.filter(date__year=month.year, date__month=month.month)
            except:
                pass
        return queryset

    @action(detail=False, methods=['post'])
    def generate_weekends(self, request):
        """Auto-generate Sundays as holidays for a month"""
        month_str = request.data.get('month')
        if not month_str:
            return Response({"error": "Month is required (YYYY-MM-01)"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            month = parse_date(month_str)
            if not month:
                raise ValueError
        except ValueError:
            return Response({"error": "Invalid date format"}, status=status.HTTP_400_BAD_REQUEST)

        admin_location = request.user.location
        _, days_in_month = calendar.monthrange(month.year, month.month)
        
        created_count = 0
        for day in range(1, days_in_month + 1):
            date = datetime(month.year, month.month, day).date()
            weekday = date.weekday()  # 6=Sunday
            
            if weekday == 6:  # Only Sunday
                _, created = Holiday.objects.get_or_create(
                    date=date,
                    location=admin_location,
                    defaults={'name': 'Sunday', 'is_weekend': True}
                )
                if created:
                    created_count += 1
        
        return Response({
            "message": f"Generated {created_count} Sunday holidays for {month.strftime('%B %Y')}",
            "created": created_count
        })

    @action(detail=False, methods=['post'])
    def add_holiday(self, request):
        """Add a single holiday for admin's location"""
        date_str = request.data.get('date')
        name = request.data.get('name', 'Holiday')
        
        if not date_str:
            return Response({"error": "Date is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            date = parse_date(date_str)
            if not date:
                raise ValueError
        except ValueError:
            return Response({"error": "Invalid date format"}, status=status.HTTP_400_BAD_REQUEST)

        admin_location = request.user.location
        holiday, created = Holiday.objects.get_or_create(
            date=date,
            location=admin_location,
            defaults={'name': name, 'is_weekend': False}
        )
        
        if not created:
            return Response({"message": "Holiday already exists", "holiday": HolidaySerializer(holiday).data})
        
        # Auto-update any ABSENT attendance records on this date to HOLIDAY
        updated = Attendance.objects.filter(
            user__location=admin_location,
            date=date,
            status='ABSENT'
        ).update(status='HOLIDAY')
        if updated > 0:
            logger.info(f"Auto-marked {updated} ABSENT records as HOLIDAY for {date}")

        return Response({
            "message": "Holiday added successfully",
            "holiday": HolidaySerializer(holiday).data
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def remove_holiday(self, request):
        """Remove a holiday by date for admin's location"""
        date_str = request.data.get('date')
        
        if not date_str:
            return Response({"error": "Date is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            date = parse_date(date_str)
            if not date:
                raise ValueError
        except ValueError:
            return Response({"error": "Invalid date format"}, status=status.HTTP_400_BAD_REQUEST)

        admin_location = request.user.location
        try:
            holiday = Holiday.objects.get(date=date, location=admin_location)
            holiday.delete()
            # Revert any HOLIDAY attendance records back to ABSENT
            reverted = Attendance.objects.filter(
                user__location=admin_location,
                date=date,
                status='HOLIDAY'
            ).update(status='ABSENT')
            if reverted > 0:
                logger.info(f"Reverted {reverted} HOLIDAY records back to ABSENT for {date}")
            return Response({"message": f"Holiday on {date} removed"})
        except Holiday.DoesNotExist:
            return Response({"error": "Holiday not found"}, status=status.HTTP_404_NOT_FOUND)


# ==========================
# LOCATION VIEWSET
# ==========================
from .models import Location
from .serializers import LocationSerializer

class LocationViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for listing locations (read-only for dropdown)"""
    queryset = Location.objects.filter(is_active=True).order_by('code')
    serializer_class = LocationSerializer
    permission_classes = [permissions.AllowAny]  # Public for signup dropdown


# ==========================
# SHIFT VIEWSET
# ==========================
from .models import Shift
from .serializers import ShiftSerializer

class ShiftViewSet(viewsets.ModelViewSet):
    """API endpoint for managing shifts"""
    queryset = Shift.objects.filter(is_active=True).order_by('start_time')
    serializer_class = ShiftSerializer
    permission_classes = [permissions.AllowAny]  # Public for mobile app dropdown
    
    def get_permissions(self):
        # Anyone can list/retrieve shifts (for dropdown)
        # Only authenticated users can create/update/delete
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]


# ==========================
# LEAVE VIEWSET
# ==========================
from .models import Leave
from .serializers import LeaveSerializer

class LeaveViewSet(viewsets.ModelViewSet):
    """API endpoint for managing employee leaves"""
    queryset = Leave.objects.all()
    serializer_class = LeaveSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        queryset = Leave.objects.all()
        
        # Filter by admin's location
        if user.role == 'ADMIN':
            queryset = queryset.filter(user__location=user.location)
        
        # Date/month filter
        date_str = self.request.query_params.get('date', None)
        if date_str:
            queryset = queryset.filter(date=date_str)
        
        month_str = self.request.query_params.get('month', None)
        if month_str:
            try:
                month = parse_date(month_str)
                if month:
                    queryset = queryset.filter(
                        date__year=month.year,
                        date__month=month.month
                    )
            except:
                pass
        
        # User filter
        user_id = self.request.query_params.get('user_id', None)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        return queryset.select_related('user')
    
    @action(detail=False, methods=['post'])
    def mark_leave(self, request):
        """Mark a leave for an employee (creates both Leave record and updates Attendance)"""
        user_id = request.data.get('user_id')
        date_str = request.data.get('date')
        leave_type = request.data.get('leave_type', 'PAID')
        reason = request.data.get('reason', '')
        
        if not user_id or not date_str:
            return Response({"error": "user_id and date are required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            date = parse_date(date_str)
            if not date:
                raise ValueError
        except ValueError:
            return Response({"error": "Invalid date format"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            employee = User.objects.get(id=user_id, role='EMPLOYEE')
        except User.DoesNotExist:
            return Response({"error": "Employee not found"}, status=status.HTTP_404_NOT_FOUND)
        
        # Check if admin has access to this employee
        if request.user.role == 'ADMIN' and employee.location != request.user.location:
            return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)
        
        # Create/update Leave record
        leave, created = Leave.objects.update_or_create(
            user=employee,
            date=date,
            defaults={
                'leave_type': leave_type,
                'reason': reason,
                'approved': True
            }
        )
        
        # Create/update Attendance record to mark as LEAVE
        Attendance.objects.update_or_create(
            user=employee,
            date=date,
            defaults={
                'status': 'LEAVE',
                'time_in': None,
                'time_out': None,
                'late_minutes': 0,
                'fine_amount': 0
            }
        )
        
        return Response({
            "message": "Leave marked successfully",
            "leave": LeaveSerializer(leave).data
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
