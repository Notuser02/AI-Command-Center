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
import re
import html as html_lib
import json
import subprocess
from urllib.parse import unquote, urlparse, parse_qs

import requests


# ── Safety limits ──────────────────────────────────────────────────
MAX_FILE_SIZE = 100_000  # 100 KB — prevents reading huge files

# Directories/files to hide from list_files (noise, not useful to agent)
IGNORED_NAMES = {"venv", "__pycache__", ".git", "node_modules", ".env"}

# search_files caps
MAX_SEARCH_MATCHES = 50
MAX_SEARCH_FILES = 500

# web tool caps
MAX_WEB_TEXT = 15_000       # characters handed to the model
MAX_WEB_DOWNLOAD = 200_000  # bytes read from the network
WEB_TIMEOUT = (10, 20)      # (connect, read) seconds

# Hosts the agent may never fetch (SSRF protection): localhost, private LAN
# ranges, the Tailscale CGNAT range, and tailnet domains.
def _is_blocked_host(hostname: str) -> bool:
    host = (hostname or "").strip().lower().rstrip(".")
    if host in ("localhost", "") or host.endswith(".ts.net") or host.endswith(".local"):
        return True
    if host in ("0.0.0.0", "::1", "[::1]"):
        return True
    parts = host.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        o1, o2 = int(parts[0]), int(parts[1])
        if o1 in (10, 127, 0):
            return True
        if o1 == 192 and o2 == 168:
            return True
        if o1 == 172 and 16 <= o2 <= 31:
            return True
        if o1 == 100 and 64 <= o2 <= 127:
            return True  # Tailscale CGNAT range
    return False

# Files the agent may never read OR write, even inside allowed dirs.
# These hold secrets (.env contains API keys) — hiding them from listings
# is not enough, the agent must not be able to open them directly either.
SENSITIVE_FILE_PREFIXES = (".env",)


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
            "search_files": self._search_files,
            "write_file": self._write_file,
            "run_command": self._run_command,
            "web_search": self._web_search,
            "web_fetch": self._web_fetch,
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
        Reject secret files (.env etc.) even though they sit inside the
        allowed directories. list_files hides them, but without this check
        the agent could still open them by guessing the path.
        """
        name = os.path.basename(abs_path).lower()
        if name.startswith(SENSITIVE_FILE_PREFIXES):
            raise PermissionError(
                f"Access denied: '{name}' is a sensitive file the agent may not touch."
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

    # ── Web tools (read-only, public internet) ────────────────────

    def _web_search(self, query):
        """
        Keyless web search. Tries DuckDuckGo's lite endpoint first; some
        networks block it, so Bing's HTML page is the fallback. Returns
        the top results as 'title — url' lines.
        """
        q = (query or "").strip()[:400]
        if not q:
            return "Error: empty query."

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        results, engines = [], []
        try:
            resp = requests.get(
                "https://lite.duckduckgo.com/lite/",
                params={"q": q},
                headers={**headers, "Referer": "https://lite.duckduckgo.com/"},
                timeout=WEB_TIMEOUT,
            )
            if resp.status_code == 200:
                anchors = re.findall(
                    r'<a[^>]*class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                    resp.text, re.S)
                for href, title_html in anchors:
                    title = html_lib.unescape(re.sub(r"<[^>]+>", "", title_html)).strip()
                    url = self._unwrap_ddg_link(href)
                    if title and url:
                        results.append(f"{title} — {url}")
                if results:
                    engines.append("duckduckgo")
        except requests.RequestException:
            pass

        if not results:
            # Bing HTML fallback (no API key needed)
            try:
                resp = requests.get(
                    "https://www.bing.com/search",
                    params={"q": q, "count": "10"},
                    headers=headers,
                    timeout=WEB_TIMEOUT,
                )
                if resp.status_code == 200:
                    anchors = re.findall(
                        r'<h2><a[^>]*href="(http[^"]+)"[^>]*>(.*?)</a></h2>',
                        resp.text, re.S)
                    for href, title_html in anchors:
                        title = html_lib.unescape(re.sub(r"<[^>]+>", "", title_html)).strip()
                        if title and href:
                            clean_href = html_lib.unescape(href)  # &amp; → & so the u= param parses
                            results.append(f"{title} — {self._unwrap_bing_link(clean_href)}")
                    if results:
                        engines.append("bing")
            except requests.RequestException:
                pass

        if not results:
            net_note = " (network may be blocking search engines)" if engines == [] else ""
            return f"No results for '{q}'{net_note}."

        return f"[via {' + '.join(engines)}]\n" + "\n".join(results[:8])

    @staticmethod
    def _unwrap_ddg_link(href):
        """DuckDuckGo wraps result URLs: //duckduckgo.com/l/?uddg=<encoded>."""
        if "uddg=" in href:
            qs = parse_qs(urlparse(href if "://" in href else "https:" + href).query)
            if "uddg" in qs:
                return qs["uddg"][0]
        return href

    @staticmethod
    def _unwrap_bing_link(href):
        """Bing wraps result URLs in /ck/a with the target base64-encoded in u=a1<...>."""
        if "/ck/a" in href:
            qs = parse_qs(urlparse(href).query)
            u = qs.get("u", [""])[0]
            if u.startswith("a1"):
                import base64
                b64 = u[2:].replace("-", "+").replace("_", "/")
                b64 += "=" * (-len(b64) % 4)  # restore padding
                try:
                    return base64.b64decode(b64).decode("utf-8", errors="replace")
                except Exception:
                    return href
        return href

    def _web_fetch(self, url):
        """
        GET a public web page and return its readable text.
        Blocks private/internal hosts and re-checks every redirect hop.
        """
        current = (url or "").strip()
        if not current:
            return "Error: empty URL."

        for _hop in range(4):  # 1 original + up to 3 redirects
            if not current.startswith(("http://", "https://")):
                return "Error: only http:// and https:// URLs are allowed."
            host = urlparse(current).hostname or ""
            if _is_blocked_host(host):
                return f"Error: fetching internal/private hosts ('{host}') is not allowed."

            try:
                resp = requests.get(
                    current,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                    timeout=WEB_TIMEOUT,
                    stream=True,
                    allow_redirects=False,  # followed manually so each hop is checked
                )
            except requests.RequestException as e:
                return f"Error: fetch failed ({type(e).__name__})."

            if resp.status_code in (301, 302, 303, 307, 308):
                next_url = resp.headers.get("Location", "")
                resp.close()
                if not next_url:
                    return "Error: redirect without a target."
                if next_url.startswith("/"):  # relative redirect
                    next_url = f"{urlparse(current).scheme}://{urlparse(current).netloc}{next_url}"
                current = next_url
                continue

            if resp.status_code != 200:
                resp.close()
                return f"Error: HTTP {resp.status_code} from {current}."

            # stream with a hard byte cap
            chunks = []
            total = 0
            for chunk in resp.iter_content(chunk_size=8192):
                chunks.append(chunk)
                total += len(chunk)
                if total >= MAX_WEB_DOWNLOAD:
                    break
            resp.close()
            raw = b"".join(chunks).decode("utf-8", errors="replace")

            text = self._html_to_text(raw)[:MAX_WEB_TEXT]
            return f"{current}\n\n{text}"

        return "Error: too many redirects."

    @staticmethod
    def _html_to_text(html):
        html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
        html = re.sub(r"(?s)<[^>]+>", " ", html)
        text = html_lib.unescape(html)
        return re.sub(r"[ \t]+", " ", re.sub(r"\s*\n\s*", "\n", text)).strip()

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
                    "name": "web_search",
                    "description": (
                        "Search the public web (DuckDuckGo). Returns the top results as "
                        "'title — url'. Use for current information, documentation, error "
                        "messages, or anything your training data may not know."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query.",
                            }
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "web_fetch",
                    "description": (
                        "Fetch a public web page and return its readable text (truncated). "
                        "Use after web_search to read a result, or for any public URL. "
                        "Internal/private addresses are blocked."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "The http(s) URL to fetch.",
                            }
                        },
                        "required": ["url"],
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
