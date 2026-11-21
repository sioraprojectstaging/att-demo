import React from 'react';
import AdminDashboard from './AdminDashboard';

// All authenticated users go to AdminDashboard
// Employee features are accessed via mobile app only
const Dashboard = () => {
    return <AdminDashboard />;
};

export default Dashboard;
