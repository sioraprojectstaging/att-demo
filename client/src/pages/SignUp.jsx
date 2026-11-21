import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate, Link } from 'react-router-dom';
import { Lock, User, Mail, MapPin, AlertCircle, Eye, EyeOff } from 'lucide-react';
import api from '../services/api';

const SignUp = () => {
    const [formData, setFormData] = useState({
        username: '',
        email: '',
        password: '',
        confirmPassword: '',
        location: ''
    });
    const [locations, setLocations] = useState([]);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const [loading, setLoading] = useState(false);
    const [showPassword, setShowPassword] = useState(false);
    const [showConfirmPassword, setShowConfirmPassword] = useState(false);
    const { register } = useAuth();
    const navigate = useNavigate();

    // Fetch locations dynamically
    useEffect(() => {
        const fetchLocations = async () => {
            try {
                const res = await api.get('locations/');
                const data = Array.isArray(res.data) ? res.data : res.data.results || [];
                setLocations(data);
                if (data.length > 0) {
                    setFormData(prev => ({ ...prev, location: data[0].id.toString() }));
                }
            } catch (err) {
                console.log('Could not fetch locations:', err);
                // No hardcoded fallback: made-up IDs may not exist in this database.
                setLocations([]);
                setError('Could not load locations. Please refresh the page or try again later.');
            }
        };
        fetchLocations();
    }, []);

    const handleChange = (e) => {
        setFormData({ ...formData, [e.target.name]: e.target.value });
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setSuccess('');

        // Collect all client-side validation errors
        const validationErrors = [];

        // Validate passwords match
        if (formData.password !== formData.confirmPassword) {
            validationErrors.push('Passwords do not match');
        }

        // Validate password length
        if (formData.password.length < 6) {
            validationErrors.push('Password must be at least 6 characters');
        }

        // Validate email format
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(formData.email)) {
            validationErrors.push('Please enter a valid email address');
        }

        // Validate username
        if (formData.username.length < 3) {
            validationErrors.push('Username must be at least 3 characters');
        }

        // If there are validation errors, show them all and return
        if (validationErrors.length > 0) {
            setError(validationErrors);
            return;
        }

        setLoading(true);
        try {
            const response = await register({
                username: formData.username,
                email: formData.email,
                password: formData.password,
                location: formData.location,
                role: 'ADMIN'  // Only admins register via web
            });
            if (response.pending_approval) {
                setSuccess(`Admin registration submitted for ${response.location || 'your location'}! Awaiting approval from system administrator.`);
            } else {
                navigate('/login');
            }
        } catch (err) {
            // Collect all errors from the response
            const errors = [];
            const errorData = err.response?.data;

            if (errorData) {
                // Handle field-specific errors (arrays of messages)
                if (errorData.username) {
                    errors.push(`Username: ${Array.isArray(errorData.username) ? errorData.username.join(', ') : errorData.username}`);
                }
                if (errorData.email) {
                    errors.push(`Email: ${Array.isArray(errorData.email) ? errorData.email.join(', ') : errorData.email}`);
                }
                if (errorData.password) {
                    errors.push(`Password: ${Array.isArray(errorData.password) ? errorData.password.join(', ') : errorData.password}`);
                }
                if (errorData.location) {
                    errors.push(`Location: ${Array.isArray(errorData.location) ? errorData.location.join(', ') : errorData.location}`);
                }
                // Handle general error message
                if (errorData.error) {
                    errors.push(errorData.error);
                }
                // Handle non_field_errors
                if (errorData.non_field_errors) {
                    errors.push(...(Array.isArray(errorData.non_field_errors) ? errorData.non_field_errors : [errorData.non_field_errors]));
                }
            }

            setError(errors.length > 0 ? errors : ['Registration failed']);
        }
        setLoading(false);
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-[#FBF8F6] p-4">
            <div className="w-full max-w-md">
                {/* Logo Section */}
                <div className="text-center mb-8">
                    <img
                        src="/sioraone.svg"
                        alt="Siora One"
                        className="h-12 mx-auto mb-4"
                    />
                    <p className="text-sm text-gray-500 mt-1">Admin Registration</p>
                </div>

                {/* SignUp Card */}
                <div className="bg-white rounded-2xl shadow-xl shadow-gray-100 p-8 border border-gray-100">
                    <h2 className="text-xl font-bold text-gray-800 text-center mb-6">Register as Admin</h2>

                    {error && error.length > 0 && (
                        <div className="bg-red-50 border border-red-200 text-red-600 px-4 py-3 rounded-lg mb-6 text-sm">
                            {Array.isArray(error) ? (
                                <ul className="list-disc list-inside space-y-1">
                                    {error.map((err, index) => (
                                        <li key={index}>{err}</li>
                                    ))}
                                </ul>
                            ) : (
                                <p className="text-center">{error}</p>
                            )}
                        </div>
                    )}

                    {success && (
                        <div className="bg-green-50 border border-green-200 text-green-600 px-4 py-3 rounded-lg mb-6 text-sm text-center">
                            {success}
                            <Link to="/login" className="block mt-2 text-green-700 font-semibold underline">
                                Go to Login
                            </Link>
                        </div>
                    )}

                    {!success && (
                        <form onSubmit={handleSubmit} className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-600 mb-2">Username</label>
                                <div className="relative">
                                    <User size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                                    <input
                                        type="text"
                                        name="username"
                                        value={formData.username}
                                        onChange={handleChange}
                                        className="w-full pl-10 pr-4 py-3 bg-gray-50 border border-gray-200 rounded-xl text-gray-800 placeholder-gray-400 outline-none focus:ring-2 focus:ring-[#E85D4E]/20 focus:border-[#E85D4E] transition-all"
                                        placeholder="Choose a username"
                                        required
                                    />
                                </div>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-600 mb-2">Email</label>
                                <div className="relative">
                                    <Mail size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                                    <input
                                        type="email"
                                        name="email"
                                        value={formData.email}
                                        onChange={handleChange}
                                        className="w-full pl-10 pr-4 py-3 bg-gray-50 border border-gray-200 rounded-xl text-gray-800 placeholder-gray-400 outline-none focus:ring-2 focus:ring-[#E85D4E]/20 focus:border-[#E85D4E] transition-all"
                                        placeholder="Enter your email"
                                        required
                                    />
                                </div>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-600 mb-2">Password</label>
                                <div className="relative">
                                    <Lock size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                                    <input
                                        type={showPassword ? "text" : "password"}
                                        name="password"
                                        value={formData.password}
                                        onChange={handleChange}
                                        className="w-full pl-10 pr-12 py-3 bg-gray-50 border border-gray-200 rounded-xl text-gray-800 placeholder-gray-400 outline-none focus:ring-2 focus:ring-[#E85D4E]/20 focus:border-[#E85D4E] transition-all"
                                        placeholder="Create a password"
                                        required
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowPassword(!showPassword)}
                                        className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
                                    >
                                        {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                                    </button>
                                </div>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-600 mb-2">Confirm Password</label>
                                <div className="relative">
                                    <Lock size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                                    <input
                                        type={showConfirmPassword ? "text" : "password"}
                                        name="confirmPassword"
                                        value={formData.confirmPassword}
                                        onChange={handleChange}
                                        className="w-full pl-10 pr-12 py-3 bg-gray-50 border border-gray-200 rounded-xl text-gray-800 placeholder-gray-400 outline-none focus:ring-2 focus:ring-[#E85D4E]/20 focus:border-[#E85D4E] transition-all"
                                        placeholder="Confirm your password"
                                        required
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                                        className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
                                    >
                                        {showConfirmPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                                    </button>
                                </div>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-600 mb-2">Location</label>
                                <div className="relative">
                                    <MapPin size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#E85D4E]" />
                                    <select
                                        name="location"
                                        value={formData.location}
                                        onChange={handleChange}
                                        className="w-full pl-10 pr-4 py-3 bg-gray-50 border border-gray-200 rounded-xl text-gray-800 outline-none focus:ring-2 focus:ring-[#E85D4E]/20 focus:border-[#E85D4E] transition-all appearance-none cursor-pointer"
                                    >
                                        {locations.map(loc => (
                                            <option key={loc.id || loc.code} value={loc.id || loc.code}>{loc.name}</option>
                                        ))}
                                    </select>
                                </div>
                            </div>

                            <div className="flex items-start gap-2 bg-[#FEF2F2] border border-[#FECACA] text-[#E85D4E] px-4 py-3 rounded-lg text-sm">
                                <AlertCircle size={18} className="flex-shrink-0 mt-0.5" />
                                <span>Admin accounts require approval from system administrator before login.</span>
                            </div>

                            <button
                                type="submit"
                                disabled={loading}
                                className="w-full bg-[#E85D4E] hover:bg-[#D54D3E] text-white font-semibold py-3 px-4 rounded-xl transition-all shadow-sm disabled:opacity-50 disabled:cursor-not-allowed mt-6"
                            >
                                {loading ? 'Submitting...' : 'Register as Admin'}
                            </button>
                        </form>
                    )}

                    <div className="mt-6 text-center">
                        <span className="text-gray-500 text-sm">Already have an account? </span>
                        <Link to="/login" className="text-[#E85D4E] hover:text-[#D54D3E] font-semibold text-sm">
                            Sign In
                        </Link>
                    </div>
                </div>

                <p className="text-center text-xs text-gray-400 mt-6">
                    © {new Date().getFullYear()} Siora One. All rights reserved.
                </p>
            </div>
        </div>
    );
};

export default SignUp;
