#!/usr/bin/env python3
"""
Test script to validate Red-DiscordBot installation and cog imports.
This script is used to verify that all cogs can be imported with redbot.core available.
"""
import sys
import importlib.util
from pathlib import Path


def test_redbot_import():
    """Test that Red-DiscordBot core modules can be imported."""
    print("Testing Red-DiscordBot core imports...")
    try:
        from redbot.core import commands, Config, checks  # noqa: F401
        print("✓ Successfully imported redbot.core modules")
        return True
    except ImportError as e:
        print(f"✗ Failed to import redbot.core: {e}")
        return False


def _get_cog_directories():
    """Get list of cog directories (excluding hidden directories)."""
    return [d for d in Path(".").iterdir() if d.is_dir() and not d.name.startswith(".")]


def test_cog_syntax():
    """Test that all cog Python files have valid syntax."""
    print("\nTesting cog file syntax...")
    cog_dirs = _get_cog_directories()

    failed_files = []
    success_count = 0

    for cog_dir in cog_dirs:
        py_files = list(cog_dir.glob("*.py"))
        for py_file in py_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    compile(f.read(), py_file, 'exec')
                success_count += 1
            except SyntaxError as e:
                failed_files.append((py_file, str(e)))
                print(f"✗ Syntax error in {py_file}: {e}")

    if not failed_files:
        print(f"✓ All {success_count} cog files have valid syntax")
        return True
    else:
        print(f"✗ {len(failed_files)} files have syntax errors")
        return False


def test_cog_imports():
    """Test that cog __init__.py files can be imported."""
    print("\nTesting cog imports...")
    cog_dirs = _get_cog_directories()

    failed_imports = []
    success_count = 0

    for cog_dir in cog_dirs:
        init_file = cog_dir / "__init__.py"
        if not init_file.exists():
            continue

        cog_name = cog_dir.name
        try:
            spec = importlib.util.spec_from_file_location(cog_name, init_file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[cog_name] = module
                spec.loader.exec_module(module)

                # Check if setup function exists
                if hasattr(module, 'setup'):
                    print(f"✓ Successfully imported {cog_name} (has setup function)")
                    success_count += 1
                else:
                    print(f"⚠ Warning: {cog_name} imported but missing setup function")
                    success_count += 1
        except Exception as e:
            failed_imports.append((cog_name, str(e)))
            print(f"✗ Failed to import {cog_name}: {e}")

    if not failed_imports:
        print(f"✓ All {success_count} cogs imported successfully")
        return True
    else:
        print(f"✗ {len(failed_imports)} cogs failed to import")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Red-DiscordBot Setup Validation")
    print("=" * 60)

    results = []
    results.append(("Red-DiscordBot Import", test_redbot_import()))
    results.append(("Cog Syntax", test_cog_syntax()))
    results.append(("Cog Imports", test_cog_imports()))

    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    all_passed = True
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")
        if not passed:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("\n✓ All tests passed!")
        return 0
    else:
        print("\n✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
