# grpc_weight_sender.py
# ======================
# FederHub - Team Beta × Team Gamma | Phase 3
# --------------------------------------------
# After local PyTorch training completes, this module loads the saved
# model checkpoint (.pt file), serializes the state_dict into Protobuf
# TensorData messages, and streams only the mathematical weight updates
# to Team Gamma's gRPC aggregation server.
#
# No raw patient/financial data ever leaves the client — only model
# parameters are transmitted.
#
# Usage:
#   python grpc_weight_sender.py \
#       --pt-file output/updated_model.pt \
#       --summary-file output/run_summary.json \
#       --server localhost:50051 \
#       --client-id "Hospital A"

import argparse
import json
import sys
from pathlib import Path

try:
    import torch
except ImportError:
    print("[SENDER ERROR] PyTorch is required. Install with: pip install torch")
    sys.exit(1)

import grpc

current_dir = Path(__file__).resolve().parent
candidate_proto_dirs = [
    current_dir / "federated-engine",
    current_dir.parent / "federated-engine",
    Path("/app/federated-engine"),
]

for proto_dir in candidate_proto_dirs:
    if proto_dir.exists():
        sys.path.insert(0, str(proto_dir))
        break

import federation_pb2
import federation_pb2_grpc


def load_checkpoint(pt_path: str) -> tuple[dict, list[str], str]:
    """Load state_dict and column metadata from a .pt checkpoint file."""
    checkpoint = torch.load(pt_path, map_location="cpu", weights_only=True)

    if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
        state_dict = checkpoint["state_dict"]
        input_columns = checkpoint.get("input_columns") or []
        label_column = checkpoint.get("label_column") or "label"
    else:
        state_dict = checkpoint
        input_columns = []
        label_column = "label"

    return state_dict, input_columns, label_column


def get_training_metrics(summary_path: str) -> dict:
    """Read sample count, accuracy, and loss from a run_summary.json file."""
    if not summary_path or not Path(summary_path).exists():
        raise RuntimeError(
            f"run_summary.json not found at '{summary_path}'. "
            "Cannot determine sample count — a missing or fabricated value would corrupt the federated weighted average."
        )

    with open(summary_path, "r") as f:
        summary = json.load(f)

    metrics = {
        "accuracy": summary.get("final_accuracy"),
        "loss": summary.get("final_loss"),
    }

    # Prefer the saved sample_count; fall back to counting CSV rows
    sample_count = summary.get("sample_count")
    if not sample_count:
        dataset_path = summary.get("dataset", "")
        if dataset_path and Path(dataset_path).exists():
            try:
                with open(dataset_path, "r") as csv_f:
                    sample_count = max(sum(1 for _ in csv_f) - 1, 0)
            except OSError as e:
                raise RuntimeError(
                    f"sample_count is missing from run_summary.json and the dataset CSV "
                    f"at '{dataset_path}' could not be read to count rows: {e}"
                ) from e

    if not sample_count:
        raise RuntimeError(
            "sample_count could not be determined: it is missing from run_summary.json "
            "and the dataset path is unavailable. Cannot submit weights — a fabricated "
            "sample count would corrupt the federated weighted average."
        )

    metrics["sample_count"] = sample_count
    return metrics


def state_dict_to_proto_layers(state_dict: dict) -> list:
    """Convert a PyTorch state_dict into a list of TensorData protos."""
    layers = []
    for layer_name, tensor in state_dict.items():
        tensor_data = federation_pb2.TensorData(
            layer_name=str(layer_name),
            shape=list(tensor.shape),
            data=tensor.flatten().tolist(),
        )
        layers.append(tensor_data)
    return layers


def describe_model(state_dict: dict) -> str:
    """Generate a human-readable architecture summary from the state_dict."""
    parts = []
    for name, tensor in state_dict.items():
        parts.append(f"{name}: {list(tensor.shape)}")
    return " | ".join(parts)


def send_weights(
    pt_path: str,
    summary_path: str,
    server_address: str,
    client_id: str,
    job_id: int = 0,
    token: str = "",
) -> bool:
    """
    Load a .pt file and send the weights to Gamma's gRPC server.

    Args:
        pt_path: Path to the .pt checkpoint file.
        summary_path: Path to run_summary.json (for sample count and metrics).
        server_address: Gamma server address (e.g. "localhost:50051").
        client_id: Identifier for this edge node (e.g. "Hospital A").
        job_id: Target job ID for multi-tenant routing.

    Returns:
        True if the submission was acknowledged, False otherwise.
    """
    # 1. Load the model weights
    print(f"[SENDER] Loading checkpoint: {pt_path}")
    state_dict, input_columns, label_column = load_checkpoint(pt_path)

    total_params = sum(t.numel() for t in state_dict.values())
    print(f"[SENDER] Model loaded: {len(state_dict)} layers, {total_params} parameters.")
    if input_columns:
        print(f"[SENDER] Columns: {', '.join(input_columns)} → {label_column}")

    # 2. Get sample count and training metrics from run_summary.json
    metrics = get_training_metrics(summary_path)
    sample_count = metrics["sample_count"]
    print(f"[SENDER] Sample count: {sample_count}")
    if metrics["accuracy"] is not None:
        print(f"[SENDER] Final accuracy: {metrics['accuracy']:.4f} | loss: {metrics['loss']:.4f}")

    # 3. Serialize into protobuf
    # Encode accuracy/loss in model_architecture as JSON so the server can store real metrics
    layers = state_dict_to_proto_layers(state_dict)
    metrics_payload = json.dumps({
        "architecture": describe_model(state_dict),
        "accuracy": metrics["accuracy"],
        "loss": metrics["loss"],
        "input_columns": input_columns,
        "label_column": label_column,
    })

    request = federation_pb2.WeightUpdate(
        client_id=client_id,
        sample_count=sample_count,
        layers=layers,
        model_architecture=metrics_payload,
        job_id=job_id,
    )

    # 4. Send to Gamma's server
    print(f"[SENDER] Connecting to Gamma aggregation server at {server_address}...")
    channel = grpc.insecure_channel(server_address)
    stub = federation_pb2_grpc.AggregatorStub(channel)

    metadata = []
    if token:
        metadata.append(("authorization", f"Bearer {token}"))

    try:
        response = stub.SubmitWeightUpdate(request, timeout=30, metadata=metadata)
        print(f"[SENDER] Server response: {response.message}")
        channel.close()
        return response.success
    except grpc.RpcError as e:
        print(f"[SENDER ERROR] gRPC call failed: {e.code()} - {e.details()}")
        channel.close()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="FederHub Phase 3: Stream trained PyTorch weights to Gamma's aggregation server"
    )
    parser.add_argument(
        "--pt-file", required=True,
        help="Path to the .pt checkpoint file containing trained model weights"
    )
    parser.add_argument(
        "--summary-file", default="",
        help="Path to run_summary.json (used to determine sample count)"
    )
    parser.add_argument(
        "--server", default="localhost:50051",
        help="Gamma gRPC server address (default: localhost:50051)"
    )
    parser.add_argument(
        "--client-id", required=True,
        help="Identifier for this edge node (e.g. 'Hospital A')"
    )
    parser.add_argument(
        "--job-id", type=int, default=0,
        help="Target Job ID to submit weights to (required for multi-job isolation)"
    )
    args = parser.parse_args()

    success = send_weights(
        pt_path=args.pt_file,
        summary_path=args.summary_file,
        server_address=args.server,
        client_id=args.client_id,
        job_id=args.job_id,
    )

    if success:
        print("[SENDER] Weight submission complete. Only mathematical updates were transmitted.")
    else:
        print("[SENDER] Weight submission failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
