import pytest
import sys
from pathlib import Path

# Ensure Python can find your fedavg_mock.py file
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fedavg_mock import federated_average, federated_average_state_dicts

def test_flat_federated_average_equal_weights():
    """
    Test 1: Two hospitals submit flat arrays with EQUAL sample counts.
    The result should be a perfect 50/50 split.
    """
    client_weights = [
        [1.0, 2.0, 3.0],  # Hospital A
        [3.0, 4.0, 5.0]   # Hospital B
    ]
    sample_counts = [100, 100]  # Both have 100 patients

    # Expected: (1+3)/2=2.0, (2+4)/2=3.0, (3+5)/2=4.0
    global_weights = federated_average(client_weights, sample_counts)
    
    assert global_weights == [2.0, 3.0, 4.0]

def test_flat_federated_average_unequal_weights():
    """
    Test 2: Two hospitals submit flat arrays with UNEQUAL sample counts.
    Hospital B has 3x more patients, so its weights should dominate the average.
    """
    client_weights = [
        [1.0, 1.0],  # Hospital A
        [5.0, 5.0]   # Hospital B
    ]
    sample_counts = [10, 30]  # Total samples = 40

    # Expected for index 0: ((1.0 * 10) + (5.0 * 30)) / 40 = 160 / 40 = 4.0
    global_weights = federated_average(client_weights, sample_counts)
    
    assert global_weights == [4.0, 4.0]

def test_structured_federated_average():
    """
    Test 3: Two hospitals submit complex PyTorch State Dictionaries (Phase 3).
    Ensures multi-layer nested data is averaged correctly.
    """
    client_state_dicts = [
        {
            "layer1.weight": {"data": [2.0, 4.0], "shape": [2]},
            "layer1.bias":   {"data": [10.0], "shape": [1]}
        },
        {
            "layer1.weight": {"data": [6.0, 8.0], "shape": [2]},
            "layer1.bias":   {"data": [20.0], "shape": [1]}
        }
    ]
    sample_counts = [50, 50]  # 50/50 split

    global_state_dict = federated_average_state_dicts(client_state_dicts, sample_counts)

    # Assert shapes are preserved
    assert global_state_dict["layer1.weight"]["shape"] == [2]
    assert global_state_dict["layer1.bias"]["shape"] == [1]

    # Assert mathematical averages
    assert global_state_dict["layer1.weight"]["data"] == [4.0, 6.0]
    assert global_state_dict["layer1.bias"]["data"] == [15.0]

def test_empty_submissions_raise_error():
    """
    Test 4: Edge Case. If the server tries to average 0 clients, it should raise a ValueError,
    preventing a Divide-By-Zero crash.
    """
    with pytest.raises(ValueError):
        federated_average(client_weights=[], sample_counts=[])