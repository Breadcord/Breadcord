# syntax=docker/dockerfile:1

FROM python:3.11.2-slim-bullseye@sha256:28e5366ce5c423639950d3962b668730535da08cd235bdacef32171e26cd2b5c as build

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential
ENV PYTHONDONTWRITEBYTECODE=1
RUN python -m venv venv
ENV PATH="/app/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt


FROM python:3.11.2-slim-bullseye@sha256:28e5366ce5c423639950d3962b668730535da08cd235bdacef32171e26cd2b5c

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY --from=build /app/venv ./venv
COPY breadcord ./breadcord

ENV PATH="/app/venv/bin:$PATH"
CMD ["python", "-m", "breadcord"]
