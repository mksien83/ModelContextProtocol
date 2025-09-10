#!/usr/bin/env python
# coding: utf-8

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.genai import types
from toolbox_core import ToolboxSyncClient

import asyncio
import os
import logging
import json # You may need this for parsing JSON if you get any in the future

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# TODO(developer): replace this with your Google API key
os.environ['GOOGLE_API_KEY'] = 'your-api-key'

async def main():
    try:
        with ToolboxSyncClient("http://127.0.0.1:5000") as toolbox_client:
            prompt = """
            You're a helpful hotel assistant. You handle hotel searching, booking and
            cancellations. When the user searches for a hotel, mention its name, id,
            location and price tier. Always mention hotel ids while performing any
            searches. This is very important for any operations. For any bookings or
            cancellations, please provide the appropriate confirmation. Be sure to
            update checkin or checkout dates if mentioned by the user.
            Don't ask for confirmations from the user.
            """

            root_agent = Agent(
                model='gemini-2.0-flash-001',
                name='hotel_agent',
                description='A helpful AI assistant.',
                instruction=prompt,
                tools=toolbox_client.load_toolset("my-toolset"),
            )

            session_service = InMemorySessionService()
            artifacts_service = InMemoryArtifactService()
            session = await session_service.create_session(
                state={}, app_name='hotel_agent', user_id='123'
            )
            runner = Runner(
                app_name='hotel_agent',
                agent=root_agent,
                artifact_service=artifacts_service,
                session_service=session_service,
            )

            queries = [
                "Find hotels in Basel with Basel in its name.",
                "Can you book the Hilton Basel for me?",
                "Oh wait, this is too expensive. Please cancel it and book the Hyatt Regency instead.",
                "My check in dates would be from April 10, 2024 to April 19, 2024.",
            ]

            for query in queries:
                logging.info(f"\n[USER]: {query}")
                content = types.Content(role='user', parts=[types.Part(text=query)])
                events = runner.run(session_id=session.id, user_id='123', new_message=content)

                for event in events:
                    if hasattr(event, 'name') and event.name == 'tool_code_execution':
                        tool_call = event.tool_call
                        
                        # 데이터베이스를 변경하는 도구 호출 후 commit 실행
                        if tool_call.name in ["book-hotel", "update-hotel", "cancel-hotel"]:
                            logging.info(f"[AGENT]: Calling '{tool_call.name}' tool...")
                            
                            # **commit-transaction 도구 호출 로직**
                            # commit-transaction 도구를 호출하기 위한 메시지 이벤트 생성
                            commit_event_content = types.Content(
                                role='tool_code',
                                parts=[
                                    types.Part(
                                        tool_code=types.ToolCode(
                                            tool_name='commit-transaction',
                                            arguments={},
                                        )
                                    )
                                ]
                            )
                            # runner.run()을 다시 호출하여 commit-transaction 도구 실행
                            commit_events = runner.run(
                                session_id=session.id,
                                user_id='123',
                                new_message=commit_event_content
                            )
                            # 커밋 이벤트 로깅
                            for commit_event in commit_events:
                                if hasattr(commit_event, 'name'):
                                    logging.info(f"[COMMIT]: {commit_event.name}")
                                    if commit_event.content.parts[0].text:
                                        logging.info(f" -> {commit_event.content.parts[0].text}")
                                else:
                                    logging.warning(f"[COMMIT]: Skipping event of type {type(commit_event)}.")

                    # 모델 응답 텍스트 출력
                    responses = (
                        part.text
                        for part in event.content.parts
                        if part.text is not None
                    )

                    for text in responses:
                        print(f"[AGENT]: {text}")

    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        
asyncio.run(main())