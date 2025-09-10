
# 수정된 코드 (오류 처리 강화)

import sys
import os
import requests
import json
import google.generativeai as genai

# 환경 변수에서 API 키와 URL을 로드합니다.
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
PG_MCP_URL = os.getenv("PG_MCP_URL")
DATABASE_URL = os.getenv("DATABASE_URL")

if not GOOGLE_API_KEY or not PG_MCP_URL or not DATABASE_URL:
    print("Error: Required environment variables are not set.")
    sys.exit(1)

genai.configure(api_key=GOOGLE_API_KEY)


def get_gemini_response(prompt_text):
    """
    Gemini 모델을 호출하여 자연어를 SQL로 변환합니다.
    """
    try:
        model = genai.GenerativeModel("gemini-2.0-flash-001")
        response = model.generate_content(prompt_text)
        return response.text.strip()
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return None


def get_db_schema_info():
    """
    데이터베이스 스키마 정보를 가져와서 프롬프트에 활용합니다.
    """
    return """
    테이블: customers (customer_id, customer_name)
    테이블: orders (order_id, customer_id, total_sales)
    """


def main():
    if len(sys.argv) < 2:
        print("Usage: python gemini_cli.py \"Your natural language query\"")
        sys.exit(1)

    natural_language_query = sys.argv[1]

    schema_info = get_db_schema_info()
    prompt = f"""
    아래 주어진 데이터베이스 스키마 정보를 활용하여, 
    사용자의 자연어 쿼리를 정확한 SQL 쿼리로 변환해줘. 
    SQL 쿼리 외에 다른 설명은 포함하지 말고 SQL 코드만 출력해줘.

    데이터베이스 스키마:
    {schema_info}

    사용자 쿼리: "{natural_language_query}"
    """

    generated_sql = get_gemini_response(prompt)
    if not generated_sql:
        sys.exit(1)

    print(f"Generated SQL: \n{generated_sql}")

    try:
        # 데이터베이스 연결 요청
        connect_response = requests.post(
            f"{PG_MCP_URL}/connections",  # /connections 엔드포인트 사용
            json={"url": DATABASE_URL}  # data 대신 json 매개변수 사용
        )
        connect_response.raise_for_status() # HTTP 오류 발생 시 예외를 발생시킵니다.
        
        # JSON 디코딩 시도
        try:
            connect_data = connect_response.json()
            connection_id = connect_data["connectionId"]
        except json.JSONDecodeError:
            print(f"Error: Server response is not a valid JSON. Response content: {connect_response.text}")
            sys.exit(1)

        # SQL 쿼리 실행
        query_response = requests.post(
            f"{PG_MCP_URL}/pg_query",
            data=json.dumps({"connectionId": connection_id, "query": generated_sql}),
            headers={"Content-Type": "application/json"}
        )
        query_response.raise_for_status() # HTTP 오류 발생 시 예외를 발생시킵니다.

        # JSON 디코딩 시도
        try:
            query_data = query_response.json()
            print("\nQuery Results:")
            print(json.dumps(query_data, indent=2))
        except json.JSONDecodeError:
            print(f"Error: Server response is not a valid JSON. Response content: {query_response.text}")
            sys.exit(1)

    except requests.exceptions.RequestException as e:
        print(f"Error communicating with pg-mcp-server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()



# # example-clients/gemini_cli.py

# import sys
# import os
# import requests
# import json
# import google.generativeai as genai

# # 환경 변수에서 API 키와 URL을 로드합니다.
# from dotenv import load_dotenv

# load_dotenv()

# GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
# PG_MCP_URL = os.getenv("PG_MCP_URL")
# DATABASE_URL = os.getenv("DATABASE_URL")

# if not GOOGLE_API_KEY or not PG_MCP_URL or not DATABASE_URL:
#     print("Error: Required environment variables are not set.")
#     sys.exit(1)

# genai.configure(api_key=GOOGLE_API_KEY)


# def get_gemini_response(prompt_text):
#     """
#     Gemini 모델을 호출하여 자연어를 SQL로 변환합니다.
#     """
#     try:
#         model = genai.GenerativeModel("gemini-2.0-flash-001")
#         response = model.generate_content(prompt_text)
#         return response.text.strip()
#     except Exception as e:
#         print(f"Error calling Gemini API: {e}")
#         return None


# def get_db_schema_info():
#     """
#     데이터베이스 스키마 정보를 가져와서 프롬프트에 활용합니다.
#     실제 구현 시에는 pg-mcp-server의 기능을 활용해야 합니다.
#     이 예시에서는 간단하게 하드코딩된 스키마를 사용합니다.
#     """
#     return """
#     테이블: customers (customer_id, customer_name)
#     테이블: orders (order_id, customer_id, total_sales)
#     """


# def main():
#     if len(sys.argv) < 2:
#         print("Usage: python gemini_cli.py \"Your natural language query\"")
#         sys.exit(1)

#     natural_language_query = sys.argv[1]

#     # 1단계: 자연어 쿼리 + 스키마 정보를 포함한 프롬프트 생성
#     schema_info = get_db_schema_info()
#     prompt = f"""
#     아래 주어진 데이터베이스 스키마 정보를 활용하여, 
#     사용자의 자연어 쿼리를 정확한 SQL 쿼리로 변환해줘. 
#     SQL 쿼리 외에 다른 설명은 포함하지 말고 SQL 코드만 출력해줘.

#     데이터베이스 스키마:
#     {schema_info}

#     사용자 쿼리: "{natural_language_query}"
#     """

#     # 2단계: Gemini API 호출하여 SQL 쿼리 생성
#     generated_sql = get_gemini_response(prompt)
#     if not generated_sql:
#         sys.exit(1)

#     print(f"Generated SQL: \n{generated_sql}")

#     # 3단계: (선택 사항) 생성된 SQL을 pg-mcp-server에 보내서 실행
#     try:
#         # 이 부분은 pg-mcp-server의 실제 API 호출 로직을 따릅니다.
#         # 예시로 'connect'와 'pg_query' 기능을 사용하는 방식을 가정합니다.
        
#         # 1. 데이터베이스 연결 요청
#         connect_response = requests.post(
#             f"{PG_MCP_URL}/connect",
#             data=json.dumps({"connection_string": DATABASE_URL}),
#             headers={"Content-Type": "application/json"}
#         )
#         connect_data = connect_response.json()

#         connection_id = connect_data["connectionId"]
#         # 2. SQL 쿼리 실행
#         query_response = requests.post(
#             f"{PG_MCP_URL}/pg_query",
#             data=json.dumps({"connectionId": connection_id, "query": generated_sql}),
#             headers={"Content-Type": "application/json"}
#         )
#         query_data = query_response.json()
#         print("\nQuery Results:")
#         print(json.dumps(query_data, indent=2))

#     except Exception as e:
#         print(f"Error communicating with pg-mcp-server: {e}")


# if __name__ == "__main__":
#     main()