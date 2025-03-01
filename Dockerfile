# syntax=docker/dockerfile:1

FROM python:3.13.2-slim-bullseye as build

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1

RUN apt update && apt install -y --no-install-recommends curl
ADD --chmod=755 https://astral.sh/uv/install.sh ./install.sh
RUN ./install.sh && rm ./install.sh

COPY . .
RUN /root/.local/bin/uv venv --seed
RUN /root/.local/bin/uv pip install --no-cache .


FROM python:3.13.2-slim-bullseye

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY --from=build /app/.venv ./.venv

ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["python", "-m", "breadcord"]
CMD ["--no-ui"]
