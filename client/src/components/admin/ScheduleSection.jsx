import React, { useEffect, useState } from 'react';
import api from '../../services/api';
import { Calendar as CalendarIcon } from 'lucide-react';

const ScheduleSection = () => {
    const [selectedDate, setSelectedDate] = useState(() => {
        const d = new Date();
        const offset = d.getTimezoneOffset() * 60000;
        return new Date(d.getTime() - offset).toISOString().slice(0, 10);
    });
    const [employees, setEmployees] = useState([]);
    const [shifts, setShifts] = useState([]);
    const [attendanceMap, setAttendanceMap] = useState({});
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [editingEmployee, setEditingEmployee] = useState(null);
    const [selectedShift, setSelectedShift] = useState('');

    useEffect(() => {
        fetchData();
    }, [selectedDate]);

    const fetchData = async () => {
        setLoading(true);
        try {
            const [empRes, shiftRes, attRes] = await Promise.all([
                api.get('users/?role=EMPLOYEE'),
                api.get('shifts/'),
                api.get(`attendance/?date=${selectedDate}`)
            ]);
            setEmployees(Array.isArray(empRes.data) ? empRes.data : empRes.data.results || []);
            setShifts(Array.isArray(shiftRes.data) ? shiftRes.data : shiftRes.data.results || []);

            const attData = Array.isArray(attRes.data) ? attRes.data : attRes.data.results || [];
            const map = {};
            attData.forEach(att => {
                map[att.user?.id || att.user] = att;
            });
            setAttendanceMap(map);
        } catch (e) {
            console.error('Failed to fetch schedule data', e);
        }
        setLoading(false);
    };

    const openEditModal = (emp) => {
        setEditingEmployee(emp);
        const att = attendanceMap[emp.id];
        setSelectedShift(att?.shift || emp.shift || '');
        setShowModal(true);
    };

    const handleSaveShift = async () => {
        try {
            const att = attendanceMap[editingEmployee.id];
            if (att) {
                await api.patch(`attendance/${att.id}/`, { shift: selectedShift || null });
            } else {
                await api.post('attendance/', {
                    user: editingEmployee.id,
                    date: selectedDate,
                    shift: selectedShift || null,
                    status: 'PRESENT'
                });
            }
            await fetchData();
            setShowModal(false);
        } catch (e) {
            console.error('Failed to update shift', e);
            alert('Failed to update shift: ' + (e.response?.data?.error || e.message));
        }
    };

    const getShiftName = (shiftId) => {
        const shift = shifts.find(s => s.id === parseInt(shiftId));
        return shift ? shift.name : 'No Shift';
    };

    const formatTime = (timeStr) => {
        if (!timeStr) return '--:--';
        try {
            const [hours, minutes] = timeStr.split(':');
            const h = parseInt(hours, 10);
            const ampm = h >= 12 ? 'PM' : 'AM';
            const h12 = h % 12 || 12;
            return `${h12}:${minutes} ${ampm}`;
        } catch { return timeStr; }
    };

    const avatarColors = ['bg-violet-500', 'bg-pink-500', 'bg-amber-500', 'bg-teal-500', 'bg-blue-500', 'bg-rose-500'];

    if (loading) return <div className="text-center py-12 text-gray-400">Loading schedule...</div>;

    return (
        <div className="space-y-6 max-w-5xl mx-auto animate-fade-in">
            {/* Header with Date Picker */}
            <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <div>
                    <h3 className="text-lg font-bold text-gray-800">Daily Shift Schedule</h3>
                    <p className="text-gray-500 text-sm">View and edit employee shifts for any date</p>
                </div>
                <div className="flex items-center gap-3">
                    <div className="relative">
                        <CalendarIcon className="absolute left-3 top-1/2 -translate-y-1/2 text-[#E85D4E]" size={16} />
                        <input
                            type="date"
                            value={selectedDate}
                            onChange={(e) => setSelectedDate(e.target.value)}
                            className="pl-10 pr-4 py-2.5 bg-gray-50 border border-gray-200 rounded-lg text-sm font-medium text-gray-800 outline-none focus:ring-2 focus:ring-[#E85D4E]/20 focus:border-[#E85D4E]"
                        />
                    </div>
                </div>
            </div>

            {/* Schedule Table */}
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
                <div className="p-4 border-b border-gray-100 bg-gray-50">
                    <span className="text-sm font-medium text-gray-600">
                        {new Date(selectedDate).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}
                    </span>
                    <span className="ml-4 text-sm text-gray-400">{employees.length} employees</span>
                </div>
                <table className="w-full text-left text-sm">
                    <thead>
                        <tr className="text-gray-500 text-xs font-bold uppercase tracking-wider border-b border-gray-100">
                            <th className="p-4">Employee</th>
                            <th className="p-4 text-center">Default Shift</th>
                            <th className="p-4 text-center">Today's Shift</th>
                            <th className="p-4 text-center">Check In</th>
                            <th className="p-4 text-center">Check Out</th>
                            <th className="p-4 text-right">Action</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                        {employees.map((emp, idx) => {
                            const att = attendanceMap[emp.id];
                            const todayShift = att?.shift || att?.shift_details?.id;
                            const defaultShift = emp.shift_details || emp.shift;
                            return (
                                <tr key={emp.id} className="hover:bg-gray-50 transition-colors">
                                    <td className="p-4">
                                        <div className="flex items-center gap-3">
                                            <div className={`w-9 h-9 rounded-full flex items-center justify-center text-white font-bold text-xs ${avatarColors[idx % avatarColors.length]}`}>
                                                {(emp.first_name?.[0] || '') + (emp.last_name?.[0] || '') || 'U'}
                                            </div>
                                            <div>
                                                <div className="font-medium text-gray-800">{emp.first_name} {emp.last_name}</div>
                                                <div className="text-xs text-gray-400">{emp.department || '-'}</div>
                                            </div>
                                        </div>
                                    </td>
                                    <td className="p-4 text-center text-gray-500 text-xs">
                                        {defaultShift?.name || getShiftName(defaultShift) || 'None'}
                                    </td>
                                    <td className="p-4 text-center">
                                        <span className={`px-2 py-1 rounded text-xs font-medium ${todayShift ? 'bg-emerald-50 text-emerald-600' : 'bg-gray-100 text-gray-400'}`}>
                                            {todayShift ? (att?.shift_details?.name || getShiftName(todayShift)) : 'Not Set'}
                                        </span>
                                    </td>
                                    <td className="p-4 text-center font-mono text-emerald-600">
                                        {att?.time_in ? formatTime(att.time_in) : '--:--'}
                                    </td>
                                    <td className="p-4 text-center font-mono text-gray-400">
                                        {att?.time_out ? formatTime(att.time_out) : '--:--'}
                                    </td>
                                    <td className="p-4 text-right">
                                        <button onClick={() => openEditModal(emp)} className="text-[#E85D4E] hover:text-[#D54D3E] text-sm font-medium">
                                            Edit Shift
                                        </button>
                                    </td>
                                </tr>
                            );
                        })}
                        {employees.length === 0 && (
                            <tr>
                                <td colSpan="6" className="p-12 text-center text-gray-400 italic">No employees found.</td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>

            {/* Edit Shift Modal */}
            {showModal && editingEmployee && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl">
                        <h4 className="text-lg font-bold text-gray-800 mb-2">Edit Shift</h4>
                        <p className="text-gray-500 text-sm mb-4">
                            {editingEmployee.first_name} {editingEmployee.last_name} - {new Date(selectedDate).toLocaleDateString()}
                        </p>
                        <div>
                            <label className="block text-xs font-semibold text-gray-500 uppercase mb-2">Select Shift</label>
                            <select
                                value={selectedShift}
                                onChange={(e) => setSelectedShift(e.target.value)}
                                className="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-800 outline-none focus:ring-2 focus:ring-[#E85D4E]/20 focus:border-[#E85D4E]"
                            >
                                <option value="">No Shift Assigned</option>
                                {shifts.map(s => (
                                    <option key={s.id} value={s.id}>{s.name}</option>
                                ))}
                            </select>
                        </div>
                        <div className="flex justify-end gap-3 mt-6">
                            <button onClick={() => setShowModal(false)} className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg text-sm font-medium">Cancel</button>
                            <button onClick={handleSaveShift} className="px-4 py-2 bg-[#E85D4E] hover:bg-[#D54D3E] text-white rounded-lg text-sm font-medium">Save</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default ScheduleSection;
