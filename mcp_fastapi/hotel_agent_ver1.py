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

# Gemini API 키를 환경 변수 또는 직접 설정합니다.
# PostgreSQL 데이터베이스 URL을 환경 변수로 설정합니다.
os.environ['GOOGLE_API_KEY'] = 'gemini-api-key'
os.environ['DATABASE_URL'] = 'database_url'


# 실제 배포 시에는 환경 변수를 사용하는 것이 보안에 좋습니다.
genai.configure(api_key=os.environ.get('GOOGLE_API_KEY'))
genai.configure(api_key=os.environ.get('DATABASE_URL'))


# =========================================================================
# === 데이터베이스 세션 관리 클래스 ===
# =========================================================================
class RelationalSessionService:
    """
    PostgreSQL 데이터베이스에 채팅 세션을 저장하고 관리하는 클래스입니다.
    `_get_conn`을 통해 데이터베이스 연결을 관리하고,
    `_ensure_table_exists`를 통해 sessions 테이블의 존재를 확인합니다.
    """
    def __init__(self, db_url: str):
        self.db_url = db_url
        self._ensure_table_exists()

    def _get_conn(self):
        """데이터베이스 연결을 생성하고 반환합니다."""
        return psycopg2.connect(self.db_url)

    def _ensure_table_exists(self):
        """
        `sessions` 테이블이 존재하지 않으면 생성합니다.
        `user_id`를 기준으로 인덱스를 생성하여 검색 성능을 향상시킵니다.
        """
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

# =========================================================================
# === 도구 호출 로직 ===
# =========================================================================
def call_tool(tool_name: str, params: Dict[str, Any]):
    """
    FastAPI 서버의 도구 함수를 호출합니다.
    URL을 구성하고 HTTP 요청을 보냅니다.
    """
    url = f"http://127.0.0.1:8000/{tool_name.replace('-', '_')}"
    
    http_method = "GET"
    if "book" in tool_name or "cancel" in tool_name or "update" in tool_name:
        http_method = "POST"

    try:
        if http_method == "GET":
            response = requests.get(url, params=params)
        else:
            response = requests.post(url, json=params)

        # HTTP 오류가 발생하면 예외를 발생시킵니다.
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"API 호출 실패: {e}"}

# =========================================================================
# === 모델 설정 및 프롬프트 엔지니어링 ===
# =========================================================================
# `tools.yaml` 파일에서 도구 정의를 로드합니다.
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

# Gemini 모델을 초기화합니다.
model = GenerativeModel(
    'gemini-2.0-flash-001',
    generation_config=GenerationConfig(temperature=0.1)
)

# =========================================================================
# === 메인 실행 로직 ===
# =========================================================================
async def main():
    """
    호텔 에이전트의 메인 실행 루프입니다.
    사용자 입력을 받고, 모델과 상호작용하며, 도구를 호출하고,
    대화 기록을 데이터베이스에 저장합니다.
    """
    try:
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
        
        # 데이터베이스의 기록을 모델이 이해할 수 있는 형식으로 변환합니다.
        formatted_history = []
        for turn in history:
            formatted_history.append({
                'role': turn['role'],
                'parts': [{'text': turn['text']}]
            })
            
        # ChatSession을 초기화하고 기록을 제공합니다.
        chat = model.start_chat(history=formatted_history)

        # 시스템 프롬프트는 대화의 첫 번째 메시지로만 보냅니다.
        system_prompt = f"""
You are a helpful hotel assistant. You handle hotel searching, booking, and cancellations.
When the user searches for a hotel, mention its name, id, location, and price tier.
Always mention hotel IDs while performing any operations. This is very important for any operations.
For any bookings or cancellations, please provide the appropriate confirmation. Be sure to
update checkin or checkout dates if mentioned by the user.

Based on the user's intent, you can decide to respond directly or call a tool.

## Available Tools
{tool_descriptions}

## Instructions
- To respond directly, provide your answer.
- To call a tool, you must respond with a single JSON object. The JSON object MUST contain "tool" and "parameters" keys.
- The "tool" key must be the name of the tool to be called (e.g., "search-hotels-by-name").
- The "parameters" key must be a JSON object containing the parameters for the tool.
- DO NOT include any other text besides the JSON object if you decide to call a tool.

## Example (Tool Call)
User: 서울에 있는 호텔을 찾아줘
Response:
```json
{{
  "tool": "search-hotels-by-location",
  "parameters": {{
    "location": "서울",
    "user_id": "{user_id}"
  }}
}}
```
"""
        if not formatted_history:
            chat.send_message(system_prompt)

        # 메인 대화 루프
        while True:
            query = input(f"\n[{user_id}]: ")
            if query.lower() in ['종료', 'exit']:
                print("[AGENT]: 감사합니다. 다음에 또 만나요!")
                break

            try:
                # 1단계: 사용자 입력에 대한 모델의 첫 번째 응답을 받습니다.
                response = chat.send_message(query)
                model_text = response.text.strip()
                
                final_response_text = ""

                try:
                    # 모델 응답이 JSON(도구 호출)인지 확인하고, JSON이라면 출력합니다.
                    tool_call = json.loads(model_text)
                    tool_name = tool_call.get('tool')
                    params = tool_call.get('parameters', {})
                    
                    if tool_name:
                        # 사용자 요청에 따라 도구 호출 JSON을 출력합니다.
                        print(f"[AGENT]: ```json\n{json.dumps(tool_call, indent=2)}\n```")
                        
                        logging.info(f"✅ 도구 호출 감지: {tool_name} with params {params}")
                        
                        # 2단계: 도구를 실행합니다.
                        tool_result = call_tool(tool_name, params)
                        logging.info(f"✅ 도구 실행 성공: {tool_result}")

                        # 3단계: 도구 실행 결과와 함께 최종 응답을 요청합니다.
                        tool_result_content = json.dumps(tool_result, ensure_ascii=False)
                        
                        # 모델에게 도구 결과를 바탕으로 자연어 답변을 생성하도록 명시적으로 지시합니다.
                        final_prompt = f"The previous tool call to '{tool_name}' returned the following result:\n{tool_result_content}\n\nBased on this result, please provide a clear and conversational final response to the user's query. Do not output any JSON or code blocks."
                        
                        final_response = chat.send_message(final_prompt)
                        final_response_text = final_response.text.strip()
                    else:
                        final_response_text = model_text

                except (json.JSONDecodeError, KeyError):
                    # 모델 응답이 JSON이 아닐 경우 (일반 대화인 경우)
                    final_response_text = model_text
                
                if final_response_text:
                    print(f"[AGENT]: {final_response_text}")
                
            except Exception as e:
                logging.error(f"예상치 못한 오류가 발생했습니다: {e}")
                print("[AGENT]: 죄송합니다. 처리 중 오류가 발생했습니다. 다시 시도해주세요.")
            
            # 대화 기록을 데이터베이스에 저장합니다.
            db_history = []
            for turn in chat.history:
                if turn.role in ['user', 'model'] and turn.parts:
                    text_part = [part.text for part in turn.parts if hasattr(part, 'text')]
                    if text_part:
                        db_history.append({'role': turn.role, 'text': text_part[0]})
            await session_service.update_session_state(user_id, {'history': db_history})

    except Exception as e:
        logging.error(f"메인 함수 실행 중 예상치 못한 오류가 발생했습니다: {e}")
        
if __name__ == "__main__":
    asyncio.run(main())
