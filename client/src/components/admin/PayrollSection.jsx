import React, { useState } from "react";
import api, { API_BASE_URL } from "../../services/api";
import {
  Search,
  Calendar as CalendarIcon,
  Download,
  Settings,
  Banknote,
  CheckCircle,
  X,
} from "lucide-react";

const PayrollSection = ({
  payrollMonth,
  setPayrollMonth,
  handleGeneratePayroll,
  payrollData,
  setPayrollData,
  downloadPayrollPDF,
  onEmployeeClick,
}) => {
  const [editMode, setEditMode] = useState(false);
  const [editedData, setEditedData] = useState({});
  const [searchQuery, setSearchQuery] = useState(
    () => sessionStorage.getItem("payrollSearchQuery") || "",
  );
  const [shiftFilter, setShiftFilter] = useState(
    () => sessionStorage.getItem("payrollShiftFilter") || "all",
  );

  React.useEffect(() => {
    sessionStorage.setItem("payrollSearchQuery", searchQuery);
  }, [searchQuery]);

  React.useEffect(() => {
    sessionStorage.setItem("payrollShiftFilter", shiftFilter);
  }, [shiftFilter]);

  // Sanitize input: only allow digits and one decimal point, no negatives/alphabets
  const sanitizeNumericInput = (value) => {
    // Remove everything except digits and decimal point
    let sanitized = value.replace(/[^0-9.]/g, "");
    // Ensure only one decimal point
    const parts = sanitized.split(".");
    if (parts.length > 2) {
      sanitized = parts[0] + "." + parts.slice(1).join("");
    }
    // Limit to 9999999.99
    if (sanitized && parseFloat(sanitized) > 9999999) {
      sanitized = "9999999";
    }
    return sanitized;
  };

  const handleFieldChange = (id, field, rawValue) => {
    const sanitized = sanitizeNumericInput(rawValue);
    setEditedData((prev) => ({
      ...prev,
      [id]: { ...(prev[id] || {}), [field]: sanitized },
    }));
    return sanitized;
  };

  const saveAllChanges = async () => {
    // Validate all edited fields before saving
    for (const [id, data] of Object.entries(editedData)) {
      for (const [field, value] of Object.entries(data)) {
        const num = parseFloat(value);
        if (isNaN(num) || num < 0) {
          alert(
            `Invalid value for ${field.replace(/_/g, " ")}. Please enter a valid positive number.`,
          );
          return;
        }
        if (num > 9999999) {
          alert(
            `Value for ${field.replace(/_/g, " ")} is too large. Maximum allowed is 9,999,999.`,
          );
          return;
        }
      }
    }

    try {
      for (const [id, data] of Object.entries(editedData)) {
        // log
        if (Object.keys(data).length > 0) {
          await api.patch(`payroll/${id}/update_base_salary/`, data);
          //log
        }
      }
      // Fetch updated payroll data (don't regenerate - that would overwrite edits!)
      const res = await api.get(`payroll/fetch/?month=${payrollMonth}`);
      setPayrollData(res.data);
      setEditedData({});
      setEditMode(false);
      alert("Payroll updated successfully!");
    } catch (error) {
      console.error("Error updating payroll", error);
      const errorMsg =
        error.response?.data?.error || "Failed to update payroll";
      alert(errorMsg);
    }
  };

  const getInitials = (p) => {
    const fn = p.user_details?.first_name || "";
    const ln = p.user_details?.last_name || "";
    if (fn && ln) return `${fn[0]}${ln[0]}`.toUpperCase();
    if (fn) return fn.slice(0, 2).toUpperCase();
    return "N";
  };

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

  const filteredPayroll = payrollData
    .filter((p) => {
      const q = searchQuery.toLowerCase();
      const name =
        `${p.user_details?.first_name || ""} ${p.user_details?.last_name || ""}`.toLowerCase();
      if (!name.includes(q)) return false;
      if (shiftFilter !== "all") {
        const shiftName = (
          p.user_details?.shift_details?.name || ""
        ).toLowerCase();
        if (shiftFilter === "godown") {
          if (!(shiftName.includes("godown") || shiftName.includes("godwon")))
            return false;
        } else if (shiftFilter === "shop") {
          if (!shiftName.includes("shop")) return false;
        }
      }
      return true;
    })
    .sort((a, b) => {
      const nameA =
        `${a.user_details?.first_name || ""} ${a.user_details?.last_name || ""}`.toLowerCase();
      const nameB =
        `${b.user_details?.first_name || ""} ${b.user_details?.last_name || ""}`.toLowerCase();
      return nameA.localeCompare(nameB);
    });

  return (
    <div className="space-y-6 max-w-[1700px] mx-auto animate-fade-in">
      {/* Filter Bar */}
      <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100 flex flex-col md:flex-row justify-between items-start md:items-end gap-6">
        <div>
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            Select Month
          </label>
          <div className="relative">
            <CalendarIcon
              className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
              size={16}
            />
            <input
              type="month"
              value={payrollMonth.slice(0, 7)}
              onChange={(e) => setPayrollMonth(e.target.value + "-01")}
              className="pl-10 pr-4 py-2.5 bg-gray-50 border border-gray-200 rounded-lg text-sm font-medium text-gray-800 outline-none focus:ring-2 focus:ring-orange-100 w-full sm:w-56 transition-all"
            />
          </div>
        </div>
        <div className="flex gap-3">
          {editMode ? (
            <>
              <button
                onClick={saveAllChanges}
                className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors shadow-sm"
              >
                <CheckCircle size={16} /> Save Changes
              </button>
              <button
                onClick={() => {
                  setEditMode(false);
                  setEditedData({});
                }}
                className="flex items-center gap-2 bg-gray-500 hover:bg-gray-600 text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors shadow-sm"
              >
                <X size={16} /> Cancel
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => setEditMode(true)}
                className="flex items-center gap-2 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 px-5 py-2.5 rounded-lg text-sm font-medium transition-colors shadow-sm"
              >
                <Settings size={16} /> Edit
              </button>
              <button
                onClick={handleGeneratePayroll}
                className="flex items-center gap-2 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 px-5 py-2.5 rounded-lg text-sm font-medium transition-colors shadow-sm"
              >
                <Banknote size={16} /> Generate Payroll
              </button>
              <button
                onClick={downloadPayrollPDF}
                className="flex items-center gap-2 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 px-5 py-2.5 rounded-lg text-sm font-medium transition-colors shadow-sm"
              >
                <Download size={16} /> PDF
              </button>
              <button
                onClick={async () => {
                  try {
                    const token = localStorage.getItem("access_token");
                    const url = `${API_BASE_URL}payroll/export_excel/?month=${payrollMonth}`;

                    const response = await fetch(url, {
                      headers: {
                        Authorization: `Bearer ${token}`,
                      },
                    });

                    if (!response.ok) {
                      throw new Error("Failed to download Excel file");
                    }

                    const blob = await response.blob();
                    const downloadUrl = window.URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = downloadUrl;
                    a.download = `payroll_${payrollMonth}.xlsx`;
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(downloadUrl);
                    document.body.removeChild(a);
                  } catch (error) {
                    console.error("Error downloading Excel:", error);
                    alert("Failed to download Excel file. Please try again.");
                  }
                }}
                className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors shadow-sm"
              >
                <Download size={16} /> Excel
              </button>
            </>
          )}
        </div>
      </div>

      {/* Data Card */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="p-6 border-b border-gray-100 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h3 className="text-gray-800 font-bold text-lg">
              Payroll Report:{" "}
              {new Date(payrollMonth).toLocaleString("default", {
                month: "long",
                year: "numeric",
              })}
            </h3>
            <p className="text-gray-500 text-sm mt-1">
              {filteredPayroll.length} Records Found
            </p>
          </div>
          <div className="flex flex-col sm:flex-row gap-3 w-full sm:w-auto">
          <select
            value={shiftFilter}
            onChange={(e) => setShiftFilter(e.target.value)}
            className="px-4 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-800 outline-none focus:ring-2 focus:ring-[#E85D4E]/20 focus:border-[#E85D4E] transition-all"
          >
            <option value="all">All Shifts</option>
            <option value="godown">Godown</option>
            <option value="shop">Shop</option>
          </select>
          <div className="relative">
            <Search
              className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
              size={16}
            />
            <input
              type="text"
              placeholder="Search employee..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 pr-10 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-800 placeholder-gray-400 outline-none focus:ring-2 focus:ring-[#E85D4E]/20 focus:border-[#E85D4E] w-full sm:w-56 transition-all"
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

        <div className="overflow-x-auto overflow-y-auto max-h-[66vh]">
          <table className="w-full text-left text-sm min-w-[1000px]">
            <thead className="sticky top-0 z-10">
              <tr className="text-gray-500 text-xs font-bold uppercase tracking-wider border-b border-gray-100 bg-gray-50">
                <th className="p-4 text-center w-16">Sr.</th>
                <th className="p-4">Name</th>
                <th className="p-4">Email</th>
                <th className="p-4 text-center">Present</th>
                <th className="p-4 text-right">Base Salary</th>
                <th
                  className="p-4 text-right text-rose-500"
                  title="Late Checkin + Early Checkout Fines"
                >
                  Total Fines
                </th>
                <th className="p-4 text-right text-rose-500">ESI</th>
                <th className="p-4 text-right text-rose-500">EPF</th>
                <th className="p-4 text-right text-emerald-600">Overtime</th>
                <th className="p-4 text-right text-emerald-600">Net Salary</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {filteredPayroll.length > 0 ? (
                filteredPayroll.map((p, index) => (
                  <tr key={p.id} className="hover:bg-gray-50 transition-colors">
                    <td className="p-4 text-center text-gray-400 font-mono">
                      {index + 1}
                    </td>
                    <td className="p-4">
                      <div className="flex items-center gap-3">
                        <div
                          className={`w-9 h-9 rounded-full flex items-center justify-center text-white font-bold text-xs ${avatarColors[index % avatarColors.length]}`}
                        >
                          {getInitials(p)}
                        </div>
                        <button
                          onClick={() =>
                            onEmployeeClick &&
                            p.user_details &&
                            onEmployeeClick(p.user_details)
                          }
                          className="font-medium text-gray-800 hover:text-[#E85D4E] hover:underline transition-colors text-left cursor-pointer"
                        >
                          {p.user_details
                            ? `${p.user_details.first_name || ""} ${p.user_details.last_name || ""}`.trim() ||
                              "N/A"
                            : "N/A"}
                        </button>
                      </div>
                    </td>
                    <td className="p-4 text-gray-500 text-xs">
                      {p.user_details?.email || "-"}
                    </td>
                    <td className="p-4 text-center">
                      <span
                        className={`inline-flex items-center justify-center w-auto px-2 min-w-[1.75rem] h-7 rounded-full text-xs font-bold ${
                          p.total_present_days > 0
                            ? "bg-emerald-100 text-emerald-600"
                            : "bg-gray-100 text-gray-400"
                        }`}
                      >
                        {p.total_present_days}
                      </span>
                    </td>
                    <td className="p-4 text-right font-mono text-gray-700">
                      {editMode ? (
                        <input
                          type="text"
                          inputMode="decimal"
                          value={editedData[p.id]?.base_salary ?? p.base_salary}
                          onChange={(e) =>
                            handleFieldChange(
                              p.id,
                              "base_salary",
                              e.target.value,
                            )
                          }
                          className="w-24 bg-gray-50 border border-[#E85D4E] rounded px-2 py-1 text-right text-gray-800 outline-none text-sm"
                        />
                      ) : (
                        <span>₹{Number(p.base_salary || 0).toFixed(2)}</span>
                      )}
                    </td>
                    <td className="p-4 text-right font-mono text-rose-500">
                      <span>-{Number(p.fine_deductions || 0).toFixed(2)}</span>
                    </td>
                    <td className="p-4 text-right font-mono text-rose-500">
                      {editMode ? (
                        <input
                          type="text"
                          inputMode="decimal"
                          value={
                            editedData[p.id]?.esi_deductions ?? p.esi_deductions
                          }
                          onChange={(e) =>
                            handleFieldChange(
                              p.id,
                              "esi_deductions",
                              e.target.value,
                            )
                          }
                          className="w-20 bg-gray-50 border border-rose-400 rounded px-2 py-1 text-right text-gray-800 outline-none text-sm"
                        />
                      ) : (
                        <span>-{Number(p.esi_deductions || 0).toFixed(2)}</span>
                      )}
                    </td>
                    <td className="p-4 text-right font-mono text-rose-500">
                      {editMode ? (
                        <input
                          type="text"
                          inputMode="decimal"
                          value={
                            editedData[p.id]?.epf_deductions ?? p.epf_deductions
                          }
                          onChange={(e) =>
                            handleFieldChange(
                              p.id,
                              "epf_deductions",
                              e.target.value,
                            )
                          }
                          className="w-20 bg-gray-50 border border-rose-400 rounded px-2 py-1 text-right text-gray-800 outline-none text-sm"
                        />
                      ) : (
                        <span>-{Number(p.epf_deductions || 0).toFixed(2)}</span>
                      )}
                    </td>
                    <td className="p-4 text-right font-mono text-emerald-600">
                      <span>+{Number(p.overtime_pay || 0).toFixed(2)}</span>
                    </td>
                    <td className="p-4 text-right font-bold font-mono text-emerald-600 text-base">
                      ₹{Number(p.calculated_salary || 0).toFixed(2)}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td
                    colSpan="10"
                    className="p-12 text-center text-gray-400 italic"
                  >
                    No payroll records. Click "Generate Payroll" to create.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="p-4 border-t border-gray-100 flex justify-between items-center text-gray-500 text-sm">
          <span>
            Showing {filteredPayroll.length > 0 ? 1 : 0} to{" "}
            {filteredPayroll.length} of {payrollData.length} entries
          </span>
        </div>
      </div>

      <div className="text-center text-xs text-slate-400 py-4">
        © {new Date().getFullYear()} Siora One. All rights reserved.
      </div>
    </div>
  );
};

export default PayrollSection;
