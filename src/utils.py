from datetime import datetime
from pathlib import Path
import json

def write_report(items, output_dir="reports"):
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
    out_path = Path(output_dir) / f"daily_digest_{stamp}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    print(f"Wrote report: {out_path}")