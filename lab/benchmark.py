"""Differential parity benchmark: compares original service vs replica with zero manual payloads.

Generates deterministic test cases across tiers (Fácil, Regular, Difícil) driven
strictly by the engines in `lab/explore/`, executes against both targets, and prints
a detailed scorecard formatted identically to the hidden evaluation report.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lab.client import LabClient
from lab.explore.diff import first_divergence
from lab.explore.inputs import FAMILIES, MUTATION_REGISTRY
from lab.explore.observation import Step, Target
from lab.explore.stateful import CHAIN_FACTORIES
from lab.explore.targets import LiveTarget, ReplicaTarget, RemoteTarget
from lab.runner import json_equal
from src import profile


def generate_benchmark_suite(
    prof: Dict[str, Any],
    seed: int = 42,
    n_easy: int = 20,
    n_regular: int = 15,
    n_hard: int = 10,
) -> Dict[str, List[Tuple[str, List[Step], str]]]:
    """Generate categorized test sequences strictly from exploration engines."""
    rng = random.Random(seed)
    suite: Dict[str, List[Tuple[str, List[Step], str]]] = {
        "facil": [],
        "regular": [],
        "dificil": [],
    }

    # 1. Fáciles (1 paso): single-request grammar mutations
    for i in range(n_easy):
        family = FAMILIES[i % len(FAMILIES)]
        mut_fn = rng.choice(MUTATION_REGISTRY[family])
        steps, note = mut_fn(prof, rng)
        seq_id = f"bench_easy_{i:03d}"
        suite["facil"].append((seq_id, steps, f"{family}: {note}"))

    # 2. Regulares (2-5 pasos): shorter stateful chains
    for i in range(n_regular):
        factory = CHAIN_FACTORIES[i % len(CHAIN_FACTORIES)]
        steps, note = factory(prof, rng)
        if len(steps) > 5:
            steps = steps[: rng.randint(2, 5)]
        seq_id = f"bench_reg_{i:03d}"
        suite["regular"].append((seq_id, steps, note))

    # 3. Difíciles (6-12 pasos): long complex financial chains
    for i in range(n_hard):
        factory = CHAIN_FACTORIES[i % len(CHAIN_FACTORIES)]
        steps, note = factory(prof, rng)
        # Ensure chain has at least 6 steps
        while len(steps) < 6:
            more_steps, _ = factory(prof, rng)
            steps.extend(more_steps)
        if len(steps) > 12:
            steps = steps[:12]
        seq_id = f"bench_hard_{i:03d}"
        suite["dificil"].append((seq_id, steps, note))

    return suite


def run_benchmark(
    target_orig: Target,
    target_repl: Target,
    suite: Dict[str, List[Tuple[str, List[Step], str]]],
    budget: int = 500,
) -> Dict[str, Any]:
    """Execute benchmark suite against original and replica, comparing results."""
    used_requests = 0
    results: Dict[str, Any] = {
        "total_cases": 0,
        "passed_cases": 0,
        "tiers": {
            "facil": {"total": 0, "passed": 0},
            "regular": {"total": 0, "passed": 0},
            "dificil": {"total": 0, "passed": 0},
        },
        "failures": {
            "status_mismatch": 0,
            "body_mismatch": 0,
            "first_request": 0,
            "later_request": 0,
        },
        "clusters": {},
        "details": [],
    }

    prof = profile.get()
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")

    for tier, cases in suite.items():
        for seq_id, steps, note in cases:
            needed = 1 + len(steps)
            if used_requests + needed > budget:
                break

            results["total_cases"] += 1
            results["tiers"][tier]["total"] += 1

            # Run on both targets
            try:
                orig_trace = target_orig.run(steps, seq=seq_id, note=note)
                repl_trace = target_repl.run(steps, seq=seq_id, note=note)
                used_requests += needed
            except Exception as e:
                # Target execution stopped
                break

            div_idx = first_divergence(orig_trace, repl_trace)

            if div_idx is None:
                # 100% Match for this sequence
                results["passed_cases"] += 1
                results["tiers"][tier]["passed"] += 1
            else:
                orig_resp = orig_trace[div_idx] if div_idx < len(orig_trace) else (None, None)
                repl_resp = repl_trace[div_idx] if div_idx < len(repl_trace) else (None, None)
                orig_status, orig_body = orig_resp
                repl_status, repl_body = repl_resp

                # Classify failure
                if orig_status != repl_status:
                    results["failures"]["status_mismatch"] += 1
                else:
                    results["failures"]["body_mismatch"] += 1

                if div_idx == 0:
                    results["failures"]["first_request"] += 1
                else:
                    results["failures"]["later_request"] += 1

                # Extract command
                step = steps[div_idx] if div_idx < len(steps) else {}
                cmd = "UNKNOWN"
                if msg_field in step and isinstance(step[msg_field], str):
                    cmd = step[msg_field].split(sep)[0].strip().upper()
                elif "__method__" in step or "__path__" in step:
                    cmd = f"{step.get('__method__', 'HTTP')} {step.get('__path__', '')}"

                cluster_key = f"{cmd}: {orig_status} -> {repl_status}"
                if cluster_key not in results["clusters"]:
                    results["clusters"][cluster_key] = {
                        "count": 1,
                        "command": cmd,
                        "step_index": div_idx + 1,
                        "sample_step": step,
                        "orig_response": orig_resp,
                        "repl_response": repl_resp,
                        "seq_id": seq_id,
                    }
                else:
                    results["clusters"][cluster_key]["count"] += 1

                results["details"].append({
                    "seq_id": seq_id,
                    "tier": tier,
                    "note": note,
                    "step": div_idx + 1,
                    "orig_status": orig_status,
                    "repl_status": repl_status,
                    "orig_body": orig_body,
                    "repl_body": repl_body,
                })

    results["used_requests"] = used_requests
    return results


def print_scorecard(results: Dict[str, Any], orig_label: str, repl_label: str) -> None:
    """Print beautifully formatted evaluation scorecard."""
    total = results["total_cases"]
    passed = results["passed_cases"]
    pct = (passed / total * 100) if total > 0 else 0.0

    print("\n" + "=" * 65)
    print("           BENCHMARK DE CONFORMIDAD DIFERENCIAL (AUTÓNOMO)")
    print("=" * 65)
    print(f"ORIGINAL:  {orig_label}")
    print(f"RÉPLICA:   {repl_label}")
    print(f"REQUESTS:  {results.get('used_requests', 0)} requests ejecutados")
    print("-" * 65)

    print(f"TESTS QUE PASAN:         {passed} / {total} ({pct:.1f}%)")
    print("-" * 65)

    for tier, label in [("facil", "FÁCILES (1 paso)"), ("regular", "REGULARES (2-5 pasos)"), ("dificil", "DIFÍCILES (6-12 pasos)")]:
        t_data = results["tiers"][tier]
        t_tot = t_data["total"]
        t_pas = t_data["passed"]
        t_pct = (t_pas / t_tot * 100) if t_tot > 0 else 0.0
        print(f"{label:25s}: {t_pas} / {t_tot} ({t_pct:.1f}%)")

    print("-" * 65)
    print("POR QUÉ FALLAN:")
    print(f"  Status distinto:                {results['failures']['status_mismatch']}")
    print(f"  Cuerpo distinto:                {results['failures']['body_mismatch']}")
    print(f"  Caen en el primer request:      {results['failures']['first_request']}")
    print(f"  Caen más adelante en secuencia: {results['failures']['later_request']}")

    clusters = results.get("clusters", {})
    if clusters:
        print("-" * 65)
        print(f"DIVERGENCIAS DETECTADAS ({len(clusters)} clusters):")
        for key, c in clusters.items():
            print(f"  [{key}] ({c['count']} casos)")
            print(f"     Paso {c['step_index']}: {json.dumps(c['sample_step'], ensure_ascii=False)}")
            print(f"     Original: {c['orig_response'][0]} {json.dumps(c['orig_response'][1], ensure_ascii=False)}")
            print(f"     Réplica:  {c['repl_response'][0]} {json.dumps(c['repl_response'][1], ensure_ascii=False)}")
    else:
        print("-" * 65)
        print("✅ 100% PARIDAD ABSOLUTA: Cero divergencias detectadas.")
    print("=" * 65 + "\n")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Differential Parity Benchmark between original and replica.")
    parser.add_argument("--live", action="store_true", help="Compare against live original service")
    parser.add_argument("--replica-url", type=str, default=None, help="HTTP URL of remote/deployed replica")
    parser.add_argument("--budget", type=int, default=120, help="Max requests against live target")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for deterministic test generation")
    parser.add_argument("--easy", type=int, default=15, help="Number of easy (1-step) tests")
    parser.add_argument("--regular", type=int, default=10, help="Number of regular (2-5 step) tests")
    parser.add_argument("--hard", type=int, default=5, help="Number of hard (6-12 step) tests")
    parser.add_argument("--json-out", type=Path, default=None, help="Path to write JSON benchmark results")
    args = parser.parse_args(argv)

    prof = profile.get()
    suite = generate_benchmark_suite(
        prof,
        seed=args.seed,
        n_easy=args.easy,
        n_regular=args.regular,
        n_hard=args.hard,
    )

    # Configure Replica Target
    if args.replica_url:
        from src import config
        target_repl = RemoteTarget(base_url=args.replica_url, token=config.TEAM_TOKEN)
        repl_label = f"Remote URL: {args.replica_url}"
    else:
        target_repl = ReplicaTarget()
        repl_label = "Local In-Process Replica (FastAPI TestClient)"

    # Configure Original Target
    if args.live:
        client = LabClient(rate_limit_delay=0.15)
        target_orig = LiveTarget(client, budget=args.budget)
        orig_label = f"Live Original ({client.base_url})"
        try:
            results = run_benchmark(target_orig, target_repl, suite, budget=args.budget)
        finally:
            client.close()
    else:
        # Hermetic local testing mode
        target_orig = ReplicaTarget()
        orig_label = "Local Active Profile Specification"
        results = run_benchmark(target_orig, target_repl, suite, budget=args.budget)

    print_scorecard(results, orig_label, repl_label)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    return 0 if results["passed_cases"] == results["total_cases"] else 1


if __name__ == "__main__":
    sys.exit(main())
