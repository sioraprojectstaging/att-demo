import React from 'react';
import { useNavigate } from 'react-router-dom';

const SidebarItem = ({ id, label, icon: Icon, activeTab, sidebarOpen }) => {
    const navigate = useNavigate();

    return (
        <div
            onClick={() => navigate(`/dashboard/${id === 'overview' ? '' : id}`)}
            className={`flex items-center gap-3 mx-3 px-4 py-3 cursor-pointer transition-all duration-200 rounded-lg ${activeTab === id
                ? 'bg-[#E85D4E]/10 text-[#E85D4E]'
                : 'text-gray-600 hover:bg-gray-100 hover:text-gray-800'
                }`}
        >
            <Icon size={18} />
            {sidebarOpen && <span className="whitespace-nowrap text-sm font-medium flex-1">{label}</span>}
            {activeTab === id && sidebarOpen && <span className="w-2 h-2 bg-[#E85D4E] rounded-full"></span>}
        </div>
    );
};

export default SidebarItem;
