"""A tiny read-only MCP server over one local Markdown file."""
from pathlib import Path
import re
import subprocess
import sys

from mcp.server.fastmcp import FastMCP

FILE = Path(__file__).parent / "data" / "software_policy.md"
mcp = FastMCP("markdown-reader")


def chunks() -> list[dict]:
    """Split the demo file by Markdown headings into stable, numbered chunks."""
    text = FILE.read_text(encoding="utf-8-sig")
    sections, current = [], {"heading": "document", "lines": []}
    for line in text.splitlines():
        if re.match(r"^#{1,6}\s+", line):
            if current["lines"]:
                sections.append(current)
            current = {"heading": line.lstrip("#").strip(), "lines": []}
        else:
            current["lines"].append(line)
    if current["lines"]:
        sections.append(current)
    return [{"index": i, "heading": item["heading"], "text": "\n".join(item["lines"]).strip()}
            for i, item in enumerate(sections)]


@mcp.tool()
def list_chunks() -> str:
    """List available chunk IDs and headings without exposing their full text."""
    return "\n".join(f"chunk={item['index']} heading={item['heading']}" for item in chunks())


@mcp.tool()
def read_chunk(index: int) -> str:
    """Read one numbered Markdown chunk; this is the controlled file-read permission."""
    available = chunks()
    if index < 0 or index >= len(available):
        return f"Invalid chunk {index}. Valid IDs: 0..{len(available) - 1}."
    item = available[index]
    return f"chunk={item['index']} heading={item['heading']}\n{item['text']}"


@mcp.tool()
def run_terminal(command: str) -> str:
    """Run a restricted read-only terminal command for the demo Markdown file.

    Only cat/type/Get-Content of data/software_policy.md is allowed.
    This demonstrates terminal permission without exposing arbitrary shell access.
    """
    match = re.fullmatch(r"\s*(?:cat|type|Get-Content)\s+['\"]?([^'\"]+)['\"]?\s*", command)
    if not match:
        return "Blocked: only cat/type/Get-Content data/software_policy.md is allowed."
    requested = Path(match.group(1).replace("\\", "/"))
    if requested.is_absolute() or ".." in requested.parts or requested.as_posix() != "data/software_policy.md":
        return "Blocked: terminal access is limited to data/software_policy.md."
    # Execute a separate read-only process to make the terminal boundary visible.
    try:
        result = subprocess.run(
            [sys.executable, "-c", "from pathlib import Path; print(Path('data/software_policy.md').read_text(encoding='utf-8-sig'))"],
            cwd=Path(__file__).parent,
            stdin=subprocess.DEVNULL,  # Do not inherit MCP's stdio input on Windows.
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return result.stdout[:6000]
    except subprocess.TimeoutExpired:
        return "Terminal read timed out after 5 seconds."
    except subprocess.CalledProcessError as error:
        return f"Terminal read failed: {error}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
