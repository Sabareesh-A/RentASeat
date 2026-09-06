import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Navbar } from '../../components/ui';
import { Button } from '../../components/ui/Button';
import { Input, Select, Checkbox } from '../../components/ui/Input';
import { authService } from '../../services';
import { validateEmail, validatePassword, validatePasswordMatch, validatePhone } from '../../validation';
import './Auth.css';

const RegisterPage: React.FC = () => {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    phone: '',
    password: '',
    confirmPassword: '',
    role: 'passenger' as const,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [agreedToTerms, setAgreedToTerms] = useState(false);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!formData.name || formData.name.length < 2) {
      setError('Please enter a valid name');
      return;
    }

    if (!validateEmail(formData.email)) {
      setError('Please enter a valid email');
      return;
    }

    if (!validatePhone(formData.phone)) {
      setError('Please enter a valid phone number');
      return;
    }

    const passwordValidation = validatePassword(formData.password);
    if (passwordValidation.score < 2) {
      setError('Password is too weak. ' + passwordValidation.feedback.join(', '));
      return;
    }

    if (!validatePasswordMatch(formData.password, formData.confirmPassword)) {
      setError('Passwords do not match');
      return;
    }

    if (!agreedToTerms) {
      setError('Please agree to the Terms of Service');
      return;
    }

    setLoading(true);
    try {
      const response = await authService.register(formData);
      if (response.success) {
        localStorage.setItem('user', JSON.stringify(response.data));
        navigate(`/${formData.role}/dashboard`);
      } else {
        setError(response.error || 'Registration failed');
      }
    } catch (err) {
      setError('An unexpected error occurred');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <Navbar />
      <div className="auth-container">
        <div className="auth-card">
          <h1>Create Account</h1>
          <p>Join RentASeat and start your journey</p>

          {error && <div style={{ color: 'red', marginBottom: '1rem' }}>{error}</div>}

          <form onSubmit={handleRegister}>
            <Input
              label="Full Name"
              placeholder="John Doe"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              disabled={loading}
            />

            <Input
              label="Email"
              type="email"
              placeholder="your@email.com"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              disabled={loading}
            />

            <Input
              label="Phone"
              type="tel"
              placeholder="+1 (555) 000-0000"
              value={formData.phone}
              onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
              disabled={loading}
            />

            <Select
              label="I want to be a"
              options={[
                { value: 'passenger', label: 'Passenger' },
                { value: 'driver', label: 'Driver' },
              ]}
              value={formData.role}
              onChange={(e) => setFormData({ ...formData, role: e.target.value as any })}
            />

            <Input
              label="Password"
              type="password"
              placeholder="Enter your password"
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              disabled={loading}
            />

            <Input
              label="Confirm Password"
              type="password"
              placeholder="Confirm your password"
              value={formData.confirmPassword}
              onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
              disabled={loading}
            />

            <Checkbox
              label="I agree to the Terms of Service and Privacy Policy"
              checked={agreedToTerms}
              onChange={(e) => setAgreedToTerms(e.target.checked)}
            />

            <Button type="submit" fullWidth loading={loading}>
              Create Account
            </Button>
          </form>

          <div style={{ marginTop: '1.5rem', paddingTop: '1.5rem', borderTop: '1px solid #e5e7eb', textAlign: 'center' }}>
            Already have an account?{' '}
            <Link to="/login" style={{ fontWeight: 'bold' }}>
              Sign In
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
};

export default RegisterPage;
