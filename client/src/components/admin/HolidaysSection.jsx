import React, { useEffect, useState } from 'react';
import api from '../../services/api';
import { ChevronLeft, ChevronRight, Calendar as CalendarIcon } from 'lucide-react';

const HolidaysSection = ({ holidayMonth, setHolidayMonth }) => {
    const [holidays, setHolidays] = useState([]);
    const [loading, setLoading] = useState(false);
    const [modalOpen, setModalOpen] = useState(false);
    const [selectedDate, setSelectedDate] = useState(null);
    const [holidayName, setHolidayName] = useState('');
    const [isRemoving, setIsRemoving] = useState(false);

    useEffect(() => {
        const fetchHolidays = async () => {
            try {
                const res = await api.get(`holidays/?month=${holidayMonth}`);
                setHolidays(res.data);
            } catch (e) {
                console.error("Failed to fetch holidays", e);
            }
        };
        fetchHolidays();
    }, [holidayMonth]);

    const handleGenerateWeekends = async () => {
        setLoading(true);
        try {
            const res = await api.post('holidays/generate_weekends/', { month: holidayMonth });
            alert(res.data.message);
            const refreshRes = await api.get(`holidays/?month=${holidayMonth}`);
            setHolidays(refreshRes.data);
        } catch (e) {
            console.error("Failed to generate weekends", e);
            alert("Failed to generate weekends");
        }
        setLoading(false);
    };

    const handleDayClick = (date) => {
        const existing = holidays.find(h => h.date === date);
        setSelectedDate(date);
        if (existing) {
            setHolidayName(existing.name);
            setIsRemoving(true);
        } else {
            setHolidayName('');
            setIsRemoving(false);
        }
        setModalOpen(true);
    };

    const handleAddHoliday = async () => {
        if (!holidayName.trim()) {
            alert('Please enter a holiday name');
            return;
        }
        try {
            await api.post('holidays/add_holiday/', { date: selectedDate, name: holidayName });
            const res = await api.get(`holidays/?month=${holidayMonth}`);
            setHolidays(res.data);
            setModalOpen(false);
        } catch (e) {
            console.error("Error adding holiday", e);
            alert("Failed to add holiday");
        }
    };

    const handleRemoveHoliday = async () => {
        try {
            await api.post('holidays/remove_holiday/', { date: selectedDate });
            const res = await api.get(`holidays/?month=${holidayMonth}`);
            setHolidays(res.data);
            setModalOpen(false);
        } catch (e) {
            console.error("Error removing holiday", e);
            alert("Failed to remove holiday");
        }
    };

    const generateCalendarDays = () => {
        const [year, month] = holidayMonth.split('-').map(Number);
        const firstDay = new Date(year, month - 1, 1);
        const lastDay = new Date(year, month, 0);
        const daysInMonth = lastDay.getDate();
        const startWeekday = firstDay.getDay();

        const days = [];
        for (let i = 0; i < startWeekday; i++) {
            days.push(null);
        }
        for (let d = 1; d <= daysInMonth; d++) {
            const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
            const dayOfWeek = new Date(year, month - 1, d).getDay();
            const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
            const holiday = holidays.find(h => h.date === dateStr);
            days.push({
                day: d,
                date: dateStr,
                isWeekend,
                isHoliday: !!holiday,
                holidayName: holiday?.name || '',
                isWeekendHoliday: holiday?.is_weekend || false
            });
        }
        return days;
    };

    const calendarDays = generateCalendarDays();
    const weekdays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const [year, month] = holidayMonth.split('-').map(Number);
    const monthName = new Date(year, month - 1).toLocaleString('default', { month: 'long' });

    return (
        <>
            <div className="space-y-6 max-w-4xl mx-auto animate-fade-in">
                {/* Month Header */}
                <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
                    <div className="flex items-center justify-between">
                        <button
                            onClick={() => {
                                const prev = new Date(year, month - 2, 1);
                                setHolidayMonth(`${prev.getFullYear()}-${String(prev.getMonth() + 1).padStart(2, '0')}-01`);
                            }}
                            className="p-3 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors text-gray-600"
                        >
                            <ChevronLeft size={20} />
                        </button>
                        <div className="text-center">
                            <h2 className="text-3xl font-bold text-gray-800">{monthName}</h2>
                            <p className="text-gray-500 text-lg">{year}</p>
                        </div>
                        <button
                            onClick={() => {
                                const next = new Date(year, month, 1);
                                setHolidayMonth(`${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}-01`);
                            }}
                            className="p-3 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors text-gray-600"
                        >
                            <ChevronRight size={20} />
                        </button>
                    </div>
                    <div className="mt-4 flex items-center justify-between">
                        <span className="text-gray-600">Total Holidays: <span className="text-[#E85D4E] font-bold text-xl">{holidays.length}</span></span>
                        <button
                            onClick={handleGenerateWeekends}
                            disabled={loading}
                            className="flex items-center gap-2 bg-[#E85D4E] hover:bg-[#D54D3E] text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                        >
                            <CalendarIcon size={16} /> {loading ? 'Generating...' : 'Auto-mark Weekends'}
                        </button>
                    </div>
                </div>

                {/* Calendar Grid */}
                <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
                    <div className="grid grid-cols-7 border-b border-gray-100">
                        {weekdays.map(wd => (
                            <div key={wd} className={`p-3 text-center text-xs font-bold uppercase tracking-wider ${wd === 'Sun' || wd === 'Sat' ? 'text-rose-500 bg-rose-50' : 'text-gray-500'}`}>
                                {wd}
                            </div>
                        ))}
                    </div>
                    <div className="grid grid-cols-7">
                        {calendarDays.map((d, idx) => (
                            <div
                                key={idx}
                                onClick={() => d && handleDayClick(d.date)}
                                className={`p-3 min-h-[80px] border-r border-b border-gray-50 cursor-pointer transition-all hover:bg-gray-50 ${!d ? 'bg-gray-50/50' : ''
                                    } ${d?.isHoliday ? (d.isWeekendHoliday ? 'bg-rose-100 hover:bg-rose-200' : 'bg-amber-100 hover:bg-amber-200') : ''}`}
                            >
                                {d && (
                                    <>
                                        <div className={`text-lg font-bold ${d.isHoliday ? (d.isWeekendHoliday ? 'text-rose-600' : 'text-amber-700') : d.isWeekend ? 'text-rose-400' : 'text-gray-800'}`}>
                                            {d.day}
                                        </div>
                                        {d.isHoliday && (
                                            <div className={`text-xs mt-1 ${d.isWeekendHoliday ? 'text-rose-600' : 'text-amber-700'} truncate`}>
                                                {d.holidayName}
                                            </div>
                                        )}
                                    </>
                                )}
                            </div>
                        ))}
                    </div>
                </div>

                {/* Legend */}
                <div className="flex flex-wrap gap-6 text-sm justify-center">
                    <div className="flex items-center gap-2">
                        <div className="w-4 h-4 bg-rose-100 border border-rose-200 rounded"></div>
                        <span className="text-gray-600">Weekend</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <div className="w-4 h-4 bg-amber-100 border border-amber-200 rounded"></div>
                        <span className="text-gray-600">Custom Holiday</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <div className="w-4 h-4 bg-white border border-gray-200 rounded"></div>
                        <span className="text-gray-600">Working Day</span>
                    </div>
                </div>

            </div>
            {/* Modal */}
            {modalOpen && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setModalOpen(false)}>
                    <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl" onClick={e => e.stopPropagation()}>
                        <h3 className="text-xl font-bold text-gray-800 mb-2">
                            {isRemoving ? 'Holiday Details' : 'Add Holiday'}
                        </h3>
                        <p className="text-gray-500 text-sm mb-4">
                            {new Date(selectedDate).toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
                        </p>
                        <div className="mb-4">
                            <label className="block text-sm font-medium text-gray-600 mb-2">Holiday Name</label>
                            <input
                                type="text"
                                value={holidayName}
                                onChange={(e) => setHolidayName(e.target.value)}
                                className="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl text-gray-800 outline-none focus:ring-2 focus:ring-[#E85D4E]/20 focus:border-[#E85D4E]"
                                placeholder="e.g. Diwali, Christmas, Company Anniversary"
                                disabled={isRemoving}
                            />
                        </div>
                        <div className="flex gap-3">
                            {isRemoving ? (
                                <>
                                    <button onClick={() => setModalOpen(false)} className="flex-1 py-3 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-xl font-medium transition-colors">
                                        Close
                                    </button>
                                    <button onClick={handleRemoveHoliday} className="flex-1 py-3 bg-rose-500 hover:bg-rose-600 text-white rounded-xl font-medium transition-colors">
                                        Remove Holiday
                                    </button>
                                </>
                            ) : (
                                <>
                                    <button onClick={() => setModalOpen(false)} className="flex-1 py-3 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-xl font-medium transition-colors">
                                        Cancel
                                    </button>
                                    <button onClick={handleAddHoliday} className="flex-1 py-3 bg-[#E85D4E] hover:bg-[#D54D3E] text-white rounded-xl font-medium transition-colors">
                                        Add Holiday
                                    </button>
                                </>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </>
    );
};

export default HolidaysSection;
