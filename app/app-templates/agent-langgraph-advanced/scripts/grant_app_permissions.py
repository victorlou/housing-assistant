"""Grant Lakebase permissions to the deployed app's service principal.

Run this after 'databricks bundle deploy && databricks bundle run' to allow
the app's SP to create schemas and tables in Lakebase.

Usage:
    uv run grant-app-permissions
    uv run grant-app-permissions --app-name housing-assistant-dev
    uv run grant-app-permissions --app-name housing-assistant-dev --memory-type langgraph
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_DIR = Path(__file__).parent


def _get_sp_client_id(app_name: str, profile: str) -> str:
    result = subprocess.run(
        [
            "databricks",
            "apps",
            "get",
            app_name,
            "--profile",
            profile,
            "--output",
            "json",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Error fetching app '{app_name}':\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(result.stdout)
    sp_client_id = data.get("service_principal_client_id")
    if not sp_client_id:
        print(
            f"Error: app '{app_name}' has no service_principal_client_id. "
            "Has it been deployed yet?",
            file=sys.stderr,
        )
        sys.exit(1)
    return sp_client_id


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--app-name",
        default=os.getenv("DATABRICKS_APP_NAME", "housing-assistant-dev"),
        help="Databricks App name (default: DATABRICKS_APP_NAME env var or 'housing-assistant-dev')",
    )
    parser.add_argument(
        "--memory-type",
        default="langgraph",
        choices=["langgraph", "openai"],
        help="Agent memory type (default: langgraph)",
    )
    parser.add_argument(
        "--profile",
        default=os.getenv("DATABRICKS_CONFIG_PROFILE", "DEFAULT"),
        help="Databricks config profile (default: DATABRICKS_CONFIG_PROFILE or 'DEFAULT')",
    )
    args = parser.parse_args()

    print(f"Fetching service principal for app '{args.app_name}'...")
    sp_client_id = _get_sp_client_id(args.app_name, args.profile)
    print(f"  SP client ID: {sp_client_id}")

    # Resolve Lakebase connection from .env
    endpoint = os.getenv("LAKEBASE_AUTOSCALING_ENDPOINT", "").strip()
    instance = os.getenv("LAKEBASE_INSTANCE_NAME", "").strip()

    if not endpoint and not instance:
        print(
            "Error: Set LAKEBASE_AUTOSCALING_ENDPOINT or LAKEBASE_INSTANCE_NAME in .env",
            file=sys.stderr,
        )
        sys.exit(1)

    grant_script = _DIR / "grant_lakebase_permissions.py"
    cmd = [
        sys.executable,
        str(grant_script),
        sp_client_id,
        "--memory-type",
        args.memory_type,
    ]

    if instance:
        cmd += ["--instance-name", instance]
    else:
        cmd += ["--autoscaling-endpoint", endpoint]

    print(f"\nGranting Lakebase permissions to SP '{sp_client_id}'...")
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
