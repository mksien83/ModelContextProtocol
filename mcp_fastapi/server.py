# server.py

from fastapi import FastAPI, HTTPException
import psycopg2
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel
from typing import Optional
import os
import logging

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Hotel Agent API",
    description="API for managing hotel searches, bookings, and cancellations.",
    version="1.0.0"
)

def get_db_connection():

    try:
        DATABASE_URL = os.environ.get('DATABASE_URL')
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        logging.error(f"Database connection failed: {e}")
        raise HTTPException(status_code=500, detail="Database connection failed")

# Define Pydantic models for request bodies
class HotelID(BaseModel):
    id: int
    user_id: Optional[str] = None

class HotelBooking(BaseModel):
    id: int
    user_id: Optional[str] = None
    checkin_date: Optional[str] = None
    checkout_date: Optional[str] = None
    
# ✨ New API Endpoint: Root URL
@app.get("/")
def read_root():
    return {"message": "Welcome to the Hotel Agent API. Please use a specific endpoint."}

# The rest of the API endpoints remain unchanged.
@app.get("/list-all-tables")
def list_all_tables():
    """
    Returns a list of all user-defined tables in the database.
    """
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                AND table_type = 'BASE TABLE';
            """)
            tables = [row['table_name'] for row in cur.fetchall()]
        return {"tables": tables}
    finally:
        conn.close()

# The rest of the API endpoints remain unchanged from the previous version.
@app.get("/get-table-schema")
def get_table_schema(table_name: str):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position;
            """, (table_name,))
            schema = cur.fetchall()
            if not schema:
                raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found.")
        return schema
    finally:
        conn.close()

@app.get("/get-sample-data")
def get_sample_data(table_name: str, limit: int = 5):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"SELECT * FROM {table_name} LIMIT %s;", (limit,))
            data = cur.fetchall()
            if not data:
                raise HTTPException(status_code=404, detail=f"No data found in table '{table_name}'.")
        return data
    finally:
        conn.close()

@app.get("/search-hotels-by-name")
def search_hotels_by_name(name: str, user_id: str):
    logging.info(f"User '{user_id}' is searching for hotels named '{name}'.")
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM hotels WHERE name ILIKE %s;", ('%' + name + '%',))
            hotels = cur.fetchall()
        return hotels
    finally:
        conn.close()

@app.get("/search-hotels-by-location")
def search_hotels_by_location(location: str, user_id: str):
    logging.info(f"User '{user_id}' is searching for hotels in location '{location}'.")
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM hotels WHERE location ILIKE %s;", ('%' + location + '%',))
            hotels = cur.fetchall()
        return hotels
    finally:
        conn.close()

@app.post("/book-hotel")
def book_hotel(booking: HotelID):
    logging.info(f"User '{booking.user_id}' is booking hotel ID {booking.id}.")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE hotels SET booked = B'1' WHERE id = %s;", (booking.id,))
            conn.commit()
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Hotel not found")
        return {"status": "success", "message": f"Hotel ID {booking.id} booked successfully."}
    finally:
        conn.close()

@app.post("/cancel-hotel")
def cancel_hotel(booking: HotelID):
    logging.info(f"User '{booking.user_id}' is cancelling hotel ID {booking.id}.")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE hotels SET booked = B'0' WHERE id = %s;", (booking.id,))
            conn.commit()
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Hotel not found")
        return {"status": "success", "message": f"Hotel ID {booking.id} booking cancelled successfully."}
    finally:
        conn.close()

@app.post("/update-hotel")
def update_hotel(booking: HotelBooking):
    logging.info(f"User '{booking.user_id}' is updating dates for hotel ID {booking.id}.")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            query = "UPDATE hotels SET "
            params = []
            if booking.checkin_date:
                query += "checkin_date = %s, "
                params.append(booking.checkin_date)
            if booking.checkout_date:
                query += "checkout_date = %s, "
                params.append(booking.checkout_date)
            
            query = query.rstrip(', ')
            query += " WHERE id = %s;"
            params.append(booking.id)

            cur.execute(query, tuple(params))
            conn.commit()
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Hotel not found")

        return {"status": "success", "message": f"Hotel ID {booking.id} updated successfully."}
    finally:
        conn.close()