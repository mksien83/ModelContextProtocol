# session_service.py

import psycopg2
import json
import logging
from google.adk.sessions import BaseSessionService, Session
# from google.adk.types import SessionState
import os
import uuid

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

class RelationalSessionService(BaseSessionService):
    def __init__(self, db_url: str):
        self.db_url = db_url
        self._ensure_table_exists()

    def _get_conn(self):
        return psycopg2.connect(self.db_url)

    def _ensure_table_exists(self):
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        id VARCHAR(36) PRIMARY KEY,
                        app_name TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        state JSONB,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions (user_id);
                """)
                conn.commit()
            logging.info("Sessions table checked/created successfully.")
        except Exception as e:
            logging.error(f"Error creating sessions table: {e}")
            conn.rollback()
        finally:
            conn.close()

    async def create_session(self, state: dict, app_name: str, user_id: str) -> Session:
        session_id = str(uuid.uuid4())
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO sessions (id, app_name, user_id, state) VALUES (%s, %s, %s, %s);",
                    (session_id, app_name, user_id, json.dumps(state))
                )
                conn.commit()
            return Session(id=session_id, app_name=app_name, user_id=user_id, state=state)
        except Exception as e:
            logging.error(f"Error creating session: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    async def get_session(self, session_id: str) -> Session:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id, app_name, user_id, state FROM sessions WHERE id = %s;", (session_id,))
                row = cur.fetchone()
                if not row:
                    raise FileNotFoundError(f"Session with ID '{session_id}' not found.")
                
                session_id, app_name, user_id, state_json = row
                state = json.loads(state_json)
                return Session(id=session_id, app_name=app_name, user_id=user_id, state=state)
        except Exception as e:
            logging.error(f"Error getting session: {e}")
            raise
        finally:
            conn.close()

    async def update_session_state(self, session_id: str, state: dict) -> None:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE sessions SET state = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s;",
                    (json.dumps(state), session_id)
                )
                conn.commit()
        except Exception as e:
            logging.error(f"Error updating session state: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()