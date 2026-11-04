SCALE ?= starter
B = cd backend &&
.PHONY: install test lint migrate data pipeline all api docs web mobile

install: ; $(B) uv sync
test: ; $(B) uv run pytest -q
lint: ; $(B) uv run ruff check app tests
migrate: ; $(B) uv run alembic upgrade head
data: ; $(B) uv run python -m app.cli generate --scale $(SCALE)
pipeline: ; $(B) uv run python -m app.cli pipeline
all: ; $(B) uv run python -m app.cli all --scale $(SCALE)
api: ; $(B) uv run uvicorn app.main:app --reload --port 8000
docs: ; $(B) uv run python -m app.cli docs
web: ; cd web && npm run dev
