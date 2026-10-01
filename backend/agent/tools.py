"""
Tool system for the AI Command Center agent.

KEY CONCEPT: The ToolRegistry holds a list of "allowed directories".
Every tool that touches the filesystem checks the requested path
against this allowlist BEFORE doing anything. If the path is outside
the allowed directories, the tool refuses.

This is the "sandbox" — the agent can inspect files, but only where
you explicitly permit.
"""

import os
import json


# ── Safety limits ──────────────────────────────────────────────────
MAX_FILE_SIZE = 100_000  # 100 KB — prevents reading huge files

# Directories/files to hide from list_files (noise, not useful to agent)
IGNORED_NAMES = {"venv", "__pycache__", ".git", "node_modules", ".env"}


class ToolRegistry:
    """
    Holds the available tools and enforces path-based security.

    Usage:
        registry = ToolRegistry(allowed_dirs=["C:/Users/me/project"])
        result = registry.execute("list_files", {"directory": "C:/Users/me/project"})
    """

    def __init__(self, allowed_dirs):
        # Convert all allowed dirs to absolute paths for reliable comparison
        self.allowed_dirs = [os.path.abspath(d) for d in allowed_dirs]

        # Map of tool name → method
        # Adding a new tool? Just add it here and write the method below.
        self._tools = {
            "list_files": self._list_files,
            "read_file": self._read_file,
        }

    # ── Path validation ────────────────────────────────────────────

    def _validate_path(self, path):
        """
        Check that `path` is inside one of the allowed directories.
        Returns the absolute path if valid, raises PermissionError if not.

        This catches tricks like:
            ../../Windows/System32
            C:/Users/someone_else/secrets.txt
        """
        abs_path = os.path.abspath(path)

        for allowed in self.allowed_dirs:
            # The path must BE the allowed dir or START WITH it + separator
            # (the separator check prevents "/allowed_dir_extra" matching "/allowed_dir")
            if abs_path == allowed or abs_path.startswith(allowed + os.sep):
                return abs_path

        raise PermissionError(
            f"Access denied: path is outside allowed directories. "
            f"Allowed: {self.allowed_dirs}"
        )

    # ── Tool implementations ──────────────────────────────────────

    def _list_files(self, directory):
        """List files and folders in a directory (one level deep)."""
        safe_path = self._validate_path(directory)

        if not os.path.isdir(safe_path):
            return f"Error: '{directory}' is not a directory."

        entries = []
        for entry in sorted(os.listdir(safe_path)):
            if entry in IGNORED_NAMES:
                continue
            full = os.path.join(safe_path, entry)
            # Add a trailing "/" to directories so the agent can tell them apart
            marker = "/" if os.path.isdir(full) else ""
            entries.append(f"{entry}{marker}")

        return "\n".join(entries) if entries else "(empty directory)"

    def _read_file(self, file_path):
        """Read contents of a text file."""
        safe_path = self._validate_path(file_path)

        if not os.path.isfile(safe_path):
            return f"Error: '{file_path}' is not a file."

        size = os.path.getsize(safe_path)
        if size > MAX_FILE_SIZE:
            return f"Error: file is {size:,} bytes (limit is {MAX_FILE_SIZE:,})."

        try:
            with open(safe_path, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            return "Error: file appears to be binary, cannot read as text."

    # ── Execution ──────────────────────────────────────────────────

    def execute(self, tool_name, arguments):
        """
        Run a tool by name with the given arguments dict.
        Returns the tool's output as a string, or an error message.
        """
        if tool_name not in self._tools:
            return f"Error: unknown tool '{tool_name}'."

        try:
            return self._tools[tool_name](**arguments)
        except PermissionError as e:
            return f"Permission denied: {e}"
        except TypeError as e:
            # Wrong/missing arguments
            return f"Error: bad arguments for '{tool_name}': {e}"
        except Exception as e:
            return f"Error running '{tool_name}': {e}"

    # ── Tool definitions (sent to the LLM) ─────────────────────────

    def get_definitions(self):
        """
        Return tool definitions in the OpenAI-compatible format
        that Ollama (and most LLM APIs) expect.

        This is what tells the LLM "here are the tools you can call,
        here's what arguments each one takes."
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "list_files",
                    "description": (
                        "List files and folders in a directory. "
                        "Only works within allowed project directories."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "directory": {
                                "type": "string",
                                "description": "Absolute path to the directory to list.",
                            }
                        },
                        "required": ["directory"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": (
                        "Read the text contents of a file. "
                        "Only works within allowed project directories. "
                        "Max file size: 100 KB."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Absolute path to the file to read.",
                            }
                        },
                        "required": ["file_path"],
                    },
                },
            },
        ]
