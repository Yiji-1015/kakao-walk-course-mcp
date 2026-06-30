from typing import Any
from mcp.server.fastmcp import FastMCP
from course_planner import Place, plan_course


mcp = FastMCP("kakao-course-planner")

def to_place(item: dict[str, Any]):
    return Place(
        name=item["name"],
        fixed_time=item.get("fixed_time"),
    )


@mcp.tool()
def plan_kakao_course(
    places: list[dict[str, Any]],
    area_hint: str | None = None,
    start_time: str | None = None,
    max_count: int = 5,
    top_n: int = 50,
):
    """
    후보 장소 목록을 받아 도보 기준 카카오 코스를 추천한다.

    사용자가 단톡방에서 공유한 맛집/카페/술집 후보를 말하면,
    호스트 LLM은 장소명을 추출해서 places에 넣어야 한다.

    places는 장소 객체 리스트다.
    예:
    [
      {"name": "한성돈까스"},
      {"name": "냐벱인다낭", "fixed_time": "20:00"}
    ]

    fixed_time은 해당 장소에 반드시 그 시각쯤 도착해야 하는 예약/약속 시간이다.
    area_hint는 검색 보정을 위한 지역명이다. 예: "위례", "연남동".
    start_time은 선택 입력이다. 없으면 실제 시각 대신 상대 소요시간만 반환한다.

    결과는 추천 순서, 총 도보 거리/시간, 장소별 도착/체류 시간,
    검색 실패 장소, 카카오맵 도보 경로 링크를 포함한다.
    """
    parsed_places = [to_place(item) for item in places]

    return plan_course(
        places=parsed_places,
        area_hint=area_hint,
        start=start_time,
        max_count=max_count,
        top_n=top_n,
    )


if __name__ == "__main__":
    mcp.run(transport="streamable-http")