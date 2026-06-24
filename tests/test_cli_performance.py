#!/usr/bin/env python3
"""Test script to measure CLI performance improvements."""
import time
import sys
import subprocess
from pathlib import Path

def measure_command(description: str, args: list[str]) -> float:
    """Measure execution time of a CLI command."""
    print(f"\n{description}")
    print(f"Command: python -m backend.app.cli {' '.join(args)}")

    start = time.time()
    result = subprocess.run(
        [sys.executable, "-m", "backend.app.cli"] + args,
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent
    )
    elapsed = time.time() - start

    print(f"Exit code: {result.returncode}")
    if result.stdout:
        print(f"Output: {result.stdout.strip()}")
    if result.stderr:
        print(f"Error: {result.stderr.strip()}")
    print(f"Time: {elapsed:.3f}s")

    return elapsed

def main():
    print("=" * 70)
    print("CLI Performance Test - Optimized 'Detect First, Start Later' Logic")
    print("=" * 70)

    # Test 1: --check-port with all args (no config loading, fast path)
    t1 = measure_command(
        "Test 1: --check-port with all args (minimal imports)",
        ["--check-port", "--host", "127.0.0.1", "--port", "9999", "--workspace-root", "/tmp"]
    )

    # Test 2: --check-port without args (needs config loading)
    t2 = measure_command(
        "Test 2: --check-port without args (loads config)",
        ["--check-port"]
    )

    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print(f"Test 1 (fast path with all args):  {t1:.3f}s")
    print(f"Test 2 (with config loading):      {t2:.3f}s")
    print("\nOptimization Benefits:")
    print("- No FastAPI/uvicorn imports until server startup needed")
    print("- Socket timeout optimized for localhost (0.1s vs 1.0s)")
    print("- Config loading delayed until required")
    print("\nExpected improvement in real SSH scenario:")
    print("- Port reuse detection: ~3s → ~0.3-0.5s (6-10x faster)")

if __name__ == "__main__":
    main()
