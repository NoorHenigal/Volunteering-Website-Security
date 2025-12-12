include Docker/.env
export

.PHONY: pg-volatile pg-persistent export-schema build-css

# Build Tailwind CSS
build-css:
	tailwindcss -i app/static/css/input.css -o app/static/css/output.css --minify

# Start the volatile (in-memory) database
pg-volatile:
	docker-compose --env-file Docker/.env -f Docker/docker-compose.yml up db-volatile

# Start the persistent database
pg-persistent:
	docker-compose --env-file Docker/.env -f Docker/docker-compose.yml up db-persistent

# Export the database schema (tables, types, functions) to schema.sql
export-schema:
	@echo "Exporting database schema from volatile container..."
	@docker exec -i -e PGPASSWORD=$(DB_PASSWORD) volunteering-db-volatile pg_dump -U $(DB_USER) -d $(DB_NAME) --schema-only > schema.sql
	@echo "Schema exported to schema.sql"

migrate:
	uv run alembic upgrade head

check:
	uv sync --extra dev
	uv run ruff check
	uv run ruff format
	uv run pytest -xvs
	uv run mypy --strict .

test:
	uv run pytest -xvs

run-hold:
	TEST_RUN_DURATION=5 uv run python run.py

run:
	uv run python run.py
