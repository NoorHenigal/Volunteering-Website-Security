# KV6014-Volunteering-Project

## Dev Setup Guide

1. Install Python 3.14.
2. Install [*uv*](https://docs.astral.sh/uv/getting-started/installation/).
3. Install Docker (if you're working on databases and/or want to test the web app).
4. Clone this repository: `git clone https://github.com/M-AlNoaimi/KV6014-Volunteering-Project.git`.
    > You might need to set your Git up with GitHub (use YouTube).
5. Enter the repository via your terminal `cd KV6014-Volunteering-Project`.
6. Run `uv sync --dev`.
7. Create a new file in the `Docker/` folder called `.env`.
8. Paste the contents of `Docker/.env.example` into `Docker/.env`.
9. Create a new file in the root directory called `.env`.
10. Paste the contents of `.env.example` into `.env`.
11. Run `uv run generate_keys.py`.
12. Use the generated keys (copy cleanly) to replace the placeholder keys set in `Docker/.env` and `.env`.
13. You're good to go!

## Database Setup Guide

1. Have Docker Installed (use YouTube or Google).
2. Open up your Terminal and Navigate to the repository

### To run the *volatile* database

> This database type is *in-memory* only! But it should be the main one you're using during development, and/or when exporting schema's.

Run this from the root directory:

```bash
docker-compose --env-file Docker/.env -f Docker/docker-compose.yml up db-volatile
```

or simply:

```bash
make pg-volatile
```

### To run the *persistent* database

> This database type stores data on disk, so it will persist between container restarts.

Run this from the root directory:

```bash
docker-compose --env-file Docker/.env -f Docker/docker-compose.yml up db-persistent
```

or simply:

```bash
make pg-persistent
```
