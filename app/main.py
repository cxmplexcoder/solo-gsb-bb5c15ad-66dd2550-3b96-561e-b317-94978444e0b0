"""离线小册子拼版 API。"""
from __future__ import annotations

from typing import Annotated, Literal, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict, StringConstraints, model_validator

from .imposition import impose, impose_chapters, plan_reprint

app = FastAPI(
    title="离线小册子拼版 API",
    description=(
        "按帖拆分并完成小册子拼版（signature imposition）。"
        "左装订最外张正面为 末页/首页，背面为 次页/倒数第二页；"
        "右装订左右页位镜像交换。"
        "支持按章节首页分帖：章节不可跨帖，相邻章节可合帖。"
        "支持补印复用：新版印张四页位与旧版相同且均未改动时复用旧印张，否则整张重印。"
    ),
    version="1.2.0",
)

# 非空页面 ID
PageId = Annotated[str, StringConstraints(min_length=1)]


class ImpositionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_pages: int = Field(
        ..., ge=1, description="总页数，正整数（1, 2, 3, ...）"
    )
    max_sheets_per_signature: int = Field(
        ..., ge=1, description="每帖最多纸张数，正整数；每帖最多容纳其 4 倍页数"
    )
    binding: Literal["left", "right"] = Field(
        ..., description="装订方向：left=左装订，right=右装订"
    )


class PagePair(BaseModel):
    left: Optional[int] = Field(..., description="左页页码，空白页为 null")
    right: Optional[int] = Field(..., description="右页页码，空白页为 null")


class Sheet(BaseModel):
    sheet_index: int = Field(..., description="帖内纸张序号，从 1 开始（1 为最外张）")
    front: PagePair = Field(..., description="正面左右页码")
    back: PagePair = Field(..., description="背面左右页码")


class Signature(BaseModel):
    signature_index: int = Field(..., description="帖号，从 1 开始")
    sheet_count: int = Field(..., description="本帖纸张数")
    page_count_padded: int = Field(..., description="本帖补齐空白后的总页数（4 的倍数）")
    sheets: list[Sheet] = Field(..., description="帖内纸张，按从外到内排列")


class ImpositionResponse(BaseModel):
    total_pages: int
    max_sheets_per_signature: int
    binding: Literal["left", "right"]
    signature_count: int
    signatures: list[Signature]


class ChapterImpositionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_pages: int = Field(
        ..., ge=1, description="总页数，正整数（1, 2, 3, ...）"
    )
    max_sheets_per_signature: int = Field(
        ..., ge=1, description="每帖最多纸张数，正整数；每帖最多容纳其 4 倍页数"
    )
    binding: Literal["left", "right"] = Field(
        ..., description="装订方向：left=左装订，right=右装订"
    )
    chapter_starts: list[int] = Field(
        ..., min_length=1, description="各章节首页页码，严格递增且首项为 1"
    )

    @model_validator(mode="after")
    def validate_chapter_starts(self) -> "ChapterImpositionRequest":
        starts = self.chapter_starts
        if starts[0] != 1:
            raise ValueError("chapter_starts 首项必须为 1")
        if any(curr <= prev for prev, curr in zip(starts, starts[1:])):
            raise ValueError("chapter_starts 必须严格递增")
        if starts[-1] > self.total_pages:
            raise ValueError("chapter_starts 不能超过 total_pages")
        capacity = self.max_sheets_per_signature * 4
        ends = starts[1:] + [self.total_pages + 1]
        for start, end in zip(starts, ends):
            if end - start > capacity:
                raise ValueError(
                    f"起始页为 {start} 的章节共 {end - start} 页，"
                    f"超过单帖容量 {capacity} 页（4 × max_sheets_per_signature）"
                )
        return self


class ChapterSignature(BaseModel):
    signature_index: int = Field(..., description="帖号，从 1 开始")
    sheet_count: int = Field(..., description="本帖纸张数")
    page_count_padded: int = Field(..., description="本帖补齐空白后的总页数（4 的倍数）")
    page_start: int = Field(..., description="本帖原页起始页码")
    page_end: int = Field(..., description="本帖原页结束页码")
    blank_count: int = Field(..., description="本帖尾部补齐的空白页数")
    sheets: list[Sheet] = Field(..., description="帖内纸张，按从外到内排列")


class ChapterImpositionResponse(BaseModel):
    total_pages: int
    max_sheets_per_signature: int
    binding: Literal["left", "right"]
    chapter_starts: list[int]
    signature_count: int
    signatures: list[ChapterSignature]


class ReprintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    old_page_ids: list[PageId] = Field(
        ...,
        min_length=1,
        description="旧版页面 ID，按阅读顺序排列；非空字符串且不重复",
    )
    new_page_ids: list[PageId] = Field(
        ...,
        min_length=1,
        description="新版页面 ID，按阅读顺序排列；非空字符串且不重复",
    )
    max_sheets_per_signature: int = Field(
        ..., ge=1, description="两版共用的每帖最多纸张数，正整数；每帖最多容纳其 4 倍页数"
    )
    binding: Literal["left", "right"] = Field(
        ..., description="两版共用的装订方向：left=左装订，right=右装订"
    )
    changed_page_ids: list[PageId] = Field(
        ..., description="新版内容改动的页面 ID；每项必须属于 new_page_ids，可为空数组"
    )

    @model_validator(mode="after")
    def validate_reprint_request(self) -> "ReprintRequest":
        if len(set(self.old_page_ids)) != len(self.old_page_ids):
            raise ValueError("old_page_ids 内页面 ID 不得重复")
        if len(set(self.new_page_ids)) != len(self.new_page_ids):
            raise ValueError("new_page_ids 内页面 ID 不得重复")
        not_in_new = set(self.changed_page_ids) - set(self.new_page_ids)
        if not_in_new:
            raise ValueError(
                f"changed_page_ids 必须属于 new_page_ids，越界 ID: {sorted(not_in_new)}"
            )
        return self


class ReprintPagePair(BaseModel):
    left: Optional[PageId] = Field(..., description="左页页面 ID，空白页为 null")
    right: Optional[PageId] = Field(..., description="右页页面 ID，空白页为 null")


class ReprintSheet(BaseModel):
    sheet_index: int = Field(..., description="新版帖内纸张序号，从 1 开始（1 为最外张）")
    reused: bool = Field(..., description="是否复用旧印张；true=复用，false=重印")
    reprint: bool = Field(..., description="是否整张重印；与 reused 互为相反")
    old_signature_index: Optional[int] = Field(
        ..., description="复用时的旧版帖号（从 1 开始）；重印时为 null"
    )
    old_sheet_index: Optional[int] = Field(
        ..., description="复用时的旧版帖内张号（从 1 开始）；重印时为 null"
    )
    front: ReprintPagePair = Field(..., description="新版正面左右页面 ID")
    back: ReprintPagePair = Field(..., description="新版背面左右页面 ID")


class ReprintSignature(BaseModel):
    signature_index: int = Field(..., description="新版帖号，从 1 开始")
    sheet_count: int = Field(..., description="本帖纸张数")
    sheets: list[ReprintSheet] = Field(..., description="帖内纸张，按从外到内排列")


class ReprintResponse(BaseModel):
    max_sheets_per_signature: int
    binding: Literal["left", "right"]
    signature_count: int = Field(..., description="新版帖数")
    reprint_sheet_count: int = Field(..., description="需整张重印的印张总数")
    signatures: list[ReprintSignature] = Field(..., description="新版各帖逐张复用/重印结果")


@app.get("/health", tags=["健康检查"])
def health() -> dict:
    return {"status": "ok"}


@app.post(
    "/api/v1/impose",
    response_model=ImpositionResponse,
    tags=["拼版"],
    summary="小册子拼版",
)
def create_imposition(request: ImpositionRequest) -> ImpositionResponse:
    signatures = impose(
        total_pages=request.total_pages,
        max_sheets=request.max_sheets_per_signature,
        binding=request.binding,
    )
    return ImpositionResponse(
        total_pages=request.total_pages,
        max_sheets_per_signature=request.max_sheets_per_signature,
        binding=request.binding,
        signature_count=len(signatures),
        signatures=signatures,
    )


@app.post(
    "/api/v1/impose/chapters",
    response_model=ChapterImpositionResponse,
    tags=["拼版"],
    summary="按章节分帖的小册子拼版",
)
def create_chapter_imposition(
    request: ChapterImpositionRequest,
) -> ChapterImpositionResponse:
    signatures = impose_chapters(
        total_pages=request.total_pages,
        max_sheets=request.max_sheets_per_signature,
        binding=request.binding,
        chapter_starts=request.chapter_starts,
    )
    return ChapterImpositionResponse(
        total_pages=request.total_pages,
        max_sheets_per_signature=request.max_sheets_per_signature,
        binding=request.binding,
        chapter_starts=request.chapter_starts,
        signature_count=len(signatures),
        signatures=signatures,
    )


@app.post(
    "/api/v1/impose/reprint",
    response_model=ReprintResponse,
    tags=["拼版"],
    summary="补印复用规划",
)
def create_reprint_plan(request: ReprintRequest) -> ReprintResponse:
    result = plan_reprint(
        old_page_ids=request.old_page_ids,
        new_page_ids=request.new_page_ids,
        max_sheets=request.max_sheets_per_signature,
        binding=request.binding,
        changed_page_ids=request.changed_page_ids,
    )
    return ReprintResponse(**result)


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request, exc: Exception) -> JSONResponse:
    # 兜底：未预期错误统一返回 500，避免向前端泄漏堆栈
    return JSONResponse(status_code=500, content={"detail": "内部错误"})
