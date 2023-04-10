# syntax=docker/dockerfile:1

FROM python:3.11.3-slim-bullseye@sha256:5a67c38a7c28ad09d08f4e153280023a2df77189b55af7804d7ceb96fee6a68f as build

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential
ENV PYTHONDONTWRITEBYTECODE=1
RUN python -m venv venv
ENV PATH="/app/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt


FROM python:3.11.3-slim-bullseye@sha256:5a67c38a7c28ad09d08f4e153280023a2df77189b55af7804d7ceb96fee6a68f

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY --from=build /app/venv ./venv
COPY breadcord ./breadcord

ENV PATH="/app/venv/bin:$PATH"
CMD ["python", "-m", "breadcord"]
