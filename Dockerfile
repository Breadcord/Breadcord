# syntax=docker/dockerfile:1

FROM python:3.11.0-slim-bullseye@sha256:1cd45c5dad845af18d71745c017325725dc979571c1bbe625b67e6051533716c as build

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential
ENV PYTHONDONTWRITEBYTECODE=1
RUN python -m venv venv
ENV PATH="/app/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt


FROM python:3.11.0-slim-bullseye@sha256:1cd45c5dad845af18d71745c017325725dc979571c1bbe625b67e6051533716c

RUN groupadd -g 999 python \
    && useradd -r -u 999 -g python python \
    && mkdir /app \
    && chown python:python /app
USER 999
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY --chown=python:python --from=build /app/venv ./venv
COPY --chown=python:python src ./src

ENV PATH="/app/venv/bin:$PATH"
CMD ["python", "src/main.py"]
