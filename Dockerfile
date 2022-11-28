# syntax=docker/dockerfile:1

FROM python:3.11.0-slim-bullseye as build

WORKDIR /app

RUN python -m venv venv
ENV PATH="/app/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt


FROM python:3.11.0-slim-bullseye

RUN groupadd -g 999 python && useradd -r -u 999 -g python python
USER 999
WORKDIR /app

COPY --chown=python:python --from=build /app/venv ./venv
COPY --chown=python:python src ./src

ENV PATH="/app/venv/bin:$PATH"
CMD ["python", "src/main.py"]
