#!/usr/bin/env python3
"""
Convert a FederHub global model JSON download into a PyTorch .pt checkpoint.

The JSON from /jobs/{id}/model contains per-layer weights stored by the gRPC
aggregation server. This script reconstructs the state_dict and saves a .pt
file that can be loaded directly as a checkpoint for the next training round.

Usage (via Docker):
    python3 /app/ml/convert_model.py /data/model.json /output/checkpoint.pt
"""
import json
import sys
from pathlib import Path

try:
    import torch
except ImportError:
    print("ERROR: PyTorch is required. Run inside the federhub-beta-trainer container.", file=sys.stderr)
    sys.exit(1)


def convert(json_path: str, pt_path: str) -> None:
    with open(json_path, "r") as f:
        payload = json.load(f)

    # The weights dict is nested under "weights" in the API response.
    weights_data = payload.get("weights", payload)

    state_dict = {}
    for layer_name, layer_info in weights_data.items():
        # Skip metadata keys.
        if layer_name in ("_meta",) or not isinstance(layer_info, dict):
            continue
        if "data" not in layer_info or "shape" not in layer_info:
            continue

        tensor = torch.tensor(
            layer_info["data"], dtype=torch.float32
        ).reshape(layer_info["shape"])
        state_dict[layer_name] = tensor

    if not state_dict:
        print(
            "ERROR: No layer weights found in the JSON.\n"
            "This job may have been aggregated via the REST path (flat weights only) "
            "or the snapshot predates the full-weight storage fix.",
            file=sys.stderr,
        )
        sys.exit(1)

    input_columns = payload.get("input_columns") or []
    label_column = payload.get("label_column") or "label"
    if not input_columns:
        print(
            "ERROR: This model download is missing dataset schema metadata. "
            "Train from a FederHub checkpoint that includes input_columns and label_column.",
            file=sys.stderr,
        )
        sys.exit(1)

    checkpoint = {
        "state_dict": state_dict,
        "job_id": payload.get("job_id"),
        "job_name": payload.get("job_name"),
        "round_number": payload.get("round_number"),
        "input_columns": input_columns,
        "label_column": label_column,
    }

    Path(pt_path).parent.mkdir(parents=True, exist_ok=True)
    torch.save(checkpoint, pt_path)

    print(f"Checkpoint saved: {pt_path}", flush=True)
    print(f"Layers: {', '.join(state_dict.keys())}", flush=True)
    print(f"Total parameters: {sum(t.numel() for t in state_dict.values())}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.json> <output.pt>", file=sys.stderr)
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
