#!/usr/bin/env python3
"""
Test suite for Icarus Mount Editor CLI.

Validates all CLI commands and verifies mount types against game PAK files.

Usage:
    python test_cli.py              # Run all tests
    python test_cli.py --quick      # Skip PAK scan and modifications
    python test_cli.py --pak-only   # Only run PAK verification
    python test_cli.py --mods       # Include modification tests (creates/deletes test mount)
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple, Optional, Set

# Import our modules for PAK scanning
from mount_types import MOUNT_TYPES


# =============================================================================
# Test Infrastructure
# =============================================================================

class TestResult:
    """Result of a single test."""
    def __init__(self, name: str, passed: bool, message: str = ""):
        self.name = name
        self.passed = passed
        self.message = message


class TestRunner:
    """Simple test runner with colored output."""

    def __init__(self):
        self.results: List[TestResult] = []
        self.current_section = ""

    def section(self, name: str):
        """Start a new test section."""
        self.current_section = name
        print(f"\n[{name}]")

    def test(self, name: str, passed: bool, message: str = ""):
        """Record a test result."""
        result = TestResult(name, passed, message)
        self.results.append(result)

        status = "PASS" if passed else "FAIL"
        symbol = "+" if passed else "X"
        print(f"  [{symbol}] {name}")
        if message and not passed:
            print(f"      {message}")

    def summary(self):
        """Print test summary."""
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)

        print("\n" + "=" * 50)
        if passed == total:
            print(f"PASSED: {passed}/{total} tests")
        else:
            print(f"FAILED: {total - passed}/{total} tests failed")
            print("\nFailed tests:")
            for r in self.results:
                if not r.passed:
                    print(f"  - {r.name}: {r.message}")

        return passed == total


def run_cli(*args) -> Tuple[int, str, str]:
    """Run the CLI with given arguments and return (exit_code, stdout, stderr)."""
    cmd = [sys.executable, "mount_cli.py"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=Path(__file__).parent)
    return result.returncode, result.stdout, result.stderr


# =============================================================================
# CLI Smoke Tests
# =============================================================================

def test_cli_smoke(runner: TestRunner):
    """Test basic CLI functionality without game data."""
    runner.section("CLI Smoke Tests")

    # Test --help
    code, stdout, stderr = run_cli("--help")
    runner.test(
        "--help returns usage info",
        code == 0 and "usage:" in stdout.lower(),
        f"Exit code: {code}"
    )

    # Test --version
    code, stdout, stderr = run_cli("--version")
    runner.test(
        "--version shows version",
        code == 0 and "1.0" in stdout,
        f"Output: {stdout.strip()}"
    )

    # Test types command
    code, stdout, stderr = run_cli("types")
    mount_count = len(MOUNT_TYPES)
    runner.test(
        f"types lists {mount_count} mount types",
        code == 0 and "Terrenus" in stdout and "Tusker" in stdout,
        f"Exit code: {code}"
    )

    # Test config command
    code, stdout, stderr = run_cli("config")
    runner.test(
        "config shows configuration",
        code == 0 and "Steam IDs" in stdout,
        f"Exit code: {code}"
    )

    # Test skin --help
    code, stdout, stderr = run_cli("skin", "--help")
    runner.test(
        "skin --help shows usage",
        code == 0 and "skin" in stdout.lower() and "index" in stdout.lower(),
        f"Exit code: {code}"
    )

    # Test invalid command
    code, stdout, stderr = run_cli("invalidcommand")
    runner.test(
        "invalid command shows error",
        code != 0,
        f"Exit code: {code} (expected non-zero)"
    )

    # Test malformed JSON handling (ensures json module is imported)
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("{invalid json content")
        temp_path = f.name
    try:
        code, stdout, stderr = run_cli("--file", temp_path, "list")
        # Should fail gracefully with ERROR message, not crash with NameError
        runner.test(
            "malformed JSON shows error (not crash)",
            code != 0 and "NameError" not in stderr,
            f"stderr: {stderr[:200]}" if stderr else "no stderr"
        )
    finally:
        Path(temp_path).unlink(missing_ok=True)


# =============================================================================
# Mount Data Tests
# =============================================================================

def test_mount_data(runner: TestRunner):
    """Test commands that require mount data."""
    runner.section("Mount Data Tests")

    # Test list command
    code, stdout, stderr = run_cli("list")
    if code != 0:
        runner.test("list command", False, f"Exit code: {code}, stderr: {stderr}")
        return

    # Count mounts from output
    lines = [l for l in stdout.split('\n') if l.strip().startswith('|') and not 'Name' in l and not '---' in l]
    mount_count = len([l for l in lines if re.match(r'\|\s*\d+\s*\|', l)])
    runner.test(
        f"list returns {mount_count} mounts",
        mount_count > 0,
        f"Found {mount_count} mounts"
    )

    # Test info command
    code, stdout, stderr = run_cli("info", "0")
    runner.test(
        "info 0 shows mount details",
        code == 0 and "Name:" in stdout and "Type:" in stdout,
        f"Exit code: {code}"
    )

    # Test validate command
    code, stdout, stderr = run_cli("validate")
    # Validate may find issues, that's okay - just check it runs
    runner.test(
        "validate runs without crash",
        code == 0,
        f"Exit code: {code}"
    )


# =============================================================================
# PAK Verification
# =============================================================================

def find_icarus_installation() -> Optional[Path]:
    """Find Icarus installation path."""
    common_paths = [
        Path(r"F:\SteamLibrary\steamapps\common\Icarus"),
        Path(r"C:\Program Files (x86)\Steam\steamapps\common\Icarus"),
        Path(r"D:\SteamLibrary\steamapps\common\Icarus"),
        Path(r"E:\SteamLibrary\steamapps\common\Icarus"),
        Path(r"G:\SteamLibrary\steamapps\common\Icarus"),
    ]

    for path in common_paths:
        if path.exists():
            return path

    return None


def scan_pak_for_mounts(pak_path: Path) -> Set[str]:
    """Scan a PAK file for mount blueprints."""
    blueprints = set()

    try:
        with open(pak_path, 'rb') as f:
            content = f.read()

        text = content.decode('ascii', errors='ignore')
        matches = re.findall(r'BP_Mount_[A-Za-z0-9_]+', text)

        for match in matches:
            # Normalize: remove _C suffix if present
            bp = match.rstrip('_C')
            # Skip base/corpse/known broken
            if bp not in ('BP_Mount_Base', 'BP_Mount_Corpse', 'BP_Mount_Blueback',
                          'BP_Mount_Horse_Standard_Corpse', 'BP_Mount_Zebra_Corpse',
                          'BP_Mount_Zebra_Quest'):
                blueprints.add(bp)

    except Exception as e:
        print(f"    Warning: Error reading {pak_path.name}: {e}")

    return blueprints


def test_pak_verification(runner: TestRunner):
    """Verify mount types against game PAK files."""
    runner.section("PAK Verification")

    icarus_path = find_icarus_installation()
    if not icarus_path:
        runner.test("Find Icarus installation", False, "Icarus not found in common locations")
        return

    paks_dir = icarus_path / "Icarus" / "Content" / "Paks"
    if not paks_dir.exists():
        runner.test("Find PAK directory", False, f"PAK dir not found: {paks_dir}")
        return

    print(f"  Scanning {paks_dir}...")

    # Scan all PAK files
    all_blueprints: Set[str] = set()
    pak_files = list(paks_dir.glob("*.pak"))

    for pak_path in pak_files:
        blueprints = scan_pak_for_mounts(pak_path)
        all_blueprints.update(blueprints)

    print(f"  Found {len(all_blueprints)} unique mount blueprints")

    # Build expected blueprints from MOUNT_TYPES
    expected_blueprints = {mt.blueprint.rstrip('_C') for mt in MOUNT_TYPES.values()}

    # Check all expected are found
    missing = expected_blueprints - all_blueprints
    runner.test(
        f"All {len(expected_blueprints)} known blueprints found in game",
        len(missing) == 0,
        f"Missing: {', '.join(sorted(missing))}" if missing else ""
    )

    # Check for new blueprints
    # Filter to only mount blueprints (not animations, stats, etc.)
    mount_blueprints = {bp for bp in all_blueprints if bp.startswith('BP_Mount_')}
    new_mounts = mount_blueprints - expected_blueprints

    if new_mounts:
        print(f"\n  NEW MOUNTS DISCOVERED:")
        for bp in sorted(new_mounts):
            print(f"    + {bp}")

    runner.test(
        "Check for new mount blueprints",
        True,  # This is informational, not a failure
        f"Found {len(new_mounts)} new blueprints" if new_mounts else "No new mounts"
    )


# =============================================================================
# Modification Tests
# =============================================================================

def test_modifications(runner: TestRunner):
    """Test modification commands using a temp copy (never touches prod data)."""
    runner.section("Modification Tests")

    # Copy prod Mounts.json to temp file in test_output/ subfolder
    import shutil
    from pathlib import Path

    test_dir = Path(__file__).parent
    output_dir = test_dir / "test_output"
    output_dir.mkdir(exist_ok=True)
    temp_mounts = output_dir / "Mounts.test.json"

    # Find the prod file
    base_path = Path(os.path.expandvars(r'%LOCALAPPDATA%\Icarus\Saved\PlayerData'))
    prod_file = None
    for steam_dir in base_path.iterdir():
        if steam_dir.is_dir() and steam_dir.name.isdigit():
            candidate = steam_dir / "Mounts.json"
            if candidate.exists():
                prod_file = candidate
                break

    if not prod_file:
        runner.test("setup test file", False, "No Mounts.json found")
        return

    # Copy to temp location
    shutil.copy(prod_file, temp_mounts)
    runner.test("setup test file", True, f"Copied to {temp_mounts.name}")

    try:
        _run_modification_tests(runner, str(temp_mounts))
    finally:
        # Always clean up temp file
        if temp_mounts.exists():
            temp_mounts.unlink()
        runner.test("cleanup test file", True, "")


def _run_modification_tests(runner: TestRunner, test_file: str):
    """Internal: Run the actual modification tests against a temp file."""

    def run_test_cli(*args) -> Tuple[int, str, str]:
        """Run CLI with --file pointing to temp test file."""
        return run_cli("--file", test_file, *args)

    # Clone a mount (--no-backup must come before command)
    code, stdout, stderr = run_test_cli("--no-backup", "clone", "0", "CLI_Test_Mount")
    if code != 0:
        runner.test("clone mount", False, f"Failed to clone: {stderr}")
        return

    # Find the new index from output
    match = re.search(r'index\s+(\d+)', stdout)
    if not match:
        runner.test("clone mount", False, "Could not find new mount index in output")
        return

    new_index = match.group(1)
    runner.test(f"clone 0 'CLI_Test_Mount' created index {new_index}", True, "")

    # Set level
    code, stdout, stderr = run_test_cli("--no-backup", "level", new_index, "50")
    runner.test(
        f"level {new_index} 50",
        code == 0 and "50" in stdout,
        f"Exit code: {code}"
    )

    # Verify with info
    code, stdout, stderr = run_test_cli("info", new_index)
    has_correct_level = "Level:" in stdout and "50" in stdout
    runner.test(
        f"info {new_index} shows level 50",
        code == 0 and has_correct_level,
        f"Level not updated correctly"
    )

    # Test reset-talents (cloned mount should have talents from source)
    code, stdout, stderr = run_test_cli("--no-backup", "reset-talents", new_index, "--confirm")
    # Either finds talents to reset OR reports no talents - both are valid outcomes
    talents_reset = code == 0 and ("Reset" in stdout or "No talents" in stdout)
    runner.test(
        f"reset-talents {new_index}",
        talents_reset,
        f"Exit code: {code}, stderr: {stderr}"
    )

    # Test variant on non-horse mount (should fail gracefully)
    code, stdout, stderr = run_test_cli("--no-backup", "variant", new_index, "A1")
    # Should fail because cloned mount is not a Workshop Horse
    variant_error = code != 0 or "not a Workshop Horse" in stdout or "ERROR" in stdout
    runner.test(
        f"variant {new_index} A1 (non-horse, should fail)",
        variant_error,
        f"Expected error for non-horse mount"
    )

    # Test variant on a cloned Workshop Horse (if one exists)
    # Look for a mount with Mount_Horse_Standard in AI setup
    code, stdout, stderr = run_test_cli("list")
    workshop_horse_index = None
    for line in stdout.split('\n'):
        if 'Mount_Horse_Standard' in line:
            match = re.match(r'\|\s*(\d+)\s*\|', line)
            if match:
                workshop_horse_index = match.group(1)
                break

    if workshop_horse_index:
        # Clone the Workshop Horse for testing
        code, stdout, stderr = run_test_cli("--no-backup", "clone", workshop_horse_index, "CLI_Test_Horse")
        horse_match = re.search(r'index\s+(\d+)', stdout)
        if horse_match:
            test_horse_index = horse_match.group(1)
            # Test changing variant on the clone
            code, stdout, stderr = run_test_cli("--no-backup", "variant", test_horse_index, "A3")
            runner.test(
                f"variant {test_horse_index} A3 (cloned Workshop Horse)",
                code == 0 and "Done" in stdout,
                f"Exit code: {code}, stderr: {stderr}"
            )
            # Delete the test clone
            run_test_cli("--no-backup", "delete", test_horse_index, "--confirm")
        else:
            runner.test("variant on Workshop Horse", False, "Failed to clone Workshop Horse")
    else:
        runner.test("variant on Workshop Horse (skipped)", True, "No Workshop Horse found")

    # Test skin command (set cosmetic skin index)
    code, stdout, stderr = run_test_cli("--no-backup", "skin", new_index, "1")
    runner.test(
        f"skin {new_index} 1",
        code == 0 and "Done" in stdout,
        f"Exit code: {code}, stderr: {stderr}"
    )

    # Test skin command with different index
    code, stdout, stderr = run_test_cli("--no-backup", "skin", new_index, "2")
    runner.test(
        f"skin {new_index} 2",
        code == 0 and "CosmeticSkinIndex" in stdout,
        f"Exit code: {code}, stderr: {stderr}"
    )

    # Test type command (change mount type)
    code, stdout, stderr = run_test_cli("--no-backup", "type", new_index, "Tusker", "--confirm")
    runner.test(
        f"type {new_index} Tusker",
        code == 0 and "Tusker" in stdout,
        f"Exit code: {code}, stderr: {stderr}"
    )

    # Verify type change with info
    code, stdout, stderr = run_test_cli("info", new_index)
    type_changed = "Tusker" in stdout or "Mount_Tusker" in stdout
    runner.test(
        f"info {new_index} shows Tusker type",
        code == 0 and type_changed,
        f"Type not updated correctly"
    )

    # Delete the test mount (with --confirm to skip prompt)
    code, stdout, stderr = run_test_cli("--no-backup", "delete", new_index, "--confirm")
    runner.test(
        f"delete {new_index}",
        code == 0,
        f"Exit code: {code}"
    )

    # Verify deletion
    code, stdout, stderr = run_test_cli("list")
    runner.test(
        "test mount removed from list",
        "CLI_Test_Mount" not in stdout,
        "Mount still appears in list"
    )


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Test suite for Icarus Mount Editor CLI")
    parser.add_argument("--quick", action="store_true",
                        help="Skip PAK scan (faster)")
    parser.add_argument("--pak-only", action="store_true",
                        help="Only run PAK verification")
    parser.add_argument("--mods", action="store_true",
                        help="Include modification tests (creates/deletes test mount)")

    args = parser.parse_args()

    print("=" * 50)
    print("Icarus Mount Editor - Test Suite")
    print("=" * 50)

    runner = TestRunner()

    if args.pak_only:
        test_pak_verification(runner)
    else:
        # Always run smoke tests
        test_cli_smoke(runner)

        # Mount data tests (require save file)
        test_mount_data(runner)

        # PAK verification (unless --quick)
        if not args.quick:
            test_pak_verification(runner)

        # Modification tests (only if --mods)
        if args.mods:
            test_modifications(runner)

    # Summary
    success = runner.summary()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
