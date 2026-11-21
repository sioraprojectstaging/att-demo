import React, { useState } from "react";
import {
  Search,
  Calendar as CalendarIcon,
  Download,
  BarChart2 as BarChartIcon,
  X,
} from "lucide-react";

const AttendanceSection = ({
  dateFilter,
  setDateFilter,
  searchQuery,
  setSearchQuery,
  downloadPDF,
  filteredLogs,
  onEmployeeClick,
}) => {
  const [expandedRow, setExpandedRow] = useState(null);
  const formatTime = (timeStr) => {
    if (!timeStr) return "--:--";
    try {
      const [hours, minutes] = timeStr.split(":");
      const h = parseInt(hours, 10);
      const ampm = h >= 12 ? "PM" : "AM";
      const h12 = h % 12 || 12;
      return `${String(h12).padStart(2, "0")}:${minutes} ${ampm}`;
    } catch {
      return timeStr;
    }
  };

  const getInitials = (log) => {
    const fn = log.user?.first_name || "";
    const ln = log.user?.last_name || "";
    if (fn && ln) return `${fn[0]}${ln[0]}`.toUpperCase();
    if (fn) return fn.slice(0, 2).toUpperCase();
    return "U";
  };

  const avatarColors = [
    "bg-violet-500",
    "bg-pink-500",
    "bg-amber-500",
    "bg-teal-500",
    "bg-blue-500",
    "bg-rose-500",
  ];

  return (
    <div className="space-y-6 max-w-[1700px] mx-auto animate-fade-in">
      {/* Filter Bar */}
      <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div className="flex flex-col sm:flex-row gap-4 w-full md:w-auto">
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
              Select Date
            </label>
            <div className="relative">
              <CalendarIcon
                className="absolute left-3 top-1/2 -translate-y-1/2 text-[#E85D4E]"
                size={16}
              />
              <input
                type="date"
                value={dateFilter}
                onChange={(e) => setDateFilter(e.target.value)}
                className="pl-10 pr-4 py-2.5 bg-gray-50 border border-gray-200 rounded-lg text-sm font-medium text-gray-800 outline-none focus:ring-2 focus:ring-[#E85D4E]/20 focus:border-[#E85D4E] w-full sm:w-48 transition-all"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
              Search Employee
            </label>
            <div className="relative">
              <Search
                className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
                size={16}
              />
              <input
                type="text"
                placeholder="Search by name or ID..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full sm:w-72 pl-10 pr-10 py-2.5 bg-gray-50 border border-gray-200 rounded-lg text-sm font-medium text-gray-800 placeholder-gray-400 outline-none focus:ring-2 focus:ring-[#E85D4E]/20 focus:border-[#E85D4E] transition-all"
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
        <button
          onClick={downloadPDF}
          className="flex items-center gap-2 bg-[#E85D4E] hover:bg-[#D54D3E] text-white px-5 py-2.5 rounded-lg text-sm font-semibold transition-colors shadow-sm mt-4 md:mt-6"
        >
          <Download size={16} /> Export PDF
        </button>
      </div>

      {/* Data Card */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="p-6 border-b border-gray-100 flex justify-between items-center">
          <h3 className="text-gray-800 font-bold text-lg flex items-center gap-2">
            <BarChartIcon size={20} className="text-[#E85D4E]" /> Employee Time
            & Status
          </h3>
          <span className="bg-[#FEF2F2] text-[#E85D4E] text-xs font-semibold px-3 py-1.5 rounded-full">
            {new Date(dateFilter).toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
              year: "numeric",
            })}
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm min-w-[1000px]">
            <thead>
              <tr className="text-gray-500 text-xs font-semibold uppercase tracking-wider border-b border-gray-100">
                <th className="p-5">Employee</th>
                <th className="p-5 text-center">Time In</th>
                <th className="p-5 text-center">Time Out</th>
                <th className="p-5 text-center">Late (Min)</th>
                <th className="p-5 text-center">Late Checkin Fine</th>
                <th className="p-5 text-center">Early (Min)</th>
                <th className="p-5 text-center">Early Checkout Fine</th>
                <th className="p-5 text-center">Worked (Min)</th>
                <th className="p-5 text-center">Gap Ded.</th>
                <th className="p-5 text-center">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {filteredLogs.length > 0 ? (
                filteredLogs.map((log, index) => (
                  <React.Fragment key={log.id}>
                    <tr className="hover:bg-gray-50/50 transition-colors">
                      <td className="p-5">
                        <div className="flex items-center gap-3">
                          <div
                            className={`w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-sm ${avatarColors[index % avatarColors.length]}`}
                          >
                            {getInitials(log)}
                          </div>
                          <div>
                            <button
                              onClick={() =>
                                onEmployeeClick &&
                                log.user &&
                                onEmployeeClick(log.user)
                              }
                              className="font-semibold text-gray-800 hover:text-[#E85D4E] hover:underline transition-colors text-left cursor-pointer"
                            >
                              {log.user
                                ? `${log.user.first_name || ""} ${log.user.last_name || ""}`.trim() ||
                                  "Unknown"
                                : `User #${log.user}`}
                            </button>
                            <div className="text-xs text-gray-400">
                              ID: #EMP
                              {String(log.user?.id || log.id).padStart(3, "0")}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="p-5 text-center font-mono text-gray-600">
                        {formatTime(log.time_in)}
                      </td>
                      <td className="p-5 text-center font-mono text-gray-400">
                        {formatTime(log.time_out)}
                      </td>
                      <td className="p-5 text-center">
                        {log.late_minutes !== null &&
                        log.late_minutes !== undefined &&
                        Number(log.late_minutes) > 0 ? (
                          <span className="text-[#E85D4E] font-bold">
                            {Number(log.late_minutes)}
                          </span>
                        ) : (
                          <span className="text-gray-400">0</span>
                        )}
                      </td>
                      <td className="p-5 text-center text-gray-600">
                        ₹{Number(log.fine_amount ?? 0).toFixed(2)}
                      </td>
                      <td className="p-5 text-center">
                        {log.early_checkout_minutes !== null &&
                        log.early_checkout_minutes !== undefined &&
                        Number(log.early_checkout_minutes) > 0 ? (
                          <span className="text-orange-500 font-bold">
                            {Number(log.early_checkout_minutes)}
                          </span>
                        ) : (
                          <span className="text-gray-400">0</span>
                        )}
                      </td>
                      <td className="p-5 text-center font-mono text-gray-600">
                        ₹{Number(log.early_checkout_fine ?? 0).toFixed(2)}
                      </td>
                      <td className="p-5 text-center">
                        {log.total_worked_minutes > 0 ? (
                          <button
                            onClick={() =>
                              setExpandedRow(
                                expandedRow === log.id ? null : log.id,
                              )
                            }
                            className="font-bold text-blue-600 hover:text-blue-800 cursor-pointer underline"
                            title="Click to see sessions"
                          >
                            {log.total_worked_minutes}
                          </button>
                        ) : (
                          <span className="text-gray-400">0</span>
                        )}
                      </td>
                      <td className="p-5 text-center">
                        {Number(log.gap_deduction ?? 0) > 0 ? (
                          <span className="text-red-500 font-bold">
                            ₹{Number(log.gap_deduction).toFixed(2)}
                          </span>
                        ) : (
                          <span className="text-gray-400">₹0.00</span>
                        )}
                      </td>
                      <td className="p-5 text-center">
                        <span
                          className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold ${
                            log.status === "PRESENT" &&
                            log.late_minutes === 0 &&
                            (log.early_checkout_minutes || 0) === 0
                              ? "bg-emerald-50 text-emerald-600"
                              : log.status === "PRESENT" &&
                                  (log.late_minutes > 0 ||
                                    (log.early_checkout_minutes || 0) > 0)
                                ? "bg-orange-50 text-orange-500"
                                : log.status === "HALF_DAY"
                                  ? "bg-amber-50 text-amber-600"
                                  : log.status === "ABSENT"
                                    ? "bg-rose-50 text-rose-500"
                                    : log.status === "LEAVE"
                                      ? "bg-blue-50 text-blue-600"
                                      : log.status === "HOLIDAY"
                                        ? "bg-purple-50 text-purple-600"
                                        : "bg-rose-50 text-rose-500"
                          }`}
                        >
                          <span
                            className={`w-1.5 h-1.5 rounded-full ${
                              log.status === "PRESENT" &&
                              log.late_minutes === 0 &&
                              (log.early_checkout_minutes || 0) === 0
                                ? "bg-emerald-500"
                                : log.status === "PRESENT" &&
                                    (log.late_minutes > 0 ||
                                      (log.early_checkout_minutes || 0) > 0)
                                  ? "bg-orange-500"
                                  : log.status === "HALF_DAY"
                                    ? "bg-amber-500"
                                    : log.status === "ABSENT"
                                      ? "bg-rose-500"
                                      : log.status === "LEAVE"
                                        ? "bg-blue-500"
                                        : log.status === "HOLIDAY"
                                          ? "bg-purple-500"
                                          : "bg-rose-500"
                            }`}
                          ></span>
                          {log.status === "PRESENT" && log.late_minutes > 0
                            ? "Late"
                            : log.status === "PRESENT" &&
                                (log.early_checkout_minutes || 0) > 0
                              ? "Early Out"
                              : log.status === "PRESENT"
                                ? "Present"
                                : log.status === "HALF_DAY"
                                  ? "Half Day"
                                  : log.status === "ABSENT"
                                    ? "Absent"
                                    : log.status === "LEAVE"
                                      ? "Leave"
                                      : log.status === "HOLIDAY"
                                        ? "Holiday"
                                        : log.status}
                        </span>
                      </td>
                    </tr>
                    {/* Expandable sessions row */}
                    {expandedRow === log.id &&
                      log.sessions &&
                      log.sessions.length > 0 && (
                        <tr className="bg-blue-50/40">
                          <td colSpan="10" className="px-8 py-3">
                            <div className="text-xs font-semibold text-gray-500 uppercase mb-2">
                              Sessions
                            </div>
                            <div className="flex flex-wrap gap-3">
                              {log.sessions.map((s) => (
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
                                  <span className="mx-1 text-gray-400">→</span>
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
                ))
              ) : (
                <tr>
                  <td
                    colSpan="10"
                    className="p-12 text-center text-gray-400 italic"
                  >
                    No attendance records found for this date.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="p-4 border-t border-gray-100 flex justify-between items-center text-gray-400 text-sm">
          <span>
            Showing {filteredLogs.length} of {filteredLogs.length} records
          </span>
        </div>
      </div>
    </div>
  );
};

export default AttendanceSection;
