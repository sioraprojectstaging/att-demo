import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Mail, Building2, ArrowLeft, CheckCircle } from 'lucide-react';
import api from '../services/api';

const ForgotPassword = () => {
    const [email, setEmail] = useState('');
    const [loading, setLoading] = useState(false);
    const [success, setSuccess] = useState(false);
    const [resetToken, setResetToken] = useState('');
    const [error, setError] = useState('');

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);
        try {
            const res = await api.post('auth/forgot-password/', { email });
            setSuccess(true);
            setResetToken(res.data.reset_token || '');
        } catch (err) {
            setError(err.response?.data?.error || 'Something went wrong');
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
                    <p className="text-sm text-gray-500 mt-1">Password Recovery</p>
                </div>

                {/* Card */}
                <div className="bg-white rounded-2xl shadow-xl shadow-orange-100 p-8 border border-orange-100">
                    {!success ? (
                        <>
                            <h2 className="text-xl font-bold text-gray-800 text-center mb-2">Forgot Password?</h2>
                            <p className="text-sm text-gray-500 text-center mb-6">
                                Enter your email and we'll generate a reset token.
                            </p>

                            {error && (
                                <div className="bg-red-50 border border-red-200 text-red-600 px-4 py-3 rounded-lg mb-6 text-sm text-center">
                                    {error}
                                </div>
                            )}

                            <form onSubmit={handleSubmit} className="space-y-5">
                                <div>
                                    <label className="block text-sm font-medium text-gray-600 mb-2">Email Address</label>
                                    <div className="relative">
                                        <Mail size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                                        <input
                                            type="email"
                                            value={email}
                                            onChange={(e) => setEmail(e.target.value)}
                                            className="w-full pl-10 pr-4 py-3 bg-gray-50 border border-gray-200 rounded-xl text-gray-800 placeholder-gray-400 outline-none focus:ring-2 focus:ring-orange-100 focus:border-orange-300 transition-all"
                                            placeholder="Enter your email"
                                            required
                                        />
                                    </div>
                                </div>

                                <button
                                    type="submit"
                                    disabled={loading}
                                    className="w-full bg-[#C2410C] hover:bg-orange-700 text-white font-semibold py-3 px-4 rounded-xl transition-all shadow-lg shadow-orange-200 disabled:opacity-50"
                                >
                                    {loading ? 'Sending...' : 'Send Reset Link'}
                                </button>
                            </form>
                        </>
                    ) : (
                        <div className="text-center">
                            <div className="inline-flex items-center justify-center w-16 h-16 bg-green-100 rounded-full mb-4">
                                <CheckCircle size={32} className="text-green-600" />
                            </div>
                            <h2 className="text-xl font-bold text-gray-800 mb-2">Check Your Email</h2>
                            <p className="text-sm text-gray-500 mb-6">
                                If an account exists with this email, a reset token has been generated.
                            </p>

                            {resetToken ? (
                                <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 mb-6">
                                    <p className="text-xs text-gray-500 mb-2">Your reset token (development only):</p>
                                    <code className="text-sm text-gray-800 break-all">{resetToken}</code>
                                </div>
                            ) : (
                                <p className="text-sm text-gray-500 mb-6">
                                    If you don't receive it, ask your administrator to reset your password.
                                </p>
                            )}

                            <Link
                                to="/reset-password"
                                className="block w-full bg-[#C2410C] hover:bg-orange-700 text-white font-semibold py-3 px-4 rounded-xl transition-all shadow-lg shadow-orange-200 text-center"
                            >
                                Reset Password
                            </Link>
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

export default ForgotPassword;
