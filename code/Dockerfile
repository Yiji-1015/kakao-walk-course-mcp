FROM python:3.13-slim

WORKDIR /app

ARG KAKAO_REST_API_KEY
ENV KAKAO_REST_API_KEY=${KAKAO_REST_API_KEY}
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

COPY code/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY code/ .

EXPOSE 8000

CMD ["python", "server.py"]
