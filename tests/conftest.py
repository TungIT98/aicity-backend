import pytest
import os

# Use test database config from environment or defaults
TEST_DB_CONFIG = {
    "DB_HOST": os.getenv("DB_HOST", "localhost"),
    "DB_PORT": os.getenv("DB_PORT", "5432"),
    "DB_NAME": os.getenv("DB_NAME", "aicity_test"),
    "DB_USER": os.getenv("DB_USER", "test"),
    "DB_PASSWORD": os.getenv("DB_PASSWORD", "test"),
}
