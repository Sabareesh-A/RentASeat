import React, { useState, useEffect, useCallback } from 'react';
import { Navbar } from '../../components/ui';
import { Card, Badge } from '../../components/ui/Card';
import { Input } from '../../components/ui/Input';
import { Button } from '../../components/ui/Button';
import { getHealth } from '../../api/health';
import type { HealthResponse } from '../../api/health';
import { ApiError } from '../../api/client';

type HealthStatus = 'idle' | 'loading' | 'ok' | 'error';

const AdminDashboard: React.FC = () => {
  const [stats] = useState({
    totalUsers: 42,
    totalDrivers: 12,
    totalPassengers: 30,
    activeJourneys: 8,
    totalBookings: 54,
  });

  // API health check state
  const [healthStatus, setHealthStatus] = useState<HealthStatus>('idle');
  const [healthData, setHealthData] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [healthCheckedAt, setHealthCheckedAt] = useState<Date | null>(null);

  const checkHealth = useCallback(async () => {
    setHealthStatus('loading');
    setHealthError(null);
    setHealthData(null);
    try {
      const data = await getHealth();
      setHealthData(data);
      setHealthStatus('ok');
      setHealthCheckedAt(new Date());
    } catch (err) {
      if (err instanceof ApiError) {
        setHealthError(`API error ${err.status}: ${err.message}`);
      } else if (err instanceof TypeError) {
        // Network failure or CORS block — message is safe to surface
        setHealthError(`Network error: ${err.message}`);
      } else {
        setHealthError('Unknown error occurred');
      }
      setHealthStatus('error');
      setHealthCheckedAt(new Date());
    }
  }, []);

  useEffect(() => {
    checkHealth();
  }, [checkHealth]);

  // ── Health badge helpers ───────────────────────────────────────────────────
  const healthBadgeVariant = (): 'success' | 'warning' | 'error' | 'info' => {
    if (healthStatus === 'ok') return 'success';
    if (healthStatus === 'error') return 'error';
    return 'info';
  };

  const healthBadgeLabel = (): string => {
    if (healthStatus === 'loading') return 'Checking…';
    if (healthStatus === 'ok') return healthData?.status ?? 'OK';
    if (healthStatus === 'error') return 'Unreachable';
    return 'Unknown';
  };

  return (
    <div>
      <Navbar />
      <div className="container" style={{ padding: '2rem' }}>
        <h1>Admin Dashboard</h1>

        {/* ── Stats grid ── */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '1.5rem',
            marginTop: '2rem',
          }}
        >
          <Card elevated>
            <h3 style={{ margin: '0 0 0.5rem 0' }}>Total Users</h3>
            <p style={{ fontSize: '2rem', fontWeight: 'bold', margin: 0 }}>
              {stats.totalUsers}
            </p>
          </Card>

          <Card elevated>
            <h3 style={{ margin: '0 0 0.5rem 0' }}>Drivers</h3>
            <p style={{ fontSize: '2rem', fontWeight: 'bold', margin: 0 }}>
              {stats.totalDrivers}
            </p>
          </Card>

          <Card elevated>
            <h3 style={{ margin: '0 0 0.5rem 0' }}>Passengers</h3>
            <p style={{ fontSize: '2rem', fontWeight: 'bold', margin: 0 }}>
              {stats.totalPassengers}
            </p>
          </Card>

          <Card elevated>
            <h3 style={{ margin: '0 0 0.5rem 0' }}>Active Journeys</h3>
            <p style={{ fontSize: '2rem', fontWeight: 'bold', margin: 0 }}>
              {stats.activeJourneys}
            </p>
          </Card>

          <Card elevated>
            <h3 style={{ margin: '0 0 0.5rem 0' }}>Total Bookings</h3>
            <p style={{ fontSize: '2rem', fontWeight: 'bold', margin: 0 }}>
              {stats.totalBookings}
            </p>
          </Card>
        </div>

        {/* ── User Management ── */}
        <h2 style={{ marginTop: '3rem' }}>User Management</h2>
        <div style={{ marginTop: '1rem' }}>
          <Input placeholder="Search users..." />
          <p style={{ marginTop: '1rem', color: '#6b7280' }}>
            User management table would go here
          </p>
        </div>

        {/* ── API Health Status ── */}
        <h2 style={{ marginTop: '3rem' }}>API Health Status</h2>
        <Card elevated>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
              flexWrap: 'wrap',
              gap: '1rem',
            }}
          >
            {/* Left: status info */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
                <span style={{ fontWeight: 600 }}>GET /health</span>
                <Badge variant={healthBadgeVariant()}>
                  {healthBadgeLabel()}
                </Badge>
              </div>

              {healthStatus === 'loading' && (
                <p style={{ color: '#6b7280', margin: 0, fontSize: '0.875rem' }}>
                  Contacting API Gateway…
                </p>
              )}

              {healthStatus === 'ok' && healthData && (
                <div style={{ fontSize: '0.875rem', color: '#374151' }}>
                  {healthData.service && (
                    <p style={{ margin: '0 0 0.25rem 0', fontWeight: 500 }}>
                      Service: {healthData.service}
                    </p>
                  )}
                  {healthData.message && (
                    <p style={{ margin: '0 0 0.25rem 0' }}>{healthData.message}</p>
                  )}
                  {healthData.timestamp && (
                    <p style={{ margin: 0, color: '#6b7280' }}>
                      Server time: {healthData.timestamp}
                    </p>
                  )}
                  {/* Render any extra fields the Lambda returns */}
                  {Object.entries(healthData)
                    .filter(([k]) => !['status', 'service', 'message', 'timestamp'].includes(k))
                    .map(([k, v]) => (
                      <p key={k} style={{ margin: '0.25rem 0 0 0', color: '#6b7280' }}>
                        {k}: {String(v)}
                      </p>
                    ))}
                </div>
              )}

              {healthStatus === 'error' && (
                <p style={{ color: 'var(--error)', margin: 0, fontSize: '0.875rem' }}>
                  {healthError}
                </p>
              )}

              {healthCheckedAt && (
                <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.75rem', color: '#9ca3af' }}>
                  Last checked: {healthCheckedAt.toLocaleTimeString()}
                </p>
              )}
            </div>

            {/* Right: refresh button */}
            <Button
              variant="ghost"
              size="sm"
              onClick={checkHealth}
              loading={healthStatus === 'loading'}
            >
              Refresh
            </Button>
          </div>
        </Card>

        {/* ── Security Events placeholder ── */}
        <h2 style={{ marginTop: '3rem' }}>Security Events</h2>
        <Card elevated>
          <p style={{ color: '#6b7280', margin: 0 }}>
            Security event logs will be displayed here (CloudTrail integration — Step 5+).
          </p>
        </Card>
      </div>
    </div>
  );
};

export default AdminDashboard;
