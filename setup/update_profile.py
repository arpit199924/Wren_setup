import json
from pathlib import Path
import sys

# Resolve paths relative to this script's directory (assumed to be in setup/)
setup_dir = Path(__file__).resolve().parent
root_dir = setup_dir.parent
profile_path = root_dir / "jaffle-wren" / "jaffle-profile.json"
duckdb_dir = root_dir / "jaffle_shop_duckdb"

if not profile_path.exists():
    print(f"Error: {profile_path} not found.", file=sys.stderr)
    sys.exit(1)

with open(profile_path, "r") as f:
    try:
        profile = json.load(f)
    except Exception as e:
        print(f"Error reading JSON from {profile_path}: {e}", file=sys.stderr)
        sys.exit(1)

# Update url to the absolute path of jaffle_shop_duckdb
profile["url"] = str(duckdb_dir.resolve())

# Write back in a clean format
with open(profile_path, "w") as f:
    json.dump(profile, f, indent=2)

print(f"Successfully updated {profile_path} URL to:")
print(f"  {profile['url']}")
