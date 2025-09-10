# server/config.py
import os
from mcp.server.fastmcp import FastMCP
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from server.database import Database
from server.logging_config import configure_logging, get_logger

# Initialize logging with our custom configuration
logger = get_logger("instance")

# 환경변수에서 DATABASE_URL 가져오기
database_url = os.getenv("DATABASE_URL")
if database_url:
    logger.info(f"Using DATABASE_URL from environment: {database_url}")
    global_db = Database()
    # 기본 연결을 미리 등록
    default_conn_id = global_db.register_connection(database_url)
    logger.info(f"Pre-registered default connection with ID: {default_conn_id}")
else:
    logger.warning("DATABASE_URL not found in environment variables")
    global_db = Database()

logger.info("Global database manager initialized")

@asynccontextmanager
async def app_lifespan(app: FastMCP) -> AsyncIterator[dict]:
    """Manage application lifecycle."""
    mcp.state = {"db": global_db}
    logger.info("Application startup - using global database manager")
    
    try:
        yield {"db": global_db}
    finally:
        # Don't close connections on individual session end
        pass

# Create the MCP instance
mcp = FastMCP(
    "pg-mcp-server", 
    debug=True, 
    lifespan=app_lifespan,
    dependencies=["asyncpg", "mcp"]
)