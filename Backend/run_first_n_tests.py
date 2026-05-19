#!/usr/bin/env python3
"""Run first N test cases from the 60-test suite.

Usage:
    python run_first_n_tests.py 15   # Run first 15 tests
    python run_first_n_tests.py 30   # Run first 30 tests
    python run_first_n_tests.py 60   # Run all 60 tests
"""

import subprocess
import sys
from pathlib import Path

# All test IDs in order (Groups A-M)
ALL_TESTS = [
    # Group A (5)
    "A1", "A2", "A3", "A4", "A5",
    # Group B (4)
    "B1", "B2", "B3", "B4",
    # Group C (4)
    "C1", "C2", "C3", "C4",
    # Group D (4)
    "D1", "D2", "D3", "D4",
    # Group E (4)
    "E1", "E2", "E3", "E4",
    # Group F (6)
    "F1", "F2", "F3", "F4", "F5", "F6",
    # Group G (6)
    "G1", "G2", "G3", "G4", "G5", "G6",
    # Group H (6)
    "H1", "H2", "H3", "H4", "H5", "H6",
    # Group I (4)
    "I1", "I2", "I3", "I4",
    # Group J (5)
    "J1", "J2", "J3", "J4", "J5",
    # Group K (6)
    "K1", "K2", "K3", "K4", "K5", "K6",
    # Group L (3)
    "L1", "L2", "L3",
    # Group M (3)
    "M1", "M2", "M3",
]


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_first_n_tests.py <number_of_tests>")
        print()
        print(f"Available tests: 1-{len(ALL_TESTS)} (total {len(ALL_TESTS)} tests)")
        print()
        print("Examples:")
        print("  python run_first_n_tests.py 5   # Run Group A only")
        print("  python run_first_n_tests.py 15  # Run Groups A-E")
        print("  python run_first_n_tests.py 30  # Run Groups A-I")
        print("  python run_first_n_tests.py 60  # Run all 60 tests")
        sys.exit(1)

    try:
        n = int(sys.argv[1])
    except ValueError:
        print(f"Error: '{sys.argv[1]}' is not a valid number")
        sys.exit(1)

    if n < 1 or n > len(ALL_TESTS):
        print(f"Error: Please specify a number between 1 and {len(ALL_TESTS)}")
        sys.exit(1)

    selected_tests = ALL_TESTS[:n]
    
    print(f"Running {n}/{len(ALL_TESTS)} tests...")
    print(f"Tests: {', '.join(selected_tests)}")
    print()

    # Run the tests
    cmd = ["python", "main.py", "--evidence_collecting"] + selected_tests
    subprocess.run(cmd)


if __name__ == "__main__":
    main()
