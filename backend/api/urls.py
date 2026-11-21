from django.urls import include, re_path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    AttendanceViewSet, PayrollViewSet, UserViewSet, RegisterView, DashboardView,
    register_employee, mark_attendance, mark_attendance_face,
    ForgotPasswordView, ResetPasswordView,
    MyProfileView, MyAttendanceView, MyPayrollView,
    HolidayViewSet, LocationViewSet, ShiftViewSet, LeaveViewSet
)
from .auth_views import CustomTokenObtainPairView

# Trailing slashes are optional on every API route ("/api/me" and "/api/me/"
# both work). Mobile HTTP clients often drop the slash, and Django can't
# redirect a POST to the slashed URL without losing the body.
router = DefaultRouter()
# DRF's constructor coerces trailing_slash to '/' or ''; set the regex directly.
router.trailing_slash = '/?'
router.register(r'attendance', AttendanceViewSet)
router.register(r'payroll', PayrollViewSet)
router.register(r'users', UserViewSet)
router.register(r'holidays', HolidayViewSet)
router.register(r'locations', LocationViewSet)
router.register(r'location', LocationViewSet, basename='location_singular')

router.register(r'shifts', ShiftViewSet)
router.register(r'leaves', LeaveViewSet)

urlpatterns = [
    # Mobile app endpoints (MUST come first to avoid router conflicts)
    re_path(r'^employee/register/?$', register_employee, name='employee_register'),
    re_path(r'^attendance/mark/?$', mark_attendance, name='attendance_mark'),
    re_path(r'^attendance/face-mark/?$', mark_attendance_face, name='attendance_face_mark'),

    # Auth endpoints
    re_path(r'^auth/register/?$', RegisterView.as_view(), name='auth_register'),
    re_path(r'^auth/login/?$', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    re_path(r'^auth/refresh/?$', TokenRefreshView.as_view(), name='token_refresh'),
    re_path(r'^auth/forgot-password/?$', ForgotPasswordView.as_view(), name='forgot_password'),
    re_path(r'^auth/reset-password/?$', ResetPasswordView.as_view(), name='reset_password'),

    # Employee personal data
    re_path(r'^me/?$', MyProfileView.as_view(), name='my_profile'),
    re_path(r'^me/attendance/?$', MyAttendanceView.as_view(), name='my_attendance'),
    re_path(r'^me/payroll/?$', MyPayrollView.as_view(), name='my_payroll'),

    # Dashboard
    re_path(r'^dashboard/?$', DashboardView.as_view(), name='dashboard'),

    # Router URLs (after specific paths)
    re_path(r'^', include(router.urls)),
]
