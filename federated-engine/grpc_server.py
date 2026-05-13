import argparse
import json
import math
import os
import grpc
from concurrent import futures
import threading
from dotenv import load_dotenv

try:
    from jose import jwt as jose_jwt, JWTError
    JOSE_AVAILABLE = True
except ImportError:
    JOSE_AVAILABLE = False

import federation_pb2
import federation_pb2_grpc
from fedavg_mock import federated_average, federated_average_state_dicts

# Optional DB integration
try:
    from db_connector import (
        create_db_session,
        fetch_job_config,
        fetch_latest_round_metric,
        record_round_metric,
        update_job_status,
        record_client_submission,
        validate_job_assignment,
    )
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

SERVICE_ROOT = os.path.dirname(__file__)
PROJECT_ROOT = os.path.dirname(SERVICE_ROOT)

load_dotenv(os.path.join(SERVICE_ROOT, ".env"))
load_dotenv(os.path.join(PROJECT_ROOT, "backend", ".env"))


class AggregatorServicer(federation_pb2_grpc.AggregatorServicer):
    def __init__(self, db_url: str = None):
        self.lock = threading.Lock()
        self.active_jobs = {}
        
        self.db_session = None
        if DB_AVAILABLE and db_url:
            try:
                self.db_session, _ = create_db_session(db_url)
                print("[SERVER] Connected to database for Live Rolling Aggregation.")
            except Exception as e:
                print(f"[SERVER WARNING] DB connection failed: {e}")

    def _get_or_create_job(self, job_id):
        """Creates a continuous rolling state dictionary for the specific Job ID."""
        if job_id not in self.active_jobs:
            expected_clients = 1
            if self.db_session and job_id:
                try:
                    config = fetch_job_config(self.db_session, job_id)
                    expected_clients = config.get("expected_clients", 1)
                    update_job_status(self.db_session, job_id, "running")
                except Exception as e:
                    print(f"[SERVER WARNING] Could not load job config for job_id={job_id}: {e}")

            self.active_jobs[job_id] = {
                "rolling_global_state_dict": {},
                "rolling_total_samples": 0,
                "rolling_accuracy": None,
                "rolling_loss": None,
                "participating_clients": set(),
                "total_updates_processed": 0,
                "client_rounds": {},
                "expected_clients": expected_clients,
                "input_columns": [],
                "label_column": "label",
            }

            # Restore in-memory state from the last persisted snapshot
            if self.db_session and job_id:
                try:
                    latest = fetch_latest_round_metric(self.db_session, job_id)
                    if latest and latest.global_weights_snapshot:
                        snapshot = json.loads(latest.global_weights_snapshot)
                        meta = snapshot.get("_meta", {})

                        rolling_state = {
                            key: {"data": info["data"], "shape": info["shape"]}
                            for key, info in snapshot.items()
                            if key != "_meta" and isinstance(info, dict)
                            and "data" in info and "shape" in info
                        }

                        if rolling_state:
                            self.active_jobs[job_id].update({
                                "rolling_global_state_dict": rolling_state,
                                "rolling_total_samples": meta.get("total_samples") or latest.total_samples or 0,
                                "rolling_accuracy": latest.accuracy,
                                "rolling_loss": latest.loss,
                                "participating_clients": set(meta.get("client_labels") or []),
                                "input_columns": meta.get("input_columns") or [],
                                "label_column": meta.get("label_column") or "label",
                                "total_updates_processed": (
                                    ((latest.round_number or 1) - 1) * expected_clients
                                    + min(latest.num_clients or expected_clients, expected_clients)
                                ),
                            })
                            print(f"[SERVER] Restored Job {job_id} from Round {latest.round_number} ({latest.total_samples} samples)")
                except Exception as e:
                    print(f"[SERVER WARNING] Could not restore state for job_id={job_id}: {e}")

        return self.active_jobs[job_id]

    def _validate_job_accepting_updates(self, job_id: int):
        if not job_id:
            return False, "A valid Target Job ID is required."
        if not self.db_session:
            return False, "Database-backed job validation is unavailable on the aggregation server."

        try:
            config = fetch_job_config(self.db_session, job_id)
        except Exception as exc:
            return False, str(exc)

        if config.get("status") not in {"running", "scheduled"}:
            return False, f"Job {job_id} is {config.get('status')} and is not accepting updates."

        return True, config

    def _validate_token(self, context) -> tuple[bool, str, dict]:
        """Validate JWT metadata and return the decoded token payload."""
        secret_key = os.getenv("SECRET_KEY", "")
        if not secret_key:
            return False, "SECRET_KEY is not configured on Gamma, so authenticated streaming is unavailable.", {}

        if not JOSE_AVAILABLE:
            return False, "python-jose is not installed on Gamma, so JWT validation is unavailable.", {}

        metadata = dict(context.invocation_metadata())
        auth_header = metadata.get("authorization", "")
        token = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else auth_header.strip()
        if not token:
            return False, "Authentication required. Provide a valid JWT in the 'authorization' gRPC metadata.", {}

        try:
            payload = jose_jwt.decode(token, secret_key, algorithms=["HS256"])
            if not payload.get("sub"):
                return False, "Invalid token: missing user subject.", {}
            return True, "", payload
        except JWTError as exc:
            return False, f"Invalid or expired token: {exc}", {}

    def SubmitWeightUpdate(self, request, context):
        with self.lock:
            # Fix 3: Validate JWT token
            token_ok, token_msg, token_payload = self._validate_token(context)
            if not token_ok:
                context.set_code(grpc.StatusCode.UNAUTHENTICATED)
                context.set_details(token_msg)
                return federation_pb2.UpdateAck(success=False, message=token_msg)

            job_id = getattr(request, 'job_id', 0)
            job_ok, job_validation = self._validate_job_accepting_updates(job_id)
            if not job_ok:
                context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                context.set_details(job_validation)
                return federation_pb2.UpdateAck(success=False, message=job_validation)

            try:
                token_user_id = int(token_payload.get("sub"))
            except (TypeError, ValueError):
                message = "Invalid token subject."
                context.set_code(grpc.StatusCode.UNAUTHENTICATED)
                context.set_details(message)
                return federation_pb2.UpdateAck(success=False, message=message)

            expected_client_id = f"client_id_{token_user_id}"
            if request.client_id != expected_client_id:
                message = "Client identity mismatch. The stream client_id must match the authenticated user."
                context.set_code(grpc.StatusCode.PERMISSION_DENIED)
                context.set_details(message)
                return federation_pb2.UpdateAck(success=False, message=message)

            if not validate_job_assignment(self.db_session, job_id, token_user_id):
                message = f"Client {token_user_id} is not assigned to Job {job_id}."
                context.set_code(grpc.StatusCode.PERMISSION_DENIED)
                context.set_details(message)
                return federation_pb2.UpdateAck(success=False, message=message)

            if len(request.layers) > 0:
                for tensor in request.layers:
                    for i, value in enumerate(tensor.data):
                        if not math.isfinite(value):
                            msg = f"Non-finite value in layer '{tensor.layer_name}' at index {i}."
                            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                            context.set_details(msg)
                            return federation_pb2.UpdateAck(success=False, message=msg)
                        if abs(value) > 1e6:
                            msg = f"Extreme weight value in layer '{tensor.layer_name}' at index {i}."
                            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                            context.set_details(msg)
                            return federation_pb2.UpdateAck(success=False, message=msg)
                return self._handle_structured_rolling(request, job_id, token_user_id)
            else:
                return federation_pb2.UpdateAck(success=False, message="Only structured payloads are supported in rolling mode.")

    def _handle_structured_rolling(self, request, job_id, token_user_id: int):
        job_state = self._get_or_create_job(job_id)
        
        
        # 1. Parse incoming payload
        state_dict = {}
        for tensor in request.layers:
            state_dict[tensor.layer_name] = {
                "data": list(tensor.data),
                "shape": list(tensor.shape),
            }

        # --- SERVER TRACKING (For the Graph) ---
        job_state["total_updates_processed"] += 1
        global_step = job_state["total_updates_processed"]
        expected_clients = job_state["expected_clients"]
        global_round = ((global_step - 1) // expected_clients) + 1
        updates_in_round = ((global_step - 1) % expected_clients) + 1
        job_state["participating_clients"].add(request.client_id)
        new_samples = request.sample_count

        # --- CLIENT TRACKING (For the Table) ---
        if request.client_id not in job_state["client_rounds"]:
            job_state["client_rounds"][request.client_id] = 0
        job_state["client_rounds"][request.client_id] += 1
        
        client_local_round = job_state["client_rounds"][request.client_id]

        # Parse metrics and column metadata encoded in model_architecture by the sender
        client_accuracy = None
        client_loss = None
        if request.model_architecture:
            try:
                arch_data = json.loads(request.model_architecture)
                client_accuracy = arch_data.get("accuracy")
                client_loss = arch_data.get("loss")
                if not job_state["input_columns"] and arch_data.get("input_columns"):
                    job_state["input_columns"] = arch_data["input_columns"]
                    job_state["label_column"] = arch_data.get("label_column") or "label"
            except json.JSONDecodeError as e:
                print(f"[SERVER WARNING|Job:{job_id}] Could not parse model_architecture JSON from {request.client_id}: {e}. Accuracy/loss/columns will not be recorded for this submission.")
            except (AttributeError, TypeError) as e:
                print(f"[SERVER WARNING|Job:{job_id}] Unexpected model_architecture format from {request.client_id}: {e}.")

        # Write receipt to database to unlock UI and show Client metrics
        if self.db_session:
            try:
                record_client_submission(
                    session=self.db_session,
                    job_id=job_id,
                    client_id_str=request.client_id,
                    round_number=client_local_round,
                    sample_count=new_samples,
                    state_dict=state_dict,
                    accuracy=client_accuracy,
                    loss=client_loss,
                    user_id=token_user_id,
                )
            except Exception as e:
                print(f"[SERVER ERROR] Failed to record client submission: {e}")

        print(f"\n[SERVER|Job:{job_id}] Received update from {request.client_id} (Samples: {new_samples})")

        # 2. Mathematical Rolling Average (weights, accuracy, loss)
        old_total = job_state["rolling_total_samples"]
        new_total = old_total + new_samples

        if not job_state["rolling_global_state_dict"]:
            job_state["rolling_global_state_dict"] = state_dict
            print(f"[SERVER|Job:{job_id}] Initialized new Global Model baseline.")
        else:
            for layer in state_dict:
                if layer in job_state["rolling_global_state_dict"]:
                    for i in range(len(state_dict[layer]["data"])):
                        old_val = job_state["rolling_global_state_dict"][layer]["data"][i]
                        new_val = state_dict[layer]["data"][i]
                        job_state["rolling_global_state_dict"][layer]["data"][i] = (
                            (old_val * old_total) + (new_val * new_samples)
                        ) / new_total
            print(f"[SERVER|Job:{job_id}] Rolled new weights into Global Model. Total Network Samples: {new_total}")

        job_state["rolling_total_samples"] = new_total

        # Rolling weighted average for accuracy and loss across all clients.
        if client_accuracy is not None:
            old_acc = job_state["rolling_accuracy"]
            job_state["rolling_accuracy"] = (
                client_accuracy if (old_acc is None or old_total == 0)
                else ((old_acc * old_total) + (client_accuracy * new_samples)) / new_total
            )

        if client_loss is not None:
            old_loss = job_state["rolling_loss"]
            job_state["rolling_loss"] = (
                client_loss if (old_loss is None or old_total == 0)
                else ((old_loss * old_total) + (client_loss * new_samples)) / new_total
            )

        acc_display = f"{job_state['rolling_accuracy']:.4f}" if job_state["rolling_accuracy"] is not None else "N/A"
        loss_display = f"{job_state['rolling_loss']:.4f}" if job_state["rolling_loss"] is not None else "N/A"
        print(f"[SERVER|Job:{job_id}] Metrics — accuracy={acc_display} loss={loss_display}")

        # 3. Build Snapshot and Save Global Metrics
        # Store the full per-layer weights so the snapshot can be reconstructed as a .pt checkpoint.
        snapshot_data = {
            layer: {
                "shape": info["shape"],
                "data": info["data"],
                "mean": sum(info["data"]) / max(len(info["data"]), 1),
                "num_params": len(info["data"]),
            }
            for layer, info in job_state["rolling_global_state_dict"].items()
        }
        # Inject client labels so the React tooltip works.
        snapshot_data["_meta"] = {
            "client_labels": list(job_state["participating_clients"]),
            "total_samples": job_state["rolling_total_samples"],
            "input_columns": job_state["input_columns"],
            "label_column": job_state["label_column"],
        }

        self._record_metrics_to_db(
            job_id=job_id,
            current_round=global_round,
            num_clients=updates_in_round,
            total_samples=job_state["rolling_total_samples"],
            accuracy=job_state["rolling_accuracy"],
            loss=job_state["rolling_loss"],
            global_weights_snapshot=snapshot_data,
        )

        return federation_pb2.UpdateAck(
            success=True,
            message=f"Live Aggregation Complete! Folded {new_samples} samples into Job {job_id}."
        )

    def _record_metrics_to_db(self, job_id, current_round, num_clients, total_samples,
                               accuracy, loss, global_weights_snapshot):
        if not self.db_session or not job_id:
            return
        try:
            record_round_metric(
                session=self.db_session,
                job_id=job_id,
                round_number=current_round,
                accuracy=accuracy,
                loss=loss,
                num_clients=num_clients,
                total_samples=total_samples,
                global_weights_snapshot=global_weights_snapshot,
            )
        except Exception as e:
            print(f"[SERVER WARNING] DB Write Failed: {e}")


def serve(db_url: str = None, port: int = 50051):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    federation_pb2_grpc.add_AggregatorServicer_to_server(
        AggregatorServicer(db_url=db_url),
        server,
    )
    server.add_insecure_port(f'[::]:{port}')
    print(f"[SERVER] gRPC Aggregator listening on port {port}...")
    print("[SERVER] Operating in Multi-Tenant Mode")
    server.start()
    server.wait_for_termination()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="FederHub Gamma gRPC aggregation server")
    parser.add_argument("--port", type=int, default=int(os.getenv("GRPC_PORT", "50051")))
    parser.add_argument("--db-url", default=os.getenv("DATABASE_URL", ""))
    args = parser.parse_args()

    serve(
        db_url=args.db_url or None,
        port=args.port,
    )
