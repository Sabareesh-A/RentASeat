import React from 'react';
import { Link } from 'react-router-dom';
import { Navbar } from '../../components/ui';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';

const PassengerDashboard: React.FC = () => {
  return (
    <div>
      <Navbar
        links={[
          { label: 'Search', href: '/search' },
          { label: 'My Bookings', href: '/passenger/bookings' },
          { label: 'Profile', href: '/passenger/profile' },
        ]}
      />
      <div className="container" style={{ padding: '2rem' }}>
        <h1>Passenger Dashboard</h1>
        <p>Welcome to your RentASeat Passenger Dashboard</p>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1.5rem', marginTop: '2rem' }}>
          <Card elevated>
            <h3>Book a Ride</h3>
            <p>Find and book your next ride</p>
            <Link to="/search">
              <Button fullWidth>Search Rides</Button>
            </Link>
          </Card>

          <Card elevated>
            <h3>My Bookings</h3>
            <p>View your booking history</p>
            <Link to="/passenger/bookings">
              <Button fullWidth>View Bookings</Button>
            </Link>
          </Card>

          <Card elevated>
            <h3>Profile</h3>
            <p>Manage your account</p>
            <Link to="/passenger/profile">
              <Button fullWidth>Edit Profile</Button>
            </Link>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default PassengerDashboard;
