"""Dashboard application entry point with CLI routing.

Supports running collector, display, or both with optional delays.

Usage:
  python -m rubin_sunrise collector              # Start data collection only
  python -m rubin_sunrise display                # Start display only
  python -m rubin_sunrise both --delay 120       # Start collector, wait 120s, then display
  python -m rubin_sunrise both -d 60              # Default delay is 60s if not specified
"""

import argparse
import time
import threading
from rubin_sunrise.collector.collector_main import run_collector
from rubin_sunrise.dashboard.dashboard_main import run_display


def run_both_with_delay(collector_first_delay: int = 60):
    """Start collector in background, wait, then start display.
    
    Parameters
    ----------
    collector_first_delay : int
        Seconds to wait after collector starts before launching display.
    """
    # Start collector in background thread
    collector_thread = threading.Thread(
        target=run_collector,
        daemon=False,
        name="collector-thread"
    )
    collector_thread.start()
    
    print(f"Collector started. Waiting {collector_first_delay}s before starting display...")
    time.sleep(collector_first_delay)
    
    print("Starting display...")
    run_display()
    
    # After display exits (via Ctrl+C), wait for collector to finish
    collector_thread.join()


def main():
    parser = argparse.ArgumentParser(
        description="Rubin Sunrise: Data collection and dashboard display",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m rubin_sunrise collector              # Run collector only
  python -m rubin_sunrise display                # Run display only (reads existing DB)
  python -m rubin_sunrise both --delay 120       # Collector, wait 2 min, then display
  python -m rubin_sunrise both                   # Collector, default 60s delay, then display
        """
    )
    
    subparsers = parser.add_subparsers(
        dest="command",
        help="Command to run"
    )
    
    # Collector command
    subparsers.add_parser(
        "collector",
        help="Run data collection pipeline only"
    )
    
    # Display command
    subparsers.add_parser(
        "display",
        help="Run dashboard display only (reads from existing database)"
    )
    
    # Both command with optional delay
    both_parser = subparsers.add_parser(
        "both",
        help="Run collector first, then display with optional delay between"
    )
    both_parser.add_argument(
        "-d", "--delay",
        type=int,
        default=60,
        metavar="SECONDS",
        help="Seconds to wait after collector starts before launching display (default: 60)"
    )
    
    args = parser.parse_args()
    
    # Route to appropriate function
    if args.command == "collector":
        print("Starting data collector...")
        run_collector()
    
    elif args.command == "display":
        print("Starting dashboard display...")
        run_display()
    
    elif args.command == "both":
        run_both_with_delay(collector_first_delay=args.delay)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()