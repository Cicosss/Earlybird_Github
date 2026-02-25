#!/usr/bin/env python3
"""Generate architecture snapshot from source code using AST analysis."""

import ast
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple


class ArchitectureMapper:
    """Maps codebase architecture using AST analysis."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.architecture: Dict[str, Dict[str, List[Tuple[str, str]]]] = {}

    def extract_from_file(self, file_path: Path) -> Tuple[List[str], List[str]]:
        """Extract class and function names from a Python file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except (IOError, UnicodeDecodeError) as e:
            print(f"Warning: Could not read {file_path}: {e}", file=sys.stderr)
            return [], []

        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError as e:
            print(f"Warning: Syntax error in {file_path}: {e}", file=sys.stderr)
            return [], []

        # Add parent references to track nesting
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                child.parent = parent

        classes = []
        functions = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                # Check if this is a top-level function (not inside a class)
                parent = getattr(node, "parent", None)
                if not isinstance(parent, ast.ClassDef):
                    functions.append(node.name)

        # Remove duplicates while preserving order
        classes = list(dict.fromkeys(classes))
        functions = list(dict.fromkeys(functions))

        return classes, functions

    def scan_directory(self, directory: Path) -> None:
        """Recursively scan a directory for Python files."""
        if not directory.exists() or not directory.is_dir():
            print(f"Warning: Directory not found: {directory}", file=sys.stderr)
            return

        for py_file in directory.rglob("*.py"):
            # Skip __pycache__ and test files
            if "__pycache__" in py_file.parts or py_file.name.startswith("test_"):
                continue

            rel_path = py_file.relative_to(self.base_dir)
            dir_path = str(rel_path.parent)

            classes, functions = self.extract_from_file(py_file)

            if classes or functions:
                if dir_path not in self.architecture:
                    self.architecture[dir_path] = {}
                self.architecture[dir_path][py_file.name] = (classes, functions)

    def generate_markdown(self) -> str:
        """Generate hierarchical Markdown representation."""
        timestamp = datetime.now(timezone.utc).isoformat()

        lines = [
            "# Architecture Snapshot - Ground Truth for V10.5",
            "",
            f"**Generated:** {timestamp}",
            "**Purpose:** Single Source of Truth for Claude-Mem Integration",
            "**Method:** AST-based code analysis",
            "",
            "---",
            "",
            "## 📋 Metadata",
            "",
            "- **Tool:** Native Python AST Mapper",
            "- **Scanned Directories:** `src/`, `config/`",
            "- **Analysis Method:** Abstract Syntax Tree (AST) parsing",
            "- **Extraction:** Classes and Functions definitions",
            "",
            "---",
            "",
            "## 🏗️ Architecture Map",
            "",
        ]

        # Sort directories for consistent output
        sorted_dirs = sorted(self.architecture.keys())

        for dir_path in sorted_dirs:
            lines.append(f"### {dir_path if dir_path != '.' else 'Root'}")
            lines.append("")

            # Sort files within directory
            sorted_files = sorted(self.architecture[dir_path].keys())

            for file_name in sorted_files:
                classes, functions = self.architecture[dir_path][file_name]
                lines.append(f"#### `{file_name}`")
                lines.append("")

                if classes:
                    lines.append("**Classes:**")
                    for cls in sorted(classes):
                        lines.append(f"- `class {cls}`")
                    lines.append("")

                if functions:
                    lines.append("**Functions:**")
                    for func in sorted(functions):
                        lines.append(f"- `def {func}()`")
                    lines.append("")

                if not classes and not functions:
                    lines.append("*No classes or functions found*")
                    lines.append("")

                lines.append("")

        # Add statistics
        total_dirs = len(self.architecture)
        total_files = sum(len(files) for files in self.architecture.values())
        total_classes = sum(
            len(classes) for files in self.architecture.values() for classes, _ in files.values()
        )
        total_functions = sum(
            len(funcs) for files in self.architecture.values() for _, funcs in files.values()
        )

        lines.append("---")
        lines.append("")
        lines.append("## 📊 Statistics")
        lines.append("")
        lines.append(f"- **Directories scanned:** {total_dirs}")
        lines.append(f"- **Python files analyzed:** {total_files}")
        lines.append(f"- **Total classes:** {total_classes}")
        lines.append(f"- **Total functions:** {total_functions}")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("**End of Architecture Snapshot**")

        return "\n".join(lines)


def main():
    """Main entry point."""
    base_dir = Path(__file__).parent.parent
    output_path = base_dir / "ARCHITECTURE_SNAPSHOT_V10.5.md"

    print("🔍 Scanning codebase for architecture analysis...")
    print(f"   Base directory: {base_dir}")
    print()

    mapper = ArchitectureMapper(base_dir)

    # Scan src/ directory
    print("📂 Scanning src/...")
    mapper.scan_directory(base_dir / "src")

    # Scan config/ directory
    print("📂 Scanning config/...")
    mapper.scan_directory(base_dir / "config")

    print()
    print("📝 Generating architecture snapshot...")
    markdown = mapper.generate_markdown()

    print()
    print("💾 Saving snapshot...")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"✅ Snapshot saved to: {output_path}")
    print(f"   Total characters: {len(markdown):,}")
    print()
    print("💡 Next Steps:")
    print("   1. Review the generated snapshot")
    print("   2. Run 'make sync-memory' to regenerate if needed")
    print("   3. The snapshot serves as Source of Truth for Claude-Mem")


if __name__ == "__main__":
    main()
