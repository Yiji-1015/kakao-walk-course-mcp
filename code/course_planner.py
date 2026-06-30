import os
import requests
from dotenv import load_dotenv
from pydantic import BaseModel
from itertools import permutations
import heapq
from datetime import datetime, timedelta
from urllib.parse import quote

load_dotenv()
KAKAO_LOCAL_SEARCH_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"


def get_api_key():
    api_key = os.getenv("KAKAO_REST_API_KEY")
    if not api_key:
        raise RuntimeError("KAKAO_REST_API_KEY is not set")
    return api_key

# ==========================================================
# 거리 계산 및 도보 시간 계산

# 거리 구하는 함수
def dist(a, b):
    # a, b = (위도, 경도). 가까운 거리용 간단 버전, 단위 m
    lat1, lng1 = a
    lat2, lng2 = b
    dy = (lat2 - lat1) * 111000   # 위도 1도 ≈ 111km
    dx = (lng2 - lng1) * 88000    # 경도 1도 ≈ 88km (서울 위도 기준)
    return (dx**2 + dy**2) ** 0.5

# 도보 시간 계산: 직선거리(m) -> 실제 걷는 거리 보정 -> 도보 시간(분)
def walk_min(meters):
    real = meters * 1.3        # 직선거리 -> 실제 걷는 거리 보정
    return real / 67           # 도보 시간(분)


# 코스 안의 구간별 거리
def hop_distances(route):
    distances = []

    for a, b in zip(route, route[1:]):
        d = dist((a["lat"], a["lng"]), (b["lat"], b["lng"]))
        distances.append(d)

    return distances

# 총 거리
def total_walk_dist(route):
    return sum(hop_distances(route))


# 각 카테고리 당 몇 분 정도 소모하는지를 계산하기 위한 대분류 라벨링
def phase(place):
    name = place["category_name"]

    # 술집류
    if any(w in name for w in ["술집", "호프", "요리주점", "포장마차",
                               "와인바", "칵테일바", "유흥주점", "주류판매"]):
        return "술"

    # 활동: 오래 머무는 체험/관람/놀거리
    if any(w in name for w in [
        # 앉아서 오래 있는 카페형 (카페보다 먼저 걸러야 함)
        "테마카페", "고양이카페", "만화카페", "보드카페", "방탈출카페", "만화방",
        # 관람/체험
        "팝업스토어", "박물관", "전시회", "박람회", "전시관", "미술,공예", "서점",
        # 시간 많이 쓰는 놀거리
        "노래방", "게임방", "PC방",
    ]):
        return "활동"

    # 일반 카페/디저트
    if any(w in name for w in ["카페", "커피전문점", "제과,베이커리",
                               "베이커리", "디저트"]):
        return "카페"

    # 짧게 둘러보는 쇼핑/구경 -> 기타(짧은 체류)
    if any(w in name for w in [
        "뽑기방", "랜덤캡슐토이", "장난감,완구", "취미용품점",
        "액세서리", "생활용품점", "문구", "아트박스", "다이소", "올리브영", "향수",
    ]):
        return "기타"

    # 음식점
    if name.startswith("음식점"):
        return "식사"

    return "기타"

# ==========================================================
# 입력 받아서 정제

class Place(BaseModel):
    name: str
    fixed_time: str | None = None

def get_place(place, area_hint=None):
    query = place.name

    if area_hint and area_hint not in place.name:
        query = f"{area_hint} {place.name}"

    url = KAKAO_LOCAL_SEARCH_URL
    headers = {"Authorization": f"KakaoAK {get_api_key()}"}
    res = requests.get(url, headers=headers, params={"query": query})
    docs = res.json()["documents"]
    if not docs:
        return None
    p = docs[0]

    if not docs:
        return None
    return {
        "name": p["place_name"],
        "lat": float(p["y"]),
        "lng": float(p["x"]),
        "category_name": p["category_name"],
        "fixed_time": place.fixed_time,   # ← 입력에서 그대로 넘김
    }

# 장소 이름 리스트를 받아서, 코스 계산에 쓸 수 있는 장소 데이터 리스트로 바꿔주는 함수
# list[str] -> list[place_dict]
def collect(places, area_hint=None):
    result = []
    not_found = []

    for place in places:
        p = get_place(place, area_hint=area_hint)
        if p is None:
            not_found.append(place.name)
            continue

        p["phase"] = phase(p)
        result.append(p)

    return result, not_found

# ==========================================================
# 거리 기반으로 최적 경로 계산

def best_courses(places, max_count=5, top_n=5):
    # 장소가 하나도 없으면 계산할 코스가 없으므로 빈 리스트 반환
    if len(places) == 0:
        return []

    # 코스에 넣을 장소 개수
    # 예: places가 10개여도 max_count=5면 5개짜리 코스만 만듦
    count = min(len(places), max_count)

    # 거리 기준으로 좋은 후보 top_n개만 보관할 공간
    heap = []

    # heap 안에서 distance가 같은 경우 비교 오류를 피하기 위한 순번
    order = 0

    # places 중 count개를 뽑고, 그 순서까지 모두 고려한 코스를 하나씩 만든다
    # 예: A,B,C 중 2개면 (A,B), (B,A), (A,C), (C,A) ... 모두 나옴
    for course in permutations(places, count):
        # 코스 안에서 각 구간별 거리 리스트
        # 예: [식당->카페 거리, 카페->술집 거리, ...]
        hops = hop_distances(course)

        # 코스 전체 거리 = 구간별 거리의 합
        distance = sum(hops)

        # 나중에 출력하거나 스크리닝할 때 쓰기 좋게 코스 정보를 딕셔너리로 묶음
        item = {
            "course": list(course),          # 실제 장소 순서
            "distance": distance,            # 총 직선거리
            "walk_min": walk_min(distance),  # 예상 도보 시간
            "hops": hops,                    # 구간별 거리
        }

        # heapq는 기본적으로 "가장 작은 값"을 먼저 본다.
        # 우리는 top_n개 중 "가장 나쁜 후보", 즉 거리가 가장 긴 후보를 빨리 꺼내고 싶어서
        # distance에 마이너스를 붙여 저장한다.
        entry = (-distance, order, item)
        order += 1

        # 아직 후보가 top_n개보다 적으면 일단 넣는다
        if len(heap) < top_n:
            heapq.heappush(heap, entry)

        else:
            # 현재 heap 안에 있는 후보 중 가장 나쁜 후보의 거리
            # heap[0][0]은 -distance이므로 다시 마이너스를 붙여 원래 거리로 돌린다
            worst_d = -heap[0][0]

            # 새 코스가 현재 가장 나쁜 후보보다 짧으면 교체한다
            if distance < worst_d:
                heapq.heapreplace(heap, entry)

    # heap에는 entry 형태로 들어 있으므로, 그 안의 item만 꺼낸다
    results = [entry[2] for entry in heap]

    # 최종 결과는 거리 짧은 순서대로 정렬해서 보기 좋게 반환한다
    results = sorted(results, key=lambda x: x["distance"])

    return results


# ==========================================================
# Penalty 및 경로 재구성 관련

# 각 구간 당 거리가 너무 멀 경우 패널티
def has_too_long_hop(item):
    # hops가 비어 있으면, 비교할 구간이 없으므로 "너무 긴 구간 없음"으로 처리
    if not item["hops"]:
        return False

    # 구간별 거리 중 가장 긴 값이 500m를 넘으면 True
    # 즉, 이 코스는 중간에 너무 멀리 걷는 구간이 있다고 판단
    return max(item["hops"]) > 2000

def screen_courses(top_courses):
    # 최종 통과한 코스들을 담을 리스트
    passed = []

    # 거리 기준으로 뽑아둔 후보 코스를 하나씩 확인
    for item in top_courses:
        # 코스 안에 500m 넘는 구간이 있으면
        # 이 코스는 제외하고 다음 코스로 넘어감
        if has_too_long_hop(item):
            continue

        # 너무 긴 구간이 없으면 통과 리스트에 추가
        passed.append(item)

    # 통과한 코스들만 반환
    return passed

# 활동은 연속 가능
# 카페는 연속이면 어색함
# 식사는 연속이면 어색함
# 술은 식사보다 앞이면 어색함
# 술 다음 카페는 허용 가능
# 술이 꼭 마지막일 필요는 없음

def course_penalty(item, all_places):
    course = item["course"]
    phases = [p["phase"] for p in course]
    all_phases = [p["phase"] for p in all_places]

    penalty = 0

    # fixed_time이 있는 장소가 코스에 없으면 큰 패널티
    course_names = [p["name"] for p in course]
    for p in all_places:
        if p.get("fixed_time") and p["name"] not in course_names:
            penalty += 10000

    # 1. 구간이 너무 길면 소프트 패널티
    # 예: 한 구간이 500m 넘으면 탈락이 아니라 점수만 나빠짐
    for hop in item["hops"]:
        if hop > 500:
            penalty += 500

    # 2. 식사 연속 / 카페 연속은 조금 어색함
    for a, b in zip(phases, phases[1:]):
        if a == b and a in ["식사", "카페"]:
            penalty += 300

    # 3. 술이 식사보다 먼저 나오면 어색함
    if "술" in phases and "식사" in phases:
        drink_i = phases.index("술")
        meal_i = phases.index("식사")

        if drink_i < meal_i:
            penalty += 700

    # 4. 전체 후보에 식사가 있는데, 이 코스에 식사가 없으면 큰 패널티
    if "식사" in all_phases and "식사" not in phases:
        penalty += 2000

    # 5. 전체 후보에 카페가 있는데, 이 코스에 카페가 없으면 큰 패널티
    if "카페" in all_phases and "카페" not in phases:
        penalty += 2000

    if "술" in phases:
        drink_i = phases.index("술")
        after_drink = phases[drink_i + 1:]

        if "식사" in after_drink:
            penalty += 1500

        if "카페" in after_drink:
            penalty += 500

    if "기타" in all_phases and "기타" not in phases:
        penalty += 1000

    return penalty

def rank_courses(courses, all_places):
    ranked = []

    for item in courses:
        penalty = course_penalty(item, all_places)
        score = item["distance"] + penalty

        item["penalty"] = penalty
        item["score"] = score

        ranked.append(item)

    return sorted(ranked, key=lambda x: x["score"])

# ==========================================================
# phase별 머무는 시간을 고려하여 시간 고려

DWELL_MIN = {"식사": 60, "카페": 60, "술": 90, "활동": 80, "기타": 30}

def dwell_min(place):
    return DWELL_MIN.get(place["phase"], 30)

def schedule_course(item, start=None):
    course = item["course"]
    hops = item["hops"]

    arrive_min = []
    t = 0
    for i, p in enumerate(course):
        arrive_min.append(t)
        t += dwell_min(p)
        if i < len(hops):
            t += walk_min(hops[i])

    anchor = next((i for i, p in enumerate(course) if p.get("fixed_time")), None)

    # fixed_time이 있으면 실제 시각 계산
    if anchor is not None:
        fixed = datetime.strptime(course[anchor]["fixed_time"], "%H:%M")
        start_dt = fixed - timedelta(minutes=arrive_min[anchor])

    # start가 있으면 실제 시각 계산
    elif start is not None:
        start_dt = datetime.strptime(start, "%H:%M")

    # 둘 다 없으면 실제 시각 없이 상대 시간만 계산
    else:
        start_dt = None

    plan = []
    for p, m in zip(course, arrive_min):
        step = {
            "place": p,
            "arrive_after_min": round(m),
            "leave_after_min": round(m + dwell_min(p)),
        }

        if start_dt is not None:
            arrive = start_dt + timedelta(minutes=m)
            leave = arrive + timedelta(minutes=dwell_min(p))
            step["arrive"] = arrive
            step["leave"] = leave

        plan.append(step)

    item["plan"] = plan
    return item

# ==========================================================
# 링크 생성

def kakao_route_url(item, by="walk"):
    course = item["course"]
    if len(course) < 2:
        return None

    def point(p):
        name = quote(p["name"], safe="")
        return f"{name},{p['lat']},{p['lng']}"

    points = "/".join(point(p) for p in course)
    return f"https://map.kakao.com/link/by/{by}/{points}"

# ==========================================================


def plan_course(places, area_hint=None, start=None, max_count=5, top_n=50):
    route, not_found = collect(places, area_hint=area_hint)

    if not route:
        return {
            "ok": False,
            "error": "검색된 장소가 없습니다.",
            "not_found": not_found,
        }

    top_courses = best_courses(route, max_count=max_count, top_n=top_n)
    passed_courses = screen_courses(top_courses)
    ranked_courses = rank_courses(passed_courses, route)

    if not ranked_courses:
        return {
            "ok": False,
            "error": "조건에 맞는 코스를 만들 수 없습니다.",
            "found_places": route,
            "not_found": not_found,
        }

    best = ranked_courses[0]
    best = schedule_course(best, start=start)

    stops = []
    for step in best["plan"]:
        p = step["place"]

        stop = {
            "name": p["name"],
            "phase": p["phase"],
            "category_name": p["category_name"],
            "lat": p["lat"],
            "lng": p["lng"],
            "fixed_time": p.get("fixed_time"),
            "arrive_after_min": step["arrive_after_min"],
            "leave_after_min": step["leave_after_min"],
        }

        if "arrive" in step:
            stop["arrive"] = step["arrive"].strftime("%H:%M")
            stop["leave"] = step["leave"].strftime("%H:%M")

        stops.append(stop)

    return {
        "ok": True,
        "summary": " → ".join(p["name"] for p in best["course"]),
        "total_distance_m": round(best["distance"], 1),
        "total_walk_min": round(best["walk_min"], 1),
        "score": round(best["score"], 1),
        "penalty": best["penalty"],
        "stops": stops,
        "kakao_map_url": kakao_route_url(best),
        "not_found": not_found,
    }



if __name__ == "__main__":
    places = [
        Place(name="한성돈까스"),
        Place(name="카츠오모이"),
        Place(name="냐벱인다낭", fixed_time="20:00"),
        Place(name="이스트베이글"),
        Place(name="남위례역"),
        Place(name="슬로비"),
        Place(name="소정한식뷔페"),
        Place(name="플랩잭팬트리"),
    ]

    result = plan_course(
        places=places,
        area_hint="위례",
        start="18:00",
    )

    print(result)

# {'ok': True, 
# 'summary': '소정한식뷔페 → 슬로비 → 냐벱인다낭 → 이스트베이글 → 한성돈까스 위례점',
# 'total_distance_m': 918.0, 'total_walk_min': 17.8, 'score': 918.0, 'penalty': 0,
# 'stops': [
# {'name': '소정한식뷔페', 'phase': '식사', 'category_name': '음식점 > 뷔페 > 한식뷔페', 'lat': 37.466761540275, 'lng': 127.136923623352, 'fixed_time': None, 'arrive': '18:00', 'leave': '19:00'}, {'name': '슬로비', 'phase': '카페', 'category_name': '음식점 > 카페', 'lat': 37.46788619631806, 'lng': 127.13753157507368, 'fixed_time': None, 'arrive': '19:02', 'leave': '20:02'}, {'name': '냐벱인다낭', 'phase': '식사', 'category_name': '음식점 > 아시아음식 > 동남아음식 > 베트남음식', 'lat': 37.4655763744965, 'lng': 127.139522458558, 'fixed_time': None, 'arrive': '20:08', 'leave': '21:08'}, {'name': '이스트베이글', 'phase': '카페', 'category_name': '음식점 > 간식 > 제과,베이커리', 'lat': 37.4678217725857, 'lng': 127.140216181836, 'fixed_time': None, 'arrive': '21:13', 'leave': '22:13'}, {'name': '한성돈까스 위례점', 'phase': '식사', 'category_name': '음식점 > 일식 > 돈까스,우동', 'lat': 37.466373714123804, 'lng': 127.1418389761795, 'fixed_time': None, 'arrive': '22:17', 'leave': '23:17'}],
# 'kakao_map_url': 'https://map.kakao.com/link/by/walk/%EC%86%8C%EC%A0%95%ED%95%9C%EC%8B%9D%EB%B7%94%ED%8E%98,37.466761540275,127.136923623352/%EC%8A%AC%EB%A1%9C%EB%B9%84,37.46788619631806,127.13753157507368/%EB%83%90%EB%B2%B1%EC%9D%B8%EB%8B%A4%EB%82%AD,37.4655763744965,127.139522458558/%EC%9D%B4%EC%8A%A4%ED%8A%B8%EB%B2%A0%EC%9D%B4%EA%B8%80,37.4678217725857,127.140216181836/%ED%95%9C%EC%84%B1%EB%8F%88%EA%B9%8C%EC%8A%A4%20%EC%9C%84%EB%A1%80%EC%A0%90,37.466373714123804,127.1418389761795', 
# 'not_found': []}