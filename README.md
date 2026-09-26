# Military & Defense Daily News

## Local PostgreSQL database

The database runs in Docker Compose; the API can run on your host and connects
through `localhost:5434`.

1. Copy the example environment file and start PostgreSQL:

   ```sh
   cp .env.example .env
   docker compose up -d postgres
   docker compose ps
   ```

   Wait until the `postgres` service reports healthy before continuing. Compose
   stores database files in the persistent `postgres_data` volume.

2. Install the backend dependencies and apply database migrations:

   ```sh
   python3.13 -m venv .venv
   source .venv/bin/activate
   pip install -r backend/requirements.txt
   cd backend
   alembic upgrade head
   ```

3. Start the API from the `backend` directory:

   ```sh
   uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
   ```

The API reads `DATABASE_URL` from the root `.env` file. The example credentials
in `docker-compose.yml` are for local development only; use managed secrets and
credentials for deployments.
