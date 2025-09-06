#!/usr/bin/env python3
"""
Branch-aware orchestrator file reader with Windows-safe path normalization.
"""

import argparse
import os
import subprocess
import sys
from typing import Optional

def read_from_branch(branch: str, path: str) -> Optional[str]:
    # Git blob paths must use forward slashes even on Windows
    git_path = path.replace("\\", "/")
    try:
        out = subprocess.check_output(
            ["git", "show", f"{branch}:{git_path}"],
            stderr=subprocess.STDOUT
        )
        return out.decode("utf-8", errors="replace")
    except subprocess.CalledProcessError as e:
        sys.stderr.write(
            f"[orchestrator] Error reading {git_path} from {branch}:\n"
            f"{e.output.decode(errors='replace')}\n"
        )
        return None

def main():
    parser = argparse.ArgumentParser(description="Branch-aware orchestrator file reader")
    parser.add_argument("--branch", default=os.getenv("EAI_ORCH_BRANCH", "prod"),
                        help="branch to read from (default: prod)")
    parser.add_argument("--prompt", default="Prompts/Prompt_I.md",
                        help="prompt path to read")
    args = parser.parse_args()

    content = read_from_branch(args.branch, args.prompt)
    if content is None:
        sys.exit(1)

    print("----- FILE HEADER -----")
    for i, line in enumerate(content.splitlines()[:12], start=1):
        print(f"{i:02d}: {line}")
    print("-----------------------")

if __name__ == "__main__":
    main()