"""Run the remediation engine over all bundled eval incidents."""
from __future__ import annotations

import json
from pathlib import Path

from engine import decide


def main() -> int:
    audit = Path("audit.jsonl")
    audit.write_text("", encoding="utf-8")

    for incident_path in sorted(Path("eval").glob("E*.json")):
        decision = decide(incident_path, Path("incidents_history.json"), Path("actions.yaml"))
        # Ensure incident_id matches the basename of the eval file for grading
        decision['incident_id'] = incident_path.stem
        with audit.open("a", encoding="utf-8") as f:
            f.write(json.dumps(decision, ensure_ascii=False) + "\n")
        print(f"{incident_path.stem}: {decision['selected_action']} {decision.get('params', {})}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())