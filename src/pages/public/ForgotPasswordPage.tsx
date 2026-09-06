import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Navbar } from '../../components/ui';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { authService } from '../../services';
import { validateEmail } from '../../validation';
import './Auth.css';

const ForgotPasswordPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!validateEmail(email)) {
      setError('Please enter a valid email');
      return;
    }

    setLoading(true);
    try {
      const response = await authService.resetPasswordRequest(email);
      if (response.success) {
        setSent(true);
      } else {
        setError(response.error || 'Failed to send reset email');
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
          {!sent ? (
            <>
              <h1>Reset Password</h1>
              <p>Enter your email address and we'll send you a link to reset your password</p>

              {error && <div style={{ color: 'red', marginBottom: '1rem' }}>{error}</div>}

              <form onSubmit={handleSubmit}>
                <Input
                  label="Email"
                  type="email"
                  placeholder="your@email.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={loading}
                />

                <Button type="submit" fullWidth loading={loading}>
                  Send Reset Link
                </Button>
              </form>

              <div style={{ marginTop: '1.5rem', paddingTop: '1.5rem', borderTop: '1px solid #e5e7eb', textAlign: 'center' }}>
                <Link to="/login">Back to Sign In</Link>
              </div>
            </>
          ) : (
            <>
              <h1>Check Your Email</h1>
              <p>We've sent a password reset link to {email}</p>
              <p>Please check your email and click the link to reset your password.</p>

              <Button fullWidth variant="primary" onClick={() => setSent(false)}>
                Send Another Email
              </Button>

              <div style={{ marginTop: '1.5rem', paddingTop: '1.5rem', borderTop: '1px solid #e5e7eb', textAlign: 'center' }}>
                <Link to="/login">Back to Sign In</Link>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default ForgotPasswordPage;
