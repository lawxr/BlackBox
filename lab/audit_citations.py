"""Deterministic citation auditor for BlackBox.

Validates that every claim cited in especificacion.md (e.g. `exp N`, `exp X..Y`,
`mañana N`) corresponds to a verifiable entry in experimentos.jsonl or
pruebas/ejemplos.jsonl.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


from typing import Any


def _read_jsonl_ids(file_path: Path, key: str) -> set[int]:
    """Extract integer ID set from a jsonl file for a given property key."""
    ids: set[int] = set()
    if file_path.exists():
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if key in obj:
                        ids.add(int(obj[key]))
                except Exception:
                    pass
    return ids


def load_known_ids(experimentos_path: Path, ejemplos_path: Path) -> tuple[set[int], set[int]]:
    return _read_jsonl_ids(experimentos_path, "id"), _read_jsonl_ids(ejemplos_path, "n")


def parse_ranges_and_numbers(segment: str) -> set[int]:
    """Parse string tokens like '1', '2, 4', '445..486', '355-369' into integer set."""
    ids = set()
    # Split by comma or whitespace
    parts = re.split(r"[,;\s]+", segment.strip())
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Check range syntax: X..Y
        if ".." in part:
            bounds = part.split("..")
            if len(bounds) == 2 and bounds[0].isdigit() and bounds[1].isdigit():
                start, end = int(bounds[0]), int(bounds[1])
                ids.update(range(min(start, end), max(start, end) + 1))
                continue
        # Check range syntax: X-Y (where both are digits)
        if "-" in part:
            bounds = part.split("-")
            if len(bounds) == 2 and bounds[0].isdigit() and bounds[1].isdigit():
                start, end = int(bounds[0]), int(bounds[1])
                ids.update(range(min(start, end), max(start, end) + 1))
                continue
        # Simple digit
        if part.isdigit():
            ids.add(int(part))
    return ids


def audit_spec_file(
    spec_path: Path, known_exps: set[int], known_ejemplos: set[int]
) -> dict[str, Any]:
    """Scan especificacion.md and verify all citations."""
    cited_exps: dict[int, list[int]] = {}  # exp_id -> list of line numbers
    cited_ejemplos: dict[int, list[int]] = {}  # mañana_id -> list of line numbers
    broken_citations: list[dict[str, Any]] = []

    scan_targets = [
        (r"\bexp\s+([0-9\s,\.\-]+)", "experimento", known_exps, cited_exps),
        (r"\bmañana\s+([0-9\s,\.\-]+)", "mañana", known_ejemplos, cited_ejemplos),
    ]

    with spec_path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            for pattern, cite_type, known, cited_dict in scan_targets:
                for m in re.finditer(pattern, line, flags=re.IGNORECASE):
                    ids = parse_ranges_and_numbers(m.group(1).strip())
                    for cid in ids:
                        cited_dict.setdefault(cid, []).append(line_num)
                        if cid not in known:
                            broken_citations.append({
                                "type": cite_type,
                                "id": cid,
                                "line": line_num,
                                "raw": m.group(0),
                            })

    return {
        "total_exp_cited": len(cited_exps),
        "total_ejemplos_cited": len(cited_ejemplos),
        "cited_exps": cited_exps,
        "cited_ejemplos": cited_ejemplos,
        "broken_citations": broken_citations,
    }


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    spec_path = root / "especificacion.md"
    exp_path = root / "experimentos.jsonl"
    ejemplos_path = root / "pruebas" / "ejemplos.jsonl"

    print("=" * 60)
    print("BLACKBOX CITATION AUDITOR")
    print("=" * 60)
    print(f"Especificación: {spec_path.relative_to(root)}")
    print(f"Experimentos:   {exp_path.relative_to(root)}")
    print(f"Ejemplos:       {ejemplos_path.relative_to(root)}\n")

    known_exps, known_ejemplos = load_known_ids(exp_path, ejemplos_path)
    print(f"Base de evidencia disponible:")
    print(f"  - Experimentos propios registrados: {len(known_exps)} IDs")
    print(f"  - Ejemplos de referencia (mañana): {len(known_ejemplos)} IDs\n")

    result = audit_spec_file(spec_path, known_exps, known_ejemplos)

    print("Auditoría de citas en especificacion.md:")
    print(f"  - Experimentos citados: {result['total_exp_cited']} IDs únicos")
    print(f"  - Ejemplos citados:     {result['total_ejemplos_cited']} IDs únicos\n")

    broken = result["broken_citations"]
    if broken:
        print(f"❌ FALLO DE AUDITORÍA: Se encontraron {len(broken)} citas rotas o sin respaldo:")
        for b in broken:
            print(f"  - Línea {b['line']}: {b['type']} '{b['id']}' no existe en la base (texto: '{b['raw']}')")
        sys.exit(1)
    else:
        print("✅ 100% DE INTEGRIDAD: Todas las citas de especificacion.md tienen respaldo real.")
        sys.exit(0)


if __name__ == "__main__":
    main()
