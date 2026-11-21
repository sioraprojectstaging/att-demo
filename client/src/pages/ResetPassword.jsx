import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Lock, Key, Building2, CheckCircle, ArrowLeft } from 'lucide-react';
import api from '../services/api';

const ResetPassword = () => {
    const [token, setToken] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [loading, setLoading] = useState(false);
    const [success, setSuccess] = useState(false);
    const [error, setError] = useState('');
    const navigate = useNavigate();

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');

        if (password !== confirmPassword) {
            setError('Passwords do not match');
            return;
        }

        if (password.length < 6) {
            setError('Password must be at least 6 characters');
            return;
        }

        setLoading(true);
        try {
            await api.post('auth/reset-password/', { token, password });
            setSuccess(true);
            setTimeout(() => navigate('/login'), 3000);
        } catch (err) {
            setError(err.response?.data?.error || 'Invalid or expired token');
        }
        setLoading(false);
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-orange-50 via-amber-50 to-orange-100 p-4">
            <div className="w-full max-w-md">
                {/* Logo Section */}
                <div className="text-center mb-8">
                    <div className="inline-flex items-center justify-center w-16 h-16 bg-[#C2410C] rounded-2xl shadow-lg shadow-orange-200 mb-4">
                        <Building2 size={32} className="text-white" />
                    </div>
                    <h1 className="text-2xl font-bold text-gray-800">Siora One</h1>
                    <p className="text-sm text-gray-500 mt-1">Set New Password</p>
                </div>

                {/* Card */}
                <div className="bg-white rounded-2xl shadow-xl shadow-orange-100 p-8 border border-orange-100">
                    {!success ? (
                        <>
                            <h2 className="text-xl font-bold text-gray-800 text-center mb-6">Reset Password</h2>

                            {error && (
                                <div className="bg-red-50 border border-red-200 text-red-600 px-4 py-3 rounded-lg mb-6 text-sm text-center">
                                    {error}
                                </div>
                            )}

                            <form onSubmit={handleSubmit} className="space-y-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-600 mb-2">Reset Token</label>
                                    <div className="relative">
                                        <Key size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                                        <input
                                            type="text"
                                            value={token}
                                            onChange={(e) => setToken(e.target.value)}
                                            className="w-full pl-10 pr-4 py-3 bg-gray-50 border border-gray-200 rounded-xl text-gray-800 placeholder-gray-400 outline-none focus:ring-2 focus:ring-orange-100 focus:border-orange-300 transition-all"
                                            placeholder="Paste your reset token"
                                            required
                                        />
                                    </div>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-600 mb-2">New Password</label>
                                    <div className="relative">
                                        <Lock size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                                        <input
                                            type="password"
                                            value={password}
                                            onChange={(e) => setPassword(e.target.value)}
                                            className="w-full pl-10 pr-4 py-3 bg-gray-50 border border-gray-200 rounded-xl text-gray-800 placeholder-gray-400 outline-none focus:ring-2 focus:ring-orange-100 focus:border-orange-300 transition-all"
                                            placeholder="Enter new password"
                                            required
                                        />
                                    </div>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-600 mb-2">Confirm Password</label>
                                    <div className="relative">
                                        <Lock size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                                        <input
                                            type="password"
                                            value={confirmPassword}
                                            onChange={(e) => setConfirmPassword(e.target.value)}
                                            className="w-full pl-10 pr-4 py-3 bg-gray-50 border border-gray-200 rounded-xl text-gray-800 placeholder-gray-400 outline-none focus:ring-2 focus:ring-orange-100 focus:border-orange-300 transition-all"
                                            placeholder="Confirm new password"
                                            required
                                        />
                                    </div>
                                </div>

                                <button
                                    type="submit"
                                    disabled={loading}
                                    className="w-full bg-[#C2410C] hover:bg-orange-700 text-white font-semibold py-3 px-4 rounded-xl transition-all shadow-lg shadow-orange-200 disabled:opacity-50 mt-2"
                                >
                                    {loading ? 'Resetting...' : 'Reset Password'}
                                </button>
                            </form>
                        </>
                    ) : (
                        <div className="text-center">
                            <div className="inline-flex items-center justify-center w-16 h-16 bg-green-100 rounded-full mb-4">
                                <CheckCircle size={32} className="text-green-600" />
                            </div>
                            <h2 className="text-xl font-bold text-gray-800 mb-2">Password Reset!</h2>
                            <p className="text-sm text-gray-500 mb-6">
                                Your password has been reset successfully. Redirecting to login...
                            </p>
                        </div>
                    )}

                    <div className="mt-6 text-center">
                        <Link to="/login" className="text-[#C2410C] hover:text-orange-700 font-medium text-sm inline-flex items-center gap-2">
                            <ArrowLeft size={16} /> Back to Login
                        </Link>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default ResetPassword;
