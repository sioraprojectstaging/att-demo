import React, { useEffect, useState, useCallback } from "react";
import api from "../../services/api";
import {
  ArrowLeft,
  Calendar as CalendarIcon,
  Clock,
  Banknote,
  User as UserIcon,
  ChevronLeft,
  ChevronRight,
  Edit3,
  Save,
  X,
  AlertCircle,
  CheckCircle,
  Mail,
  Phone,
  DollarSign,
  Shield,
} from "lucide-react";

const EmployeeDetailPage = ({ employee, onBack }) => {
  const [attendanceData, setAttendanceData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedMonth, setSelectedMonth] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  });
  const [editingRowId, setEditingRowId] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [payrollData, setPayrollData] = useState(null);
  const [employeeData, setEmployeeData] = useState(null);
  const [expandedDetailRow, setExpandedDetailRow] = useState(null);
  const [holidayDates, setHolidayDates] = useState(new Set());

  // Always use fresh data (API fetch), falling back to prop
  const emp = employeeData || employee;

  const fetchEmployee = useCallback(async () => {
    try {
      const res = await api.get(`users/${employee.id}/`);
      setEmployeeData(res.data);
    } catch (e) {
      console.error("Failed to fetch employee data", e);
    }
  }, [employee.id]);

  const fetchHolidays = useCallback(async () => {
    try {
      const res = await api.get(`holidays/?month=${selectedMonth}-01`);
      const list = Array.isArray(res.data) ? res.data : res.data.results || [];
      setHolidayDates(new Set(list.map((h) => h.date)));
    } catch (e) {
      console.error("Failed to fetch holidays", e);
      setHolidayDates(new Set());
    }
  }, [selectedMonth]);

  const fetchAttendance = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(
        `attendance/?user=${employee.id}&month=${selectedMonth}`,
      );
      const data = Array.isArray(res.data) ? res.data : res.data.results || [];
      // Sort by date ascending
      data.sort((a, b) => new Date(a.date) - new Date(b.date));

      // Fill in missing days of the month
      const [year, month] = selectedMonth.split("-").map(Number);
      const today = new Date();
      // Use LOCAL date (not UTC) to avoid cutoff at midnight IST (UTC+5:30)
      const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
      const daysInMonth = new Date(year, month, 0).getDate();
      const existingDates = new Set(data.map((a) => a.date));
      const filledData = [];

      // Fetch holidays for this month to avoid marking them as ABSENT
      let monthHolidayDates = new Set();
      try {
        const hRes = await api.get(`holidays/?month=${selectedMonth}-01`);
        const hList = Array.isArray(hRes.data)
          ? hRes.data
          : hRes.data.results || [];
        monthHolidayDates = new Set(hList.map((h) => h.date));
        setHolidayDates(monthHolidayDates);
      } catch (_) {
        // If holiday fetch fails, proceed without holiday exclusion
      }

      for (let day = 1; day <= daysInMonth; day++) {
        const dateStr = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
        // Don't add future dates (after today)
        if (dateStr > todayStr) break;
        if (existingDates.has(dateStr)) {
          filledData.push(...data.filter((a) => a.date === dateStr));
        } else {
          // Skip Sundays — they are expected off-days
          const dayOfWeek = new Date(dateStr + "T00:00:00").getDay();
          if (dayOfWeek === 0) continue;

          // Show holiday dates with HOLIDAY status instead of ABSENT
          if (monthHolidayDates.has(dateStr)) {
            filledData.push({
              id: `holiday-${dateStr}`,
              date: dateStr,
              time_in: null,
              time_out: null,
              status: "HOLIDAY",
              late_minutes: 0,
              fine_amount: 0,
              early_checkout_minutes: 0,
              early_checkout_fine: 0,
              overtime_minutes: 0,
              overtime_amount: 0,
              _synthetic: true,
              _isHoliday: true,
            });
            continue;
          }

          filledData.push({
            id: `absent-${dateStr}`,
            date: dateStr,
            time_in: null,
            time_out: null,
            status: "ABSENT",
            late_minutes: 0,
            fine_amount: 0,
            early_checkout_minutes: 0,
            early_checkout_fine: 0,
            overtime_minutes: 0,
            overtime_amount: 0,
            _synthetic: true, // flag to prevent editing
          });
        }
      }

      setAttendanceData(filledData);
    } catch (e) {
      console.error("Failed to fetch attendance", e);
      setAttendanceData([]);
    }
    setLoading(false);
  }, [employee.id, selectedMonth]);

  const fetchPayroll = useCallback(async () => {
    try {
      const res = await api.get(`payroll/fetch/?month=${selectedMonth}-01`);
      const data = Array.isArray(res.data) ? res.data : [];
      const empPayroll = data.find(
        (p) => (p.user_details?.id || p.user) === employee.id,
      );
      setPayrollData(empPayroll || null);
    } catch (e) {
      setPayrollData(null);
    }
  }, [employee.id, selectedMonth]);

  useEffect(() => {
    fetchEmployee();
    fetchAttendance();
    fetchPayroll();
    fetchHolidays();
  }, [fetchEmployee, fetchAttendance, fetchPayroll, fetchHolidays]);

  const navigateMonth = (direction) => {
    const [year, month] = selectedMonth.split("-").map(Number);
    const d = new Date(year, month - 1 + direction, 1);
    setSelectedMonth(
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`,
    );
  };

  const monthLabel = () => {
    const [year, month] = selectedMonth.split("-").map(Number);
    return new Date(year, month - 1).toLocaleString("default", {
      month: "long",
      year: "numeric",
    });
  };

  const startEdit = (att) => {
    setEditingRowId(att.id);
    setEditForm({
      // Time fields — store as "HH:MM" (24-hr) for <input type="time">
      time_in: att.time_in ? att.time_in.slice(0, 5) : "",
      time_out: att.time_out ? att.time_out.slice(0, 5) : "",
    });
  };

  const cancelEdit = () => {
    setEditingRowId(null);
    setEditForm({});
  };

  const saveEdit = async (attId, att) => {
    setSaving(true);
    const timeRe = /^\d{2}:\d{2}$/;

    try {
      if (att && att._synthetic) {
        // ── Absent row: create a brand-new attendance record ──────────────
        // Both times are required to create a meaningful record
        if (!editForm.time_in || !editForm.time_out) {
          alert("Both check-in and check-out times are required.");
          setSaving(false);
          return;
        }
        // Format guard (browser enforces HH:MM, but be safe)
        if (!timeRe.test(editForm.time_in) || !timeRe.test(editForm.time_out)) {
          alert("Please enter valid times in HH:MM format (e.g. 10:00).");
          setSaving(false);
          return;
        }
        // Order guard
        const tin = new Date(`1970-01-01T${editForm.time_in}:00`);
        const tout = new Date(`1970-01-01T${editForm.time_out}:00`);
        if (tout <= tin) {
          alert("Check-out time must be after check-in time.");
          setSaving(false);
          return;
        }
        await api.post("attendance/create_record/", {
          user_id: employee.id,
          date: att.date,
          time_in: editForm.time_in + ":00",
          time_out: editForm.time_out + ":00",
        });
      } else {
        // ── Existing record: allow patching time AND status fields ───────────────────────
        const payload = {};

        if (editForm.time_in !== undefined && editForm.time_in !== "") {
          payload.time_in = editForm.time_in + ":00";
        }
        if (editForm.time_out !== undefined && editForm.time_out !== "") {
          payload.time_out = editForm.time_out + ":00";
        }
        if (editForm.status !== undefined && editForm.status !== "") {
          payload.status = editForm.status;
        }

        // Nothing to save if logic was skipped
        if (Object.keys(payload).length === 0) {
          setEditingRowId(null);
          setEditForm({});
          setSaving(false);
          return;
        }

        // Format guard
        if (
          (payload.time_in && !timeRe.test(editForm.time_in)) ||
          (payload.time_out && !timeRe.test(editForm.time_out))
        ) {
          alert("Please enter valid times in HH:MM format (e.g. 10:00).");
          setSaving(false);
          return;
        }

        // Order guard
        if (editForm.time_in !== "" && editForm.time_out !== "") {
          const tin = new Date(`1970-01-01T${editForm.time_in}:00`);
          const tout = new Date(`1970-01-01T${editForm.time_out}:00`);
          if (tout <= tin) {
            alert("Check-out time must be after check-in time.");
            setSaving(false);
            return;
          }
        }

        await api.patch(`attendance/${attId}/edit/`, payload);
      }
      setEditingRowId(null);
      setEditForm({});
      // Re-fetch everything so fines, salary, payroll are all fresh
      fetchEmployee();
      fetchAttendance();
      fetchPayroll();
      fetchHolidays();
    } catch (e) {
      console.error("Failed to save", e);
      alert("Failed to save: " + (e.response?.data?.error || e.message));
    }
    setSaving(false);
  };

  const formatTime = (timeStr) => {
    if (!timeStr) return "--:--";
    try {
      const [hours, minutes] = timeStr.split(":");
      const h = parseInt(hours, 10);
      const ampm = h >= 12 ? "PM" : "AM";
      const h12 = h % 12 || 12;
      return `${h12}:${minutes} ${ampm}`;
    } catch {
      return timeStr;
    }
  };

  const formatDate = (dateStr) => {
    const d = new Date(dateStr + "T00:00:00");
    return d.toLocaleDateString("en-US", {
      weekday: "short",
      day: "numeric",
      month: "short",
    });
  };

  const getDayOfWeek = (dateStr) => {
    const d = new Date(dateStr + "T00:00:00");
    return d.toLocaleDateString("en-US", { weekday: "short" });
  };

  const statusColors = {
    PRESENT: "bg-emerald-50 text-emerald-600",
    LATE: "bg-orange-50 text-orange-600",
    HALF_DAY: "bg-amber-50 text-amber-600",
    ABSENT: "bg-rose-50 text-rose-500",
    LEAVE: "bg-blue-50 text-blue-600",
    HOLIDAY: "bg-purple-50 text-purple-600",
  };

  const statusDots = {
    PRESENT: "bg-emerald-500",
    LATE: "bg-orange-500",
    HALF_DAY: "bg-amber-500",
    ABSENT: "bg-rose-500",
    LEAVE: "bg-blue-500",
    HOLIDAY: "bg-purple-500",
  };

  // Summary calculations — exclude today (T-1 logic, matches payroll)
  const _today = new Date();
  const todayStr = `${_today.getFullYear()}-${String(_today.getMonth() + 1).padStart(2, "0")}-${String(_today.getDate()).padStart(2, "0")}`;

  // For DAY COUNTS: exclude HOLIDAY rows (they don't count as present/absent/leave).
  // Include synthetic rows so that days with no DB record (e.g. no check-in at all)
  // are still counted as ABSENT.
  const completedForCounts = attendanceData.filter(
    (a) => a.date < todayStr && a.status !== "HOLIDAY",
  );

  // For MONEY TOTALS: real (non-synthetic) completed records only, excluding ABSENT/LEAVE.
  // ABSENT employees already lose a day's salary — their late/gap/checkout fines
  // should NOT stack on top of that.
  const completedForMoney = attendanceData.filter(
    (a) =>
      a.date < todayStr &&
      !a._synthetic &&
      !["ABSENT", "LEAVE"].includes(a.status),
  );

  // Apply paid-leave-first logic for display:
  // Pure-absent days (genuine no-shows: no check-in, synthetic or DB status=ABSENT with no time_in)
  // are credited as paid leave up to the monthly quota, mirroring payroll generation.
  // Additionally, half days are counted as 0.5 absent.

  const quota = emp?.paid_leaves_per_month || 0;

  // Days explicitly marked LEAVE in DB (by admin or prior payroll run)
  const rawLeaveCount = completedForCounts.filter((a) => a.status === "LEAVE").length;

  // ALL absent days (including manual edits and no-checkout ones) consume the leave quota
  const totalAbsentCount = completedForCounts.filter(
    (a) => a.status === "ABSENT"
  ).length;
  
  // Half days are equivalent to 0.5 absent days each
  const halfDayCount = completedForCounts.filter(
    (a) => a.status === "HALF_DAY"
  ).length;

  const totalAbsentEquivalent = totalAbsentCount + (halfDayCount * 0.5);

  // Auto-convert pure absent days (including half-day absolutes) to leave up to remaining quota
  const remainingQuota = Math.max(quota - rawLeaveCount, 0);
  const autoConvertTotal = Math.min(totalAbsentEquivalent, remainingQuota);

  const fullPresentCount = completedForCounts.filter((a) =>
    ["PRESENT", "LATE"].includes(a.status),
  ).length;

  // Present = full present + 0.5 * half_days
  const calculatedPresent = fullPresentCount + (halfDayCount * 0.5);

  const summary = {
    totalPresent: calculatedPresent,
    // Real absent = total absent equivalence BEYOND the paid-leave quota
    totalAbsent: totalAbsentEquivalent - autoConvertTotal,
    // Leave = explicit LEAVE records + auto-converted absents within quota
    totalLeave: rawLeaveCount + autoConvertTotal,
    totalFines: completedForMoney.reduce(
      (sum, a) =>
        sum +
        parseFloat(a.fine_amount || 0) +
        parseFloat(a.early_checkout_fine || 0) +
        parseFloat(a.gap_deduction || 0),
      0,
    ),
    totalOvertime: completedForMoney.reduce(
      (sum, a) => sum + parseFloat(a.overtime_amount || 0),
      0,
    ),
    totalLateMinutes: completedForMoney.reduce(
      (sum, a) => sum + (a.late_minutes || 0),
      0,
    ),
  };

  const shiftDisplay = emp.shift_details
    ? `${emp.shift_details.start_time ? new Date("1970-01-01T" + emp.shift_details.start_time).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true }) : ""} - ${emp.shift_details.end_time ? new Date("1970-01-01T" + emp.shift_details.end_time).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true }) : ""}`
    : "No Shift";

  return (
    <div className="space-y-6 max-w-[1700px] mx-auto animate-fade-in">
      {/* Back Button + Page Title */}
      <div className="flex items-center gap-4">
        <button
          onClick={onBack}
          className="flex items-center gap-2 text-gray-500 hover:text-[#E85D4E] transition-colors group"
        >
          <ArrowLeft
            size={20}
            className="group-hover:-translate-x-1 transition-transform"
          />
          <span className="text-sm font-medium">Back</span>
        </button>
      </div>

      {/* Employee Profile Card */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="bg-gradient-to-r from-[#E85D4E] to-[#D54D3E] p-6 sm:p-8">
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-6">
            <div className="w-20 h-20 bg-white/20 backdrop-blur-sm rounded-2xl flex items-center justify-center text-white font-bold text-2xl shadow-lg">
              {(emp.first_name?.[0] || "") + (emp.last_name?.[0] || "") || "U"}
            </div>
            <div className="flex-1">
              <h1 className="text-2xl font-bold text-white">
                {emp.first_name} {emp.last_name}
              </h1>
              <p className="text-white/70 text-sm mt-1">
                {emp.designation || emp.department || "Employee"} • ID: #EMP
                {String(emp.id).padStart(3, "0")}
              </p>
            </div>
          </div>
        </div>

        {/* Profile Details Grid */}
        <div className="p-6 sm:p-8 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
          <DetailCard
            icon={Phone}
            label="Contact"
            value={emp.contact || "-"}
            color="text-blue-600"
            bg="bg-blue-50"
          />
          <DetailCard
            icon={Mail}
            label="Email"
            value={emp.email || "-"}
            color="text-violet-600"
            bg="bg-violet-50"
          />
          <DetailCard
            icon={Clock}
            label="Shift"
            value={shiftDisplay}
            color="text-teal-600"
            bg="bg-teal-50"
          />
          <DetailCard
            icon={DollarSign}
            label="Salary"
            value={`₹${Number(emp.salary_per_month || 0).toLocaleString()}`}
            color="text-emerald-600"
            bg="bg-emerald-50"
          />
          <DetailCard
            icon={Shield}
            label="ESI / EPF"
            value={`₹${Number(emp.esi_amount || 0).toLocaleString()} / ₹${Number(emp.epf_amount || 0).toLocaleString()}`}
            color="text-rose-600"
            bg="bg-rose-50"
          />
        </div>
      </div>

      {/* Monthly Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        <SummaryCard
          label="Present Days"
          value={summary.totalPresent}
          color="text-emerald-600"
          bg="bg-emerald-50"
        />
        <SummaryCard
          label="Absent Days"
          value={summary.totalAbsent}
          color="text-rose-500"
          bg="bg-rose-50"
        />
        <SummaryCard
          label="Leave Days"
          value={summary.totalLeave}
          color="text-blue-600"
          bg="bg-blue-50"
        />
        <SummaryCard
          label="Late Minutes"
          value={summary.totalLateMinutes}
          color="text-orange-500"
          bg="bg-orange-50"
        />
        <SummaryCard
          label="Total Fines"
          value={`₹${summary.totalFines.toFixed(2)}`}
          color="text-[#E85D4E]"
          bg="bg-[#FEF2F2]"
        />
        <SummaryCard
          label="Total Overtime"
          value={`₹${summary.totalOvertime.toFixed(2)}`}
          color="text-emerald-600"
          bg="bg-emerald-50"
        />
      </div>

      {/* Payroll Summary (if exists) */}
      {payrollData &&
        (() => {
          // Show stored payroll values — these were computed at payroll-generation
          // time and are the source of truth shown in the Payroll list page.
          const storedFines = Number(payrollData.fine_deductions || 0);
          const storedOT = Number(payrollData.overtime_pay || 0);
          const storedNet = Number(payrollData.calculated_salary || 0);
          return (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
              <h3 className="text-sm font-bold text-gray-800 uppercase tracking-wider mb-4 flex items-center gap-2">
                <Banknote size={16} className="text-emerald-600" />
                Payroll Summary — {monthLabel()}
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
                <PayrollItem
                  label="Base Salary"
                  value={`₹${Number(payrollData.base_salary || emp.salary_per_month || 0).toFixed(2)}`}
                />
                <PayrollItem
                  label="ESI"
                  value={`-₹${Number(payrollData.esi_deductions || emp.esi_amount || 0).toFixed(2)}`}
                  color="text-rose-500"
                />
                <PayrollItem
                  label="EPF"
                  value={`-₹${Number(payrollData.epf_deductions || emp.epf_amount || 0).toFixed(2)}`}
                  color="text-rose-500"
                />
                <PayrollItem
                  label="Fines"
                  value={`-₹${storedFines.toFixed(2)}`}
                  color="text-rose-500"
                />
                <PayrollItem
                  label="Overtime"
                  value={`+₹${storedOT.toFixed(2)}`}
                  color="text-emerald-600"
                />
                <PayrollItem
                  label="Net Salary"
                  value={`₹${storedNet.toFixed(2)}`}
                  color="text-emerald-600"
                  highlight
                />
              </div>
            </div>
          );
        })()}

      {/* Attendance History */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        {/* Month Navigation */}
        <div className="p-6 border-b border-gray-100 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <h3 className="text-lg font-bold text-gray-800 flex items-center gap-2">
            <CalendarIcon size={20} className="text-[#E85D4E]" />
            Attendance History
          </h3>
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigateMonth(-1)}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <ChevronLeft size={18} className="text-gray-500" />
            </button>
            <div className="flex items-center gap-2 bg-gray-50 px-4 py-2 rounded-lg border border-gray-200">
              <CalendarIcon size={14} className="text-[#E85D4E]" />
              <span className="text-sm font-semibold text-gray-800 min-w-[140px] text-center">
                {monthLabel()}
              </span>
            </div>
            <button
              onClick={() => navigateMonth(1)}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <ChevronRight size={18} className="text-gray-500" />
            </button>
          </div>
        </div>

        {/* Attendance Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm min-w-[1100px]">
            <thead>
              <tr className="text-gray-500 text-xs font-bold uppercase tracking-wider border-b border-gray-100 bg-gray-50">
                <th className="p-4 text-center">Date</th>
                <th className="p-4 text-center">Check In</th>
                <th className="p-4 text-center">Check Out</th>
                <th className="p-4 text-center">Status</th>
                <th className="p-4 text-center">Late (min)</th>
                <th className="p-4 text-right">Late Fine</th>
                <th className="p-4 text-center">Early Out (min)</th>
                <th className="p-4 text-right">Early Fine</th>
                <th className="p-4 text-center">Worked (Min)</th>
                <th className="p-4 text-center">Gap (min)</th>
                <th className="p-4 text-right">Gap Fine</th>
                <th className="p-4 text-center">OT (min)</th>
                <th className="p-4 text-right">OT Pay</th>
                <th className="p-4 text-center">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {loading ? (
                <tr>
                  <td colSpan="14" className="p-12 text-center text-gray-400">
                    <div className="flex items-center justify-center gap-2">
                      <div className="w-5 h-5 border-2 border-[#E85D4E] border-t-transparent rounded-full animate-spin"></div>
                      Loading attendance...
                    </div>
                  </td>
                </tr>
              ) : attendanceData.length === 0 ? (
                <tr>
                  <td
                    colSpan="14"
                    className="p-12 text-center text-gray-400 italic"
                  >
                    <AlertCircle
                      size={24}
                      className="mx-auto mb-2 text-gray-300"
                    />
                    No attendance records for {monthLabel()}
                  </td>
                </tr>
              ) : (
                attendanceData.map((att) => {
                  const isEditing = editingRowId === att.id;
                  const dayName = getDayOfWeek(att.date);
                  const isSunday = dayName === "Sun";
                  const isHoliday = att._isHoliday || att.status === "HOLIDAY";

                  return (
                    <React.Fragment key={att.id}>
                      <tr
                        className={`hover:bg-gray-50/50 transition-colors ${isSunday ? "bg-red-50/30" : ""} ${isHoliday ? "bg-purple-50/40" : ""} ${isEditing ? "bg-blue-50/50 ring-1 ring-inset ring-blue-200" : ""}`}
                      >
                        <td className="p-4">
                          <div className="flex items-center gap-2">
                            {/* <span
                              className={`text-xs font-bold w-8 ${isSunday ? "text-rose-500" : "text-gray-400"}`}
                            >
                              {dayName}
                            </span> */}
                            <span className="font-medium text-gray-800">
                              {formatDate(att.date)}
                            </span>
                          </div>
                        </td>
                        <td className="p-4 text-center font-mono text-emerald-600 font-medium">
                          {isEditing ? (
                            <input
                              type="time"
                              value={editForm.time_in}
                              onChange={(e) =>
                                setEditForm({
                                  ...editForm,
                                  time_in: e.target.value,
                                })
                              }
                              className="w-28 text-center text-xs px-2 py-1 border border-emerald-300 rounded-lg outline-none focus:ring-2 focus:ring-emerald-200 font-mono"
                            />
                          ) : (
                            formatTime(att.time_in)
                          )}
                        </td>
                        <td className="p-4 text-center font-mono text-gray-400">
                          {isEditing ? (
                            <input
                              type="time"
                              value={editForm.time_out}
                              onChange={(e) =>
                                setEditForm({
                                  ...editForm,
                                  time_out: e.target.value,
                                })
                              }
                              className="w-28 text-center text-xs px-2 py-1 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-gray-200 font-mono"
                            />
                          ) : (
                            formatTime(att.time_out)
                          )}
                        </td>
                        <td className="p-4 text-center">
                          {isEditing ? (
                            <select
                              value={editForm.status || att.status}
                              onChange={(e) =>
                                setEditForm({
                                  ...editForm,
                                  status: e.target.value,
                                })
                              }
                              className="w-28 text-center text-xs px-2 py-1.5 border border-blue-300 rounded-lg outline-none focus:ring-2 focus:ring-blue-200"
                            >
                              <option value="PRESENT">Present</option>
                              <option value="HALF_DAY">Half Day</option>
                              <option value="LATE">Late</option>
                              <option value="ABSENT">Absent</option>
                              <option value="LEAVE">Leave</option>
                              <option value="HOLIDAY">Holiday</option>
                            </select>
                          ) : (
                            <span
                              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold ${statusColors[att.status] || "bg-gray-100 text-gray-500"}`}
                            >
                              <span
                                className={`w-1.5 h-1.5 rounded-full ${statusDots[att.status] || "bg-gray-400"}`}
                              ></span>
                              {att.status === "HALF_DAY"
                                ? "Half Day"
                                : att.status === "HOLIDAY"
                                  ? "Holiday"
                                  : att.status?.charAt(0) +
                                    att.status?.slice(1).toLowerCase()}
                            </span>
                          )}
                        </td>
                        <td className="p-4 text-center">
                          <span
                            className={
                              att.late_minutes > 0
                                ? "text-[#E85D4E] font-bold"
                                : "text-gray-400"
                            }
                          >
                            {att.late_minutes || 0}
                          </span>
                        </td>
                        <td className="p-4 text-right">
                          <span
                            className={
                              parseFloat(att.fine_amount) > 0
                                ? "text-[#E85D4E] font-medium"
                                : "text-gray-400"
                            }
                          >
                            ₹{Number(att.fine_amount || 0).toFixed(2)}
                          </span>
                        </td>
                        <td className="p-4 text-center">
                          <span
                            className={
                              att.early_checkout_minutes > 0
                                ? "text-orange-500 font-bold"
                                : "text-gray-400"
                            }
                          >
                            {att.early_checkout_minutes || 0}
                          </span>
                        </td>
                        <td className="p-4 text-right">
                          <span
                            className={
                              parseFloat(att.early_checkout_fine) > 0
                                ? "text-orange-500 font-medium"
                                : "text-gray-400"
                            }
                          >
                            ₹{Number(att.early_checkout_fine || 0).toFixed(2)}
                          </span>
                        </td>
                        <td className="p-4 text-center">
                          {att.total_worked_minutes > 0 ? (
                            <button
                              onClick={() =>
                                setExpandedDetailRow(
                                  expandedDetailRow === att.id ? null : att.id,
                                )
                              }
                              className="font-bold text-blue-600 hover:text-blue-800 cursor-pointer underline"
                              title="Click to see sessions"
                            >
                              {att.total_worked_minutes}
                            </button>
                          ) : (
                            <span className="text-gray-400">0</span>
                          )}
                        </td>
                        <td className="p-4 text-center">
                          <span
                            className={
                              (att.gap_minutes || 0) > 0
                                ? "text-amber-500 font-bold"
                                : "text-gray-400"
                            }
                          >
                            {att.gap_minutes || 0}
                          </span>
                        </td>
                        <td className="p-4 text-right">
                          {Number(att.gap_deduction ?? 0) > 0 ? (
                            <span className="text-red-500 font-medium">
                              ₹{Number(att.gap_deduction).toFixed(2)}
                            </span>
                          ) : (
                            <span className="text-gray-400">₹0.00</span>
                          )}
                        </td>
                        <td className="p-4 text-center">
                          <span
                            className={
                              att.overtime_minutes > 0
                                ? "text-emerald-600 font-bold"
                                : "text-gray-400"
                            }
                          >
                            {att.overtime_minutes || 0}
                          </span>
                        </td>
                        <td className="p-4 text-right">
                          <span
                            className={
                              parseFloat(att.overtime_amount) > 0
                                ? "text-emerald-600 font-medium"
                                : "text-gray-400"
                            }
                          >
                            ₹{Number(att.overtime_amount || 0).toFixed(2)}
                          </span>
                        </td>
                        <td className="p-4 text-center">
                          {isEditing ? (
                            <div className="flex items-center justify-center gap-1">
                              <button
                                onClick={() => saveEdit(att.id, att)}
                                disabled={saving}
                                className="p-1.5 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg transition-colors disabled:opacity-50"
                                title="Save"
                              >
                                <Save size={14} />
                              </button>
                              <button
                                onClick={cancelEdit}
                                className="p-1.5 bg-gray-400 hover:bg-gray-500 text-white rounded-lg transition-colors"
                                title="Cancel"
                              >
                                <X size={14} />
                              </button>
                            </div>
                          ) : isHoliday && att._synthetic ? (
                            <span className="text-xs text-purple-400 font-medium">
                              Holiday
                            </span>
                          ) : (
                            <button
                              onClick={() => startEdit(att)}
                              className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                              title="Edit this day"
                            >
                              <Edit3 size={14} />
                            </button>
                          )}
                        </td>
                      </tr>
                      {/* Expandable sessions row */}
                      {expandedDetailRow === att.id &&
                        att.sessions &&
                        att.sessions.length > 0 && (
                          <tr className="bg-blue-50/40">
                            <td colSpan="13" className="px-8 py-3">
                              <div className="text-xs font-semibold text-gray-500 uppercase mb-2">
                                Sessions
                              </div>
                              <div className="flex flex-wrap gap-3">
                                {att.sessions.map((s) => (
                                  <div
                                    key={s.id}
                                    className="bg-white border border-blue-100 rounded-lg px-4 py-2 text-sm shadow-sm"
                                  >
                                    <span className="font-bold text-blue-700">
                                      #{s.session_number}
                                    </span>
                                    <span className="ml-3 text-gray-600">
                                      {formatTime(s.time_in)}
                                    </span>
                                    <span className="mx-1 text-gray-400">
                                      →
                                    </span>
                                    <span className="text-gray-600">
                                      {formatTime(s.time_out)}
                                    </span>
                                    <span className="ml-3 font-semibold text-gray-700">
                                      {s.duration_minutes} min
                                    </span>
                                  </div>
                                ))}
                              </div>
                            </td>
                          </tr>
                        )}
                    </React.Fragment>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Table Footer */}
        <div className="p-4 border-t border-gray-100 flex justify-between items-center text-gray-400 text-sm">
          <span>
            {attendanceData.length} records for {monthLabel()}
          </span>
          {attendanceData.length > 0 && (
            <span className="text-xs">
              Click <Edit3 size={12} className="inline" /> to edit fines &
              status
            </span>
          )}
        </div>
      </div>
    </div>
  );
};

// --- Helper Components ---

const DetailCard = ({ icon: Icon, label, value, color, bg }) => (
  <div className="flex items-start gap-3 p-3 rounded-xl bg-gray-50/50">
    <div className={`p-2 rounded-lg ${bg}`}>
      <Icon size={16} className={color} />
    </div>
    <div className="min-w-0 flex-1">
      <p className="text-xs text-gray-400 font-medium">{label}</p>
      <p className="text-sm font-semibold text-gray-800 truncate">{value}</p>
    </div>
  </div>
);

const SummaryCard = ({ label, value, color, bg }) => (
  <div className={`${bg} rounded-xl p-4 text-center`}>
    <p className={`text-2xl font-bold ${color}`}>{value}</p>
    <p className="text-xs text-gray-500 font-medium mt-1">{label}</p>
  </div>
);

const PayrollItem = ({
  label,
  value,
  color = "text-gray-800",
  highlight = false,
}) => (
  <div
    className={`p-3 rounded-xl ${highlight ? "bg-emerald-50 border border-emerald-200" : "bg-gray-50"}`}
  >
    <p className="text-xs text-gray-400 font-medium">{label}</p>
    <p className={`text-sm font-bold ${color} mt-1 font-mono`}>{value}</p>
  </div>
);

export default EmployeeDetailPage;
