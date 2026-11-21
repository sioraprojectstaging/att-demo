import React, { createContext, useState, useEffect, useContext } from 'react';
import api from '../services/api';

export const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const token = localStorage.getItem('access_token');
        if (token) {
            // Here we should ideally validate the token or fetch user info
            // For simplicity, we'll try to get the user from local storage if I saved it, 
            // OR just keep them logged in but without details until they hit a protected route
            // A better approach for this simplified app: Store user info in localStorage on login too.
            const storedUser = localStorage.getItem('user_info');
            if (storedUser) {
                setUser(JSON.parse(storedUser));
            }
            setLoading(false);
        } else {
            setLoading(false);
        }
    }, []);

    const login = async (username, password) => {
        const response = await api.post('auth/login/', { username, password });
        const { access, refresh, user: userInfo } = response.data;
        localStorage.setItem('access_token', access);
        localStorage.setItem('refresh_token', refresh);
        localStorage.setItem('user_info', JSON.stringify(userInfo));

        setUser(userInfo);
        return true;
    };

    const register = async (userData) => {
        const response = await api.post('auth/register/', userData);
        return response.data;
    };

    const logout = () => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user_info');
        setUser(null);
    };

    return (
        <AuthContext.Provider value={{ user, login, logout, register, loading }}>
            {!loading && children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);
