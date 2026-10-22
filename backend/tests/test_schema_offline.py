#!/usr/bin/env python3
"""
Offline Schema and Migration Test Suite for RentASeat
Validates schema definition, relationships, constraints, and safety
without requiring a live database connection or AWS credentials.
"""

import re
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = BACKEND_DIR / "migrations"


class TestSchemaOffline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.up_file = MIGRATIONS_DIR / "001_initial_schema.sql"
        cls.down_file = MIGRATIONS_DIR / "001_initial_schema.down.sql"
        cls.up2_file = MIGRATIONS_DIR / "002_journey_vehicle_constraints.sql"
        cls.down2_file = MIGRATIONS_DIR / "002_journey_vehicle_constraints.down.sql"

        cls.assertTrue(cls.up_file.exists(), f"Missing up migration: {cls.up_file}")
        cls.assertTrue(cls.down_file.exists(), f"Missing down migration: {cls.down_file}")
        cls.assertTrue(cls.up2_file.exists(), f"Missing up migration 002: {cls.up2_file}")
        cls.assertTrue(cls.down2_file.exists(), f"Missing down migration 002: {cls.down2_file}")

        cls.up_sql = cls.up_file.read_text(encoding="utf-8")
        cls.down_sql = cls.down_file.read_text(encoding="utf-8")
        cls.up2_sql = cls.up2_file.read_text(encoding="utf-8")
        cls.down2_sql = cls.down2_file.read_text(encoding="utf-8")

    def test_no_secrets_or_credentials(self):
        """Ensure no secrets, passwords, or AWS access keys exist in migrations."""
        secret_patterns = [
            r"password\s*=\s*['\"][^'\"]+['\"]",
            r"AKIA[0-9A-Z]{16}",
            r"aws_secret_access_key",
            r"bearer\s+[a-zA-Z0-9_\-\.]+",
        ]
        for pattern in secret_patterns:
            self.assertIsNone(
                re.search(pattern, self.up_sql, re.IGNORECASE),
                f"Potential secret found in up migration matching {pattern}",
            )
            self.assertIsNone(
                re.search(pattern, self.down_sql, re.IGNORECASE),
                f"Potential secret found in down migration matching {pattern}",
            )

    def test_non_destructive_up_migration(self):
        """Forward migration must not contain DROP TABLE or DROP DATABASE."""
        self.assertIsNone(
            re.search(r"\bDROP\s+TABLE\b", self.up_sql, re.IGNORECASE),
            "Forward migration must not drop tables.",
        )
        self.assertIsNone(
            re.search(r"\bDROP\s+DATABASE\b", self.up_sql, re.IGNORECASE),
            "Forward migration must not drop databases.",
        )

    def test_all_expected_tables_defined(self):
        """Verify that all core domain tables are defined in the schema."""
        expected_tables = [
            "schema_migrations",
            "users",
            "vehicles",
            "journeys",
            "bookings",
            "reviews",
        ]
        for table in expected_tables:
            pattern = rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{table}\b"
            self.assertIsNotNone(
                re.search(pattern, self.up_sql, re.IGNORECASE),
                f"Table '{table}' definition not found in up migration.",
            )

    def test_user_table_columns_and_constraints(self):
        """Verify users table structure."""
        user_cols = [
            r"\bid\s+UUID\b",
            r"\bemail\s+VARCHAR\(255\)\s+NOT\s+NULL\b",
            r"\bpassword_hash\s+VARCHAR\(255\)\s+NOT\s+NULL\b",
            r"\bname\s+VARCHAR\(100\)\s+NOT\s+NULL\b",
            r"\brole\s+VARCHAR\(20\)\s+NOT\s+NULL\b",
            r"\bstatus\s+VARCHAR\(20\)\s+NOT\s+NULL\b",
            r"\bcreated_at\s+TIMESTAMPTZ\b",
            r"\bupdated_at\s+TIMESTAMPTZ\b",
        ]
        for col in user_cols:
            self.assertIsNotNone(
                re.search(col, self.up_sql, re.IGNORECASE),
                f"User column matching pattern {col} not found.",
            )

        # Check role constraint allows passenger, driver, admin
        self.assertIn("chk_users_role", self.up_sql)
        self.assertIn("'passenger'", self.up_sql)
        self.assertIn("'driver'", self.up_sql)
        self.assertIn("'admin'", self.up_sql)

        # Check email normalization constraint
        self.assertIn("chk_users_email_norm", self.up_sql)

    def test_vehicles_table_columns_and_foreign_keys(self):
        """Verify vehicles table foreign key to users."""
        self.assertRegex(
            self.up_sql,
            r"driver_id\s+UUID\s+NOT\s+NULL\s+REFERENCES\s+users\(id\)",
        )
        self.assertIn("chk_vehicles_type", self.up_sql)
        self.assertIn("seating_capacity", self.up_sql)

    def test_journeys_table_columns_and_foreign_keys(self):
        """Verify journeys table foreign keys and seat constraints."""
        self.assertRegex(
            self.up_sql,
            r"driver_id\s+UUID\s+NOT\s+NULL\s+REFERENCES\s+users\(id\)",
        )
        self.assertRegex(
            self.up_sql,
            r"vehicle_id\s+UUID\s+NOT\s+NULL\s+REFERENCES\s+vehicles\(id\)",
        )
        self.assertIn("chk_journeys_available_seats", self.up_sql)
        self.assertIn("chk_journeys_different_endpoints", self.up_sql)
        self.assertIn("price_per_seat", self.up_sql)

    def test_bookings_table_integrity_and_anti_duplicate_index(self):
        """Verify bookings table foreign keys and duplicate prevention."""
        self.assertRegex(
            self.up_sql,
            r"journey_id\s+UUID\s+NOT\s+NULL\s+REFERENCES\s+journeys\(id\)",
        )
        self.assertRegex(
            self.up_sql,
            r"passenger_id\s+UUID\s+NOT\s+NULL\s+REFERENCES\s+users\(id\)",
        )
        self.assertIn("chk_bookings_seats", self.up_sql)
        self.assertIn("uq_bookings_active_passenger", self.up_sql)

    def test_reviews_table_constraints(self):
        """Verify reviews table references and constraints."""
        self.assertRegex(
            self.up_sql,
            r"booking_id\s+UUID\s+NOT\s+NULL\s+REFERENCES\s+bookings\(id\)",
        )
        self.assertIn("chk_reviews_no_self_review", self.up_sql)
        self.assertIn("uq_reviews_booking_id", self.up_sql)

    def test_business_invariant_triggers_present(self):
        """Verify trigger functions enforce business rules."""
        functions = [
            "update_timestamp_column",
            "check_booking_passenger_not_driver",
            "check_review_eligibility",
            "recalculate_user_rating",
        ]
        for fn in functions:
            self.assertIn(fn, self.up_sql, f"Function {fn} missing from up migration.")

    def test_down_migration_structure(self):
        """Verify down migration drops tables in reverse dependency order."""
        table_order = ["reviews", "bookings", "journeys", "vehicles", "users"]
        last_pos = -1
        for table in table_order:
            match = re.search(rf"\bDROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?{table}\b", self.down_sql, re.IGNORECASE)
            self.assertIsNotNone(match, f"Drop table '{table}' missing from down migration.")
            self.assertGreater(
                match.start(),
                last_pos,
                f"Drop table '{table}' appears in incorrect order in down migration.",
            )
            last_pos = match.start()

    def test_migration_002_vehicle_driver_integrity(self):
        """Verify migration 002 checks vehicle ownership and journey capacity."""
        self.assertIn("check_journey_vehicle_integrity", self.up2_sql)
        self.assertIn("trg_journeys_verify_vehicle_owner", self.up2_sql)
        self.assertIn("schema_migrations", self.up2_sql)
        self.assertIn("'002'", self.up2_sql)

        # Check no DROP TABLE in migration 002 up
        self.assertIsNone(re.search(r"\bDROP\s+TABLE\b", self.up2_sql, re.IGNORECASE))

        # Check down migration drops the trigger and function
        self.assertIn("DROP TRIGGER", self.down2_sql)
        self.assertIn("DROP FUNCTION", self.down2_sql)
        self.assertIn("DELETE FROM schema_migrations WHERE version = '002'", self.down2_sql)

    def test_parentheses_balance(self):
        """Ensure clean SQL without unbalanced parentheses."""
        for sql in [self.up_sql, self.down_sql, self.up2_sql, self.down2_sql]:
            clean = re.sub(r"--.*$", "", sql, flags=re.MULTILINE)
            self.assertEqual(clean.count("("), clean.count(")"))


if __name__ == "__main__":
    unittest.main()
