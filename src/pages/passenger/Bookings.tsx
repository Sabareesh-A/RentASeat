import React, { useState, useEffect } from 'react';
import { Navbar } from '../../components/ui';
import { Card, Badge } from '../../components/ui/Card';
import { bookingService } from '../../services';

const PassengerBookings: React.FC = () => {
  const [bookings, setBookings] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadBookings();
  }, []);

  const loadBookings = async () => {
    try {
      const userId = JSON.parse(localStorage.getItem('user') || '{}')?.id || 'user2';
      const response = await bookingService.getBookingsByPassenger(userId);
      if (response.success) {
        setBookings(response.data || []);
      }
    } catch (err) {
      console.error('Failed to load bookings');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <Navbar />
      <div className="container" style={{ padding: '2rem' }}>
        <h1>My Bookings</h1>

        {loading ? (
          <p>Loading bookings...</p>
        ) : bookings.length === 0 ? (
          <p>No bookings found</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '2rem' }}>
            {bookings.map((booking) => (
              <Card key={booking.id} elevated>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                  <div>
                    <h3 style={{ margin: '0 0 0.5rem 0' }}>
                      {booking.journey.from} → {booking.journey.to}
                    </h3>
                    <p style={{ margin: '0.5rem 0' }}>
                      Date: {booking.journey.date} | Time: {booking.journey.departureTime}
                    </p>
                    <p style={{ margin: '0.5rem 0' }}>
                      Booking Ref: {booking.bookingReference}
                    </p>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <Badge variant={booking.status === 'confirmed' ? 'success' : 'warning'}>
                      {booking.status}
                    </Badge>
                    <p style={{ margin: '0.5rem 0 0 0', fontWeight: 'bold' }}>
                      ${booking.totalPrice}
                    </p>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default PassengerBookings;
