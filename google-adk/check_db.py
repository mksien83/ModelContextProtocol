# check_db.py

import psycopg2
import sys
import os
import urllib.parse as urlparse
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def check_postgresql_connection_and_fetch_data():
    """
    PostgreSQL 데이터베이스에 연결을 시도하고 성공 여부를 반환합니다.
    """
    # 환경 변수에서 DATABASE_URL을 가져옵니다.
    # 예시: '
    DATABASE_URL = 'postgresql://toolbox_user:my-password@127.0.0.1:5432/toolbox_db'
    # DATABASE_URL = os.getenv("DATABASE_URL")

    #     kind: postgres
    # host: 127.0.0.1
    # port: 5432
    # database: toolbox_db
    # user: toolbox_user
    # password: my-password

    if not DATABASE_URL:
        logging.error("❌ 환경 변수 DATABASE_URL이 설정되지 않았습니다.")
        return False

    try:
        # urlparse를 사용하여 DATABASE_URL 파싱
        url = urlparse.urlparse(DATABASE_URL)
        dbname = url.path[1:]
        user = url.username
        password = url.password
        host = url.hostname
        port = url.port

        # PostgreSQL 데이터베이스에 연결 시도
        conn = psycopg2.connect(
            dbname=dbname,
            user=user,
            password=password,
            host=host,
            port=port
        )

        # 연결 성공 시
        logging.info("✅ PostgreSQL 데이터베이스에 성공적으로 연결되었습니다!")
        logging.info(f"데이터베이스 버전: {conn.server_version}")

        # 2. 커서(Cursor) 생성
        cur = conn.cursor()

        # 3. hotels 테이블 조회 쿼리 실행
        logging.info("🔎 'hotels' 테이블의 데이터를 조회합니다...")
        cur.execute("SELECT * FROM hotels;")
        
        # 4. 조회된 모든 행을 가져오기
        rows = cur.fetchall()

        # 5. 컬럼명 가져오기
        column_names = [desc[0] for desc in cur.description]
        logging.info("--- 조회 결과 ---")
        logging.info(f"컬럼: {column_names}")

        if not rows:
            logging.warning("⚠️ 'hotels' 테이블에 데이터가 없습니다.")
        else:
            for row in rows:
                logging.info(row)
        
        # 6. 커서와 연결 종료
        cur.close()
        conn.close()
        return True

    except psycopg2.OperationalError as e:
        logging.error(f"❌ 데이터베이스 연결에 실패했습니다: {e}")
        return False
    except psycopg2.ProgrammingError as e:
        # 테이블이 존재하지 않는 경우를 처리
        logging.error(f"❌ SQL 쿼리 오류: {e}")
        logging.error("ℹ️ 'hotels' 테이블이 존재하지 않거나, 컬럼이 일치하지 않을 수 있습니다.")
        return False
    except Exception as e:
        logging.error(f"❌ 예상치 못한 오류가 발생했습니다: {e}")
        return False
    finally:
        # 연결이 열려있다면 반드시 닫아줌
        if conn:
            conn.close()

if __name__ == "__main__":
    if check_postgresql_connection_and_fetch_data():
        sys.exit(0)
    else:
        sys.exit(1)