-- ============================================================================
-- RentASeat Database Migration: 002_journey_vehicle_constraints.sql
-- Description: Enforce vehicle-driver ownership integrity and journey capacity
-- Engine: PostgreSQL 14+ (Amazon RDS PostgreSQL compatible)
-- Safety: Non-destructive, idempotent DDL, zero credentials.
-- ============================================================================

-- Function: Validate that the vehicle assigned to a journey is owned by the driver
-- and that journey total_seats does not exceed the vehicle seating_capacity.
CREATE OR REPLACE FUNCTION check_journey_vehicle_integrity()
RETURNS TRIGGER AS $$
DECLARE
    v_driver_id UUID;
    v_capacity SMALLINT;
BEGIN
    SELECT driver_id, seating_capacity
    INTO v_driver_id, v_capacity
    FROM vehicles
    WHERE id = NEW.vehicle_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Referenced vehicle does not exist';
    END IF;

    -- Integrity Check 1: Driver must own the vehicle
    IF v_driver_id <> NEW.driver_id THEN
        RAISE EXCEPTION 'Vehicle does not belong to the journey driver (driver_id mismatch)';
    END IF;

    -- Integrity Check 2: Total seats offered cannot exceed vehicle seating capacity
    IF NEW.total_seats > v_capacity THEN
        RAISE EXCEPTION 'Journey total seats (%) cannot exceed vehicle seating capacity (%)',
            NEW.total_seats, v_capacity;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger on journeys table
DROP TRIGGER IF EXISTS trg_journeys_verify_vehicle_owner ON journeys;
CREATE TRIGGER trg_journeys_verify_vehicle_owner
    BEFORE INSERT OR UPDATE ON journeys
    FOR EACH ROW
    EXECUTE FUNCTION check_journey_vehicle_integrity();

-- Record Migration Version in schema_migrations
INSERT INTO schema_migrations (version, name)
VALUES ('002', 'journey_vehicle_constraints')
ON CONFLICT (version) DO NOTHING;
