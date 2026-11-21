import React, { useEffect, useState } from 'react';
import api from '../../services/api';
import { Search, Calendar as CalendarIcon, X, Trash2, AlertTriangle } from 'lucide-react';

const EmployeesSection = ({ onEmployeeClick }) => {
  const [employees, setEmployees] = useState([]);
  const [shifts, setShifts] = useState([]);
  const [attendanceMap, setAttendanceMap] = useState({});
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedShift, setSelectedShift] = useState("");
  const [loading, setLoading] = useState(true);
  const [selectedDate, setSelectedDate] = useState(() => {
    const d = new Date();
    const offset = d.getTimezoneOffset() * 60000;
    return new Date(d.getTime() - offset).toISOString().slice(0, 10);
  });

  // Edit Modal State
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingEmployee, setEditingEmployee] = useState(null);
  const [editForm, setEditForm] = useState({
    // Personal
    first_name: '',
    last_name: '',
    contact: '',
    email: '',
    department: '',
    designation: '',
    // Shift
    shift: '',
    // Financial
    salary_per_month: 0,
    esi_amount: 0,
    epf_amount: 0,
    paid_leaves_per_month: 1,
    // Today's attendance data (for fine/overtime editing)
    fine_amount: 0,
    early_checkout_fine: 0,
    overtime_amount: 0,
  });
  const [attendanceId, setAttendanceId] = useState(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    fetchData();
  }, [selectedDate]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [empRes, shiftRes, attRes] = await Promise.all([
        api.get("users/?role=EMPLOYEE"),
        api.get("shifts/"),
        api.get(`attendance/?date=${selectedDate}`),
      ]);
      setEmployees(
        Array.isArray(empRes.data) ? empRes.data : empRes.data.results || [],
      );
      setShifts(
        Array.isArray(shiftRes.data)
          ? shiftRes.data
          : shiftRes.data.results || [],
      );

      const attData = Array.isArray(attRes.data)
        ? attRes.data
        : attRes.data.results || [];
      const map = {};
      attData.forEach((att) => {
        map[att.user?.id || att.user] = att;
      });
      setAttendanceMap(map);
    } catch (e) {
      console.error("Failed to fetch employees or shifts", e);
    }
    setLoading(false);
  };

  const openEditModal = (emp) => {
    const att = attendanceMap[emp.id];
    setEditingEmployee(emp);
    setAttendanceId(att?.id || null);
    setEditForm({
      first_name: emp.first_name || '',
      last_name: emp.last_name || '',
      contact: emp.contact || '',
      email: emp.email || '',
      department: emp.department || '',
      designation: emp.designation || '',
      shift: emp.shift || '',
      salary_per_month: emp.salary_per_month || 0,
      esi_amount: emp.esi_amount || 0,
      epf_amount: emp.epf_amount || 0,
      paid_leaves_per_month: emp.paid_leaves_per_month || 1,
      // Attendance data for today
      fine_amount: att?.fine_amount || 0,
      early_checkout_fine: att?.early_checkout_fine || 0,
      overtime_amount: att?.overtime_amount || 0,
    });
    setShowEditModal(true);
    setShowDeleteConfirm(false);
  };

  const handleDeleteEmployee = async () => {
    setDeleting(true);
    try {
      await api.delete(`users/${editingEmployee.id}/`);
      setShowEditModal(false);
      setShowDeleteConfirm(false);
      fetchData();
    } catch (e) {
      console.error('Failed to delete employee', e);
      alert('Failed to delete: ' + (e.response?.data?.error || e.response?.data?.detail || e.message));
    }
    setDeleting(false);
  };

  const handleSaveAll = async () => {
    // ── Name validation ──────────────────────────────────────────────
    const nameRe = /^[a-zA-Z\s\-']+$/;
    const fn = editForm.first_name.trim();
    const ln = editForm.last_name.trim();

    if (!fn || fn.length < 2 || fn.length > 25) {
      alert("First name must be between 2 and 25 characters.");
      return;
    }
    if (!nameRe.test(fn)) {
      alert(
        "First name can only contain letters, spaces, hyphens, or apostrophes.",
      );
      return;
    }
    // ────────────────────────────────────────────────────────────────
    try {
      // Update User Profile
      const userPayload = {
        first_name: editForm.first_name,
        last_name: editForm.last_name,
        contact: editForm.contact,
        email: editForm.email,
        department: editForm.department,
        designation: editForm.designation,
        shift: editForm.shift || null,
        salary_per_month: editForm.salary_per_month,
        esi_amount: editForm.esi_amount,
        epf_amount: editForm.epf_amount,
        paid_leaves_per_month: editForm.paid_leaves_per_month,
      };

      await api.patch(`users/${editingEmployee.id}/`, userPayload);

      // Update Attendance (fine, overtime) if attendance exists for today
      if (attendanceId) {
        const attPayload = {
          fine_amount: editForm.fine_amount,
          early_checkout_fine: editForm.early_checkout_fine,
          overtime_amount: editForm.overtime_amount,
          fine_edited: true,
        };
        await api.patch(`attendance/${attendanceId}/edit/`, attPayload);
      }

      alert("Employee updated successfully!");
      setShowEditModal(false);
      fetchData();
    } catch (e) {
      console.error("Failed to update employee", e);
      alert("Failed to update: " + (e.response?.data?.error || e.message));
    }
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

  const filteredEmployees = employees
    .filter((emp) => {
      const q = searchQuery.toLowerCase();
      const name =
        `${emp.first_name || ""} ${emp.last_name || ""}`.toLowerCase();
      const contact = (emp.contact || "").toLowerCase();
      const matchesSearch = name.includes(q) || contact.includes(q);
      const matchesShift =
        !selectedShift || String(emp.shift) === selectedShift;
      return matchesSearch && matchesShift;
    })
    .sort((a, b) => {
      const nameA = `${a.first_name || ""} ${a.last_name || ""}`.toLowerCase();
      const nameB = `${b.first_name || ""} ${b.last_name || ""}`.toLowerCase();
      return nameA.localeCompare(nameB);
    });

  const avatarColors = [
    "bg-indigo-500",
    "bg-emerald-500",
    "bg-amber-500",
    "bg-pink-500",
    "bg-teal-500",
    "bg-rose-500",
    "bg-violet-500",
    "bg-cyan-500",
  ];

  if (loading)
    return (
      <div className="text-center py-12 text-gray-400">
        Loading employees...
      </div>
    );

  return (
    <>
      <div className="space-y-6 max-w-[1700px] mx-auto animate-fade-in">
        {/* Header */}
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <h2 className="text-xl font-bold text-gray-800">
              Employee Management
            </h2>
            <p className="text-sm text-gray-500 mt-1">
              Manage profiles, shifts, leaves, and fines
            </p>
          </div>
          <div className="flex flex-col sm:flex-row gap-3 w-full md:w-auto">
            <div className="relative">
              <CalendarIcon
                className="absolute left-3 top-1/2 -translate-y-1/2 text-[#E85D4E]"
                size={16}
              />
              <input
                type="date"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                className="w-full sm:w-auto pl-10 pr-4 py-2.5 bg-gray-50 border border-gray-200 rounded-lg text-sm font-medium text-gray-800 outline-none focus:ring-2 focus:ring-[#E85D4E]/20 focus:border-[#E85D4E]"
              />
            </div>
            <select
              value={selectedShift}
              onChange={(e) => setSelectedShift(e.target.value)}
              className="w-full sm:w-auto px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-lg text-sm font-medium text-gray-800 outline-none focus:ring-2 focus:ring-[#E85D4E]/20 focus:border-[#E85D4E] cursor-pointer"
            >
              <option value="">All Shifts</option>
              {shifts.map((s) => (
                <option key={s.id} value={String(s.id)}>
                  {s.name}
                </option>
              ))}
            </select>
            <div className="relative flex-1">
              <Search
                className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
                size={16}
              />
              <input
                type="text"
                placeholder="Search employees..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-10 py-2.5 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-800 placeholder-gray-400 outline-none focus:ring-2 focus:ring-[#E85D4E]/20"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
                >
                  <X size={16} />
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Employee Table */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
          <div className="p-4 border-b border-gray-100 bg-gray-50 flex justify-between items-center">
            <span className="text-sm font-medium text-gray-600">
              Showing for:{" "}
              {new Date(selectedDate).toLocaleDateString("en-US", {
                weekday: "long",
                month: "long",
                day: "numeric",
              })}
            </span>
            <span className="text-xs text-gray-400">
              {filteredEmployees.length} employees
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm whitespace-nowrap">
              <thead>
                <tr className="text-gray-500 text-xs font-bold uppercase tracking-wider border-b border-gray-100 bg-gray-50">
                  <th className="p-4">Employee</th>
                  <th className="p-4">Contact</th>
                  <th className="p-4">Shift</th>
                  <th className="p-4 text-center">Check In</th>
                  <th className="p-4 text-center">Check Out</th>
                  <th className="p-4 text-center">Status</th>
                  <th className="p-4 text-center">Late (min)</th>
                  <th className="p-4 text-center">Fine</th>
                  <th className="p-4 text-center">Leaves</th>
                  <th className="p-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filteredEmployees.map((emp, idx) => {
                  const att = attendanceMap[emp.id];
                  const shiftName =
                    emp.shift_details?.name ||
                    shifts.find((s) => s.id === emp.shift)?.name ||
                    "No Shift";

                  return (
                    <tr
                      key={emp.id}
                      className="hover:bg-gray-50 transition-colors"
                    >
                      <td className="p-4">
                        <div className="flex items-center gap-3">
                          <div
                            className={`w-9 h-9 flex-shrink-0 rounded-full flex items-center justify-center text-white font-bold text-xs ${avatarColors[idx % avatarColors.length]}`}
                          >
                            {(emp.first_name?.[0] || "") +
                              (emp.last_name?.[0] || "") || "U"}
                          </div>
                          <div>
                            <button
                              onClick={() =>
                                onEmployeeClick && onEmployeeClick(emp)
                              }
                              className="font-medium text-gray-800 hover:text-[#E85D4E] hover:underline transition-colors text-left cursor-pointer"
                            >
                              {emp.first_name} {emp.last_name}
                            </button>
                            <div className="text-xs text-gray-400">
                              {emp.department || "N/A"}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="p-4">
                        <div className="text-gray-600">
                          {emp.contact || "-"}
                        </div>
                        <div className="text-xs text-gray-400 font-mono">
                          ₹{Number(emp.salary_per_month || 0).toLocaleString()}
                        </div>
                      </td>
                      <td className="p-4">
                        <div className="flex flex-col">
                          <span className="px-2 py-1 bg-blue-50 text-blue-700 text-xs font-medium rounded-lg inline-block w-fit">
                            {shiftName}
                          </span>
                          {emp.shift_details && (
                            <span className="text-[10px] text-gray-400 mt-1 pl-1">
                              {formatTime(emp.shift_details.start_time)} -{" "}
                              {formatTime(emp.shift_details.end_time)}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="p-4 text-center font-mono text-emerald-600 font-medium">
                        {att?.time_in ? formatTime(att.time_in) : "--:--"}
                      </td>
                      <td className="p-4 text-center font-mono text-gray-500">
                        {att?.time_out ? formatTime(att.time_out) : "--:--"}
                      </td>
                      <td className="p-4 text-center">
                        {(() => {
                          const status = att?.status || "ABSENT";
                          const colorMap = {
                            PRESENT: "bg-emerald-50 text-emerald-600",
                            LATE: "bg-red-50 text-red-600",
                            HALF_DAY: "bg-amber-50 text-amber-600",
                            ABSENT: "bg-rose-50 text-rose-500",
                            LEAVE: "bg-blue-50 text-blue-600",
                            HOLIDAY: "bg-purple-50 text-purple-600",
                          };
                          const dotMap = {
                            PRESENT: "bg-emerald-500",
                            LATE: "bg-red-500",
                            HALF_DAY: "bg-amber-500",
                            ABSENT: "bg-rose-500",
                            LEAVE: "bg-blue-500",
                            HOLIDAY: "bg-purple-500",
                          };
                          const labelMap = {
                            PRESENT: "Present",
                            LATE: "Late",
                            HALF_DAY: "Half Day",
                            ABSENT: "Absent",
                            LEAVE: "Leave",
                            HOLIDAY: "Holiday",
                          };
                          return (
                            <span
                              className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-semibold ${colorMap[status] || "bg-gray-100 text-gray-500"}`}
                            >
                              <span
                                className={`w-1.5 h-1.5 rounded-full ${dotMap[status] || "bg-gray-400"}`}
                              ></span>
                              {labelMap[status] || status}
                            </span>
                          );
                        })()}
                      </td>
                      <td className="p-4 text-center">
                        {att?.late_minutes > 0 ? (
                          <span className="text-[#E85D4E] font-bold">
                            {att.late_minutes}
                          </span>
                        ) : (
                          <span className="text-gray-400">0</span>
                        )}
                      </td>
                      <td className="p-4 text-center">
                        <span
                          className={`font-medium ${att?.fine_amount > 0 ? "text-[#E85D4E]" : "text-gray-400"}`}
                        >
                          ₹{Number(att?.fine_amount || 0).toFixed(2)}
                        </span>
                      </td>
                      <td className="p-4 text-center">
                        <span
                          className={`px-2 py-1 rounded-lg text-xs font-bold ${(emp.leaves_taken_this_month || 0) >
                              emp.paid_leaves_per_month
                              ? "bg-red-50 text-red-600"
                              : (emp.leaves_taken_this_month || 0) ===
                                emp.paid_leaves_per_month
                                ? "bg-amber-50 text-amber-700"
                                : "bg-emerald-50 text-emerald-700"
                            }`}
                        >
                          {emp.leaves_taken_this_month}
                        </span>
                      </td>
                      <td className="p-4 text-right">
                        <button
                          onClick={() => openEditModal(emp)}
                          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-1.5 rounded-lg text-xs font-medium transition-colors"
                        >
                          Edit
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      {/* Edit Modal */}
      {showEditModal && editingEmployee && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 backdrop-blur-sm p-4 overflow-y-auto">
          <div className="bg-white rounded-2xl w-full max-w-3xl shadow-2xl overflow-hidden flex flex-col my-auto max-h-[90vh]">
            {/* Modal Header */}
            <div className="p-6 border-b border-gray-100 flex justify-between items-center bg-gray-50">
              <div>
                <h4 className="text-lg font-bold text-gray-800">
                  Edit Employee
                </h4>
                <p className="text-sm text-gray-500">
                  {editingEmployee.first_name} {editingEmployee.last_name}
                </p>
              </div>
              <button
                onClick={() => setShowEditModal(false)}
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <X size={20} className="text-gray-500" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto flex-1">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Personal Details */}
                <div className="space-y-4">
                  <h5 className="text-sm font-bold text-[#E85D4E] uppercase border-b border-[#E85D4E]/20 pb-2">
                    Personal Details
                  </h5>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">
                        First Name
                      </label>
                      <input
                        type="text"
                        value={editForm.first_name}
                        onChange={(e) =>
                          setEditForm({
                            ...editForm,
                            first_name: e.target.value,
                          })
                        }
                        className="w-full p-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#E85D4E]/20 focus:border-[#E85D4E] outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">
                        Last Name
                      </label>
                      <input
                        type="text"
                        value={editForm.last_name}
                        onChange={(e) =>
                          setEditForm({
                            ...editForm,
                            last_name: e.target.value,
                          })
                        }
                        className="w-full p-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#E85D4E]/20 focus:border-[#E85D4E] outline-none"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">
                      Contact
                    </label>
                    <input
                      type="text"
                      value={editForm.contact}
                      onChange={(e) =>
                        setEditForm({ ...editForm, contact: e.target.value })
                      }
                      className="w-full p-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#E85D4E]/20 focus:border-[#E85D4E] outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">
                      Email
                    </label>
                    <input
                      type="email"
                      value={editForm.email}
                      onChange={(e) =>
                        setEditForm({ ...editForm, email: e.target.value })
                      }
                      className="w-full p-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#E85D4E]/20 focus:border-[#E85D4E] outline-none"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">
                        Department
                      </label>
                      <input
                        type="text"
                        value={editForm.department}
                        onChange={(e) =>
                          setEditForm({
                            ...editForm,
                            department: e.target.value,
                          })
                        }
                        className="w-full p-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#E85D4E]/20 focus:border-[#E85D4E] outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">
                        Designation
                      </label>
                      <input
                        type="text"
                        value={editForm.designation}
                        onChange={(e) =>
                          setEditForm({
                            ...editForm,
                            designation: e.target.value,
                          })
                        }
                        className="w-full p-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#E85D4E]/20 focus:border-[#E85D4E] outline-none"
                      />
                    </div>
                  </div>
                </div>

                {/* Shift & Leaves */}
                <div className="space-y-4">
                  <h5 className="text-sm font-bold text-blue-600 uppercase border-b border-blue-100 pb-2">
                    Shift & Leaves
                  </h5>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">
                      Assigned Shift
                    </label>
                    <select
                      value={editForm.shift}
                      onChange={(e) =>
                        setEditForm({ ...editForm, shift: e.target.value })
                      }
                      className="w-full p-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-200 focus:border-blue-500 outline-none"
                    >
                      <option value="">No Shift</option>
                      {shifts.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name} ({s.display_name})
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">
                      Paid Leaves / Month (Quota)
                    </label>
                    <input
                      type="number"
                      min="0"
                      value={editForm.paid_leaves_per_month}
                      onChange={(e) =>
                        setEditForm({
                          ...editForm,
                          paid_leaves_per_month: e.target.value,
                        })
                      }
                      className="w-full p-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-200 focus:border-blue-500 outline-none"
                    />
                  </div>

                  <h5 className="text-sm font-bold text-emerald-600 uppercase border-b border-emerald-100 pb-2 mt-6">
                    Salary & Deductions
                  </h5>
                  <div>
                    <label className="block text-xs font-bold text-gray-700 mb-1">
                      Monthly Salary (₹)
                    </label>
                    <input
                      type="number"
                      value={editForm.salary_per_month}
                      onChange={(e) =>
                        setEditForm({
                          ...editForm,
                          salary_per_month: e.target.value,
                        })
                      }
                      className="w-full p-2 border-2 border-emerald-200 rounded-lg text-sm font-mono focus:ring-2 focus:ring-emerald-200 focus:border-emerald-500 outline-none"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">
                        ESI Amount
                      </label>
                      <input
                        type="number"
                        value={editForm.esi_amount}
                        onChange={(e) =>
                          setEditForm({
                            ...editForm,
                            esi_amount: e.target.value,
                          })
                        }
                        className="w-full p-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-emerald-200 focus:border-emerald-500 outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">
                        EPF Amount
                      </label>
                      <input
                        type="number"
                        value={editForm.epf_amount}
                        onChange={(e) =>
                          setEditForm({
                            ...editForm,
                            epf_amount: e.target.value,
                          })
                        }
                        className="w-full p-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-emerald-200 focus:border-emerald-500 outline-none"
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* Today's Attendance Adjustments */}
              {attendanceId && (
                <div className="mt-6 pt-6 border-t border-gray-200">
                  <h5 className="text-sm font-bold text-[#E85D4E] uppercase mb-4">
                    Today's Attendance Adjustments (
                    {new Date(selectedDate).toLocaleDateString()})
                  </h5>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">
                        Late Fine (₹)
                      </label>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        value={editForm.fine_amount}
                        onChange={(e) =>
                          setEditForm({
                            ...editForm,
                            fine_amount: e.target.value,
                          })
                        }
                        className="w-full p-2 border border-red-200 rounded-lg text-sm focus:ring-2 focus:ring-red-200 focus:border-red-500 outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">
                        Early Checkout Fine (₹)
                      </label>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        value={editForm.early_checkout_fine}
                        onChange={(e) =>
                          setEditForm({
                            ...editForm,
                            early_checkout_fine: e.target.value,
                          })
                        }
                        className="w-full p-2 border border-orange-200 rounded-lg text-sm focus:ring-2 focus:ring-orange-200 focus:border-orange-500 outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">
                        Overtime Pay (₹)
                      </label>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        value={editForm.overtime_amount}
                        onChange={(e) =>
                          setEditForm({
                            ...editForm,
                            overtime_amount: e.target.value,
                          })
                        }
                        className="w-full p-2 border border-blue-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-200 focus:border-blue-500 outline-none"
                      />
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-6 border-t border-gray-100 bg-gray-50">
              {showDeleteConfirm ? (
                <div className="flex flex-col gap-3">
                  <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg">
                    <AlertTriangle size={18} className="text-red-600 flex-shrink-0" />
                    <p className="text-sm text-red-700">
                      <strong>Are you sure?</strong> This will permanently delete <strong>{editingEmployee.first_name} {editingEmployee.last_name}</strong> and all their attendance records. This action cannot be undone.
                    </p>
                  </div>
                  <div className="flex justify-end gap-3">
                    <button
                      onClick={() => setShowDeleteConfirm(false)}
                      className="px-5 py-2.5 text-gray-600 hover:bg-gray-100 rounded-lg text-sm font-medium transition-colors"
                    >
                      No, Keep Employee
                    </button>
                    <button
                      onClick={handleDeleteEmployee}
                      disabled={deleting}
                      className="px-5 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-medium shadow-lg shadow-red-600/30 transition-all disabled:opacity-50 flex items-center gap-2"
                    >
                      <Trash2 size={14} />
                      {deleting ? 'Deleting...' : 'Yes, Delete Permanently'}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex justify-between items-center">
                  <button
                    onClick={() => setShowDeleteConfirm(true)}
                    className="px-4 py-2.5 text-red-600 hover:bg-red-50 border border-red-200 rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
                  >
                    <Trash2 size={14} />
                    Delete Employee
                  </button>
                  <div className="flex gap-3">
                    <button
                      onClick={() => setShowEditModal(false)}
                      className="px-5 py-2.5 text-gray-600 hover:bg-gray-100 rounded-lg text-sm font-medium transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleSaveAll}
                      className="px-5 py-2.5 bg-[#E85D4E] hover:bg-[#D54D3E] text-white rounded-lg text-sm font-medium shadow-lg shadow-[#E85D4E]/30 transition-all"
                    >
                      Save All Changes
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default EmployeesSection;
