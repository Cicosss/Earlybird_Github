#!/usr/bin/env python3
"""
Architecture Map Generator

This script generates UML class diagrams using pyreverse (from pylint).
The diagrams are saved to docs/visual_architecture/ as SVG files.

Usage:
    python3 src/utils/gen_architecture_map.py

Requirements:
    pip install pylint
"""

import os
import subprocess
import sys


def check_pyreverse_installed():
    """Check if pyreverse is installed."""
    try:
        result = subprocess.run(
            ["pyreverse", "--version"], capture_output=True, text=True, check=False
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def generate_architecture_map():
    """Generate architecture maps using pyreverse."""

    # Check if pyreverse is installed
    if not check_pyreverse_installed():
        print("ERROR: pyreverse is not installed.")
        print("Please run: pip install pylint")
        sys.exit(1)

    # Ensure output directory exists
    output_dir = "docs/visual_architecture"
    os.makedirs(output_dir, exist_ok=True)

    # Run pyreverse command
    cmd = ["pyreverse", "-o", "svg", "-p", "EarlyBird", "-d", output_dir, "src/"]

    print("Generating architecture maps...")
    print(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("Architecture maps generated successfully!")
        print(f"Output directory: {output_dir}/")
        print("Generated files:")
        print(f"  - {output_dir}/classes_EarlyBird.svg")
        print(f"  - {output_dir}/packages_EarlyBird.svg")
    except subprocess.CalledProcessError as e:
        print("ERROR: Failed to generate architecture maps.")
        print(f"Return code: {e.returncode}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        sys.exit(1)


if __name__ == "__main__":
    generate_architecture_map()
