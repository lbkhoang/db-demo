from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.chunking import chunk_by_headers, chunks_for_page


def main():
    text = "# Leave\nEmployees receive 15 days.\n## Request\nSubmit three days before.\n# Remote work\nTwo days per week."
    chunks = chunk_by_headers(text, size=200)
    assert [item["header"] for item in chunks] == ["Leave", "Leave > Request", "Remote work"]
    assert chunks_for_page(text, "page")
    print("PASS: header hierarchy is retained in section_path")


if __name__ == "__main__":
    main()
