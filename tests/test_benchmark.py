"""Hermetic tests for lab.benchmark differential parity benchmark."""
from __future__ import annotations

import pytest

from lab import benchmark
from lab.explore.observation import Step
from src import profile


class MockBenchmarkTarget:
    def __init__(self, mutate_on: int = -1) -> None:
        self.mutate_on = mutate_on
        self.call_count = 0

    def last_exp_ids(self):
        return [999]

    def run(self, steps: list[Step], seq: str, note: str):
        self.call_count += 1
        trace = []
        for i, step in enumerate(steps):
            if i == self.mutate_on:
                trace.append((422, {"error": "E506", "mensaje": "límite excedido"}))
            else:
                trace.append((200, {"ok": True}))
        return trace


def test_generate_benchmark_suite_categorization():
    prof = profile.get()
    suite = benchmark.generate_benchmark_suite(prof, seed=1, n_easy=5, n_regular=3, n_hard=2)
    assert len(suite["facil"]) == 5
    assert len(suite["regular"]) == 3
    assert len(suite["dificil"]) == 2

    # Faciles are 1-step
    assert all(len(s[1]) == 1 for s in suite["facil"])
    # Regulares are 2-5 steps
    assert all(2 <= len(s[1]) <= 5 for s in suite["regular"])
    # Dificiles are 6-12 steps
    assert all(6 <= len(s[1]) <= 12 for s in suite["dificil"])


def test_run_benchmark_100_parity():
    t1 = MockBenchmarkTarget()
    t2 = MockBenchmarkTarget()

    prof = profile.get()
    suite = benchmark.generate_benchmark_suite(prof, seed=1, n_easy=3, n_regular=2, n_hard=1)
    results = benchmark.run_benchmark(t1, t2, suite, budget=50)

    assert results["total_cases"] == 6
    assert results["passed_cases"] == 6
    assert len(results["clusters"]) == 0


def test_run_benchmark_detects_and_clusters_divergence():
    t_orig = MockBenchmarkTarget(mutate_on=0)  # Diverges on step 0
    t_repl = MockBenchmarkTarget(mutate_on=-1)

    prof = profile.get()
    suite = benchmark.generate_benchmark_suite(prof, seed=1, n_easy=2, n_regular=1, n_hard=1)
    results = benchmark.run_benchmark(t_orig, t_repl, suite, budget=50)

    assert results["failures"]["status_mismatch"] > 0
    assert results["failures"]["first_request"] > 0
    assert len(results["clusters"]) > 0
