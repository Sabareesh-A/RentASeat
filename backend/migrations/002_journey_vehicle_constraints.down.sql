-- ============================================================================
-- RentASeat Database Migration: 002_journey_vehicle_constraints.down.sql
-- Description: Rollback script for 002_journey_vehicle_constraints.sql
-- Engine: PostgreSQL 14+ (Amazon RDS PostgreSQL compatible)
-- ============================================================================

DROP TRIGGER IF EXISTS trg_journeys_verify_vehicle_owner ON journeys;
DROP FUNCTION IF EXISTS check_journey_vehicle_integrity();

DELETE FROM schema_migrations WHERE version = '002';
