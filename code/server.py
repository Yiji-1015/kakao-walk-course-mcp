from typing import Any
from mcp.server.fastmcp import FastMCP
from course_planner import Place, plan_course
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
import os


mcp = FastMCP(
    "kakao-course-planner",
    host="0.0.0.0",
    port=int(os.getenv("PORT", "8080")),
    streamable_http_path="/mcp",
)


@mcp.custom_route("/", methods=["GET"], include_in_schema=False)
@mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)
async def health_check(request: Request) -> Response:
    return JSONResponse({"status": "ok", "service": "kakao-course-planner"})


class PlaceCandidate(BaseModel):
    name: str = Field(description="Place name to search with Kakao Local API.")
    fixed_time: str | None = Field(
        default=None,
        description="Optional reservation or appointment time in HH:MM format.",
    )


def to_place(item: PlaceCandidate | dict[str, Any]):
    if isinstance(item, dict):
        name = item.get("name")
        fixed_time = item.get("fixed_time")
    else:
        name = item.name
        fixed_time = item.fixed_time

    if not isinstance(name, str) or not name.strip():
        raise ValueError("장소 객체에는 문자열 name 필드가 필요합니다.")

    if fixed_time is not None and not isinstance(fixed_time, str):
        raise ValueError("fixed_time은 '20:00' 같은 문자열이어야 합니다.")

    return Place(
        name=name.strip(),
        fixed_time=fixed_time.strip() if fixed_time else None,
    )


@mcp.tool()
def plan_kakao_course(
    places: list[PlaceCandidate],
    area_hint: str | None = None,
    start_time: str | None = None,
    max_count: int = 5,
):
    """
    Create a walkable Kakao course from candidate places.

    Use this when the user gives restaurant, cafe, bar, or activity candidates
    and wants a reasonable walking route. Pass places as objects with a name.
    Use fixed_time only for reservations or fixed appointments in HH:MM format.
    area_hint is a Korean locality such as "연남동", "강남역", or "성수".
    start_time is optional and only adds clock times to the returned schedule.
    """
    if not places:
        return {
            "ok": False,
            "error": "places에는 최소 1개 이상의 장소가 필요합니다.",
            "not_found": [],
        }

    if max_count < 1 or max_count > 5:
        return {
            "ok": False,
            "error": "max_count는 1 이상 5 이하이어야 합니다.",
            "not_found": [],
        }

    try:
        parsed_places = [to_place(item) for item in places]
    except ValueError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "not_found": [],
        }

    return plan_course(
        places=parsed_places,
        area_hint=area_hint,
        start=start_time,
        max_count=max_count,
        top_n=50,
    )


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
