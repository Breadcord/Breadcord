# syntax=docker/dockerfile:1

FROM python:3.11.2-slim-bullseye@sha256:d0e839882b87135b355361efeb9e9030c9d2a808da06434f4c99eb4009c15e64 as build

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential
ENV PYTHONDONTWRITEBYTECODE=1
RUN python -m venv venv
ENV PATH="/app/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt


FROM python:3.11.2-slim-bullseye@sha256:d0e839882b87135b355361efeb9e9030c9d2a808da06434f4c99eb4009c15e64

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY --from=build /app/venv ./venv
COPY breadcord ./breadcord

ENV PATH="/app/venv/bin:$PATH"
CMD ["python", "-m", "breadcord"]
