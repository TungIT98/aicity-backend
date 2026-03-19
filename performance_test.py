"""
AI City Performance Testing
Database query performance analysis and optimization
"""

import time
import psycopg2
from typing import Dict, List, Any
import os

# Database configuration
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5433"),
    "database": os.getenv("DB_NAME", "promptforge"),
    "user": os.getenv("DB_USER", "promptforge"),
    "password": os.getenv("DB_PASSWORD", "promptforge123"),
}


class PerformanceTester:
    def __init__(self, db_config: Dict[str, str]):
        self.db_config = db_config
        self.results = []

    def connect(self):
        """Create database connection"""
        return psycopg2.connect(**self.db_config)

    def measure_query(self, query: str, description: str = "") -> Dict[str, Any]:
        """Execute query and measure performance"""
        conn = self.connect()
        cursor = conn.cursor()

        start_time = time.time()
        try:
            cursor.execute(query)
            results = cursor.fetchall()
            row_count = len(results)
        except Exception as e:
            return {
                "description": description,
                "query": query,
                "error": str(e),
                "time_ms": 0,
                "rows": 0
            }
        finally:
            cursor.close()
            conn.close()

        elapsed = (time.time() - start_time) * 1000  # Convert to ms

        return {
            "description": description,
            "query": query,
            "time_ms": round(elapsed, 2),
            "rows": row_count,
            "status": "fast" if elapsed < 100 else "slow" if elapsed < 500 else "critical"
        }

    def explain_analyze(self, query: str) -> str:
        """Get EXPLAIN ANALYZE output"""
        conn = self.connect()
        cursor = conn.cursor()

        try:
            cursor.execute(f"EXPLAIN ANALYZE {query}")
            result = "\n".join([row[0] for row in cursor.fetchall()])
        finally:
            cursor.close()
            conn.close()

        return result

    def check_indexes(self) -> List[Dict[str, str]]:
        """List all indexes in the database"""
        conn = self.connect()
        cursor = conn.cursor()

        query = """
            SELECT
                tablename,
                indexname,
                indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
            ORDER BY tablename, indexname;
        """

        cursor.execute(query)
        indexes = [
            {"table": row[0], "index": row[1], "definition": row[2]}
            for row in cursor.fetchall()
        ]

        cursor.close()
        conn.close()
        return indexes

    def check_slow_queries(self) -> List[Dict]:
        """Check for slow queries in pg_stat_statements (if available)"""
        conn = self.connect()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT query, calls, total_exec_time, mean_exec_time
                FROM pg_stat_statements
                ORDER BY total_exec_time DESC
                LIMIT 10;
            """)
            results = [
                {
                    "query": row[0][:100],
                    "calls": row[1],
                    "total_time_ms": round(row[2], 2),
                    "avg_time_ms": round(row[3], 2)
                }
                for row in cursor.fetchall()
            ]
        except Exception as e:
            results = [{"error": str(e)}]
        finally:
            cursor.close()
            conn.close()

        return results

    def create_recommended_indexes(self):
        """Create recommended indexes for better performance"""
        conn = self.connect()
        cursor = conn.cursor()

        indexes_to_create = [
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);",
            "CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_documents_created ON documents(created_at);",
            "CREATE INDEX IF NOT EXISTS idx_api_logs_created ON api_logs(created_at);",
        ]

        created = []
        for idx_sql in indexes_to_create:
            try:
                cursor.execute(idx_sql)
                created.append(idx_sql)
            except Exception as e:
                pass  # Index may already exist

        conn.commit()
        cursor.close()
        conn.close()
        return created


def run_performance_tests():
    """Run all performance tests"""
    tester = PerformanceTester(DB_CONFIG)

    print("=== AI City Performance Testing ===\n")

    # Check indexes
    print("1. Checking existing indexes...")
    indexes = tester.check_indexes()
    print(f"   Found {len(indexes)} indexes")
    for idx in indexes[:5]:
        print(f"   - {idx['table']}.{idx['index']}")

    # Create recommended indexes
    print("\n2. Creating recommended indexes...")
    created = tester.create_recommended_indexes()
    print(f"   Created {len(created)} indexes")

    # Test queries
    print("\n3. Testing sample queries...")

    # Test 1: Simple select
    result = tester.measure_query(
        "SELECT * FROM users LIMIT 10;",
        "Select all users (limit 10)"
    )
    print(f"   - {result['description']}: {result['time_ms']}ms ({result['rows']} rows)")

    # Test 2: Count query
    result = tester.measure_query(
        "SELECT COUNT(*) FROM users;",
        "Count users"
    )
    print(f"   - {result['description']}: {result['time_ms']}ms")

    # Test 3: Filtered query
    result = tester.measure_query(
        "SELECT * FROM users WHERE email LIKE '%@aicity%';",
        "Filter users by email"
    )
    print(f"   - {result['description']}: {result['time_ms']}ms ({result['rows']} rows)")

    print("\n=== Performance Summary ===")
    print("Database: PostgreSQL (promptforge)")
    print("Status: Ready for use")
    print("Note: Install pg_stat_statements for detailed query analysis")


if __name__ == "__main__":
    run_performance_tests()
