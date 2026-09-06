import React from 'react';
import type { Journey } from '../../types';
import { Card, Badge, StatusBadge } from '../ui/Card';
import { Button } from '../ui/Button';
import { formatCurrency, formatTime, formatDuration } from '../../utils/formatting';
import './JourneyCard.css';

interface JourneyCardProps {
  journey: Journey;
  onBook?: () => void;
  onViewDetails?: () => void;
  compact?: boolean;
}

export const JourneyCard: React.FC<JourneyCardProps> = ({
  journey,
  onBook,
  onViewDetails,
  compact = false,
}) => {
  return (
    <Card className="journey-card" elevated clickable={!!onViewDetails} onClick={onViewDetails}>
      <div className="journey-card-content">
        {/* Route */}
        <div className="journey-route">
          <div className="journey-location">
            <div className="location-label">From</div>
            <div className="location-name">{journey.from}</div>
          </div>

          <div className="journey-duration">
            <div className="duration-time">
              {formatDuration(journey.departureTime, journey.arrivalTime)}
            </div>
            <div className="duration-line"></div>
          </div>

          <div className="journey-location">
            <div className="location-label">To</div>
            <div className="location-name">{journey.to}</div>
          </div>
        </div>

        {/* Time and Seats */}
        <div className="journey-info">
          <div className="info-item">
            <span className="info-label">Departure</span>
            <span className="info-value">{formatTime(journey.departureTime)}</span>
          </div>

          <div className="info-item">
            <span className="info-label">Arrival</span>
            <span className="info-value">{formatTime(journey.arrivalTime)}</span>
          </div>

          {!compact && (
            <>
              <div className="info-item">
                <span className="info-label">Seats</span>
                <span className="info-value">
                  {journey.availableSeats} of {journey.totalSeats}
                </span>
              </div>

              <div className="info-item">
                <span className="info-label">Price</span>
                <span className="info-value price">
                  {formatCurrency(journey.pricePerSeat)}
                </span>
              </div>
            </>
          )}
        </div>

        {/* Driver Info */}
        <div className="journey-driver">
          <img
            src={journey.driver.avatar}
            alt={journey.driver.name}
            className="driver-avatar"
          />
          <div>
            <div className="driver-name">{journey.driver.name}</div>
            <div className="driver-rating">
              ⭐ {journey.driver.rating?.toFixed(1) || 'N/A'} ({journey.driver.reviews || 0})
            </div>
          </div>
        </div>

        {/* Vehicle Info */}
        {!compact && (
          <div className="journey-vehicle">
            <Badge variant="info" size="sm">
              {journey.vehicle.model}
            </Badge>
            <span className="vehicle-detail">{journey.vehicle.vehicleType}</span>
          </div>
        )}

        {/* Footer */}
        <div className="journey-footer">
          <div className="journey-badges">
            <StatusBadge status={journey.status} />
          </div>

          {onBook && (
            <Button
              size="sm"
              onClick={(e: React.MouseEvent) => {
                e.stopPropagation();
                onBook();
              }}
            >
              Book Now
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
};
