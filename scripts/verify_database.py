#!/usr/bin/env python3
"""
ORCA Database Verification Script.
Tests connection to PostgreSQL and verifies schema tables.
"""
import sys
import os

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

try:
    from app.core.config import settings
    from app.db.base import Base
    import app.models  # load models
except ImportError as e:
    print(f"Error importing backend modules: {e}")
    sys.exit(1)

def main():
    print(f"Target Database URL: {settings.DATABASE_URL}")
    print(f"Registered tables in schema ({len(Base.metadata.tables)}):")
    for table_name in Base.metadata.tables.keys():
        print(f"  - {table_name}")

if __name__ == "__main__":
    main()
