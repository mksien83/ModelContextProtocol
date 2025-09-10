#!/usr/bin/env python
"""
Simple PostgreSQL connection test script
"""
import psycopg2
import os
from urllib.parse import urlparse

def test_connection():
    # Get database URL from environment or user input
    db_url = os.getenv("DATABASE_URL")
    
    if not db_url:
        print("DATABASE_URL not found in environment variables.")
        db_url = input("Enter PostgreSQL connection URL (e.g., postgresql://user:password@localhost:5432/dbname): ")
    
    try:
        print(f"Testing connection to: {db_url}")
        print("-" * 50)
        
        # Parse the URL to show connection details (without password)
        parsed = urlparse(db_url)
        print(f"Host: {parsed.hostname}")
        print(f"Port: {parsed.port}")
        print(f"Database: {parsed.path[1:] if parsed.path else 'N/A'}")
        print(f"Username: {parsed.username}")
        print("-" * 50)
        
        # Test connection
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Test basic query
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print("✅ Connection successful!")
        print(f"PostgreSQL version: {version[0]}")
        
        # Test current database info
        cursor.execute("SELECT current_database(), current_user;")
        db_info = cursor.fetchone()
        print(f"Current database: {db_info[0]}")
        print(f"Current user: {db_info[1]}")
        
        # Test table count
        cursor.execute("""
            SELECT count(*) 
            FROM information_schema.tables 
            WHERE table_schema = 'public';
        """)
        table_count = cursor.fetchone()
        print(f"Number of tables in public schema: {table_count[0]}")
        
        # List some tables if they exist
        if table_count[0] > 0:
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                LIMIT 5;
            """)
            tables = cursor.fetchall()
            print("\nFirst 5 tables:")
            for table in tables:
                print(f"  - {table[0]}")
        
        cursor.close()
        conn.close()
        print("\n✅ Connection test completed successfully!")
        
    except psycopg2.OperationalError as e:
        print(f"❌ Connection failed: {e}")
        print("\nPossible solutions:")
        print("1. Check if PostgreSQL server is running")
        print("2. Verify connection parameters (host, port, username, password)")
        print("3. Check if the database exists")
        print("4. Verify network connectivity")
        
    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    test_connection()