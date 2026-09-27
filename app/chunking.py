import re


def chunk_text(text: str, size: int = 1000, overlap: int = 100) -> list[str]:
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("Invalid chunk size/overlap")
    result, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if value := text[start:end].strip():
            result.append(value)
        if end == len(text):
            break
        start = end - overlap
    return result


def chunk_by_headers(text: str, size: int = 1600, overlap: int = 120) -> list[dict]:
    """Split markdown/plain text by headings, retaining the active section path."""
    sections, path, body = [], [], []
    heading = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

    def flush():
        if not body:
            return
        content = "\n".join(body).strip()
        for index, value in enumerate(chunk_text(content, size, overlap)):
            sections.append({"header": " > ".join(path), "text": value, "chunk_index": index})
        body.clear()

    for line in text.splitlines():
        match = heading.match(line.strip())
        if not match:
            body.append(line)
            continue
        flush()
        level, title = len(match.group(1)), match.group(2)
        path[:] = path[: level - 1]
        path.append(title)
    flush()
    return sections


def chunks_for_page(text: str, strategy: str = "page") -> list[dict]:
    if strategy == "header":
        return chunk_by_headers(text)
    if strategy != "page":
        raise ValueError(f"Unknown chunk strategy: {strategy}")
    return [{"header": "", "text": value, "chunk_index": index}
            for index, value in enumerate(chunk_text(text))]
