# KV6014-Volunteering-Project

## Prerequisites

1. Install **Python 3.14.2**
2. Install [**uv**](https://docs.astral.sh/uv/getting-started/installation/)
3. Install **Docker** (required for databases)
4. Make sure Git is set up with GitHub

---

### Initial Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/M-AlNoaimi/KV6014-Volunteering-Project.git
   ```

2. Enter the project directory:

   ```bash
   cd KV6014-Volunteering-Project
   ```

3. Install dependencies:

   ```bash
   uv sync --extra dev
   ```

4. Create your environment file:

   ```bash
   cp .env.example .env
   ```

5. Generate required secrets:

   ```bash
   uv run generate_keys.py
   ```

6. Copy the generated values into `.env`, replacing all placeholder keys.

---

## Database Setup Guide

Docker is required for all database workflows.

### Volatile (In-Memory) Database

> Recommended for development and schema work.
> Data does **not** persist between restarts.

From the project root:

```bash
make pg-volatile
```

---

### Persistent Database

> Data is stored on disk and survives container restarts.

From the project root:

```bash
make pg-persistent
```

---

## Database Migrations

Once a database container is running:

```bash
make migrate
```

This applies all Alembic migrations to the active database.

---

## Running the Web App

```bash
make run
```

The app will start using the active database and environment configuration.

---

## Demo Data (Optional)

If `DEMO_DATA=true` is set in `.env`, demo data can be managed via the UI:

* Seed demo data from the demo settings modal
* Unseed safely without touching real data
* Requires authentication
* No auto-seeding on startup
