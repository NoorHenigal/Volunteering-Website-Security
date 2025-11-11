include Docker/.env
export

.PHONY: pg-volatile pg-persistent export-schema

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
