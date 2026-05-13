"""
fedavg_mock.py
==============
FederHub - Group 3 (Team Gamma): Phase 1 Deliverable
-----------------------------------------------------
Mocks the Federated Averaging (FedAvg) algorithm as described in:
    McMahan et al., "Communication-Efficient Learning of Deep Networks
    from Decentralized Data" (2017).

User Story Traceability:
    - Epic 5, Story 5.1: "As an ML Engineer, I want the central server to
      mathematically average the client weights, so that a new, smarter
      Master Model is created."
    - Epic 2, Story 2.3: Aggregation service receives client updates and
      computes a new global model each round.

Phase 1 Scope:
    - No real clients. No network. No gRPC.
    - Hardcoded client weight arrays simulate what clients would send.
    - Weighted average by sample size (true FedAvg, not naive mean).
    - Foundation for Phase 2 (real gRPC weight transmission).

Why Weighted Average (not simple mean)?
    Simple mean treats all clients equally regardless of how much data
    they trained on. FedAvg weights each client's contribution
    proportionally to their local dataset size, producing a fairer and
    more accurate global model. This matches the original paper and
    our aggregation service design in the system architecture.
"""

from typing import List, Tuple


def federated_average(
    client_weights: List[List[float]],
    sample_counts: List[int]
) -> List[float]:
    """
    Compute the Federated Average of client model weights.

    Each client's weights are scaled by the proportion of total training
    samples they contributed, then summed into a single global weight vector.

    Formula:
        global_w[i] = Σ (n_k / n_total) * w_k[i]
        where n_k = samples for client k, n_total = sum of all samples.

    Args:
        client_weights (List[List[float]]):
            List of weight arrays, one per client.
            Each inner list represents the model parameters (e.g., layer weights).
        sample_counts (List[int]):
            Number of training samples each client used locally.
            Must be the same length as client_weights.

    Returns:
        List[float]: The aggregated global model weights.

    Raises:
        ValueError: If inputs are mismatched or empty.
    """
    if not client_weights or not sample_counts:
        raise ValueError("client_weights and sample_counts must not be empty.")

    if len(client_weights) != len(sample_counts):
        raise ValueError(
            f"Mismatch: {len(client_weights)} weight arrays "
            f"but {len(sample_counts)} sample counts."
        )

    if any(n < 0 for n in sample_counts):
        raise ValueError("Sample counts must be non-negative.")

    weight_lengths = {len(w) for w in client_weights}
    if len(weight_lengths) > 1:
        raise ValueError(
            "All client weight arrays must have the same length. "
            f"Got lengths: {weight_lengths}"
        )

    n_total = sum(sample_counts)
    if n_total == 0:
        raise ValueError("Total sample count must be greater than zero.")

    n_params = len(client_weights[0])
    global_weights = [0.0] * n_params

    for weights, n_k in zip(client_weights, sample_counts):
        contribution = n_k / n_total
        for i in range(n_params):
            global_weights[i] += contribution * weights[i]

    return global_weights


def federated_average_state_dicts(
    client_state_dicts: List[dict],
    sample_counts: List[int],
) -> dict:
    """
    Compute Federated Average over structured PyTorch state dicts.

    Each state dict maps layer names to lists of floats (flattened tensors).
    Aggregation is performed per-layer with weighting proportional to each
    client's local dataset size.

    Args:
        client_state_dicts: List of dicts, where each dict maps
            layer_name -> {"data": List[float], "shape": List[int]}.
        sample_counts: Number of training samples each client used locally.

    Returns:
        dict: Aggregated global state dict with the same structure.

    Raises:
        ValueError: If inputs are mismatched or empty.
    """
    if not client_state_dicts or not sample_counts:
        raise ValueError("client_state_dicts and sample_counts must not be empty.")

    if len(client_state_dicts) != len(sample_counts):
        raise ValueError(
            f"Mismatch: {len(client_state_dicts)} state dicts "
            f"but {len(sample_counts)} sample counts."
        )

    if any(n < 0 for n in sample_counts):
        raise ValueError("Sample counts must be non-negative.")

    n_total = sum(sample_counts)
    if n_total == 0:
        raise ValueError("Total sample count must be greater than zero.")

    # All clients must have the same layer names
    reference_layers = list(client_state_dicts[0].keys())
    for i, sd in enumerate(client_state_dicts):
        if list(sd.keys()) != reference_layers:
            raise ValueError(
                f"Client {i} has different layer names than client 0. "
                f"Expected {reference_layers}, got {list(sd.keys())}"
            )

    global_state_dict = {}
    for layer_name in reference_layers:
        ref_data = client_state_dicts[0][layer_name]["data"]
        n_params = len(ref_data)
        aggregated = [0.0] * n_params

        for sd, n_k in zip(client_state_dicts, sample_counts):
            contribution = n_k / n_total
            layer_data = sd[layer_name]["data"]
            if len(layer_data) != n_params:
                raise ValueError(
                    f"Layer '{layer_name}' size mismatch: expected {n_params}, "
                    f"got {len(layer_data)}"
                )
            for j in range(n_params):
                aggregated[j] += contribution * layer_data[j]

        global_state_dict[layer_name] = {
            "data": aggregated,
            "shape": list(client_state_dicts[0][layer_name]["shape"]),
        }

    return global_state_dict


def run_mock_aggregation_round(round_number: int = 1) -> None:
    """
    Simulate a single federated aggregation round with hardcoded client data.

    Phase 1 Mock Setup:
        - 3 simulated clients (e.g., Hospital A, Hospital B, Bank C)
        - Each has a 6-parameter weight vector (mocking a small model)
        - Sample counts differ to demonstrate weighted averaging

    In Phase 2, these hardcoded values will be replaced by real weight
    arrays received over gRPC from actual client Docker containers.

    Args:
        round_number (int): The current training round number (for logging).
    """
    print("=" * 55)
    print(f"  FederHub - Federated Aggregation Mock | Round {round_number}")
    print("=" * 55)

    # --- Simulated Client Data ---
    # In production (Phase 3+), these arrive via gRPC from edge nodes.
    # Weights represent model parameters after local training.
    # Sample counts represent the local dataset size at each org.

    clients: List[Tuple[str, List[float], int]] = [
        (
            "Hospital A",
            [0.10, 0.25, 0.38, 0.47, 0.60, 0.72],
            300  # 300 local patient records
        ),
        (
            "Hospital B",
            [0.15, 0.20, 0.42, 0.50, 0.55, 0.68],
            500  # 500 local patient records (larger dataset, more influence)
        ),
        (
            "Bank C",
            [0.12, 0.30, 0.35, 0.44, 0.63, 0.75],
            200  # 200 local financial records
        ),
    ]

    print("\n[INPUT] Client Weight Updates Received:")
    print(f"  {'Client':<15} {'Samples':>8}   {'Weights'}")
    print(f"  {'-'*15} {'-'*8}   {'-'*30}")

    client_names = [c[0] for c in clients]
    client_weights = [c[1] for c in clients]
    sample_counts = [c[2] for c in clients]

    for name, weights, n in clients:
        formatted = [f"{w:.4f}" for w in weights]
        print(f"  {name:<15} {n:>8}   {formatted}")

    # --- Aggregation ---
    global_weights = federated_average(client_weights, sample_counts)

    # --- Results ---
    total_samples = sum(sample_counts)
    print(f"\n[AGGREGATION] FedAvg applied across {len(clients)} clients.")
    print(f"  Total samples used : {total_samples}")
    print(f"  Weight contributions:")
    for name, n in zip(client_names, sample_counts):
        pct = (n / total_samples) * 100
        print(f"    {name:<15} -> {pct:.1f}% influence")

    formatted_global = [f"{w:.6f}" for w in global_weights]
    print(f"\n[OUTPUT] New Global Model Weights:")
    print(f"  {formatted_global}")
    print("\n[STATUS] Aggregation complete. Global model ready for distribution.")
    print("=" * 55)


if __name__ == "__main__":
    run_mock_aggregation_round(round_number=1)