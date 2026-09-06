import React from 'react';
import { Navbar } from '../../components/ui';
import { Button } from '../../components/ui/Button';

const DriverJourneys: React.FC = () => {
  return (
    <div>
      <Navbar />
      <div className="container" style={{ padding: '2rem' }}>
        <h1>My Journeys</h1>
        <p>Manage your posted rides</p>
        <Button style={{ marginTop: '1rem' }}>Create New Journey</Button>
      </div>
    </div>
  );
};

export default DriverJourneys;
