-- ============================================================================
-- RentASeat Database Migration: 001_initial_schema.sql
-- Description: Initial relational schema for RentASeat
--   - Tables: schema_migrations, users, vehicles, journeys, bookings, reviews
--   - Functions: auto-update timestamps, self-booking prevention, review eligibility
--   - Indexes: search optimization, foreign key coverage, unique constraints
-- Engine: PostgreSQL 14+ (Amazon RDS PostgreSQL compatible)
-- Safety: Non-destructive, idempotent DDL (IF NOT EXISTS), zero credentials.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 0. Schema Migration Tracking Table
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- 1. Shared Utility Functions
-- ----------------------------------------------------------------------------

-- Trigger function to automatically maintain updated_at timestamps
CREATE OR REPLACE FUNCTION update_timestamp_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ----------------------------------------------------------------------------
-- 2. Table: users
-- Stores passenger, driver, and admin accounts.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(30),
    role VARCHAR(20) NOT NULL DEFAULT 'passenger',
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    avatar_url VARCHAR(500),
    rating NUMERIC(3, 2) DEFAULT 5.00,
    review_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Role and Status Integrity
    CONSTRAINT chk_users_role CHECK (role IN ('passenger', 'driver', 'admin')),
    CONSTRAINT chk_users_status CHECK (status IN ('active', 'suspended', 'deactivated')),

    -- Validation & Sanitization
    CONSTRAINT chk_users_name_len CHECK (length(trim(name)) >= 2),
    CONSTRAINT chk_users_email_norm CHECK (email = lower(trim(email))),
    CONSTRAINT chk_users_email_format CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'),
    CONSTRAINT chk_users_rating CHECK (rating >= 0 AND rating <= 5.00),
    CONSTRAINT chk_users_review_count CHECK (review_count >= 0)
);

-- Indexes for users
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email ON users (email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users (role);
CREATE INDEX IF NOT EXISTS idx_users_status ON users (status);

-- Timestamp trigger for users
DROP TRIGGER IF EXISTS trg_users_update_timestamp ON users;
CREATE TRIGGER trg_users_update_timestamp
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp_column();

-- ----------------------------------------------------------------------------
-- 3. Table: vehicles
-- Stores vehicles registered by drivers for journeys.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vehicles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    registration_number VARCHAR(30) NOT NULL,
    vehicle_type VARCHAR(20) NOT NULL,
    model VARCHAR(100) NOT NULL,
    colour VARCHAR(50),
    seating_capacity SMALLINT NOT NULL,
    image_url VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Vehicle Attributes
    CONSTRAINT chk_vehicles_type CHECK (vehicle_type IN ('sedan', 'suv', 'hatchback', 'minivan', 'van')),
    CONSTRAINT chk_vehicles_capacity CHECK (seating_capacity >= 1 AND seating_capacity <= 20),
    CONSTRAINT chk_vehicles_model_len CHECK (length(trim(model)) >= 2),
    CONSTRAINT chk_vehicles_reg_len CHECK (length(trim(registration_number)) >= 2),
    CONSTRAINT chk_vehicles_reg_norm CHECK (registration_number = upper(trim(registration_number)))
);

-- Indexes for vehicles
CREATE UNIQUE INDEX IF NOT EXISTS uq_vehicles_registration ON vehicles (registration_number);
CREATE INDEX IF NOT EXISTS idx_vehicles_driver_id ON vehicles (driver_id);

-- Timestamp trigger for vehicles
DROP TRIGGER IF EXISTS trg_vehicles_update_timestamp ON vehicles;
CREATE TRIGGER trg_vehicles_update_timestamp
    BEFORE UPDATE ON vehicles
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp_column();

-- ----------------------------------------------------------------------------
-- 4. Table: journeys
-- Scheduled ride offerings published by drivers.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS journeys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    vehicle_id UUID NOT NULL REFERENCES vehicles(id) ON DELETE RESTRICT,
    origin VARCHAR(200) NOT NULL,
    destination VARCHAR(200) NOT NULL,
    departure_date DATE NOT NULL,
    departure_time TIME NOT NULL,
    arrival_time TIME,
    total_seats SMALLINT NOT NULL,
    available_seats SMALLINT NOT NULL,
    price_per_seat NUMERIC(10, 2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    description TEXT,
    stops JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Journey Status & Capacity Constraints
    CONSTRAINT chk_journeys_status CHECK (status IN ('active', 'completed', 'cancelled')),
    CONSTRAINT chk_journeys_seats_valid CHECK (total_seats >= 1 AND total_seats <= 20),
    CONSTRAINT chk_journeys_available_seats CHECK (available_seats >= 0 AND available_seats <= total_seats),
    CONSTRAINT chk_journeys_price CHECK (price_per_seat > 0),
    CONSTRAINT chk_journeys_origin_len CHECK (length(trim(origin)) >= 2),
    CONSTRAINT chk_journeys_destination_len CHECK (length(trim(destination)) >= 2),
    CONSTRAINT chk_journeys_different_endpoints CHECK (lower(trim(origin)) <> lower(trim(destination)))
);

-- Composite search index for search rides queries: origin + destination + departure_date
CREATE INDEX IF NOT EXISTS idx_journeys_search ON journeys (lower(origin), lower(destination), departure_date, status);
CREATE INDEX IF NOT EXISTS idx_journeys_driver_id ON journeys (driver_id);
CREATE INDEX IF NOT EXISTS idx_journeys_vehicle_id ON journeys (vehicle_id);
CREATE INDEX IF NOT EXISTS idx_journeys_status ON journeys (status);
CREATE INDEX IF NOT EXISTS idx_journeys_departure ON journeys (departure_date, departure_time);

-- Timestamp trigger for journeys
DROP TRIGGER IF EXISTS trg_journeys_update_timestamp ON journeys;
CREATE TRIGGER trg_journeys_update_timestamp
    BEFORE UPDATE ON journeys
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp_column();

-- ----------------------------------------------------------------------------
-- 5. Table: bookings
-- Seat reservations made by passengers on journeys.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bookings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_reference VARCHAR(20) NOT NULL,
    journey_id UUID NOT NULL REFERENCES journeys(id) ON DELETE RESTRICT,
    passenger_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    seats_booked SMALLINT NOT NULL,
    total_price NUMERIC(10, 2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    payment_status VARCHAR(20) NOT NULL DEFAULT 'unpaid',
    pickup_location VARCHAR(255),
    dropoff_location VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Booking Integrity Constraints
    CONSTRAINT chk_bookings_status CHECK (status IN ('pending', 'confirmed', 'cancelled', 'completed')),
    CONSTRAINT chk_bookings_payment_status CHECK (payment_status IN ('unpaid', 'paid', 'refunded')),
    CONSTRAINT chk_bookings_seats CHECK (seats_booked >= 1 AND seats_booked <= 10),
    CONSTRAINT chk_bookings_total_price CHECK (total_price >= 0),
    CONSTRAINT chk_bookings_ref_len CHECK (length(trim(booking_reference)) >= 6),
    CONSTRAINT chk_bookings_ref_norm CHECK (booking_reference = upper(trim(booking_reference)))
);

-- Indexes for bookings
CREATE UNIQUE INDEX IF NOT EXISTS uq_bookings_reference ON bookings (booking_reference);
CREATE INDEX IF NOT EXISTS idx_bookings_journey_id ON bookings (journey_id);
CREATE INDEX IF NOT EXISTS idx_bookings_passenger_id ON bookings (passenger_id);
CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings (status);

-- Prevent duplicate active bookings for the same passenger on the same journey:
-- Allows a passenger to re-book if their prior booking was cancelled.
CREATE UNIQUE INDEX IF NOT EXISTS uq_bookings_active_passenger 
ON bookings (journey_id, passenger_id) 
WHERE status NOT IN ('cancelled');

-- Timestamp trigger for bookings
DROP TRIGGER IF EXISTS trg_bookings_update_timestamp ON bookings;
CREATE TRIGGER trg_bookings_update_timestamp
    BEFORE UPDATE ON bookings
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp_column();

-- Function & Trigger: Prevent drivers from booking their own journey
CREATE OR REPLACE FUNCTION check_booking_passenger_not_driver()
RETURNS TRIGGER AS $$
DECLARE
    journey_driver_id UUID;
BEGIN
    SELECT driver_id INTO journey_driver_id
    FROM journeys
    WHERE id = NEW.journey_id;

    IF journey_driver_id = NEW.passenger_id THEN
        RAISE EXCEPTION 'Driver cannot book seats on their own journey (passenger_id equals journey driver_id)';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_bookings_prevent_self_booking ON bookings;
CREATE TRIGGER trg_bookings_prevent_self_booking
    BEFORE INSERT OR UPDATE ON bookings
    FOR EACH ROW
    EXECUTE FUNCTION check_booking_passenger_not_driver();

-- ----------------------------------------------------------------------------
-- 6. Table: reviews
-- Rating and feedback submitted by passengers after journey completion.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID NOT NULL REFERENCES bookings(id) ON DELETE RESTRICT,
    journey_id UUID NOT NULL REFERENCES journeys(id) ON DELETE RESTRICT,
    reviewer_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    reviewed_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    rating SMALLINT NOT NULL,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT chk_reviews_rating CHECK (rating >= 1 AND rating <= 5),
    CONSTRAINT chk_reviews_comment_len CHECK (comment IS NULL OR length(trim(comment)) <= 1000),
    CONSTRAINT chk_reviews_no_self_review CHECK (reviewer_id <> reviewed_user_id)
);

-- Exactly one review allowed per booking
CREATE UNIQUE INDEX IF NOT EXISTS uq_reviews_booking_id ON reviews (booking_id);
CREATE INDEX IF NOT EXISTS idx_reviews_reviewed_user ON reviews (reviewed_user_id);
CREATE INDEX IF NOT EXISTS idx_reviews_reviewer ON reviews (reviewer_id);
CREATE INDEX IF NOT EXISTS idx_reviews_journey_id ON reviews (journey_id);

-- Function & Trigger: Validate review eligibility before creation
CREATE OR REPLACE FUNCTION check_review_eligibility()
RETURNS TRIGGER AS $$
DECLARE
    booking_rec RECORD;
BEGIN
    -- Verify booking exists, check status and participants
    SELECT b.status, b.passenger_id, b.journey_id, j.driver_id
    INTO booking_rec
    FROM bookings b
    JOIN journeys j ON j.id = b.journey_id
    WHERE b.id = NEW.booking_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Referenced booking does not exist';
    END IF;

    -- Only completed bookings can be reviewed
    IF booking_rec.status <> 'completed' THEN
        RAISE EXCEPTION 'Reviews can only be submitted for completed bookings (current status: %)', booking_rec.status;
    END IF;

    -- Verify reviewer is the passenger who made the booking
    IF NEW.reviewer_id <> booking_rec.passenger_id THEN
        RAISE EXCEPTION 'Reviewer must be the passenger associated with the booking';
    END IF;

    -- Verify reviewed user is the driver of the journey
    IF NEW.reviewed_user_id <> booking_rec.driver_id THEN
        RAISE EXCEPTION 'Reviewed user must be the driver of the booked journey';
    END IF;

    -- Verify journey_id matches the booking's journey
    IF NEW.journey_id <> booking_rec.journey_id THEN
        RAISE EXCEPTION 'Review journey_id does not match the booking journey';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_reviews_check_eligibility ON reviews;
CREATE TRIGGER trg_reviews_check_eligibility
    BEFORE INSERT OR UPDATE ON reviews
    FOR EACH ROW
    EXECUTE FUNCTION check_review_eligibility();

-- Function & Trigger: Recalculate driver average rating upon new review
CREATE OR REPLACE FUNCTION recalculate_user_rating()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE users
    SET rating = COALESCE(
            (SELECT round(avg(rating)::numeric, 2) FROM reviews WHERE reviewed_user_id = NEW.reviewed_user_id),
            5.00
        ),
        review_count = (SELECT count(*) FROM reviews WHERE reviewed_user_id = NEW.reviewed_user_id)
    WHERE id = NEW.reviewed_user_id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_reviews_recalculate_rating ON reviews;
CREATE TRIGGER trg_reviews_recalculate_rating
    AFTER INSERT OR UPDATE ON reviews
    FOR EACH ROW
    EXECUTE FUNCTION recalculate_user_rating();

-- ----------------------------------------------------------------------------
-- 7. Record Migration Version
-- ----------------------------------------------------------------------------
INSERT INTO schema_migrations (version, name)
VALUES ('001', 'initial_schema')
ON CONFLICT (version) DO NOTHING;
