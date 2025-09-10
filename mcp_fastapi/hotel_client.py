#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import requests
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

BASE_URL = "http://127.0.0.1:8000"

def test_search_hotels_by_name(name: str):
    logging.info(f"\n[TEST]: 호텔 이름 '{name}'으로 검색 시작...")
    url = f"{BASE_URL}/search-hotels-by-name"
    params = {"name": name}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        hotels = response.json()
        logging.info(f"[SUCCESS]: 검색 결과 ({len(hotels)}개)")
        logging.info(json.dumps(hotels, indent=2, ensure_ascii=False))
        return hotels
    except requests.exceptions.RequestException as e:
        logging.error(f"[ERROR]: 검색 요청 실패: {e}")
        return None

def test_book_hotel(hotel_id: int):
    logging.info(f"\n[TEST]: 호텔 ID {hotel_id} 예약 시작...")
    url = f"{BASE_URL}/book-hotel"
    data = {"id": hotel_id}
    try:
        response = requests.post(url, json=data)
        response.raise_for_status()
        result = response.json()
        logging.info(f"[SUCCESS]: 예약 결과 -> {result.get('message')}")
        return result
    except requests.exceptions.RequestException as e:
        logging.error(f"[ERROR]: 예약 요청 실패: {e}")
        return None

def test_cancel_hotel(hotel_id: int):
    logging.info(f"\n[TEST]: 호텔 ID {hotel_id} 예약 취소 시작...")
    url = f"{BASE_URL}/cancel-hotel"
    data = {"id": hotel_id}
    try:
        response = requests.post(url, json=data)
        response.raise_for_status()
        result = response.json()
        logging.info(f"[SUCCESS]: 취소 결과 -> {result.get('message')}")
        return result
    except requests.exceptions.RequestException as e:
        logging.error(f"[ERROR]: 취소 요청 실패: {e}")
        return None

def test_update_hotel_dates(hotel_id: int, checkin: str, checkout: str):
    logging.info(f"\n[TEST]: 호텔 ID {hotel_id} 날짜 업데이트 시작...")
    url = f"{BASE_URL}/update-hotel"
    data = {
        "id": hotel_id,
        "checkin_date": checkin,
        "checkout_date": checkout
    }
    try:
        response = requests.post(url, json=data)
        response.raise_for_status()
        result = response.json()
        logging.info(f"[SUCCESS]: 업데이트 결과 -> {result.get('message')}")
        return result
    except requests.exceptions.RequestException as e:
        logging.error(f"[ERROR]: 업데이트 요청 실패: {e}")
        return None

if __name__ == "__main__":
    hotels = test_search_hotels_by_name("Basel")
    if hotels:
        hotel_to_book_id = hotels[0]['id']
        test_book_hotel(hotel_to_book_id)
        test_cancel_hotel(hotel_to_book_id)
        test_update_hotel_dates(3, "2025-09-01", "2025-09-05")

