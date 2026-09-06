import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Navbar } from '../../components/ui';
import { Button } from '../../components/ui/Button';
import { Input, Textarea } from '../../components/ui/Input';
import { journeyService } from '../../services';

const CreateJourney: React.FC = () => {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    from: '',
    to: '',
    date: '',
    departureTime: '',
    arrivalTime: '',
    availableSeats: '1',
    pricePerSeat: '20',
    vehicleId: '',
    description: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const response = await journeyService.createJourney(formData);
      if (response.success) {
        navigate('/driver/journeys');
      } else {
        setError(response.error || 'Failed to create journey');
      }
    } catch (err) {
      setError('An unexpected error occurred');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <Navbar />
      <div className="container" style={{ padding: '2rem', maxWidth: '600px' }}>
        <h1>Create New Journey</h1>

        {error && <div style={{ color: 'red', marginBottom: '1rem' }}>{error}</div>}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <Input
            label="From"
            placeholder="Departure city"
            value={formData.from}
            onChange={(e) => setFormData({ ...formData, from: e.target.value })}
            required
          />

          <Input
            label="To"
            placeholder="Destination city"
            value={formData.to}
            onChange={(e) => setFormData({ ...formData, to: e.target.value })}
            required
          />

          <Input
            label="Date"
            type="date"
            value={formData.date}
            onChange={(e) => setFormData({ ...formData, date: e.target.value })}
            required
          />

          <Input
            label="Departure Time"
            type="time"
            value={formData.departureTime}
            onChange={(e) => setFormData({ ...formData, departureTime: e.target.value })}
            required
          />

          <Input
            label="Arrival Time"
            type="time"
            value={formData.arrivalTime}
            onChange={(e) => setFormData({ ...formData, arrivalTime: e.target.value })}
            required
          />

          <Input
            label="Available Seats"
            type="number"
            value={formData.availableSeats}
            onChange={(e) => setFormData({ ...formData, availableSeats: e.target.value })}
            required
          />

          <Input
            label="Price Per Seat ($)"
            type="number"
            step="0.01"
            value={formData.pricePerSeat}
            onChange={(e) => setFormData({ ...formData, pricePerSeat: e.target.value })}
            required
          />

          <Textarea
            label="Description"
            placeholder="Add any additional details about your journey"
            value={formData.description}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
            rows={4}
          />

          <Button type="submit" fullWidth loading={loading}>
            Create Journey
          </Button>
        </form>
      </div>
    </div>
  );
};

export default CreateJourney;
