# =========================================================================
# === 호텔 예약 어시스턴트 메인 에이전트 스크립트 ===
# =========================================================================

# 필요한 라이브러리 및 모듈을 임포트합니다.
import asyncio
import os
import logging
import json
import requests
import uuid
import psycopg2
from psycopg2.extras import Json
from typing import Dict, Any

from google.generativeai import GenerativeModel, GenerationConfig
import yaml
import google.generativeai as genai

# 로깅 설정을 구성하여 콘솔에 정보를 출력합니다.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# PostgreSQL 데이터베이스 URL을 환경 변수로 설정합니다.
os.environ['GOOGLE_API_KEY'] = 'gemini-api-key'
os.environ['DATABASE_URL'] = 'db_url'


# 환경 변수에서 Gemini API 키를 가져와 설정합니다.
genai.configure(api_key=os.environ.get('GOOGLE_API_KEY'))


# =========================================================================
# === 모델 설정 (두 개의 모델 사용) ===
# =========================================================================
# 1. 도구 호출 결정을 위한 모델:
#    JSON 응답을 정확하고 빠르게 생성하기 위해 낮은 온도(0.0)를 사용합니다.
tool_model = GenerativeModel(
    'gemini-2.0-flash-001',
    generation_config=GenerationConfig(temperature=0.0)
)
# 2. 최종 대화 생성을 위한 모델:
#    자연스럽고 풍부한 대화체 응답을 생성하기 위해 더 높은 온도(0.7)를 사용합니다.
conversational_model = GenerativeModel(
    'gemini-2.0-flash-001',
    generation_config=GenerationConfig(temperature=0.7)
)

# 툴 정의를 가져와서 프롬프트에 포함시킵니다.
with open("tools.yaml", 'r', encoding='utf-8') as f:
    tool_definitions = yaml.safe_load(f)

tool_descriptions = ""
for tool_name, tool_def in tool_definitions.items():
    if tool_name == 'toolsets':
        continue
    tool_descriptions += f"""
### Tool: {tool_name}
- Description: {tool_def['description']}
- Parameters (JSON Schema):
```json
{json.dumps(tool_def['request_schema'], indent=2)}
```
"""

# =========================================================================
# === 세션 및 API 서비스 클래스 ===
# =========================================================================
class RelationalSessionService:
    """
    PostgreSQL 데이터베이스에 채팅 세션을 저장하고 관리하는 클래스입니다.
    """
    def __init__(self, db_url: str):
        self.db_url = db_url
        self._ensure_table_exists()

    def _get_conn(self):
        """데이터베이스 연결을 생성하고 반환합니다."""
        return psycopg2.connect(self.db_url)

    def _ensure_table_exists(self):
        """sessions 테이블이 존재하지 않으면 생성합니다."""
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
            logging.error(f"Database connection failed: {e}")
            conn.rollback()
        finally:
            conn.close()

    async def create_session(self, state: dict, app_name: str, user_id: str):
        """데이터베이스에 새로운 세션을 생성합니다."""
        session_id = str(uuid.uuid4())
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO sessions (id, app_name, user_id, state) VALUES (%s, %s, %s, %s);",
                    (session_id, app_name, user_id, Json(state))
                )
                conn.commit()
            return {'id': session_id, 'app_name': app_name, 'user_id': user_id, 'state': state}
        except Exception as e:
            logging.error(f"Error creating session: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    async def get_session(self, user_id: str):
        """`user_id`를 기준으로 기존 세션을 데이터베이스에서 조회합니다."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id, app_name, user_id, state FROM sessions WHERE user_id = %s;", (user_id,))
                row = cur.fetchone()
                if not row:
                    raise FileNotFoundError(f"Session for user '{user_id}' not found.")
                
                session_id, app_name, user_id, state = row
                return {'id': session_id, 'app_name': app_name, 'user_id': user_id, 'state': state}
        except Exception as e:
            logging.error(f"Error getting session: {e}")
            raise
        finally:
            conn.close()

    async def update_session_state(self, user_id: str, state: dict) -> None:
        """`user_id`를 기준으로 세션 상태를 업데이트합니다."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE sessions SET state = %s, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s;",
                    (Json(state), user_id)
                )
                conn.commit()
        except Exception as e:
            logging.error(f"Error updating session state: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

def call_tool(tool_name: str, params: Dict[str, Any]):
    """
    FastAPI 서버의 도구 함수를 호출합니다.
    """
    url = f"http://127.0.0.1:8000/{tool_name}" # 수정된 부분: .replace('-', '_') 제거

    http_method = "GET"
    if "book" in tool_name or "cancel" in tool_name or "update" in tool_name:
        http_method = "POST"

    try:
        if http_method == "GET":
            response = requests.get(url, params=params)
        else:
            response = requests.post(url, json=params)

        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"API 호출 실패: {e}"}

# =========================================================================
# === 메인 실행 로직 (2-모델 방식) ===
# =========================================================================
async def main():
    """
    호텔 에이전트의 메인 실행 루프입니다.
    사용자 입력을 받고, 도구를 호출하거나 대화를 생성합니다.
    """
    try:
        # 데이터베이스 세션 서비스를 초기화합니다.
        session_service = RelationalSessionService(os.environ['DATABASE_URL'])
        user_id = input("사용자 ID를 입력하세요: ")

        print("안녕하세요, 호텔 예약 어시스턴트입니다. 도움을 원하시면 언제든지 말씀해주세요. (종료하려면 '종료' 또는 'exit' 입력)")

        try:
            # 기존 세션 로드 시도
            current_session_data = await session_service.get_session(user_id)
            history = current_session_data['state'].get('history', [])
            logging.info(f"기존 세션 로드 완료. 세션 ID: {current_session_data['id']}")
        except FileNotFoundError:
            # 기존 세션이 없으면 새로 생성
            current_session_data = await session_service.create_session(
                state={'history': []},
                app_name='hotel_agent',
                user_id=user_id
            )
            history = []
            logging.info(f"새로운 세션 생성 완료. 세션 ID: {current_session_data['id']}")

        # 메인 대화 루프
        while True:
            query = input(f"\n[{user_id}]: ")
            if query.lower() in ['종료', 'exit']:
                print("[AGENT]: 감사합니다. 다음에 또 만나요!")
                break

            # 1단계: tool_model을 사용해 도구 호출을 결정합니다.
            tool_prompt = f"""
            Based on the user's intent, decide if a tool needs to be called.
            If a tool is needed, respond with a single JSON object.
            If no tool is needed, respond with a JSON object with "tool": "none".
            
            ## Available Tools
            {tool_descriptions}
            
            ## Instructions
            - Respond ONLY with a single JSON object.
            - The JSON object MUST contain "tool" and "parameters" keys.
            - "tool" must be a valid tool name or "none".
            - The "parameters" key must be a JSON object containing the parameters for the tool.
            
            ## User Request
            {query}
            """
            
            tool_call = {"tool": "none"}
            try:
                tool_response = tool_model.generate_content(tool_prompt)
                tool_call_text = tool_response.text.strip().strip('`').strip('json').strip()
                tool_call = json.loads(tool_call_text)
            except Exception as e:
                logging.error(f"도구 모델 오류: {e}")
                tool_call = {"tool": "none"}

            final_response_text = ""
            if tool_call['tool'] != "none":
                # 도구 호출이 필요한 경우
                tool_name = tool_call['tool']
                params = tool_call.get('parameters', {})
                params['user_id'] = user_id
                
                # 도구 호출 JSON을 출력합니다.
                print(f"[AGENT]: ```json\n{json.dumps(tool_call, indent=2)}\n```")
                
                logging.info(f"✅ 도구 호출 감지: {tool_name} with params {params}")
                
                # 도구를 실행하고 결과를 받습니다.
                tool_result = call_tool(tool_name, params)
                logging.info(f"✅ 도구 실행 성공: {tool_result}")

                # 2단계: conversational_model을 사용해 최종 답변을 생성합니다.
                final_prompt = f"""
                Based on the user's last request and the following tool result, provide a final, conversational response.
                The response must be in natural language, not JSON. Do not include any tool-related details.
                
                ## User's Last Request
                {query}
                
                ## Tool Result
                - Tool Name: {tool_name}
                - Result:
                ```json
                {json.dumps(tool_result, indent=2)}
                ```
                """
                
                final_response = conversational_model.generate_content(final_prompt)
                final_response_text = final_response.text.strip()
                
            else:
                # 도구 호출이 필요 없는 경우, 일반 대화를 생성합니다.
                final_response = conversational_model.generate_content(query)
                final_response_text = final_response.text.strip()
            
            # 최종 응답을 출력하고 대화 기록을 업데이트합니다.
            if final_response_text:
                print(f"[AGENT]: {final_response_text}")
                history.append({'role': 'user', 'text': query})
                history.append({'role': 'model', 'text': final_response_text})
            
            await session_service.update_session_state(user_id, {'history': history})

    except Exception as e:
        logging.error(f"메인 함수 실행 중 예상치 못한 오류가 발생했습니다: {e}")
        
if __name__ == "__main__":
    asyncio.run(main())
