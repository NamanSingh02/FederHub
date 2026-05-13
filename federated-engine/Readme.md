
# FederHub – Group 3 (Team Gamma) | Phase 3: The Communication Bridge

## Overview: What We Did

This directory contains the **Phase 3 deliverable** for Team Gamma (The Federated Engine).

Building on the math foundation (Phase 1) and the gRPC stub (Phase 2), Phase 3 wires Gamma into the live system — connecting Team Beta's PyTorch edge nodes and Team Alpha's PostgreSQL backend into a unified pipeline. We implemented:

1. **Beta ↔ Gamma (Edge Integration):** Upgraded the Protobuf schema and gRPC server to accept real PyTorch `state_dict` payloads. Built a weight sender on Beta's side that loads `.pt` checkpoints and streams only mathematical updates to Gamma's aggregation server.
2. **Alpha ↔ Gamma (Central Integration):** Created a database connector and Celery orchestrator that reads job configurations from Alpha's PostgreSQL (AWS RDS), writes back per-round metrics (accuracy, loss), and updates job status transitions for the React dashboard.

## Rationale: Why We Did It

### gRPC Weight Streaming
Phase 2 proved the gRPC pipe works with dummy data. Phase 3 makes it real — supporting variable-size PyTorch tensors organized by layer name, so the aggregation server can perform per-layer weighted FedAvg on actual deep learning models. This directly satisfies **Epic 5, Story 5.1**: *"Securely stream only mathematical updates to the aggregation server."*

### Database Integration
For Gamma to orchestrate multi-round training jobs, it must know *how many* rounds to run, *which clients* to expect, and *where* to report progress. By linking Celery to Alpha's PostgreSQL, the system becomes dynamic — admins configure jobs via the dashboard, and Gamma executes them autonomously.

## Architecture

### Beta ↔ Gamma: Weight Streaming Flow

```
  Beta Edge Node                         Gamma Aggregation Server
  ┌──────────────────┐                  ┌──────────────────────────┐
  │ train.py          │                  │ grpc_server.py            │
  │   ↓               │                  │   ↓                      │
  │ Save .pt file     │                  │ SubmitWeightUpdate()     │
  │   ↓               │   gRPC/Proto     │   ↓                      │
  │ grpc_weight_sender│ ──────────────►  │ Auto-detect mode:        │
  │   - Load state_dict│  TensorData[]   │   flat (Phase 2) or      │
  │   - Serialize layers│               │   structured (Phase 3)   │
  │   - Send to server │                │   ↓                      │
  └──────────────────┘                  │ fedavg_mock.py            │
                                        │   - Per-layer FedAvg      │
                                        │   - Weighted by samples   │
                                        │   ↓                      │
                                        │ Global model ready       │
                                        └──────────────────────────┘
```

### Alpha ↔ Gamma: Database Integration Flow

```
  Alpha Dashboard (React)               Gamma Engine
  ┌──────────────────┐                  ┌──────────────────────────┐
  │ Create Job        │                  │ celery_app.py             │
  │   round_count=5  │                  │   ↓                      │
  │   local_epochs=3 │                  │ Fetch job config from DB │
  └────────┬─────────┘                  │   ↓                      │
           │                            │ Status → "running"       │
           ▼                            │   ↓                      │
  ┌──────────────────┐                  │ For each round:          │
  │ PostgreSQL (RDS)  │◄─────────────── │   - Wait for weights     │
  │                   │  db_connector   │   - Run FedAvg            │
  │ job_configurations│  read/write     │   - Record metrics       │
  │ round_metrics     │                  │   ↓                      │
  └──────────────────┘                  │ Status → "completed"     │
           ▲                            └──────────────────────────┘
           │
  Dashboard shows real-time
  training progress
```

## Methodology: How We Did It

### Part 1: gRPC Weight Streaming

* **Proto Upgrade (`federation.proto`):** Added `TensorData` message carrying `layer_name`, `shape[]`, and `data[]` for each tensor. The existing flat `weights` field is preserved for backward compatibility.
* **Protobuf Regeneration:** Compiled updated `.proto` into `federation_pb2.py` + `federation_pb2_grpc.py`.
* **Structured Aggregation (`fedavg_mock.py`):** Added `federated_average_state_dicts()` — performs weighted FedAvg independently per-layer, respecting tensor shapes and producing a global `state_dict`.
* **Server Upgrade (`grpc_server.py`):** Auto-detects flat vs. structured mode based on whether `request.layers` is populated. Full backward compatibility with Phase 2.
* **Weight Sender (`beta/grpc_weight_sender.py`):** Loads `.pt` files via `torch.load()`, extracts `state_dict`, serializes each layer into `TensorData` Protobuf messages, and sends to Gamma.
* **Train Integration (`beta/ml/train.py`):** Added `--server` and `--client-id` flags. When provided, weights are streamed to Gamma after local training completes.

### Part 2: Database Integration

* **Models (`models.py`):** Defines `RoundMetric` table (job_id, round_number, accuracy, loss, num_clients, total_samples, global_weights_snapshot) alongside a read-only mirror of Alpha's `JobConfiguration`.
* **DB Connector (`db_connector.py`):** Provides `fetch_job_config()`, `update_job_status()`, `record_round_metric()`, and `get_round_metrics()` using SQLAlchemy.
* **Celery Orchestrator (`celery_app.py`):** Defines `run_federation_job` task that reads job params from DB, executes rounds, records metrics, and manages status transitions (`draft → running → completed`). Uses Redis as broker.
* **Server Integration (`grpc_server.py`):** After each structured aggregation, automatically writes round metrics to the DB (optional — gracefully degrades if DB is unavailable).

## Files

```
gama/phase2/                       (Gamma – Aggregation Server)
├── federation.proto                # Upgraded Protobuf schema
├── federation_pb2.py               # Generated data classes
├── federation_pb2_grpc.py          # Generated gRPC stubs
├── grpc_server.py                  # gRPC server (flat + structured modes)
├── fedavg_mock.py                  # FedAvg engine (flat + per-layer)
├── models.py                       # RoundMetric + JobConfiguration models
├── db_connector.py                 # PostgreSQL read/write operations
├── celery_app.py                   # Multi-round job orchestrator
├── .env.example                    # Environment config template
├── dummy_client.py                 # Phase 2 test client (preserved)
├── test_fedavg.py                  # Phase 1 FedAvg tests (9 tests)
├── test_grpc_bridge.py             # Phase 2 serialization test (1 test)
├── test_phase3_integration.py      # Phase 3 gRPC + aggregation tests (10 tests)
├── test_db_connector.py            # Phase 3 DB connector tests (10 tests)
└── Readme.md                       # This file

beta/                               (Beta – Edge Node, modified by Gamma)
├── grpc_weight_sender.py           # NEW: PyTorch → gRPC weight sender
└── ml/train.py                     # MODIFIED: added --server, --client-id flags
```

## How to Run

**Requirements:** Python 3.8+, `grpcio`, `grpcio-tools`, `sqlalchemy`, `torch` (for Beta sender), `celery` + `redis` (for orchestrator).

### Install dependencies:
```bash
pip install grpcio grpcio-tools sqlalchemy torch celery redis
```

### Run the gRPC aggregation server:
```bash
cd gama/phase2
python grpc_server.py
```

### Send weights from Beta (in another terminal):
```bash
cd beta
python grpc_weight_sender.py \
    --pt-file demo-client-data/sample_model.pt \
    --server localhost:50051 \
    --client-id "Hospital A"
```

### Run the Celery orchestrator (requires Redis):
```bash
cd gama/phase2
export DATABASE_URL="postgresql://..."
export REDIS_URL="redis://localhost:6379/0"
celery -A celery_app worker --loglevel=info
```

### Run all tests:
```bash
cd gama/phase2
python -m pytest test_fedavg.py test_grpc_bridge.py test_phase3_integration.py test_db_connector.py -v
```

## Validated Outputs

### 1. Full Test Suite (30/30 Passed)
```bash
$ python -m pytest test_db_connector.py test_phase3_integration.py test_grpc_bridge.py test_fedavg.py -v

test_db_connector.py::TestDBConnector::test_fetch_job_config_returns_correct_data PASSED
test_db_connector.py::TestDBConnector::test_fetch_job_config_missing_job_raises  PASSED
test_db_connector.py::TestDBConnector::test_full_job_lifecycle                   PASSED
test_db_connector.py::TestDBConnector::test_get_round_metrics_empty_job          PASSED
test_db_connector.py::TestDBConnector::test_get_round_metrics_returns_ordered    PASSED
test_db_connector.py::TestDBConnector::test_record_round_metric_basic            PASSED
test_db_connector.py::TestDBConnector::test_record_round_metric_with_snapshot    PASSED
test_db_connector.py::TestDBConnector::test_update_job_status_invalid_raises     PASSED
test_db_connector.py::TestDBConnector::test_update_job_status_missing_job_raises PASSED
test_db_connector.py::TestDBConnector::test_update_job_status_valid_transition   PASSED
test_phase3_integration.py::TestPhase3StructuredAggregation::test_01_single      PASSED
test_phase3_integration.py::TestPhase3StructuredAggregation::test_02_three       PASSED
test_phase3_integration.py::TestPhase3StructuredAggregation::test_03_precision   PASSED
test_phase3_integration.py::TestPhase2BackwardCompatibility::test_flat_mode      PASSED
test_phase3_integration.py::TestFedAvgStateDicts::test_equal_weights             PASSED
test_phase3_integration.py::TestFedAvgStateDicts::test_weighted_average          PASSED
test_phase3_integration.py::TestFedAvgStateDicts::test_shape_preserved           PASSED
test_phase3_integration.py::TestFedAvgStateDicts::test_empty_input_raises        PASSED
test_phase3_integration.py::TestFedAvgStateDicts::test_mismatched_layers_raises  PASSED
test_grpc_bridge.py::TestGRPCBridge::test_weight_submission_serialization        PASSED
test_fedavg.py::TestFederatedAverage (9 tests)                                   PASSED

=============== 30 passed in 0.30s ===============
```

## Phase Roadmap

| Phase | Gamma Deliverable | Status |
|-------|------------------|--------|
| Phase 1 | FedAvg mock script + Redis cloud setup | ✅ Done |
| Phase 2 | `.proto` files, gRPC server stub | ✅ Done |
| **Phase 3** | **Communication Bridge: Beta gRPC + Alpha DB integration** | **✅ This PR** |
| Phase 4 | End-to-end integration with Alpha & Beta | 🔜 Next |

## Branch Strategy

```
main
 └── dev-gamma
      └── feature/phase3-communication-bridge  ← this branch
```

PR from `feature/phase3-communication-bridge` → `dev-gamma` for team review.

## User Story Traceability

| File | Epic | Story | Acceptance Criteria |
|------|------|-------|---------------------|
| `federation.proto` | Epic 5 | 5.1 | Structured tensor payloads transmitted via gRPC |
| `grpc_server.py` | Epic 5 | 5.1 | Aggregator receives real PyTorch weights → executes FedAvg |
| `grpc_weight_sender.py` | Epic 5 | 5.1 | Beta hooks PyTorch output into gRPC client |
| `fedavg_mock.py` | Epic 2 | 2.3 | Per-layer weighted aggregation of state dicts |
| `db_connector.py` | Epic 2 | 2.3 | Job status and metrics dynamically updated in PostgreSQL |
| `celery_app.py` | Epic 2 | 2.3 | Multi-round federated training orchestration |
| `models.py` | Epic 2 | 2.3 | Round metrics stored for dashboard display |

## References

- McMahan, H. B., et al. (2017). *Communication-Efficient Learning of Deep Networks from Decentralized Data*. AISTATS 2017. https://arxiv.org/abs/1602.05629
- gRPC Python Documentation: https://grpc.io/docs/languages/python/
- Celery Documentation: https://docs.celeryq.dev/
