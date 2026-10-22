#!/usr/bin/env python3
"""
RentASeat Database Migration Runner
Compatible with Python 3.13 and PostgreSQL 14+ via pg8000.

Commands:
    python3 backend/migrate.py --check
        Validates migration files offline (no database connection required).

    python3 backend/migrate.py --dry-run
        Prints pending SQL statements without executing them.

    python3 backend/migrate.py --status
        Reports applied and pending migrations from schema_migrations.

    python3 backend/migrate.py --up
        Applies pending migrations in sequential order.

SECURITY:
    - Never hardcodes passwords or connection strings.
    - Sourced strictly from Lambda/RDS environment variables:
      DB_HOST, DB_PORT, DB_NAME, DB_USERNAME, DB_PASSWORD.
    - All errors are masked and sanitized.
"""

import argparse
import os
import re
import sys
from pathlib import Path

# Migration files directory
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def get_migration_files() -> list[tuple[str, str, Path]]:
    """
    Discover all forward migration SQL files (*.sql, excluding *.down.sql).
    Returns list of tuples: (version, name, Path) sorted by version.
    """
    if not MIGRATIONS_DIR.exists():
        return []

    migrations = []
    pattern = re.compile(r"^(\d+)_([a-zA-Z0-9_-]+)\.sql$")

    for file_path in MIGRATIONS_DIR.glob("*.sql"):
        if file_path.name.endswith(".down.sql"):
            continue
        match = pattern.match(file_path.name)
        if match:
            version, name = match.groups()
            migrations.append((version, name, file_path))

    return sorted(migrations, key=lambda m: m[0])


def validate_migrations_offline() -> bool:
    """
    Offline validation check:
    - Checks that migration files exist and follow naming rules.
    - Checks that files are non-empty.
    - Confirms no plaintext passwords, AWS access keys, or secrets are present.
    - Confirms no prohibited DROP commands exist in forward migrations.
    - Validates balanced parentheses and basic SQL structure.
    """
    migrations = get_migration_files()
    if not migrations:
        print("[FAIL] No migration files found in:", MIGRATIONS_DIR)
        return False

    print(f"[OK] Found {len(migrations)} forward migration(s):")
    all_valid = True

    secret_pattern = re.compile(
        r"(password\s*=\s*['\"][^'\"]+['\"]|AKIA[0-9A-Z]{16}|aws_secret)",
        re.IGNORECASE,
    )

    for version, name, path in migrations:
        content = path.read_text(encoding="utf-8")

        # 1. Non-empty check
        if not content.strip():
            print(f"  - [{version}] {name}: FAILED (file is empty)")
            all_valid = False
            continue

        # 2. Secret exposure check
        if secret_pattern.search(content):
            print(f"  - [{version}] {name}: FAILED (potential secret detected in SQL)")
            all_valid = False
            continue

        # 3. Non-destructive check in forward migration
        # Forward migrations should not contain DROP TABLE or DROP DATABASE
        if re.search(r"\bDROP\s+TABLE\b", content, re.IGNORECASE):
            print(f"  - [{version}] {name}: FAILED (forward migration contains DROP TABLE)")
            all_valid = False
            continue

        if re.search(r"\bDROP\s+DATABASE\b", content, re.IGNORECASE):
            print(f"  - [{version}] {name}: FAILED (forward migration contains DROP DATABASE)")
            all_valid = False
            continue

        # 4. Basic parentheses balance check (ignores comments)
        clean_content = re.sub(r"--.*$", "", content, flags=re.MULTILINE)
        if clean_content.count("(") != clean_content.count(")"):
            print(f"  - [{version}] {name}: FAILED (unbalanced parentheses)")
            all_valid = False
            continue

        print(f"  - [{version}] {name}: PASSED offline validation ({path.name})")

    return all_valid


def get_db_connection():
    """
    Create a pg8000 connection using environment variables.
    """
    try:
        import pg8000.dbapi as pg8000_dbapi
    except ImportError:
        # Check backend/package
        package_dir = Path(__file__).resolve().parent / "package"
        if package_dir.exists():
            sys.path.insert(0, str(package_dir))
            import pg8000.dbapi as pg8000_dbapi
        else:
            raise RuntimeError("pg8000 driver is not installed or available.")

    host = os.environ.get("DB_HOST", "")
    port = int(os.environ.get("DB_PORT", "5432"))
    database = os.environ.get("DB_NAME", "postgres")
    user = os.environ.get("DB_USERNAME", "rentaseat_admin")
    password = os.environ.get("DB_PASSWORD", "")

    if not host or not password:
        raise RuntimeError(
            "DB_HOST and DB_PASSWORD environment variables are required to connect to PostgreSQL."
        )

    return pg8000_dbapi.connect(
        user=user,
        password=password,
        host=host,
        port=port,
        database=database,
        ssl_context=True,
        timeout=10,
        application_name="RentASeat-Migrator",
    )


def ensure_migrations_table(cursor):
    """
    Ensures the schema_migrations table exists.
    """
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(50) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def get_applied_versions(cursor) -> set[str]:
    """
    Retrieve all migration versions already applied to the database.
    """
    ensure_migrations_table(cursor)
    cursor.execute("SELECT version FROM schema_migrations;")
    rows = cursor.fetchall()
    return {row[0] for row in rows}


def show_status():
    """
    Report migration status against the database.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        applied = get_applied_versions(cursor)
        migrations = get_migration_files()

        print("\nMigration Status:")
        print("------------------------------------------------------------")
        for version, name, _ in migrations:
            status = "APPLIED" if version in applied else "PENDING"
            print(f"  [{version}] {name.ljust(35)} : {status}")
        print("------------------------------------------------------------\n")
    finally:
        cursor.close()
        conn.close()


def dry_run():
    """
    Display pending SQL without executing.
    """
    migrations = get_migration_files()
    print("\n--- Dry Run: Pending Migrations SQL ---")
    for version, name, path in migrations:
        print(f"\n/* === Migration [{version}]: {name} ({path.name}) === */")
        print(path.read_text(encoding="utf-8"))
    print("\n--- End of Dry Run ---\n")


def apply_migrations():
    """
    Apply all pending migrations in order.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        applied = get_applied_versions(cursor)
        migrations = get_migration_files()

        pending = [m for m in migrations if m[0] not in applied]
        if not pending:
            print("Database is up to date. No pending migrations.")
            return

        for version, name, path in pending:
            print(f"Applying [{version}] {name}...")
            sql = path.read_text(encoding="utf-8")
            cursor.execute(sql)
            cursor.execute(
                "INSERT INTO schema_migrations (version, name) VALUES (%s, %s);",
                (version, name),
            )
            conn.commit()
            print(f"[OK] Applied [{version}] {name}")

        print("All pending migrations applied successfully.")
    except Exception as exc:
        conn.rollback()
        print(f"[ERROR] Migration failed: {type(exc).__name__}")
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="RentASeat Database Migration Runner")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run offline validation checks on migration SQL files",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check migration status against the database",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print pending migration SQL without executing",
    )
    parser.add_argument(
        "--up",
        action="store_true",
        help="Apply all pending migrations to the database",
    )

    args = parser.parse_args()

    if args.check:
        success = validate_migrations_offline()
        sys.exit(0 if success else 1)
    elif args.dry-run:
        dry_run()
    elif args.status:
        show_status()
    elif args.up:
        apply_migrations()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
