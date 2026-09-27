import re


def chunk_text(text, size=1600, overlap=120):
    result, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        value = text[start:end].strip()
        if value:
            result.append(value)
        if end == len(text):
            break
        start = end - overlap
    return result


def chunks_for_page(text, strategy="page"):
    if strategy == "page":
        return [{"header": "", "text": value, "chunk_index": index}
                for index, value in enumerate(chunk_text(text, 1000, 100))]
    if strategy != "header":
        raise ValueError(f"Unknown chunk strategy: {strategy}")
    groups, path, body = [], [], []
    heading = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

    def flush():
        if body:
            content = "\n".join(body).strip()
            for index, value in enumerate(chunk_text(content)):
                groups.append({"header": " > ".join(path), "text": value, "chunk_index": index})
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
    return groups
