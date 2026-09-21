#!/usr/bin/env python3
"""
Minimal script to run the collector subsystem in a repeating loop.

Calls `python -m rubin_sunrise collector` repeatedly, allowing each run to 
complete its full cycle (determined by SIM_START and SIM_END dates in config.py).
The outer loop can be interrupted with Ctrl+C.

Usage:
    python run_collector_loop.py
"""

import subprocess
import sys
import time


def run_collector_loop():
    """Run the collector in a repeating loop that can be interrupted by Ctrl+C."""
    loop_count = 0
    
    try:
        while True:
            loop_count += 1
            print(f"\n{'='*60}")
            print(f"[LOOP #{loop_count}] Starting collector...")
            print(f"{'='*60}\n")
            
            # Run the collector subprocess
            result = subprocess.run(
                [sys.executable, "-m", "rubin_sunrise", "collector"],
                check=False
            )
            
            if result.returncode != 0:
                print(f"\n[WARNING] Collector exited with return code {result.returncode}")
            
            print(f"\n[LOOP #{loop_count}] Collector finished. Repeating...\n")
            time.sleep(1)  # Brief pause before next loop
            
    except KeyboardInterrupt:
        print(f"\n\n{'='*60}")
        print("Interrupted by user. Shutting down...")
        print(f"{'='*60}")
        sys.exit(0)


if __name__ == "__main__":
    run_collector_loop()
