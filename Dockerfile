FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /srv

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./
COPY app ./app

# 기동 시 스키마를 최신으로 맞춘 뒤 봇을 띄운다.
CMD ["sh", "-c", "alembic upgrade head && python -m app.main"]
