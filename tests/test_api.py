"""API 层测试：正常请求与非法参数（4xx）。"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_impose_basic_left():
    response = client.post(
        "/api/v1/impose",
        json={
            "total_pages": 16,
            "max_sheets_per_signature": 4,
            "binding": "left",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["signature_count"] == 1
    assert data["signatures"][0]["signature_index"] == 1
    assert data["signatures"][0]["sheet_count"] == 4
    first = data["signatures"][0]["sheets"][0]
    assert first["sheet_index"] == 1
    assert first["front"] == {"left": 16, "right": 1}
    assert first["back"] == {"left": 2, "right": 15}


def test_impose_right_binding():
    response = client.post(
        "/api/v1/impose",
        json={
            "total_pages": 16,
            "max_sheets_per_signature": 4,
            "binding": "right",
        },
    )
    assert response.status_code == 200
    first = response.json()["signatures"][0]["sheets"][0]
    assert first["front"] == {"left": 1, "right": 16}
    assert first["back"] == {"left": 15, "right": 2}


def test_impose_null_blank_pages():
    response = client.post(
        "/api/v1/impose",
        json={"total_pages": 1, "max_sheets_per_signature": 1, "binding": "left"},
    )
    assert response.status_code == 200
    sheet = response.json()["signatures"][0]["sheets"][0]
    # 1 页补 3 空白：最外张正面 空白/1
    assert sheet["front"] == {"left": None, "right": 1}
    assert sheet["back"] == {"left": None, "right": None}


def test_invalid_total_pages_zero():
    response = client.post(
        "/api/v1/impose",
        json={"total_pages": 0, "max_sheets_per_signature": 4, "binding": "left"},
    )
    assert 400 <= response.status_code < 500
    assert response.status_code == 422


def test_invalid_total_pages_negative():
    response = client.post(
        "/api/v1/impose",
        json={"total_pages": -5, "max_sheets_per_signature": 4, "binding": "left"},
    )
    assert response.status_code == 422


def test_invalid_total_pages_not_integer():
    response = client.post(
        "/api/v1/impose",
        json={"total_pages": 1.5, "max_sheets_per_signature": 4, "binding": "left"},
    )
    assert response.status_code == 422


def test_invalid_max_sheets_zero():
    response = client.post(
        "/api/v1/impose",
        json={"total_pages": 10, "max_sheets_per_signature": 0, "binding": "left"},
    )
    assert response.status_code == 422


def test_invalid_binding_value():
    response = client.post(
        "/api/v1/impose",
        json={"total_pages": 10, "max_sheets_per_signature": 4, "binding": "top"},
    )
    assert response.status_code == 422


def test_missing_required_field():
    response = client.post(
        "/api/v1/impose",
        json={"total_pages": 10, "max_sheets_per_signature": 4},
    )
    assert response.status_code == 422


def test_unknown_field_rejected():
    response = client.post(
        "/api/v1/impose",
        json={
            "total_pages": 10,
            "max_sheets_per_signature": 4,
            "binding": "left",
            "extra": 1,
        },
    )
    assert response.status_code == 422


def test_empty_body_returns_422():
    response = client.post("/api/v1/impose", json={})
    assert response.status_code == 422


def test_impose_chapters_basic():
    response = client.post(
        "/api/v1/impose/chapters",
        json={
            "total_pages": 20,
            "max_sheets_per_signature": 2,
            "binding": "left",
            "chapter_starts": [1, 5, 9, 13],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["signature_count"] == 3
    ranges = [
        (s["page_start"], s["page_end"], s["blank_count"])
        for s in data["signatures"]
    ]
    assert ranges == [(1, 4, 0), (5, 12, 0), (13, 20, 0)]
    # 沿用 sheets 页位结构：首帖最外张正面 = 末页/首页
    first = data["signatures"][0]["sheets"][0]
    assert first["front"] == {"left": 4, "right": 1}
    assert first["back"] == {"left": 2, "right": 3}


def test_impose_chapters_right_binding_and_blanks():
    response = client.post(
        "/api/v1/impose/chapters",
        json={
            "total_pages": 10,
            "max_sheets_per_signature": 2,
            "binding": "right",
            "chapter_starts": [1, 6, 9],
        },
    )
    assert response.status_code == 200
    sigs = response.json()["signatures"]
    assert [(s["page_start"], s["page_end"]) for s in sigs] == [(1, 8), (9, 10)]
    # 右装订镜像：最外张正面 = 首页/末页
    assert sigs[0]["sheets"][0]["front"] == {"left": 1, "right": 8}
    # 末帖 2 页补 2 空白
    assert sigs[1]["blank_count"] == 2
    assert sigs[1]["sheets"][0]["front"] == {"left": 9, "right": None}


def test_chapters_first_start_not_one():
    response = client.post(
        "/api/v1/impose/chapters",
        json={
            "total_pages": 10,
            "max_sheets_per_signature": 2,
            "binding": "left",
            "chapter_starts": [2, 5],
        },
    )
    assert response.status_code == 422


def test_chapters_not_strictly_increasing():
    for starts in ([1, 3, 3], [1, 5, 4]):
        response = client.post(
            "/api/v1/impose/chapters",
            json={
                "total_pages": 10,
                "max_sheets_per_signature": 2,
                "binding": "left",
                "chapter_starts": starts,
            },
        )
        assert response.status_code == 422


def test_chapters_empty_list():
    response = client.post(
        "/api/v1/impose/chapters",
        json={
            "total_pages": 10,
            "max_sheets_per_signature": 2,
            "binding": "left",
            "chapter_starts": [],
        },
    )
    assert response.status_code == 422


def test_chapters_start_beyond_total_pages():
    response = client.post(
        "/api/v1/impose/chapters",
        json={
            "total_pages": 10,
            "max_sheets_per_signature": 2,
            "binding": "left",
            "chapter_starts": [1, 11],
        },
    )
    assert response.status_code == 422


def test_chapters_single_chapter_too_long():
    # 单章 10 页 > 容量 8（2 张 × 4）-> 422
    response = client.post(
        "/api/v1/impose/chapters",
        json={
            "total_pages": 10,
            "max_sheets_per_signature": 2,
            "binding": "left",
            "chapter_starts": [1],
        },
    )
    assert response.status_code == 422


def test_chapters_missing_field():
    response = client.post(
        "/api/v1/impose/chapters",
        json={
            "total_pages": 10,
            "max_sheets_per_signature": 2,
            "binding": "left",
        },
    )
    assert response.status_code == 422


def test_chapters_unknown_field_rejected():
    response = client.post(
        "/api/v1/impose/chapters",
        json={
            "total_pages": 10,
            "max_sheets_per_signature": 2,
            "binding": "left",
            "chapter_starts": [1],
            "extra": 1,
        },
    )
    assert response.status_code == 422


def test_reprint_identical_versions_reuse_all():
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": ["p1", "p2", "p3", "p4"],
            "new_page_ids": ["p1", "p2", "p3", "p4"],
            "max_sheets_per_signature": 1,
            "binding": "left",
            "changed_page_ids": [],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["signature_count"] == 1
    assert data["reprint_sheet_count"] == 0
    sheet = data["signatures"][0]["sheets"][0]
    assert sheet["reused"] is True
    assert sheet["reprint"] is False
    assert sheet["old_signature_index"] == 1
    assert sheet["old_sheet_index"] == 1
    assert sheet["front"] == {"left": "p4", "right": "p1"}
    assert sheet["back"] == {"left": "p2", "right": "p3"}


def test_reprint_cross_signature_match():
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": [f"p{i}" for i in range(1, 9)],
            "new_page_ids": ["p5", "p6", "p7", "p8", "p1", "p2", "p3", "p4"],
            "max_sheets_per_signature": 1,
            "binding": "left",
            "changed_page_ids": [],
        },
    )
    assert response.status_code == 200
    sheets = [
        sh
        for s in response.json()["signatures"]
        for sh in s["sheets"]
    ]
    assert response.json()["reprint_sheet_count"] == 0
    assert [(sh["old_signature_index"], sh["old_sheet_index"]) for sh in sheets] == [
        (2, 1),
        (1, 1),
    ]


def test_reprint_changed_and_new_sheet():
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": ["p1", "p2", "p3", "p4"],
            "new_page_ids": ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"],
            "max_sheets_per_signature": 1,
            "binding": "left",
            "changed_page_ids": ["p2"],
        },
    )
    assert response.status_code == 200
    sheets = [
        sh
        for s in response.json()["signatures"]
        for sh in s["sheets"]
    ]
    # 第 1 张含改动页 p2 -> 重印；第 2 张新版独有 -> 重印
    assert response.json()["reprint_sheet_count"] == 2
    assert all(sh["reused"] is False for sh in sheets)
    assert all(sh["old_signature_index"] is None for sh in sheets)


def test_reprint_null_blank_positions():
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": ["a"],
            "new_page_ids": ["a"],
            "max_sheets_per_signature": 1,
            "binding": "left",
            "changed_page_ids": [],
        },
    )
    assert response.status_code == 200
    sheet = response.json()["signatures"][0]["sheets"][0]
    assert sheet["front"] == {"left": None, "right": "a"}
    assert sheet["back"] == {"left": None, "right": None}
    assert sheet["reused"] is True


def test_reprint_empty_page_list():
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": [],
            "new_page_ids": ["a"],
            "max_sheets_per_signature": 1,
            "binding": "left",
            "changed_page_ids": [],
        },
    )
    assert response.status_code == 422


def test_reprint_duplicate_id_within_version():
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": ["a", "b"],
            "new_page_ids": ["a", "a"],
            "max_sheets_per_signature": 1,
            "binding": "left",
            "changed_page_ids": [],
        },
    )
    assert response.status_code == 422


def test_reprint_blank_id_rejected():
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": ["a"],
            "new_page_ids": ["a", ""],
            "max_sheets_per_signature": 1,
            "binding": "left",
            "changed_page_ids": [],
        },
    )
    assert response.status_code == 422


def test_reprint_changed_id_not_in_new():
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": ["a"],
            "new_page_ids": ["a"],
            "max_sheets_per_signature": 1,
            "binding": "left",
            "changed_page_ids": ["zzz"],
        },
    )
    assert response.status_code == 422


def test_reprint_changed_id_from_old_only_rejected():
    # 改动 ID 只存在于旧版、不在新版 -> 非法
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": ["a", "b"],
            "new_page_ids": ["a"],
            "max_sheets_per_signature": 1,
            "binding": "left",
            "changed_page_ids": ["b"],
        },
    )
    assert response.status_code == 422


def test_reprint_invalid_max_sheets_and_binding():
    payload = {
        "old_page_ids": ["a"],
        "new_page_ids": ["a"],
        "max_sheets_per_signature": 0,
        "binding": "top",
        "changed_page_ids": [],
    }
    response = client.post("/api/v1/impose/reprint", json=payload)
    assert response.status_code == 422


def test_reprint_missing_field():
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": ["a"],
            "new_page_ids": ["a"],
            "binding": "left",
            "changed_page_ids": [],
        },
    )
    assert response.status_code == 422


def test_reprint_unknown_field_rejected():
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": ["a"],
            "new_page_ids": ["a"],
            "max_sheets_per_signature": 1,
            "binding": "left",
            "changed_page_ids": [],
            "extra": 1,
        },
    )
    assert response.status_code == 422
