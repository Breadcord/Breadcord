# syntax=docker/dockerfile:1

FROM python:3.11.8-slim-bullseye as build

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1

RUN apt update && apt install -y --no-install-recommends curl
ADD --chmod=755 https://astral.sh/uv/install.sh ./install.sh
RUN ./install.sh && rm ./install.sh

COPY requirements.txt .
RUN /root/.cargo/bin/uv venv --seed
RUN /root/.cargo/bin/uv pip install --no-cache -r requirements.txt


FROM python:3.11.8-slim-bullseye

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY --from=build /app/.venv ./.venv
COPY breadcord ./breadcord

ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["python", "-m", "breadcord"]
CMD ["--no-ui"]
