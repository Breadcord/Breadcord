# syntax=docker/dockerfile:1

FROM python:3.11.2-slim-bullseye@sha256:1d2b7101658e795e4d878d3f54f3354838630e1d16f5868ea18b338c12bb92c9 as build

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential
ENV PYTHONDONTWRITEBYTECODE=1
RUN python -m venv venv
ENV PATH="/app/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt


FROM python:3.11.2-slim-bullseye@sha256:1d2b7101658e795e4d878d3f54f3354838630e1d16f5868ea18b338c12bb92c9

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY --from=build /app/venv ./venv
COPY breadcord ./breadcord

ENV PATH="/app/venv/bin:$PATH"
CMD ["python", "-m", "breadcord"]
