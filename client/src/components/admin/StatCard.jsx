import React from 'react';

const StatCard = ({ label, value, icon: Icon, colorClass, bgClass }) => (
    <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100 flex items-center gap-6 relative overflow-hidden">
        <div className={`w-14 h-14 rounded-full flex items-center justify-center ${bgClass} ${colorClass}`}>
            <Icon size={28} />
        </div>
        <div>
            <div className="text-gray-500 text-sm font-medium">{label}</div>
            <div className="text-3xl font-bold text-gray-800 mt-1">{value}</div>
        </div>
    </div>
);

export default StatCard;
