import React, { useEffect, useState, useMemo } from 'react';
import api from '../../services/api';
import { Clock, Users, MoreHorizontal } from 'lucide-react';
import StatCard from './StatCard';

/**
 * Stat configuration map - defines all stat card types
 * Each stat config contains: key (for accessing stats object), label, icon, colorClass, bgClass
 */
const STAT_CONFIG = [
    {
        key: 'total_employees',
        label: 'Total Employees',
        icon: Users,
        colorClass: 'text-blue-600',
        bgClass: 'bg-blue-50',
    },
    {
        key: 'present_today',
        label: 'Present Today',
        icon: Clock,
        colorClass: 'text-emerald-500',
        bgClass: 'bg-emerald-50',
    },
    {
        key: 'pending_payroll',
        label: 'Pending Payrolls',
        icon: MoreHorizontal,
        colorClass: 'text-[#E85D4E]',
        bgClass: 'bg-[#FEF2F2]',
    },
];

const OverviewSection = ({ stats, setActiveTab, onEmployeeClick }) => {
    const [employees, setEmployees] = useState([]);
    const [attendanceLogs, setAttendanceLogs] = useState([]);

    useEffect(() => {
        const fetchData = async () => {
            try {
                // Fetch employees
                const empRes = await api.get('users/?role=EMPLOYEE');
                let empData = Array.isArray(empRes.data) ? empRes.data : empRes.data.results || [];
                // Sort alphabetically
                empData = empData.sort((a, b) => {
                    const nameA = `${a.first_name || ''} ${a.last_name || ''}`.toLowerCase();
                    const nameB = `${b.first_name || ''} ${b.last_name || ''}`.toLowerCase();
                    return nameA.localeCompare(nameB);
                });
                setEmployees(empData);

                // Fetch today's attendance
                const today = new Date();
                const localDate = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
                const attRes = await api.get(`attendance/?date=${localDate}`);
                const attData = Array.isArray(attRes.data) ? attRes.data : attRes.data.results || [];

                // Merge: include absent employees (no attendance record) as synthetic entries
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
                        _synthetic: true,
                    }));
                // Real attendance logs first, then absent ones
                setAttendanceLogs([...attData, ...absentLogs]);
            } catch (e) {
                console.log("Could not fetch data for overview", e);
            }
        };
        fetchData();
    }, []);

    // Memoize stat cards - re-compute only when specific stat values change
    const memoizedStatCards = useMemo(() => {
        return STAT_CONFIG.map((statConfig) => (
            <StatCard
                key={statConfig.key}
                label={statConfig.label}
                value={stats[statConfig.key]}
                icon={statConfig.icon}
                colorClass={statConfig.colorClass}
                bgClass={statConfig.bgClass}
            />
        ));
    }, [stats.total_employees, stats.present_today, stats.pending_payroll]);

    return (
        <div className="space-y-8 max-w-[1700px] mx-auto">
            {/* Stats Row */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {memoizedStatCards}
            </div>

            {/* Main Grid - Today's Attendance & Employees Side by Side */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {/* Today's Attendance Widget */}
                <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
                    <div className="flex justify-between items-center mb-6">
                        <h3 className="font-bold text-gray-800 flex items-center gap-2">
                            <Clock size={18} className="text-[#E85D4E]" /> Today's Attendance
                        </h3>
                        <button onClick={() => setActiveTab('attendance')} className="text-xs font-semibold text-[#E85D4E] hover:text-[#D54D3E]">View All</button>
                    </div>
                    <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
                        <table className="w-full text-left text-sm">
                            <thead className="sticky top-0 bg-white">
                                <tr className="text-gray-400 text-xs font-bold uppercase tracking-wider border-b border-gray-50">
                                    <th className="pb-3">Employee</th>
                                    <th className="pb-3 text-center">Check In</th>
                                    <th className="pb-3 text-center">Check Out</th>
                                    <th className="pb-3 text-right">Status</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-50">
                                {attendanceLogs.slice(0, 10).map(log => (
                                    <tr key={log.id} className="group hover:bg-[#FEF2F2]/30 transition-colors">
                                        <td className="py-4 font-medium text-gray-700">
                                            <button
                                                onClick={() => onEmployeeClick && onEmployeeClick(log.user)}
                                                className="hover:text-[#E85D4E] hover:underline transition-colors text-left cursor-pointer"
                                            >
                                                {log.user ? `${log.user.first_name || ''} ${log.user.last_name || ''}`.trim() || 'Unknown' : `User #${log.user}`}
                                            </button>
                                        </td>
                                        <td className="py-4 text-center font-mono text-emerald-600 font-medium">
                                            {log.time_in ? log.time_in.slice(0, 5) : '--:--'}
                                        </td>
                                        <td className="py-4 text-center font-mono text-gray-400">
                                            {log.time_out ? log.time_out.slice(0, 5) : '--:--'}
                                        </td>
                                        <td className="py-4 text-right">
                                            <span className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-semibold ${log.status === 'PRESENT' ? 'bg-emerald-50 text-emerald-600' :
                                                log.status === 'HALF_DAY' ? 'bg-amber-50 text-amber-600' :
                                                    log.status === 'LATE' ? 'bg-red-50 text-red-600' :
                                                        log.status === 'ABSENT' ? 'bg-rose-50 text-rose-500' :
                                                            log.status === 'LEAVE' ? 'bg-blue-50 text-blue-600' :
                                                                log.status === 'HOLIDAY' ? 'bg-purple-50 text-purple-600' :
                                                                    'bg-gray-100 text-gray-500'
                                                }`}>
                                                <span className={`w-1.5 h-1.5 rounded-full ${log.status === 'PRESENT' ? 'bg-emerald-500' :
                                                    log.status === 'HALF_DAY' ? 'bg-amber-500' :
                                                        log.status === 'LATE' ? 'bg-red-500' :
                                                            log.status === 'ABSENT' ? 'bg-rose-500' :
                                                                log.status === 'LEAVE' ? 'bg-blue-500' :
                                                                    log.status === 'HOLIDAY' ? 'bg-purple-500' :
                                                                        'bg-gray-400'
                                                    }`}></span>
                                                {log.status === 'PRESENT' ? 'Present' :
                                                    log.status === 'HALF_DAY' ? 'Half Day' :
                                                        log.status === 'LATE' ? 'Late' :
                                                            log.status === 'ABSENT' ? 'Absent' :
                                                                log.status === 'LEAVE' ? 'Leave' :
                                                                    log.status === 'HOLIDAY' ? 'Holiday' : log.status}
                                            </span>
                                        </td>
                                    </tr>
                                ))}
                                {attendanceLogs.length === 0 && (
                                    <tr><td colSpan="4" className="py-6 text-center text-gray-400 italic">No attendance marked today.</td></tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>

                {/* Employees Widget */}
                <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
                    <div className="flex justify-between items-center mb-6">
                        <h3 className="font-bold text-gray-800 flex items-center gap-2">
                            <Users size={18} className="text-blue-600" /> Employees
                        </h3>
                        <button
                            onClick={() => setActiveTab('payroll')}
                            className="bg-[#E85D4E] hover:bg-[#D54D3E] text-white text-xs px-4 py-2 rounded-lg font-medium transition-colors shadow-sm"
                        >
                            Run Payroll
                        </button>
                    </div>
                    <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
                        <table className="w-full text-left text-sm">
                            <thead className="sticky top-0 bg-white">
                                <tr className="text-gray-400 text-xs font-bold uppercase tracking-wider border-b border-gray-50">
                                    <th className="pb-3">Name</th>
                                    <th className="pb-3">Contact</th>
                                    <th className="pb-3 text-right">Salary</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-50">
                                {employees.map((emp, idx) => (
                                    <tr key={emp.id || idx} className="group hover:bg-gray-50 transition-colors">
                                        <td className="py-4 font-medium text-gray-700">
                                            <button
                                                onClick={() => onEmployeeClick && onEmployeeClick(emp)}
                                                className="hover:text-[#E85D4E] hover:underline transition-colors text-left cursor-pointer"
                                            >
                                                {emp.first_name ? `${emp.first_name} ${emp.last_name || ''}`.trim() : emp.username || 'Unknown'}
                                            </button>
                                        </td>
                                        <td className="py-4 text-gray-500 text-sm">
                                            {emp.contact || '-'}
                                        </td>
                                        <td className="py-4 text-right font-mono text-gray-600">
                                            ₹{Number(emp.salary_per_month || 0).toLocaleString()}
                                        </td>
                                    </tr>
                                ))}
                                {employees.length === 0 && (
                                    <tr><td colSpan="3" className="py-6 text-center text-gray-400 italic">No employees found.</td></tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default OverviewSection;
