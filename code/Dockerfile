FROM python:3.13-slim

WORKDIR /app

COPY code/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY code/ ./code/

WORKDIR /app/code

CMD ["python", "server.py"]