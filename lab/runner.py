from __future__ import annotations
import json
from pathlib import Path
from typing import List, Dict, Any


def load_ejemplos(path: str = "pruebas/ejemplos.jsonl") -> List[Dict[str, Any]]:
    """Load reference examples recorded from the morning service."""
    file_path = Path(path)
    if not file_path.exists():
        return []
    examples = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                examples.append(json.loads(line))
    return examples
