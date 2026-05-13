import json
import sys
from pathlib import Path

try:
    import torch
except Exception as exc:
    print(json.dumps({
        "ok": False,
        "columns": [],
        "summary": f"PyTorch is not available in this environment: {exc}",
    }))
    raise SystemExit(0)


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "ok": False,
            "columns": [],
            "summary": "No checkpoint path provided.",
        }))
        return

    path = Path(sys.argv[1]).resolve()

    try:
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    except Exception as exc:
        print(json.dumps({
            "ok": False,
            "columns": [],
            "summary": f"Checkpoint could not be read: {exc}",
        }))
        return

    metadata = checkpoint if isinstance(checkpoint, dict) else {}
    input_columns = metadata.get("input_columns") or metadata.get("feature_columns") or []
    label_column = metadata.get("label_column") or "label"

    if input_columns:
        columns = list(input_columns) + [label_column]
        print(json.dumps({
            "ok": True,
            "columns": columns,
            "summary": f"Required CSV columns: {', '.join(columns)}.",
        }))
        return

    # No column metadata — fail clearly instead of guessing
    print(json.dumps({
        "ok": False,
        "columns": [],
        "summary": (
            "This checkpoint does not contain column metadata. "
            "Use a checkpoint produced by FederHub training, or download one from the job page."
        ),
    }))


if __name__ == "__main__":
    main()
