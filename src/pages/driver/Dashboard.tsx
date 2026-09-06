import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Navbar } from '../../components/ui';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { journeyService } from '../../services';

const DriverDashboard: React.FC = () => {
  const [journeys, setJourneys] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadJourneys();
  }, []);

  const loadJourneys = async () => {
    try {
      const userId = JSON.parse(localStorage.getItem('user') || '{}')?.id || 'user1';
      const response = await journeyService.getJourneysByDriver(userId);
      if (response.success) {
        setJourneys(response.data || []);
      }
    } catch (err) {
      console.error('Failed to load journeys');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <Navbar
        links={[
          { label: 'My Journeys', href: '/driver/journeys' },
          { label: 'Create Journey', href: '/driver/journeys/create' },
          { label: 'Profile', href: '/passenger/profile' },
        ]}
      />
      <div className="container" style={{ padding: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h1>Driver Dashboard</h1>
          <Link to="/driver/journeys/create">
            <Button variant="primary">Create Journey</Button>
          </Link>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1.5rem', marginTop: '2rem' }}>
          <Card elevated>
            <h3>Active Journeys</h3>
            <p style={{ fontSize: '2rem', fontWeight: 'bold' }}>{journeys.filter(j => j.status === 'active').length}</p>
          </Card>

          <Card elevated>
            <h3>Completed Rides</h3>
            <p style={{ fontSize: '2rem', fontWeight: 'bold' }}>{journeys.filter(j => j.status === 'completed').length}</p>
          </Card>

          <Card elevated>
            <h3>Total Earnings</h3>
            <p style={{ fontSize: '2rem', fontWeight: 'bold' }}>$0</p>
          </Card>
        </div>

        <h2 style={{ marginTop: '3rem' }}>Recent Journeys</h2>
        {loading ? (
          <p>Loading journeys...</p>
        ) : journeys.length === 0 ? (
          <p>No journeys found. <Link to="/driver/journeys/create">Create one now!</Link></p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1rem' }}>
            {journeys.slice(0, 3).map((journey) => (
              <Card key={journey.id}>
                <h3 style={{ margin: '0 0 0.5rem 0' }}>
                  {journey.from} → {journey.to}
                </h3>
                <p style={{ margin: '0.5rem 0' }}>
                  {journey.date} at {journey.departureTime} | {journey.availableSeats} seats available
                </p>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default DriverDashboard;
