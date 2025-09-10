#!/usr/bin/env python
# example-clients/gemini-agent-cli.py
import asyncio
import argparse
import os
import json
import codecs
import sys
import dotenv
import warnings

# Suppress deprecation warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

from mcp import ClientSession
from mcp.client.sse import sse_client
from tabulate import tabulate
from pydantic_ai import Agent
from pydantic_ai.models.gemini import GeminiModel
from pydantic_ai.providers.google_gla import GoogleGLAProvider
from httpx import AsyncClient

# Load environment variables
dotenv.load_dotenv()

# Default values
DEFAULT_MCP_URL = os.getenv("PG_MCP_URL", "http://localhost:8000/sse")
DEFAULT_DB_URL = os.getenv("DATABASE_URL", "")
DEFAULT_API_KEY = os.getenv("GEMINI_API_KEY", "")

class AgentCLI:
    def __init__(self, mcp_url, db_url, api_key):
        self.mcp_url = mcp_url
        self.db_url = db_url
        self.api_key = api_key
        self.conn_id = None
        
        print("🤖 Initializing Gemini model...")
        custom_http_client = AsyncClient(timeout=30)
        model = GeminiModel(
            'gemini-2.0-flash-exp',
            provider=GoogleGLAProvider(api_key=api_key, http_client=custom_http_client),
        )
        self.agent = Agent(model)
        print("✅ Gemini model initialized")
    
    # async def initialize(self):
    #     """Initialize the session and connect to the database."""
    #     print(f"🔗 Connecting to MCP server at {self.mcp_url}...")
    #     async with sse_client(url=self.mcp_url) as streams:
    #         async with ClientSession(*streams) as self.session:
    #             await self.session.initialize()

    #                 # 서버가 연결을 초기화할 시간을 주기 위해 지연 추가 (예: 5초)
    #             print("⏳ Waiting for server to initialize connection...")
    #             await asyncio.sleep(5)
    
    #             # 하드코딩된 conn_id 사용 (서버에서 미리 등록한 것)
    #             # 서버 로그에서 "Pre-registered default connection with ID: ..."에 나온 ID를 사용
    #             self.conn_id = "f02b4541-fe64-542c-b03d-7202197426ea"  # 실제 ID로 변경
    #             print(f"✅ Using pre-registered connection ID: {self.conn_id}")
                
    #             # 기존 연결 시도 코드는 주석 처리
    #             # try:
    #             #     connect_result = await self.session.call_tool(...)
    #             # except Exception as e:
    #             #     ...
                
    #             # Main interaction loop
    #             print("\n🎯 Ready for queries! Type 'exit' to quit.")
    #             while True:
    #                 try:
    #                     await self.process_user_query()
    #                 except KeyboardInterrupt:
    #                     print("\nExiting.")
    #                     return


    async def initialize(self):
        """Initialize the session and connect to the database."""
        print(f"🔗 Connecting to MCP server at {self.mcp_url}...")

        self.conn_id = "f02b4541-fe64-542c-b03d-7202197426ea"
        
        async with sse_client(url=self.mcp_url) as streams:
            async with ClientSession(*streams) as self.session:
                await self.session.initialize()
    
                print("⏳ Attempting to establish database connection with server...")
                try:
                    # Call the pg_connect tool to register the database connection.
                    connect_result = await self.session.call_tool(
                        "pg_connect",
                        {
                            "conn_id": self.conn_id, # Use the hardcoded ID
                            "connection_string": self.db_url # Use the database URL
                        }
                    )
                    print("✅ Database connection established.")
                    # print(f"Connection result: {connect_result.content}")
    
                except Exception as e:
                    print(f"❌ Error during connection: {e}")
                    # You can add logic here to handle the error, such as exiting.
                    return
    
                # Main interaction loop
                print("\n🎯 Ready for queries! Type 'exit' to quit.")
                while True:
                    try:
                        await self.process_user_query()
                    except KeyboardInterrupt:
                        print("\nExiting.")
                        return
        
    async def process_user_query(self):
        """Process a natural language query from the user."""
        if not self.conn_id:
            print("Error: Not connected to database")
            return
            
        # Get the user's natural language query
        print("\n" + "="*60)
        user_query = input("💬 Enter your question: ")
        
        if user_query.lower() in ['exit', 'quit']:
            raise KeyboardInterrupt()
        
        try:
            print("📡 Getting database schema from MCP server...")
            # Get the prompt from server
            prompt_response = await self.session.get_prompt('generate_sql', {
                'conn_id': self.conn_id,
                'nl_query': user_query
            })
            
            # Extract messages from prompt response
            if not hasattr(prompt_response, 'messages') or not prompt_response.messages:
                print("❌ Error: Invalid prompt response from server")
                return
            
            print("🧠 Sending to Gemini for SQL generation...")
            
            # Convert MCP messages to format expected by Gemini
            messages = []
            for msg in prompt_response.messages:
                messages.append({
                    "role": msg.role,
                    "content": msg.content.text if hasattr(msg.content, 'text') else str(msg.content)
                })
            
            # Use the agent with the formatted messages
            response = await self.agent.run(str(messages))
            
            # Access the response content
            if hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)
            
            # Extract SQL from response
            sql_query = None
            
            # Look for SQL in code blocks
            if "```sql" in response_text and "```" in response_text.split("```sql", 1)[1]:
                sql_start = response_text.find("```sql") + 6
                remaining_text = response_text[sql_start:]
                sql_end = remaining_text.find("```")
                
                if sql_end > 0:
                    sql_query = remaining_text[:sql_end].strip()
            
            # If still no SQL query found, check if the whole response might be SQL
            if not sql_query and ("SELECT" in response_text or "WITH" in response_text):
                for keyword in ["WITH", "SELECT", "CREATE", "INSERT", "UPDATE", "DELETE"]:
                    if keyword in response_text:
                        keyword_pos = response_text.find(keyword)
                        sql_query = response_text[keyword_pos:].strip()
                        for end_marker in ["\n\n", "```"]:
                            if end_marker in sql_query:
                                sql_query = sql_query[:sql_query.find(end_marker)].strip()
                        break
            
            if not sql_query:
                print("\n❌ Could not extract SQL from the response.")
                print("🤖 Full AI Response:")
                print("-" * 40)
                print(response_text)
                print("-" * 40)
                return
            
            # Add trailing semicolon if missing
            sql_query = sql_query.strip()
            if not sql_query.endswith(';'):
                sql_query = sql_query + ';'
            
            # Handle escaped characters
            unescaped_sql_query = codecs.decode(sql_query, 'unicode_escape')
            
            # Display and confirm
            print("\n📝 Generated SQL query:")
            print("-" * 40)
            print(unescaped_sql_query)
            print("-" * 40)
            
            execute = input("\n❓ Execute this query? (y/n): ")
            if execute.lower() != 'y':
                return
            
            # Execute the query
            print("⚡ Executing query...")
            result = await self.session.call_tool(
                "pg_query",
                {
                    "query": unescaped_sql_query,
                    "conn_id": self.conn_id
                }
            )
            
            # Process results
            if hasattr(result, 'content') and result.content:
                query_results = []
                
                # Extract all content items and parse the JSON
                for content_item in result.content:
                    if hasattr(content_item, 'text'):
                        try:
                            # Parse each row from JSON
                            row_data = json.loads(content_item.text)
                            if isinstance(row_data, list):
                                query_results.extend(row_data)
                            else:
                                query_results.append(row_data)
                        except json.JSONDecodeError:
                            print(f"Error parsing result item: {content_item.text[:100]}")
                
                # Display the formatted results
                if query_results:
                    print("\n📊 Query Results:")
                    table = tabulate(
                        query_results,
                        headers="keys",
                        tablefmt="pretty"
                    )
                    print(table)
                    print(f"\n📈 Total rows: {len(query_results)}")
                else:
                    print("\n✅ Query executed successfully but returned no results.")
            else:
                print("✅ Query executed but no content returned")

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

async def main():
    parser = argparse.ArgumentParser(description="Natural Language to SQL CLI for PG-MCP")
    parser.add_argument("--mcp-url", default=DEFAULT_MCP_URL, help="MCP server URL")
    parser.add_argument("--db-url", default=DEFAULT_DB_URL, help="PostgreSQL connection URL")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="Gemini API key")
    
    args = parser.parse_args()
    
    if not args.api_key:
        print("❌ Error: Gemini API key is required")
        print("Set GEMINI_API_KEY in .env file or provide via --api-key argument")
        sys.exit(1)
    
    print("🚀 Starting Gemini Agent CLI for PostgreSQL")
    print(f"📍 MCP Server: {args.mcp_url}")
    
    agent = AgentCLI(args.mcp_url, args.db_url, args.api_key)
    await agent.initialize()

if __name__ == "__main__":
    asyncio.run(main())