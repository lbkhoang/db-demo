"""Generate four Word fixtures and upload through the public ingestion API."""
import json
from pathlib import Path
import time

from docx import Document
from docx.shared import Pt
import httpx

ROOT = Path("/data/files/demo")


def sentences(kind: str, version: int) -> list[str]:
    if kind == "hr_policy":
        return [
            f"HR-01: Nhân viên chính thức được nghỉ phép {12 if version == 1 else 15} ngày mỗi năm.",
            f"HR-02: Nhân viên được làm việc từ xa {2 if version == 1 else 3} ngày mỗi tuần.",
            "HR-03: Giờ làm việc bắt đầu lúc 9 giờ sáng.",
            "HR-04: Thời gian nghỉ trưa là 60 phút.",
            "HR-05: Nhân viên phải báo nghỉ phép trước 3 ngày làm việc.",
            "HR-06: Nhân viên mới tham gia đào tạo hội nhập trong tuần đầu tiên.",
            "HR-07: Công ty đánh giá hiệu suất mỗi 6 tháng.",
            "HR-08: Nhân viên được cấp một máy tính để làm việc.",
            "HR-09: Yêu cầu cập nhật thông tin cá nhân được gửi cho bộ phận nhân sự.",
            "HR-10: Mọi nhân viên phải hoàn thành khóa học bảo mật hằng năm.",
        ]
    return [
        f"BONUS-01: Nhân viên đạt loại A được thưởng {2 if version == 1 else 3} tháng lương cơ bản.",
        f"BONUS-02: Điều kiện nhận thưởng là làm việc đủ {6 if version == 1 else 9} tháng.",
        "BONUS-03: Nhân viên đạt loại B được thưởng một tháng lương cơ bản.",
        "BONUS-04: Tiền thưởng được chi trả trong tháng 1 năm tiếp theo.",
        "BONUS-05: Thưởng giới thiệu nhân sự thành công là 5 triệu đồng.",
        "BONUS-06: Thưởng sáng kiến được xét duyệt theo từng quý.",
        "BONUS-07: Nhân viên thử việc không thuộc diện thưởng hiệu suất.",
        "BONUS-08: Trưởng bộ phận đề xuất danh sách nhận thưởng.",
        "BONUS-09: Phòng nhân sự tiếp nhận thắc mắc tiền thưởng trong 7 ngày.",
        "BONUS-10: Chính sách thưởng này sử dụng dữ liệu giả lập phục vụ demo.",
    ]


def make_doc(path: Path, lines: list[str]):
    doc = Document()
    doc.styles["Normal"].font.name = "Liberation Sans"
    doc.styles["Normal"].font.size = Pt(12)
    for index, sentence in enumerate(lines):
        if index:
            doc.add_page_break()
        doc.add_paragraph(sentence)
    doc.save(path)


def wait_job(client: httpx.Client, job_id: str, timeout: int = 240):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/jobs/{job_id}")
        response.raise_for_status()
        job = response.json()
        if job["status"] == "ready":
            return job
        if job["status"] == "failed":
            raise RuntimeError(job["error"])
        time.sleep(1)
    raise TimeoutError(f"Job {job_id} chưa hoàn thành")


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = ROOT / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    with httpx.Client(base_url="http://app:8000", timeout=30) as client:
        for kind in ("hr_policy", "bonus_policy"):
            document_id = manifest.get(f"{kind}_v0.1", {}).get("document_id")
            for version in (1, 2):
                key = f"{kind}_v0.{version}"
                path = ROOT / f"{key}.docx"
                make_doc(path, sentences(kind, version))
                if key not in manifest:
                    endpoint = f"/documents/{document_id}/versions" if document_id else "/documents"
                    with path.open("rb") as source:
                        response = client.post(endpoint, files={"file": (path.name, source)}, data={"title": kind})
                    response.raise_for_status()
                    manifest[key] = response.json()
                    document_id = manifest[key]["document_id"]
                    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                item = manifest[key]
                wait_job(client, item["job_id"])
                response = client.get(f"/versions/{item['version_id']}/pages")
                response.raise_for_status()
                pages = response.json()
                assert len(pages) == 10, (key, len(pages))
                for page, expected in zip(pages, sentences(kind, version)):
                    assert " ".join(page["text"].split()) == expected, (key, page)
                print(f"{key}: 10 pages verified", flush=True)


if __name__ == "__main__":
    main()
