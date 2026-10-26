import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is missing.")
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

def init_db():
    """Initializes schema for leads and transactions."""
    query_leads = """
    CREATE TABLE IF NOT EXISTS leads (
        id SERIAL PRIMARY KEY,
        vertical TEXT NOT NULL,
        company_name TEXT NOT NULL,
        location TEXT NOT NULL,
        contact_email TEXT NOT NULL,
        pain_point TEXT NOT NULL,
        ai_pitch TEXT NOT NULL,
        status TEXT DEFAULT 'New',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    query_transactions = """
    CREATE TABLE IF NOT EXISTS transactions (
        id SERIAL PRIMARY KEY,
        reference TEXT UNIQUE NOT NULL,
        customer_email TEXT,
        amount NUMERIC,
        access_tier TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(query_leads)
    cur.execute(query_transactions)
    conn.commit()
    cur.close()
    conn.close()
