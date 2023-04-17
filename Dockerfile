# syntax=docker/dockerfile:1

FROM python:3.11.3-slim-bullseye@sha256:286f2f1d6f2f730a44108656afb04b131504b610a6cb2f3413918e98dabba67e as build

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential
ENV PYTHONDONTWRITEBYTECODE=1
RUN python -m venv venv
ENV PATH="/app/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt


FROM python:3.11.3-slim-bullseye@sha256:286f2f1d6f2f730a44108656afb04b131504b610a6cb2f3413918e98dabba67e

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY --from=build /app/venv ./venv
COPY breadcord ./breadcord

ENV PATH="/app/venv/bin:$PATH"
CMD ["python", "-m", "breadcord"]
