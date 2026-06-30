# kakao-walk-course-mcp

A rule-based MCP server that turns a list of Kakao places into a walkable course with a Kakao Map route link.

## Environment

Create a local `.env` file:

```env
KAKAO_REST_API_KEY=your_kakao_rest_api_key_here
```

Do not commit `.env`. Use `.env.example` as the public template.

## MVP Tool

`plan_course`

Input:

```json
{
  "places": ["저스트텐동 연남본점", "테일러커피 연남점", "연주방"],
  "start": "홍대입구역",
  "end": null,
  "start_time": "18:00"
}
```

Output includes a selected walking course, estimated walking time, excluded places, and a Kakao Map route link.
