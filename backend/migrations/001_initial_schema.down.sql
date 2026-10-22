-- ============================================================================
-- RentASeat Database Migration: 001_initial_schema.down.sql
-- Description: Rollback script for 001_initial_schema.sql
-- Engine: PostgreSQL 14+ (Amazon RDS PostgreSQL compatible)
-- Usage: Local development and testing rollback ONLY.
--        DO NOT run against production or live RDS with real data.
-- ============================================================================

-- 1. Drop Triggers and Dependent Functions
DROP TRIGGER IF EXISTS trg_reviews_recalculate_rating ON reviews;
DROP TRIGGER IF EXISTS trg_reviews_check_eligibility ON reviews;
DROP TRIGGER IF EXISTS trg_bookings_prevent_self_booking ON bookings;
DROP TRIGGER IF EXISTS trg_bookings_update_timestamp ON bookings;
DROP TRIGGER IF EXISTS trg_journeys_update_timestamp ON journeys;
DROP TRIGGER IF EXISTS trg_vehicles_update_timestamp ON vehicles;
DROP TRIGGER IF EXISTS trg_users_update_timestamp ON users;

DROP FUNCTION IF EXISTS recalculate_user_rating();
DROP FUNCTION IF EXISTS check_review_eligibility();
DROP FUNCTION IF EXISTS check_booking_passenger_not_driver();
DROP FUNCTION IF EXISTS update_timestamp_column();

-- 2. Drop Tables in Reverse Dependency Order
DROP TABLE IF EXISTS reviews;
DROP TABLE IF EXISTS bookings;
DROP TABLE IF EXISTS journeys;
DROP TABLE IF EXISTS vehicles;
DROP TABLE IF EXISTS users;

-- 3. Remove Migration Record
DELETE FROM schema_migrations WHERE version = '001';
