# FederHub — Federated Learning Platform

FederHub is a privacy-preserving federated machine learning platform. It connects a React/FastAPI web dashboard with an Electron-based Edge Node desktop application. Clients train PyTorch models locally inside Docker containers and stream only mathematical weight updates — never raw data — to a Python gRPC aggregation server that runs live FedAvg across all participants.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Web Dashboard (React)                  │
│  Create jobs · Assign clients · View metrics · Download  │
└────────────────────────┬────────────────────────────────┘
                         │ REST (JWT)
┌────────────────────────▼────────────────────────────────┐
│                  Backend API (FastAPI)                   │
│  Auth · Job management · Aggregation · Model download    │
│  Database: SQLite (dev) / PostgreSQL (prod)              │
└────────────────────────┬────────────────────────────────┘
                         │ SQLAlchemy (shared DB)
┌────────────────────────▼────────────────────────────────┐
│              Gamma gRPC Aggregation Server               │
│  Receives weight updates · Rolling FedAvg · Persists     │
│  state to DB · Restores state on restart                 │
└────────────────────────▲────────────────────────────────┘
                         │ gRPC (JWT-authenticated)
┌────────────────────────┴────────────────────────────────┐
│              Edge Node Desktop App (Electron)            │
│  Authenticates · Validates job · Runs Docker training    │
│  Streams weights to Gamma                                │
└────────────────────────┬────────────────────────────────┘
                         │ docker run
┌────────────────────────▼────────────────────────────────┐
│          Training Container (federhub-beta-trainer)      │
│  PyTorch · Reads CSV · Trains model · Saves checkpoint   │
│  Column names embedded in .pt · Streams via gRPC sender  │
└─────────────────────────────────────────────────────────┘
```

---

## Roles

| Role | Can do |
|---|---|
| `platform_admin` | Manage all users, all jobs, publish results |
| `ml_engineer` | Create and manage their own jobs, assign clients |
| `client_operator` | Train locally and submit updates via desktop app |

---

## Key Features

- **Live rolling FedAvg** — weights are aggregated the moment any client submits; no waiting for a full round
- **Multi-tenant isolation** — each job has its own state dictionary; weights from different jobs never mix
- **JWT-authenticated gRPC** — clients must present a valid token; identity is verified against job assignment
- **Column name passthrough** — CSV column names are read at training time, embedded in the `.pt` checkpoint, passed through gRPC metadata, stored in round snapshots, and restored on server restart
- **State persistence** — gRPC server restores full rolling state from the database on restart; no data lost
- **Model versioning** — every aggregation round produces a downloadable checkpoint in `.pt` or JSON format
- **Zero-knowledge privacy** — client operators cannot view global model weights or metrics until they have contributed a local update
- **Docker isolation** — client training runs in a pre-built container; no local Python environment required on client machines

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- Docker Desktop (must be running before launching the desktop client)
- Git

---

## Setup

Run once to install all dependencies and build the Docker training image.

**Windows:**
```bat
setup_windows_dependencies.bat
```

**macOS:**
```bash
chmod +x setup_mac_dependencies.command
./setup_mac_dependencies.command
```

This installs Python packages for the backend and federated engine, Node packages for the frontend and client, and builds the `federhub-beta-trainer` Docker image.

> **After changing any Python training file** (`client/ml/train.py`, `client/grpc_weight_sender.py`, etc.), rebuild the Docker image from the project root:
> ```bash
> docker build -t federhub-beta-trainer -f client/Dockerfile .
> ```

---

## Running the Platform

### Start all backend services

**Windows:**
```bat
run_all_services_windows.bat
```

**macOS:**
```bash
chmod +x run_all_services_mac.command
./run_all_services_mac.command
```

Opens three terminals:
- **Gamma gRPC server** — `federated-engine/grpc_server.py`
- **Backend API** — FastAPI on `http://localhost:8000`
- **Frontend** — React on `http://localhost:3000`

### Start the desktop client

**Windows:**
```bat
run_client_windows.bat
```

**macOS:**
```bash
chmod +x run_client_mac.command
./run_client_mac.command
```

Installs Node dependencies if missing, then launches the Electron app from source.

> **Do not run the app from `client/dist/`** during development — that is the packaged build and will not pick up source changes.

---

## First-Time Configuration

1. Open `http://localhost:3000` and register a `platform_admin` account
2. Register an `ml_engineer` account and one or more `client_operator` accounts
3. Log in as ML Engineer → **Create Job** → configure rounds and local epochs → assign clients
4. Click **Start Orchestration** on the job card
5. Log into the desktop client as a client operator, select the job ID, choose a CSV dataset, and start training
6. Watch the Gamma terminal aggregate weights in real time; view metrics on the web dashboard

---

## Desktop Client Distribution

The compiled Windows installer is served by the backend at `/download/client/windows`. To rebuild it after making code changes:

1. From the `client/` directory, run:
   ```bat
   npm run pack:win
   ```
2. Copy the output installer to the downloads folder:
   ```
   client/dist/FederHub Edge Node Setup 0.1.0.exe  →  backend/downloads/FederHub-Edge-Client.exe
   ```

> A macOS build can only be produced on a Mac. From the `client/` directory run `npm run pack:mac`, then copy the output `.dmg` to `backend/downloads/`.

---

## Environment Variables

Copy the `.env.example` files in `federated-engine/` and `backend/` to `.env` and fill in the values:

```env
# federated-engine/.env
DATABASE_URL=sqlite:///./federhub_local.db   # or postgresql://...
GRPC_PORT=50051
SECRET_KEY=your-secret-key-here

# backend/.env
DATABASE_URL=sqlite:///./federhub_local.db
SECRET_KEY=your-secret-key-here
ALLOWED_ORIGINS=http://localhost:3000
```

Both services must use the **same `SECRET_KEY`** — the gRPC server validates JWTs issued by the backend.

---

## Project Structure

```
FederHub/
├── backend/                  # FastAPI REST API
│   ├── app/
│   │   ├── routers/jobs.py   # Job CRUD, aggregation, model download
│   │   ├── routers/auth.py   # Registration, login, user management
│   │   ├── models.py         # SQLAlchemy ORM models
│   │   └── schemas.py        # Pydantic request/response schemas
│   └── downloads/            # Compiled client installers
├── federated-engine/         # gRPC aggregation server
│   ├── grpc_server.py        # Rolling FedAvg, JWT validation, state persistence
│   ├── db_connector.py       # DB helpers shared between server and tasks
│   └── models.py             # SQLAlchemy models (mirrors backend)
├── frontend/                 # React web dashboard
│   └── src/pages/
│       ├── Dashboard.js      # Job list, start/publish/delete, user management
│       ├── JobDetailsPage.js # Round metrics, model version download
│       └── CreateJobPage.js  # Job creation form
├── client/                   # Electron desktop app
│   ├── main.js               # IPC handlers, Docker orchestration, auth
│   ├── ml/
│   │   ├── train.py          # PyTorch training, CSV column detection
│   │   └── inspect_checkpoint.py  # Checkpoint column validation
│   ├── grpc_weight_sender.py # Streams .pt weights to Gamma via gRPC
│   └── Dockerfile            # Training container definition
├── run_all_services_windows.bat
├── run_all_services_mac.command
├── run_client_windows.bat
├── run_client_mac.command
├── setup_windows_dependencies.bat
└── setup_mac_dependencies.command
```

---

## Testing

```bash
# Backend API tests
cd backend
pytest

# Federated engine unit tests
cd federated-engine
python -m pytest
```
