"""Live exploration campaign runner executing A1 (stateful) and A2 (inputs) against original service."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from lab.client import LabClient
from lab.explore import diff, inputs, stateful
from lab.explore.targets import LiveTarget, ReplicaTarget


def run_campaign(
    inputs_budget: int = 300,
    stateful_budget: int = 700,
    seed: int = 42,
    output_dir: str = "lab/reports",
) -> Dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    client = LabClient(rate_limit_delay=0.15)
    live_target = LiveTarget(client, budget=inputs_budget + stateful_budget)
    replica_target = ReplicaTarget()

    print(f"=== Starting A2: Inputs Mutation Campaign (budget={inputs_budget}) ===")
    inputs_obs = inputs.explore(
        live_target,
        seed=seed,
        n=100,
        budget=inputs_budget,
    )
    print(f"A2 Live Observations collected: {len(inputs_obs)}. Used reqs: {live_target.used_requests}")
    cov = inputs.coverage(inputs_obs)
    print(f"A2 Coverage by family: {cov}")

    print("Replaying A2 against ReplicaTarget...")
    inputs_diff = diff.differential(inputs_obs, replica_target)
    print(f"A2 Compared: {inputs_diff['total_compared']}, Divergences: {inputs_diff['divergent_count']}")
    if inputs_diff['clusters']:
        print("A2 Divergence clusters:", list(inputs_diff['clusters'].keys()))

    (out_dir / "a2_inputs_diff.json").write_text(json.dumps(inputs_diff, indent=2, default=str), encoding="utf-8")

    used_before_a1 = live_target.used_requests
    print(f"\n=== Starting A1: Stateful Chain Campaign (budget={stateful_budget}) ===")
    stateful_obs = stateful.explore(
        live_target,
        seed=seed,
        n=60,
        budget=inputs_budget + stateful_budget,
    )
    a1_used = live_target.used_requests - used_before_a1
    print(f"A1 Live Observations collected: {len(stateful_obs)}. Used reqs: {a1_used}")

    print("Replaying A1 against ReplicaTarget...")
    stateful_diff = diff.differential(stateful_obs, replica_target)
    print(f"A1 Compared: {stateful_diff['total_compared']}, Divergences: {stateful_diff['divergent_count']}")
    if stateful_diff['clusters']:
        print("A1 Divergence clusters:", list(stateful_diff['clusters'].keys()))

    (out_dir / "a1_stateful_diff.json").write_text(json.dumps(stateful_diff, indent=2, default=str), encoding="utf-8")

    summary = {
        "seed": seed,
        "total_requests_used": live_target.used_requests,
        "a2_inputs": {
            "observations": len(inputs_obs),
            "coverage": cov,
            "compared": inputs_diff["total_compared"],
            "divergent_count": inputs_diff["divergent_count"],
            "clusters": list(inputs_diff["clusters"].keys()),
        },
        "a1_stateful": {
            "observations": len(stateful_obs),
            "compared": stateful_diff["total_compared"],
            "divergent_count": stateful_diff["divergent_count"],
            "clusters": list(stateful_diff["clusters"].keys()),
        },
    }
    (out_dir / "campaign_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run live exploration campaign.")
    parser.add_argument("--inputs-budget", type=int, default=300)
    parser.add_argument("--stateful-budget", type=int, default=700)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=str, default="lab/reports")
    args = parser.parse_args()

    summary = run_campaign(
        inputs_budget=args.inputs_budget,
        stateful_budget=args.stateful_budget,
        seed=args.seed,
        output_dir=args.output_dir,
    )
    print("\n=== Campaign Summary ===")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
