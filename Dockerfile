# syntax=docker/dockerfile:1

FROM python:3.11.2-slim-bullseye@sha256:2f749ef90f54fd4b3c77cde78eec23ab5b8199d9ac84e4ced6ae523ef223ef7b as build

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential
ENV PYTHONDONTWRITEBYTECODE=1
RUN python -m venv venv
ENV PATH="/app/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt


FROM python:3.11.2-slim-bullseye@sha256:2f749ef90f54fd4b3c77cde78eec23ab5b8199d9ac84e4ced6ae523ef223ef7b

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY --from=build /app/venv ./venv
COPY breadcord ./breadcord

ENV PATH="/app/venv/bin:$PATH"
CMD ["python", "-m", "breadcord"]
