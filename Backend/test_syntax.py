#!/usr/bin/env python3
"""Quick syntax check for modified files."""

try:
    import phase7.phase7_lean_runner as p7
    print("✓ phase7_lean_runner.py imports OK")
except Exception as e:
    print(f"✗ phase7_lean_runner.py import failed: {e}")

try:
    import phase6_repair.rule_repair as rr
    print("✓ rule_repair.py imports OK")
except Exception as e:
    print(f"✗ rule_repair.py import failed: {e}")

# Try to call the modified functions
try:
    result = p7._synthesize_fitch_from_premises_and_goal([], "P → (Q → P)")
    if result:
        print(f"✓ D1 pattern detected, generated {len(result)} steps")
    else:
        print("✗ D1 pattern not handled")
except Exception as e:
    print(f"✗ D1 synthesis failed: {e}")

try:
    result = p7._synthesize_fitch_from_premises_and_goal([], "P → (P ∨ Q)")
    if result:
        print(f"✓ D3 pattern detected, generated {len(result)} steps")
    else:
        print("✗ D3 pattern not handled")
except Exception as e:
    print(f"✗ D3 synthesis failed: {e}")

print("\nSyntax check complete!")
