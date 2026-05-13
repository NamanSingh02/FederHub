import argparse
import csv
import json
import os
import sys
from pathlib import Path

try:
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset
except ImportError as exc:
    raise SystemExit(
        "PyTorch is not installed. Install it with `pip install torch` before running training."
    ) from exc


DEFAULT_LABEL_COLUMN = "label"


def read_columns_from_csv(csv_path: Path, label_column: str) -> list[str]:
    """Read input column names directly from a CSV header, excluding the label column."""
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, [])
    return [col.strip() for col in header if col.strip() and col.strip() != label_column]


def resolve_dataset_path(input_dir: Path | None, csv_path: Path | None):
    if csv_path is not None:
        return csv_path.resolve()

    if input_dir is None:
        raise ValueError("Provide either --data or --input-dir before starting training.")

    csv_candidates = sorted(input_dir.glob("*.csv"))
    if not csv_candidates:
        raise ValueError(
            f"No CSV files were found in {input_dir}. Place a dataset CSV in the selected folder."
        )

    return csv_candidates[0].resolve()


def load_checkpoint_metadata(checkpoint_path: Path | None) -> dict:
    """Load column metadata from a checkpoint. Returns had_columns=False if not embedded."""
    if checkpoint_path is None:
        return {"input_columns": None, "label_column": DEFAULT_LABEL_COLUMN, "had_columns": False}

    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    metadata = checkpoint if isinstance(checkpoint, dict) else {}

    input_columns = metadata.get("input_columns") or metadata.get("feature_columns")
    label_column = metadata.get("label_column") or DEFAULT_LABEL_COLUMN

    return {
        "input_columns": list(input_columns) if input_columns else None,
        "label_column": label_column,
        "had_columns": bool(input_columns),
    }


def load_dataset(csv_path: Path, input_columns: list[str], label_column: str):
    features = []
    labels = []

    with csv_path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        required_columns = set(input_columns + [label_column])
        missing_columns = required_columns.difference(reader.fieldnames or [])
        if missing_columns:
            raise ValueError(
                "Dataset is missing required columns: "
                + ", ".join(sorted(missing_columns))
            )

        for row in reader:
            features.append([float(row[column]) for column in input_columns])
            labels.append(float(row[label_column]))

    if len(features) == 0:
        raise ValueError(
            "Training dataset is empty. Ensure the CSV file contains at least "
            "one data row before training."
        )

    x_tensor = torch.tensor(features, dtype=torch.float32)
    y_tensor = torch.tensor(labels, dtype=torch.float32).unsqueeze(1)
    return TensorDataset(x_tensor, y_tensor)


def create_model(input_size: int):
    return nn.Sequential(
        nn.Linear(input_size, 8),
        nn.ReLU(),
        nn.Linear(8, 1),
        nn.Sigmoid(),
    )


def load_checkpoint_if_present(model: nn.Module, checkpoint_path: Path | None):
    if checkpoint_path is None:
        print("Checkpoint: starting from a fresh model.", flush=True)
        return

    try:
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
        state_dict = checkpoint.get("state_dict", checkpoint) if isinstance(checkpoint, dict) else checkpoint
        model.load_state_dict(state_dict)
    except Exception as exc:
        raise ValueError(
            "The selected checkpoint could not be loaded into the current model layout. "
            "Choose a compatible `.pt` file."
        ) from exc
    print(f"Checkpoint loaded from: {checkpoint_path}", flush=True)


def build_output_checkpoint_path(output_dir: Path, checkpoint_path: Path | None):
    if checkpoint_path is not None:
        return output_dir / f"updated_{checkpoint_path.name}"
    return output_dir / "updated_model.pt"


def train_model(
    dataset: TensorDataset,
    epochs: int,
    checkpoint_path: Path | None,
    input_size: int,
):
    loader = DataLoader(dataset, batch_size=4, shuffle=True)
    model = create_model(input_size)
    load_checkpoint_if_present(model, checkpoint_path)

    loss_fn = nn.BCELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.03)

    final_accuracy = 0.0
    final_loss = 0.0

    for epoch in range(1, epochs + 1):
        epoch_loss = 0.0
        correct_predictions = 0
        total_examples = 0

        for batch_inputs, batch_labels in loader:
            optimizer.zero_grad()
            outputs = model(batch_inputs)
            loss = loss_fn(outputs, batch_labels)
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item() * len(batch_inputs)
            predictions = (outputs >= 0.5).float()
            correct_predictions += (predictions == batch_labels).sum().item()
            total_examples += len(batch_inputs)

        if total_examples == 0:
            raise ValueError(
                "Training dataset is empty. Ensure the CSV file contains at least "
                "one data row before training."
            )

        final_accuracy = correct_predictions / total_examples
        final_loss = epoch_loss / total_examples
        print(
            f"Epoch {epoch:02d} | loss={final_loss:.4f} | accuracy={final_accuracy:.2%}",
            flush=True,
        )

    return model, final_accuracy, final_loss


def flush_sensitive_tensors(*tensors):
    for tensor in tensors:
        if tensor is not None:
            tensor.zero_()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def main():
    parser = argparse.ArgumentParser(description="FederHub Team Beta Phase 2/3 trainer")
    parser.add_argument("--data", help="Path to a CSV dataset")
    parser.add_argument('--job-id', type=int, default=0, help='Target Job ID for Gamma aggregation')
    parser.add_argument(
        "--input-dir",
        help="Directory containing the client dataset CSV mounted into the Docker sandbox",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for saved model files")
    parser.add_argument(
        "--selected-folder",
        default="",
        help="Folder selected in the desktop client for local data mapping",
    )
    parser.add_argument(
        "--checkpoint",
        help="Optional .pt checkpoint path to load before local training",
    )
    parser.add_argument("--operator", default="", help="Client operator username")
    parser.add_argument("--epochs", type=int, default=8, help="Number of local training epochs")
    parser.add_argument(
        "--server",
        default="",
        help="Phase 3: Gamma gRPC server address to stream weights to (e.g. localhost:50051)",
    )
    parser.add_argument(
        "--client-id",
        default="",
        help="Phase 3: Identifier for this edge node (e.g. 'Hospital A')",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve() if args.input_dir else None
    csv_path = Path(args.data).resolve() if args.data else None
    checkpoint_path = Path(args.checkpoint).resolve() if args.checkpoint else None
    data_path = resolve_dataset_path(input_dir, csv_path)
    checkpoint_metadata = load_checkpoint_metadata(checkpoint_path)
    label_column = checkpoint_metadata["label_column"]

    # Always read column names from the CSV — it is the ground truth for this client's data.
    # Checkpoint-embedded columns are only used when no CSV is available (e.g. standalone sender).
    input_columns = read_columns_from_csv(data_path, label_column)
    if not input_columns:
        if checkpoint_metadata["had_columns"]:
            input_columns = checkpoint_metadata["input_columns"]
            print(f"CSV had no usable columns — falling back to checkpoint metadata: {', '.join(input_columns)}", flush=True)
        else:
            raise ValueError(
                "Could not detect input columns. The CSV header is empty or only contains the label column."
            )
    else:
        print(f"Columns read from CSV: {', '.join(input_columns)}", flush=True)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("FederHub Beta trainer starting...", flush=True)
    if args.operator:
        print(f"Operator: {args.operator}", flush=True)
    print(
        f"Checkpoint: {checkpoint_path if checkpoint_path else '[fresh model]'}",
        flush=True,
    )
    print(f"Input columns: {', '.join(input_columns)}", flush=True)
    print(f"Label column: {label_column}", flush=True)
    print(f"Dataset: {data_path}", flush=True)
    print(
        f"Selected local folder: {args.selected_folder or '[not provided in this demo]'}",
        flush=True,
    )

    dataset = load_dataset(data_path, input_columns, label_column)

    training_inputs = dataset.tensors[0].clone()
    training_labels = dataset.tensors[1].clone()
    training_dataset = TensorDataset(training_inputs, training_labels)

    model, final_accuracy, final_loss = train_model(
        training_dataset,
        args.epochs,
        checkpoint_path,
        len(input_columns),
    )

    weights_path = build_output_checkpoint_path(output_dir, checkpoint_path)
    metadata_path = output_dir / "run_summary.json"
    torch.save({
        "state_dict": model.state_dict(),
        "input_columns": input_columns,
        "label_column": label_column,
    }, weights_path)

    metadata = {
        "weights_path": str(weights_path),
        "epochs": args.epochs,
        "checkpoint": str(checkpoint_path) if checkpoint_path else "",
        "operator": args.operator,
        "input_columns": input_columns,
        "label_column": label_column,
        "selected_folder": args.selected_folder,
        "input_dir": str(input_dir) if input_dir else "",
        "dataset": str(data_path),
        "sample_count": len(dataset),
        "final_accuracy": round(final_accuracy, 6),
        "final_loss": round(final_loss, 6),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    flush_sensitive_tensors(training_inputs, training_labels)

    print(f"Saved weights to: {weights_path}", flush=True)
    print(f"Saved run summary to: {metadata_path}", flush=True)
    print(
        "Memory flush step completed for in-process training tensors. Only model weights remain.",
        flush=True,
    )

    # --- Phase 3: Stream weights to Gamma's aggregation server ---
    if args.server:
        client_id = args.client_id or args.operator or "anonymous-client"
        print(f"\n[PHASE 3] Streaming trained weights to Gamma server at {args.server}...", flush=True)
        try:
            # Import the sender module from the beta directory
            sender_dir = Path(__file__).resolve().parent.parent
            sys.path.insert(0, str(sender_dir))
            from grpc_weight_sender import send_weights

            success = send_weights(
                pt_path=str(weights_path),
                summary_path=str(metadata_path),
                server_address=args.server,
                client_id=client_id,
                job_id=args.job_id,
                token=os.environ.get("FEDERHUB_TOKEN", ""),
            )
            if success:
                print("[PHASE 3] Weight streaming complete. Only mathematical updates were transmitted.", flush=True)
            else:
                print("[PHASE 3] Weight streaming failed. Weights are still saved locally.", flush=True)
        except Exception as e:
            print(f"[PHASE 3] Weight streaming error: {e}. Weights are still saved locally.", flush=True)


if __name__ == "__main__":
    main()
