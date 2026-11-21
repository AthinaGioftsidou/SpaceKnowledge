"""Tests for BrokerMetrics."""

import threading
import unittest

from spaceknowledge.broker.metrics import BrokerMetrics


class TestCounting(unittest.TestCase):
    def test_a_new_one_is_all_zeros(self) -> None:
        snapshot = BrokerMetrics().snapshot()
        self.assertEqual(0, snapshot["requests_served"])
        self.assertEqual(0, snapshot["pending_operations"])
        self.assertEqual({"count": 0, "mean": 0.0, "max": 0.0, "p95": 0.0},
                         snapshot["latency_ms"])

    def test_each_outcome_has_its_own_counter(self) -> None:
        metrics = BrokerMetrics()
        for outcome in ("served", "served", "lost", "failed"):
            metrics.record(1.0, outcome)
        snapshot = metrics.snapshot()
        self.assertEqual((2, 1, 1), (snapshot["requests_served"],
                                     snapshot["requests_lost_connection"],
                                     snapshot["requests_failed"]))

    def test_pending_and_recovered_are_set_not_added(self) -> None:
        metrics = BrokerMetrics()
        metrics.set_pending(3)
        metrics.set_pending(1)
        metrics.set_recovered(2)
        snapshot = metrics.snapshot()
        self.assertEqual((1, 2), (snapshot["pending_operations"], snapshot["recovered_at_start"]))


class TestLatency(unittest.TestCase):
    def test_mean_max_and_p95(self) -> None:
        metrics = BrokerMetrics()
        for value in (10.0, 20.0, 30.0):
            metrics.record(value, "served")
        self.assertEqual({"count": 3, "mean": 20.0, "max": 30.0, "p95": 30.0},
                         metrics.snapshot()["latency_ms"])

    def test_p95_of_a_hundred_samples_is_the_ninety_fifth(self) -> None:
        metrics = BrokerMetrics(window=100)
        for value in range(1, 101):
            metrics.record(float(value), "served")
        self.assertEqual(95.0, metrics.snapshot()["latency_ms"]["p95"])

    def test_p95_only_looks_at_the_recent_window_but_max_remembers_everything(self) -> None:
        metrics = BrokerMetrics(window=5)
        metrics.record(1000.0, "served")
        for _ in range(5):
            metrics.record(1.0, "served")
        latency = metrics.snapshot()["latency_ms"]
        self.assertEqual((6, 1.0, 1000.0), (latency["count"], latency["p95"], latency["max"]))


class TestSafety(unittest.TestCase):
    def test_several_threads_recording_at_once_lose_nothing(self) -> None:
        metrics = BrokerMetrics()

        def work() -> None:
            for _ in range(500):
                metrics.record(1.0, "served")

        threads = [threading.Thread(target=work) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(2000, metrics.snapshot()["requests_served"])

    def test_the_snapshot_is_a_copy(self) -> None:
        metrics = BrokerMetrics()
        metrics.snapshot()["latency_ms"]["count"] = 99
        self.assertEqual(0, metrics.snapshot()["latency_ms"]["count"])

    def test_bad_values_are_refused(self) -> None:
        metrics = BrokerMetrics()
        with self.assertRaises(ValueError):
            metrics.record(1.0, "nonsense")
        with self.assertRaises(ValueError):
            metrics.record(-1.0, "served")
        for bad in (-1, True, 1.5):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    metrics.set_pending(bad)  # type: ignore[arg-type]
                with self.assertRaises(ValueError):
                    metrics.set_recovered(bad)  # type: ignore[arg-type]
        for window in (0, True, 1.5):
            with self.subTest(window=window):
                with self.assertRaises(ValueError):
                    BrokerMetrics(window=window)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()