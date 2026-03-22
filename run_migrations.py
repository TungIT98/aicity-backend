#!/usr/bin/env python3
"""
Migration runner for AI City PostgreSQL database.
Usage: python run_migrations.py [--direction=upgrade|downgrade] [--revision=head]
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    import asyncio
    import argparse
    from alembic.config import CommandLine
    from alembic.config import Config as AlembicConfig

    parser = argparse.ArgumentParser(description="Run database migrations")
    parser.add_argument(
        "--direction",
        choices=["upgrade", "downgrade"],
        default="upgrade",
        help="Migration direction",
    )
    parser.add_argument(
        "--revision",
        default="head",
        help="Target revision (default: head)",
    )
    args = parser.parse_args()

    alembic_cfg = AlembicConfig("alembic.ini")

    if args.direction == "upgrade":
        from alembic import command
        revision = args.revision if args.revision != "head" else "head"
        command.upgrade(alembic_cfg, revision)
    else:
        from alembic import command
        command.downgrade(alembic_cfg, args.revision)
