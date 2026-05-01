"""Database initialization script"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import init_db, drop_db
from src.config import settings

# Import all models so SQLAlchemy knows about them
from src import models  # noqa: F401


def main():
    """Initialize database"""
    print("📦 Initializing database...")
    settings.ensure_storage_paths()
    print(f"✅ Storage paths created at {settings.storage_path}")

    init_db()
    print(f"✅ Database initialized at {settings.database_url}")

    print("🎉 Database setup complete!")


if __name__ == "__main__":
    main()
