"""
test_fedavg.py
==============
FederHub - Group 3 (Team Gamma): Phase 1 Unit Tests
----------------------------------------------------
Tests for fedavg_mock.py using Python's built-in unittest.
No external dependencies required.

User Story Traceability:
    - Epic 5, Story 5.1 Acceptance Criteria:
      "Given the aggregator receives weights from multiple participating
       clients, when the round ends, then it executes the FedAvg algorithm."
    - Confirmation: "Test the aggregation engine with simulated client arrays."

Run with:
    python -m pytest test_fedavg.py -v
    or
    python test_fedavg.py
"""

import unittest
from fedavg_mock import federated_average


class TestFederatedAverage(unittest.TestCase):
    """Unit tests for the federated_average() function."""

    # ------------------------------------------------------------------ #
    # Correctness Tests
    # ------------------------------------------------------------------ #

    def test_equal_sample_counts_is_simple_mean(self):
        """
        When all clients have equal sample counts, FedAvg should produce
        the same result as a simple mean.
        """
        weights = [
            [1.0, 2.0, 3.0],
            [3.0, 4.0, 5.0],
        ]
        samples = [100, 100]
        result = federated_average(weights, samples)
        expected = [2.0, 3.0, 4.0]
        for r, e in zip(result, expected):
            self.assertAlmostEqual(r, e, places=6)

    def test_weighted_by_sample_size(self):
        """
        A client with more samples should have greater influence on the
        global model. Validates the core FedAvg weighting logic.
        """
        weights = [
            [0.0, 0.0],  # Client A: contributes 0-values
            [1.0, 1.0],  # Client B: contributes 1-values
        ]
        # Client B has 3x the samples → result should be closer to [1,1]
        samples = [100, 300]
        result = federated_average(weights, samples)
        # Expected: (0*100 + 1*300) / 400 = 0.75 for each param
        self.assertAlmostEqual(result[0], 0.75, places=6)
        self.assertAlmostEqual(result[1], 0.75, places=6)

    def test_single_client(self):
        """
        With only one client, the global model should equal that client's
        weights exactly.
        """
        weights = [[0.5, 0.3, 0.8]]
        samples = [500]
        result = federated_average(weights, samples)
        for r, e in zip(result, [0.5, 0.3, 0.8]):
            self.assertAlmostEqual(r, e, places=6)

    def test_three_clients_weighted(self):
        """
        Integration-style test matching the mock scenario in fedavg_mock.py:
        3 clients (Hospital A, Hospital B, Bank C) with different sample sizes.
        """
        weights = [
            [0.10, 0.25, 0.38, 0.47, 0.60, 0.72],
            [0.15, 0.20, 0.42, 0.50, 0.55, 0.68],
            [0.12, 0.30, 0.35, 0.44, 0.63, 0.75],
        ]
        samples = [300, 500, 200]
        result = federated_average(weights, samples)

        # Manually compute expected for first param:
        # (0.10*300 + 0.15*500 + 0.12*200) / 1000 = (30+75+24)/1000 = 0.129
        self.assertAlmostEqual(result[0], 0.129, places=6)
        self.assertEqual(len(result), 6)

    def test_output_length_matches_input(self):
        """Global weight vector must have same length as client weight vectors."""
        weights = [[0.1, 0.2, 0.3, 0.4, 0.5]] * 4
        samples = [100, 200, 150, 250]
        result = federated_average(weights, samples)
        self.assertEqual(len(result), 5)

    # ------------------------------------------------------------------ #
    # Edge Case / Error Handling Tests
    # ------------------------------------------------------------------ #

    def test_empty_inputs_raise_error(self):
        """Empty inputs should raise a ValueError."""
        with self.assertRaises(ValueError):
            federated_average([], [])

    def test_mismatched_lengths_raise_error(self):
        """Mismatched number of weight arrays and sample counts raises ValueError."""
        with self.assertRaises(ValueError):
            federated_average([[0.1, 0.2], [0.3, 0.4]], [100])

    def test_zero_total_samples_raise_error(self):
        """Zero total samples should raise a ValueError (division by zero guard)."""
        with self.assertRaises(ValueError):
            federated_average([[0.1, 0.2]], [0])

    def test_negative_sample_count_raises_error(self):
        """Negative sample counts are invalid and should raise a ValueError."""
        with self.assertRaises(ValueError):
            federated_average([[0.1, 0.2], [0.3, 0.4]], [100, -50])

    def test_unequal_weight_vector_lengths_raise_error(self):
        """Clients with different parameter counts should raise a ValueError."""
        with self.assertRaises(ValueError):
            federated_average([[0.1, 0.2], [0.3, 0.4, 0.5]], [100, 200])


if __name__ == "__main__":
    unittest.main(verbosity=2)