# test_phase3_integration.py
# ===========================
# FederHub Federated Engine — FedAvg Math Unit Tests

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fedavg_mock import federated_average_state_dicts


class TestFedAvgStateDicts(unittest.TestCase):
    """Unit tests for the new federated_average_state_dicts function."""

    def test_equal_weights_two_clients(self):
        """Two clients with equal samples -> simple average."""
        sd1 = {
            "layer1": {"data": [1.0, 2.0, 3.0], "shape": [3]},
            "layer2": {"data": [4.0, 5.0], "shape": [2]},
        }
        sd2 = {
            "layer1": {"data": [3.0, 4.0, 5.0], "shape": [3]},
            "layer2": {"data": [6.0, 7.0], "shape": [2]},
        }

        result = federated_average_state_dicts([sd1, sd2], [100, 100])

        # Simple average: (1+3)/2=2, (2+4)/2=3, (3+5)/2=4
        for expected, actual in zip([2.0, 3.0, 4.0], result["layer1"]["data"]):
            self.assertAlmostEqual(expected, actual, places=6)
        for expected, actual in zip([5.0, 6.0], result["layer2"]["data"]):
            self.assertAlmostEqual(expected, actual, places=6)

    def test_weighted_average(self):
        """Weighted FedAvg: 300 vs 700 samples."""
        sd1 = {"w": {"data": [10.0], "shape": [1]}}
        sd2 = {"w": {"data": [20.0], "shape": [1]}}

        result = federated_average_state_dicts([sd1, sd2], [300, 700])

        # (300/1000)*10 + (700/1000)*20 = 3 + 14 = 17.0
        self.assertAlmostEqual(result["w"]["data"][0], 17.0, places=6)

    def test_shape_preserved(self):
        """Output shapes match input shapes."""
        sd = {"fc": {"data": [1.0] * 32, "shape": [8, 4]}}
        result = federated_average_state_dicts([sd], [100])
        self.assertEqual(result["fc"]["shape"], [8, 4])

    def test_empty_input_raises(self):
        """Empty inputs should raise ValueError."""
        with self.assertRaises(ValueError):
            federated_average_state_dicts([], [])

    def test_mismatched_layers_raises(self):
        """Clients with different layer names should raise ValueError."""
        sd1 = {"a": {"data": [1.0], "shape": [1]}}
        sd2 = {"b": {"data": [2.0], "shape": [1]}}
        with self.assertRaises(ValueError):
            federated_average_state_dicts([sd1, sd2], [100, 100])


if __name__ == '__main__':
    unittest.main(verbosity=2)
