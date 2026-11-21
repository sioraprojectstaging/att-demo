import React, { useEffect, useState } from 'react';
import api from '../../services/api';
import { Plus } from 'lucide-react';

const ShiftsSection = () => {
    const [shifts, setShifts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [editingShift, setEditingShift] = useState(null);
    const [formData, setFormData] = useState({ name: '', start_time: '10:00', end_time: '18:30', buffer_minutes: 10 });

    useEffect(() => {
        fetchShifts();
    }, []);

    const fetchShifts = async () => {
        try {
            const res = await api.get('shifts/');
            setShifts(Array.isArray(res.data) ? res.data : res.data.results || []);
        } catch (e) {
            console.error('Failed to fetch shifts', e);
        }
        setLoading(false);
    };

    const openAddModal = () => {
        setEditingShift(null);
        setFormData({ name: '', start_time: '10:00', end_time: '18:30', buffer_minutes: 10 });
        setShowModal(true);
    };

    const openEditModal = (shift) => {
        setEditingShift(shift);
        setFormData({
            name: shift.name,
            start_time: shift.start_time.slice(0, 5),
            end_time: shift.end_time.slice(0, 5),
            buffer_minutes: shift.buffer_minutes
        });
        setShowModal(true);
    };

    const handleSave = async () => {
        const payload = {
            name: formData.name || `${formData.start_time} - ${formData.end_time}`,
            start_time: formData.start_time,
            end_time: formData.end_time,
            buffer_minutes: parseInt(formData.buffer_minutes) || 10
        };
        try {
            if (editingShift) {
                await api.patch(`shifts/${editingShift.id}/`, payload);
            } else {
                await api.post('shifts/', payload);
            }
            await fetchShifts();
            setShowModal(false);
            alert(`Shift ${editingShift ? 'updated' : 'added'} successfully!`);
        } catch (e) {
            console.error('Failed to save shift', e);
            alert('Failed to save shift: ' + (e.response?.data?.error || e.message));
        }
    };

    const handleDelete = async (shiftId) => {
        if (!confirm('Delete this shift? Employees using it will have no shift assigned.')) return;
        try {
            await api.delete(`shifts/${shiftId}/`);
            await fetchShifts();
        } catch (e) {
            console.error('Failed to delete shift', e);
            alert('Failed to delete shift');
        }
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

    if (loading) return <div className="text-center py-12 text-gray-400">Loading shifts...</div>;

    return (
        <>
            <div className="space-y-6 max-w-4xl mx-auto animate-fade-in">
                {/* Header */}
                <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100 flex justify-between items-center">
                    <div>
                        <h3 className="text-lg font-bold text-gray-800">Shift Management</h3>
                        <p className="text-gray-500 text-sm">Create and manage work shift timings</p>
                    </div>
                    <button onClick={openAddModal} className="flex items-center gap-2 bg-[#E85D4E] hover:bg-[#D54D3E] text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
                        <Plus size={16} /> Add Shift
                    </button>
                </div>

                {/* Shifts List */}
                <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
                    <table className="w-full text-left text-sm">
                        <thead>
                            <tr className="text-gray-500 text-xs font-bold uppercase tracking-wider border-b border-gray-100 bg-gray-50">
                                <th className="p-4">Shift Name</th>
                                <th className="p-4 text-center">Start Time</th>
                                <th className="p-4 text-center">End Time</th>
                                <th className="p-4 text-center">Buffer (min)</th>
                                <th className="p-4 text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-50">
                            {shifts.map(shift => (
                                <tr key={shift.id} className="hover:bg-gray-50 transition-colors">
                                    <td className="p-4 font-medium text-gray-800">{shift.name}</td>
                                    <td className="p-4 text-center text-emerald-600 font-mono">{formatTime(shift.start_time)}</td>
                                    <td className="p-4 text-center text-gray-600 font-mono">{formatTime(shift.end_time)}</td>
                                    <td className="p-4 text-center text-gray-500">{shift.buffer_minutes}</td>
                                    <td className="p-4 text-right">
                                        <button onClick={() => openEditModal(shift)} className="text-blue-600 hover:text-blue-800 mr-4 text-sm font-medium">Edit</button>
                                        <button onClick={() => handleDelete(shift.id)} className="text-rose-500 hover:text-rose-700 text-sm font-medium">Delete</button>
                                    </td>
                                </tr>
                            ))}
                            {shifts.length === 0 && (
                                <tr>
                                    <td colSpan="5" className="p-12 text-center text-gray-400 italic">No shifts created. Click "Add Shift" to create one.</td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>

            </div>
            {/* Modal */}
            {showModal && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl">
                        <h4 className="text-lg font-bold text-gray-800 mb-4">{editingShift ? 'Edit Shift' : 'Add New Shift'}</h4>
                        <div className="space-y-4">
                            <div>
                                <label className="block text-xs font-semibold text-gray-500 uppercase mb-2">Shift Name (optional)</label>
                                <input
                                    type="text"
                                    placeholder="e.g., Morning Shift"
                                    value={formData.name}
                                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                    className="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-800 outline-none focus:ring-2 focus:ring-[#E85D4E]/20 focus:border-[#E85D4E]"
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-xs font-semibold text-gray-500 uppercase mb-2">Start Time</label>
                                    <input
                                        type="time"
                                        value={formData.start_time}
                                        onChange={(e) => setFormData({ ...formData, start_time: e.target.value })}
                                        className="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-800 outline-none focus:ring-2 focus:ring-[#E85D4E]/20 focus:border-[#E85D4E]"
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs font-semibold text-gray-500 uppercase mb-2">End Time</label>
                                    <input
                                        type="time"
                                        value={formData.end_time}
                                        onChange={(e) => setFormData({ ...formData, end_time: e.target.value })}
                                        className="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-800 outline-none focus:ring-2 focus:ring-[#E85D4E]/20 focus:border-[#E85D4E]"
                                    />
                                </div>
                            </div>
                            <div>
                                <label className="block text-xs font-semibold text-gray-500 uppercase mb-2">Buffer Minutes (grace period)</label>
                                <input
                                    type="number"
                                    value={formData.buffer_minutes}
                                    onChange={(e) => setFormData({ ...formData, buffer_minutes: e.target.value })}
                                    className="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-800 outline-none focus:ring-2 focus:ring-[#E85D4E]/20 focus:border-[#E85D4E]"
                                />
                            </div>
                        </div>
                        <div className="flex justify-end gap-3 mt-6">
                            <button onClick={() => setShowModal(false)} className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg text-sm font-medium">Cancel</button>
                            <button onClick={handleSave} className="px-4 py-2 bg-[#E85D4E] hover:bg-[#D54D3E] text-white rounded-lg text-sm font-medium">Save Shift</button>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
};

export default ShiftsSection;
