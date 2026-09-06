import React from 'react';
import { useParams } from 'react-router-dom';
import { Navbar } from '../../components/ui';
import { Button } from '../../components/ui/Button';
import { journeyService } from '../../services';
import { LoadingState, ErrorState } from '../../components/ui/StateComponents';

const JourneyDetailsPage: React.FC = () => {
  const { id } = useParams();
  const [journey, setJourney] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    loadJourney();
  }, [id]);

  const loadJourney = async () => {
    if (!id) return;
    try {
      const response = await journeyService.getJourneyById(id);
      if (response.success) {
        setJourney(response.data);
      } else {
        setError(response.error || 'Journey not found');
      }
    } catch (err) {
      setError('Failed to load journey');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <Navbar />
      <div className="container" style={{ padding: '2rem' }}>
        {loading ? (
          <LoadingState />
        ) : error ? (
          <ErrorState message={error} retry={loadJourney} />
        ) : journey ? (
          <div>
            <h1>Journey Details</h1>
            <p>Route: {journey.from} → {journey.to}</p>
            <p>Date: {journey.date}</p>
            <p>Price: ${journey.pricePerSeat}</p>
            <p>Available Seats: {journey.availableSeats}</p>
            <Button onClick={() => alert('Booking feature coming soon!')}>
              Book This Ride
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default JourneyDetailsPage;
