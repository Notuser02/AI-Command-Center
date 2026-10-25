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
import ipaddress
import json
import socket
import subprocess


# ── Safety limits ──────────────────────────────────────────────────
MAX_FILE_SIZE = 100_000  # 100 KB — prevents reading huge files

# Directories/files to hide from list_files (noise, not useful to agent)
IGNORED_NAMES = {"venv", "__pycache__", ".git", "node_modules", ".env", "sessions"}

# search_files caps
MAX_SEARCH_MATCHES = 50
MAX_SEARCH_FILES = 500

# Hosts the agent may never fetch (SSRF protection). _is_blocked_host is the
# fast string check on the hostname itself; _host_resolves_private additionally
# resolves DNS and checks every returned IP — together they catch IP-encoding
# tricks (decimal/hex/short forms), IPv4-mapped IPv6, and DNS names that
# resolve to private addresses (nip.io / localtest.me style).
def _ip_is_private(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # unparseable = treat as unsafe
    if addr.is_private or addr.is_loopback or addr.is_link_local \
            or addr.is_reserved or addr.is_multicast or addr.is_unspecified:
        return True
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        return _ip_is_private(str(addr.ipv4_mapped))
    if isinstance(addr, ipaddress.IPv4Address):
        o1, o2 = str(addr).split(".")[:2]
        if o1 == "100" and 64 <= int(o2) <= 127:
            return True  # Tailscale CGNAT range
    return False


def _is_blocked_host(hostname: str) -> bool:
    host = (hostname or "").strip().lower().rstrip(".")
    if not host:
        return True
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]

    # IPv4-mapped IPv6 written as plain string
    if host.startswith("::ffff:"):
        return _ip_is_private(host.split(":", 1)[1]) or True

    # DNS / keyword names
    if host == "localhost" or host.endswith(".ts.net") or host.endswith(".local") \
            or host.endswith(".internal"):
        return True

    # Numeric IP encodings: decimal (2130706433), hex (0x7f000001),
    # short dotted (127.1) — normalize to the address they mean.
    try:
        addr = ipaddress.ip_address(host)
        return _ip_is_private(str(addr))
    except ValueError:
        pass

    parts = host.split(".")
    if len(parts) <= 4 and all(p and (p.isdigit() or (p.startswith("0x") and len(p) > 2)) for p in parts):
        try:
            if len(parts) == 1:
                n = int(parts[0], 0)  # honors 0x prefix
                dotted = ipaddress.ip_address(n)
                return _ip_is_private(str(dotted))
            if len(parts) in (2, 3) and "0x" not in host:
                # short forms like 127.1 → 127.0.0.1
                nums = [int(p) for p in parts]
                if all(n <= 255 for n in nums):
                    while len(nums) < 4:
                        nums.insert(len(nums) - 1, 0)
                    dotted = ".".join(map(str, nums))
                    return _ip_is_private(dotted)
        except (ValueError, OverflowError):
            pass

    return False


def _host_resolves_private(hostname: str) -> bool:
    """Resolve the hostname and check EVERY returned IP. This is the
    authoritative check — it catches DNS names that point at private
    addresses (nip.io, localtest.me, internal hostnames)."""
    try:
        infos = socket.getaddrinfo(hostname.strip("[]"), None)
    except (OSError, socket.gaierror):
        return True  # unresolvable = unusable, treat as blocked
    for info in infos:
        ip = info[4][0]
        if _ip_is_private(ip):
            return True
    return False

# Files the agent may never read OR write, even inside allowed dirs.
# .env* hold secrets; tasks.db* holds every conversation; session journals
# (backend/sessions/) are blocked by directory below.
SENSITIVE_FILE_PREFIXES = (".env",)
SENSITIVE_FILE_NAMES = {"tasks.db", "tasks.db-journal", "tasks.db-wal", "tasks.db-shm"}


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
        # (Web tools — web_search/web_fetch — were removed for now; they live
        #  in git history. The SSRF helpers below stay: /online/config uses
        #  them to validate base URLs.)
        self._tools = {
            "list_files": self._list_files,
            "read_file": self._read_file,
            "search_files": self._search_files,
            "write_file": self._write_file,
            "run_command": self._run_command,
        }

        # Sensitive tools that require human approval before execution
        self._sensitive_tools = {"write_file", "run_command"}

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

    def _validate_sensitive(self, abs_path):
        """
        Reject secret files (.env etc.) and internal data stores (tasks.db,
        session journals) even though they sit inside the allowed directories.
        list_files hides them, but without this check the agent could still
        open them by guessing the path.
        """
        name = os.path.basename(abs_path).lower()
        if name.startswith(SENSITIVE_FILE_PREFIXES) or name in SENSITIVE_FILE_NAMES:
            raise PermissionError(
                f"Access denied: '{name}' is a sensitive file the agent may not touch."
            )
        # session journals live in a sessions/ directory — block by path
        norm = abs_path.lower().replace("/", os.sep)
        if f"{os.sep}sessions{os.sep}" in norm:
            raise PermissionError(
                "Access denied: session journals are internal records the agent may not read."
            )
        return abs_path

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
        safe_path = self._validate_sensitive(self._validate_path(file_path))

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

    def _search_files(self, directory, query):
        """
        Grep-like search across text files inside the sandbox.
        Case-insensitive substring match; returns path:line: text entries.
        """
        safe_path = self._validate_path(directory)
        if not os.path.isdir(safe_path):
            return f"Error: '{directory}' is not a directory."

        needle = (query or "").strip().lower()
        if not needle:
            return "Error: empty query."

        matches = []
        files_scanned = 0
        for root, dirs, files in os.walk(safe_path):
            dirs[:] = [d for d in dirs if d not in IGNORED_NAMES]
            for name in sorted(files):
                if len(matches) >= MAX_SEARCH_MATCHES or files_scanned >= MAX_SEARCH_FILES:
                    break
                full = os.path.join(root, name)
                files_scanned += 1
                # secrets stay invisible to the agent, in search too
                if os.path.basename(full).lower().startswith(SENSITIVE_FILE_PREFIXES):
                    continue
                try:
                    if os.path.getsize(full) > MAX_FILE_SIZE:
                        continue
                    with open(full, "r", encoding="utf-8") as f:
                        text = f.read()
                except (UnicodeDecodeError, OSError):
                    continue  # binary or unreadable — skip
                for lineno, line in enumerate(text.splitlines(), start=1):
                    if needle in line.lower():
                        rel = os.path.relpath(full, safe_path)
                        matches.append(f"{rel}:{lineno}: {line.strip()[:150]}")
                        if len(matches) >= MAX_SEARCH_MATCHES:
                            break
            if len(matches) >= MAX_SEARCH_MATCHES or files_scanned >= MAX_SEARCH_FILES:
                break

        if not matches:
            return f"No matches for '{query}' in {directory}."

        header = f"Matches for '{query}' ({len(matches)} shown, {files_scanned} files scanned):"
        return header + "\n" + "\n".join(matches)

    def _write_file(self, file_path, content):
        """
        Create or overwrite a text file inside the sandbox.
        Sensitive tool: requires human approval before it runs.
        """
        safe_path = self._validate_sensitive(self._validate_path(file_path))

        if not isinstance(content, str):
            return "Error: 'content' must be a string."

        if len(content.encode("utf-8")) > MAX_FILE_SIZE:
            return f"Error: content exceeds {MAX_FILE_SIZE:,} byte limit."

        # Allow the agent to create files in new subfolders (path is already
        # validated to be inside the sandbox at this point).
        parent = os.path.dirname(safe_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        try:
            # newline="\n" stops Windows from converting \n to \r\n — keeps
            # line endings consistent with git and other tools.
            with open(safe_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
        except OSError as e:
            return f"Error writing file: {e}"

        return f"OK: wrote {len(content)} characters to {safe_path}"

    def _run_command(self, command: str):
        """
        Execute a shell command inside the project directory with strict limits.
        This is a sensitive tool and must be approved by the user before running.
        """
        if not command or not command.strip():
            return "Error: command cannot be empty."

        cwd = self.allowed_dirs[0]
        try:
            res = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=20
            )
            output = res.stdout
            if res.stderr:
                output += ("\nSTDERR:\n" + res.stderr)
            if not output.strip():
                output = f"(Command exited with code {res.returncode} and produced no output)"
            return output[:MAX_FILE_SIZE]
        except subprocess.TimeoutExpired:
            return "Error: command timed out after 20 seconds."
        except Exception as e:
            return f"Error executing command: {e}"

    # ── Permission & Approval ──────────────────────────────────────

    def requires_approval(self, tool_name: str) -> bool:
        """Returns True if the specified tool requires explicit human approval."""
        return tool_name in self._sensitive_tools

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
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": (
                        "Create or overwrite a text file with the given content. "
                        "Only works within allowed project directories. "
                        "NOTE: This is a sensitive action that requires explicit human approval before running."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Absolute path of the file to create or overwrite.",
                            },
                            "content": {
                                "type": "string",
                                "description": "The complete text content to write into the file.",
                            }
                        },
                        "required": ["file_path", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_files",
                    "description": (
                        "Search for a text (case-insensitive) across files in a directory, "
                        "returning path:line: text matches. Much faster than reading files "
                        "one by one when looking for where something is defined or used. "
                        "Only works within allowed project directories."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "directory": {
                                "type": "string",
                                "description": "Absolute path to the directory to search in.",
                            },
                            "query": {
                                "type": "string",
                                "description": "The text to search for.",
                            }
                        },
                        "required": ["directory", "query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "run_command",
                    "description": (
                        "Execute a shell command inside the project directory. "
                        "NOTE: This is a sensitive action that requires explicit human approval before running."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The shell command to execute, e.g. 'git status' or 'python --version'.",
                            }
                        },
                        "required": ["command"],
                    },
                },
            },
        ]
