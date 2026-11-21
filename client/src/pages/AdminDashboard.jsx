import React, { useEffect, useState, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import {
    LayoutDashboard,
    Clock,
    Banknote,
    Users,
    Settings,
    LogOut,
    Menu,
    X,
    Calendar as CalendarIcon
} from 'lucide-react';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';

// Import extracted components
import {
    SidebarItem,
    OverviewSection,
    AttendanceSection,
    PayrollSection,
    HolidaysSection,
    EmployeesSection,
    ShiftsSection,
    EmployeeDetailPage
} from '../components/admin';

// --- MAIN WRAPPER ---

const AdminDashboard = () => {
    const { user, logout } = useAuth();
    const location = useLocation();
    const navigate = useNavigate();
    const [sidebarOpen, setSidebarOpen] = useState(window.innerWidth > 1024);

    // Derive activeTab from URL path
    const activeTab = useMemo(() => {
        const path = location.pathname.replace('/dashboard', '').replace(/^\//, '');
        if (!path || path === '') return 'overview';
        if (path === 'employee-detail') return 'employee-detail';
        return path;
    }, [location.pathname]);

    // Helper to navigate tabs (replaces setActiveTab)
    const setActiveTab = (tab) => {
        navigate(`/dashboard/${tab === 'overview' ? '' : tab}`);
    };

    // Data States
    const [stats, setStats] = useState({
        total_employees: 0,
        present_today: 0,
        pending_payroll: 0,
        recent_attendance: [],
        recent_registrations: [],
        location: '',
        location_display: ''
    });
    const [attendanceLogs, setAttendanceLogs] = useState([]);
    const [filteredLogs, setFilteredLogs] = useState([]);
    const [payrollData, setPayrollData] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedEmployee, setSelectedEmployee] = useState(null);

    // Clean up employee detail state when navigating away (including browser back)
    useEffect(() => {
        if (activeTab !== 'employee-detail' && selectedEmployee) {
            setSelectedEmployee(null);
            if (window.innerWidth > 1024) {
                setSidebarOpen(true);
            }
        }
    }, [activeTab]);

    const handleEmployeeClick = (employee) => {
        setSelectedEmployee(employee);
        navigate('/dashboard/employee-detail');
        setSidebarOpen(false);
    };

    const handleBackFromDetail = () => {
        setSelectedEmployee(null);
        navigate(-1); // Go back to the previous page
        // Restore sidebar on larger screens
        if (window.innerWidth > 1024) {
            setSidebarOpen(true);
        }
    };

    // Filters
    const [dateFilter, setDateFilter] = useState(() => {
        const d = new Date();
        const offset = d.getTimezoneOffset() * 60000;
        return new Date(d.getTime() - offset).toISOString().slice(0, 10);
    });
    const [searchQuery, setSearchQuery] = useState('');
    const [payrollMonth, setPayrollMonth] = useState(new Date().toISOString().slice(0, 7) + "-01");
    const [holidayMonth, setHolidayMonth] = useState(new Date().toISOString().slice(0, 7) + "-01");

    // Fetch dashboard stats on mount and whenever tab changes (so edits in Employees sync to Overview)
    useEffect(() => {
        const fetchStats = async () => {
            try {
                const statsRes = await api.get('dashboard/');
                setStats(statsRes.data);
            } catch (e) { console.error("Stats fetch failed", e); }
            setLoading(false);
        };
        fetchStats();
    }, [activeTab]);

    // Window resize listener
    useEffect(() => {
        const handleResize = () => setSidebarOpen(window.innerWidth > 1024);
        window.addEventListener('resize', handleResize);
        return () => window.removeEventListener('resize', handleResize);
    }, []);

    // Tab Fetch
    useEffect(() => {
        if (activeTab === 'attendance') {
            Promise.all([
                api.get(`attendance/?date=${dateFilter}`),
                api.get('users/?role=EMPLOYEE')
            ]).then(([attRes, empRes]) => {
                const attData = Array.isArray(attRes.data) ? attRes.data : attRes.data.results || [];
                const empData = Array.isArray(empRes.data) ? empRes.data : empRes.data.results || [];

                // Find employees with no attendance record and create synthetic ABSENT entries
                const attendedUserIds = new Set(attData.map(a => a.user?.id || a.user));
                const absentLogs = empData
                    .filter(emp => !attendedUserIds.has(emp.id))
                    .map(emp => ({
                        id: `absent-${emp.id}`,
                        user: emp,
                        time_in: null,
                        time_out: null,
                        status: 'ABSENT',
                        late_minutes: 0,
                        fine_amount: 0,
                        early_checkout_minutes: 0,
                        early_checkout_fine: 0,
                        _synthetic: true,
                    }));

                const merged = [...attData, ...absentLogs];
                setAttendanceLogs(merged);
                setFilteredLogs(merged);
            });
        }
    }, [activeTab, dateFilter]);

    // Search Filter
    useEffect(() => {
        if (attendanceLogs.length > 0) {
            const q = searchQuery.toLowerCase();
            setFilteredLogs(attendanceLogs.filter(log =>
                (log.user?.first_name || '').toLowerCase().includes(q) ||
                (log.user?.last_name || '').toLowerCase().includes(q) ||
                (log.user?.email || '').toLowerCase().includes(q)
            ));
        }
    }, [searchQuery, attendanceLogs]);

    // Fetch existing payroll data when switching to payroll tab or changing month
    useEffect(() => {
        if (activeTab === 'payroll') {
            api.get(`payroll/fetch/?month=${payrollMonth}`)
                .then(res => {
                    setPayrollData(res.data);
                })
                .catch(err => {
                    console.log("No existing payroll data for this month, or fetch error:", err);
                    setPayrollData([]);
                });
        }
    }, [activeTab, payrollMonth]);

    const handleGeneratePayroll = async () => {
        try {
            const res = await api.post('payroll/generate/', { month: payrollMonth });
            setPayrollData(res.data);
            alert("Payroll generated successfully!");
        } catch (error) {
            console.error("Error generating payroll:", error);
            alert("Error generating payroll");
        }
    };

    // PDF Handlers
    const downloadPDF = () => {
        try {
            const doc = new jsPDF();
            doc.setFontSize(18);
            doc.text("Siora One - Attendance Record", 14, 15);
            doc.setFontSize(12);
            doc.text(`Date: ${dateFilter}`, 14, 25);

            const tableColumn = ["Employee", "Time In", "Time Out", "Late (min)", "Fine", "Status"];
            const tableRows = [];

            filteredLogs.forEach(log => {
                const employeeName = log.user ? `${log.user.first_name || ''} ${log.user.last_name || ''}` : `User ${log.user}`;
                const timeIn = log.time_in ? log.time_in.slice(0, 5) : '-';
                const timeOut = log.time_out ? log.time_out.slice(0, 5) : '-';
                const late = log.late_minutes || 0;
                const fine = log.fine_amount || 0;
                const status = log.status || 'ABSENT';

                tableRows.push([employeeName, timeIn, timeOut, late, fine, status]);
            });

            autoTable(doc, {
                head: [tableColumn],
                body: tableRows,
                startY: 30,
                styles: { fontSize: 10, cellPadding: 3 },
                headStyles: { fillColor: [194, 65, 12] }
            });

            doc.save(`attendance_report_${dateFilter}.pdf`);
        } catch (err) {
            console.error("PDF Export Error:", err);
            alert("Failed to export PDF. Check console.");
        }
    };

    const downloadPayrollPDF = () => {
        try {
            console.log("Starting PDF generation for payroll...", payrollData);
            const doc = new jsPDF();
            doc.setFontSize(18);
            doc.text("Siora One - Payroll Report", 14, 15);
            doc.setFontSize(12);
            doc.text(`Month: ${new Date(payrollMonth).toLocaleString('default', { month: 'long', year: 'numeric' })}`, 14, 25);

            const tableColumn = ["Sr.", "Name", "Email", "Days Present", "Base Salary", "Fines", "ESI", "EPF", "Net Salary"];
            const tableRows = [];

            if (!payrollData || payrollData.length === 0) {
                alert("No payroll data to export");
                return;
            }

            payrollData.forEach((p, index) => {
                let name = 'N/A';
                let email = '-';

                if (p.user_details) {
                    name = `${p.user_details.first_name || ''} ${p.user_details.last_name || ''}`.trim();
                    if (!name) name = p.user_details.username || 'User';
                    email = p.user_details.email || '-';
                } else {
                    name = `User #${p.user}`;
                }

                const salary = p.base_salary ? String(p.base_salary) : '0.00';

                tableRows.push([
                    index + 1,
                    name,
                    email,
                    String(p.total_present_days || 0),
                    salary,
                    `-${p.fine_deductions || 0}`,
                    `-${p.esi_deductions || 0}`,
                    `-${p.epf_deductions || 0}`,
                    `${p.calculated_salary || 0}`
                ]);
            });

            autoTable(doc, {
                head: [tableColumn],
                body: tableRows,
                startY: 30,
                styles: { fontSize: 9, cellPadding: 2 },
                headStyles: { fillColor: [194, 65, 12] }
            });

            doc.save(`payroll_report_${payrollMonth}.pdf`);
        } catch (err) {
            console.error("Payroll PDF Error", err);
            alert("Failed to export Payroll PDF: " + err.message);
        }
    };

    if (loading) return <div className="h-screen flex items-center justify-center bg-[#FBF8F6] text-slate-600">Loading Siora One...</div>;

    return (
        <div className="flex h-screen bg-[#FBF8F6] font-sans selection:bg-orange-100 selection:text-orange-900">
            {/* SIDEBAR - Light Theme */}
            <aside
                className={`flex-shrink-0 bg-white border-r border-gray-100 transition-all duration-300 flex flex-col relative z-20 ${sidebarOpen && !selectedEmployee ? 'w-64' : 'w-0 overflow-hidden'}`}
            >
                <div className="h-20 flex items-center gap-3 px-4 border-b border-gray-100">
                    <img
                        src="/sioraone.svg"
                        alt="Siora One"
                        className="h-8"
                    />
                </div>

                {/* Location Display - Prominent */}
                {stats.location_display && (
                    <div className="px-6 py-4 bg-[#E85D4E]/5 border-b border-[#E85D4E]/10">
                        <div className="flex items-center gap-2">
                            <div className="w-2 h-2 bg-[#E85D4E] rounded-full"></div>
                            <p className="text-xs text-[#E85D4E] font-semibold uppercase tracking-wider">Current Location</p>
                        </div>
                        <p className="text-base font-bold text-gray-800 mt-1">{stats.location_display}</p>
                    </div>
                )}

                <div className="px-4 pt-6 pb-2">
                    <p className="text-xs text-gray-400 font-medium uppercase tracking-wider">Main Menu</p>
                </div>

                <div className="flex-1 py-2 space-y-1 overflow-y-auto">
                    <SidebarItem id="overview" label="Overview" icon={LayoutDashboard} activeTab={activeTab} sidebarOpen={sidebarOpen} />
                    <SidebarItem id="attendance" label="Attendance Record" icon={Clock} activeTab={activeTab} sidebarOpen={sidebarOpen} />
                    <SidebarItem id="payroll" label="Payroll" icon={Banknote} activeTab={activeTab} sidebarOpen={sidebarOpen} />
                    <SidebarItem id="holidays" label="Holidays" icon={CalendarIcon} activeTab={activeTab} sidebarOpen={sidebarOpen} />
                    <SidebarItem id="shifts" label="Shifts" icon={Settings} activeTab={activeTab} sidebarOpen={sidebarOpen} />
                    <SidebarItem id="employees" label="Employees" icon={Users} activeTab={activeTab} sidebarOpen={sidebarOpen} />
                </div>

                <div className="p-6 border-t border-gray-100">
                    <button onClick={logout} className="flex items-center gap-3 text-gray-500 hover:text-[#E85D4E] transition-colors">
                        <LogOut size={18} />
                        <span className="font-medium text-sm">Log out</span>
                    </button>
                </div>
            </aside>

            {/* MAIN CONTENT */}
            <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
                {/* HEADER */}
                <header className="h-20 bg-white border-b border-gray-100 flex items-center justify-between px-8 z-10">
                    <div className="flex items-center gap-4">
                        <button onClick={() => setSidebarOpen(!sidebarOpen)} className="p-2 text-gray-400 hover:bg-gray-50 rounded-lg lg:hidden">
                            {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
                        </button>
                        <div>
                            <div className="flex items-center gap-3">
                                <h2 className="text-xl font-bold text-gray-800">
                                    {selectedEmployee
                                        ? `${selectedEmployee.first_name || ''} ${selectedEmployee.last_name || ''}`.trim() || 'Employee Details'
                                        : activeTab === 'overview' ? 'Overview' :
                                            activeTab === 'attendance' ? 'Attendance Record' :
                                                activeTab === 'payroll' ? 'Payroll' :
                                                    activeTab === 'holidays' ? 'Holiday Calendar' :
                                                        activeTab === 'employees' ? 'Employees' : 'Dashboard'}
                                </h2>
                                {stats.location_display && (
                                    <span className="bg-[#E85D4E]/10 text-[#E85D4E] text-xs font-semibold px-3 py-1 rounded-full border border-[#E85D4E]/20">
                                        {stats.location_display}
                                    </span>
                                )}
                            </div>
                            <p className="text-sm text-gray-400 mt-0.5">
                                {selectedEmployee
                                    ? 'Employee attendance and details'
                                    : activeTab === 'attendance' ? 'Manage daily attendance and logs' :
                                        activeTab === 'holidays' ? 'Mark holidays to affect payroll calculations' :
                                            activeTab === 'employees' ? 'View and manage employee records' :
                                                'Welcome back to Siora One'}
                            </p>
                        </div>
                    </div>
                    <div className="flex items-center gap-4">
                        <div className="hidden sm:flex flex-col items-end">
                            <span className="text-sm font-semibold text-gray-800">{user?.username || 'Admin User'}</span>
                            <span className="text-xs text-gray-400">Administrator</span>
                        </div>
                        <div className="w-10 h-10 bg-[#E85D4E] rounded-full flex items-center justify-center text-white font-bold text-sm shadow-sm">
                            {user?.username?.slice(0, 2)?.toUpperCase() || 'AD'}
                        </div>
                    </div>
                </header>

                {/* SCROLLABLE AREA */}
                <main className="flex-1 overflow-y-auto p-8 scroll-smooth">
                    {activeTab === 'employee-detail' && selectedEmployee ? (
                        <EmployeeDetailPage
                            employee={selectedEmployee}
                            onBack={handleBackFromDetail}
                        />
                    ) : activeTab === 'employee-detail' && !selectedEmployee ? (
                        // If user navigated to /dashboard/employee-detail directly without selecting employee
                        (() => { navigate('/dashboard'); return null; })()
                    ) : (
                        <>
                            {activeTab === 'overview' && (
                                <OverviewSection
                                    stats={stats}
                                    setActiveTab={setActiveTab}
                                    onEmployeeClick={handleEmployeeClick}
                                />
                            )}
                            {activeTab === 'attendance' && (
                                <AttendanceSection
                                    dateFilter={dateFilter}
                                    setDateFilter={setDateFilter}
                                    searchQuery={searchQuery}
                                    setSearchQuery={setSearchQuery}
                                    downloadPDF={downloadPDF}
                                    filteredLogs={filteredLogs}
                                    onEmployeeClick={handleEmployeeClick}
                                />
                            )}
                            {activeTab === 'payroll' && (
                                <PayrollSection
                                    payrollMonth={payrollMonth}
                                    setPayrollMonth={setPayrollMonth}
                                    handleGeneratePayroll={handleGeneratePayroll}
                                    payrollData={payrollData}
                                    setPayrollData={setPayrollData}
                                    downloadPayrollPDF={downloadPayrollPDF}
                                    onEmployeeClick={handleEmployeeClick}
                                />
                            )}
                            {activeTab === 'holidays' && (
                                <HolidaysSection
                                    holidayMonth={holidayMonth}
                                    setHolidayMonth={setHolidayMonth}
                                />
                            )}
                            {activeTab === 'employees' && (
                                <EmployeesSection onEmployeeClick={handleEmployeeClick} />
                            )}
                            {activeTab === 'shifts' && (
                                <ShiftsSection />
                            )}
                        </>
                    )}
                </main>

                {/* FOOTER */}
                <footer className="h-12 bg-white border-t border-gray-100 flex items-center justify-center">
                    <p className="text-xs text-gray-400">© {new Date().getFullYear()} Siora One. All rights reserved.</p>
                </footer>
            </div>
        </div>
    );
};

export default AdminDashboard;
