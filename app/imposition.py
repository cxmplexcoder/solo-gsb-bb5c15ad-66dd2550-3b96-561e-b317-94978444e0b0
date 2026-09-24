"""小册子拼版核心算法。

规则
----
1. 按原页顺序分帖，每帖最多容纳 ``max_sheets * 4`` 页；
2. 仅末帖在尾部补空白页至 4 的倍数，空白页用 ``None`` 表示；
3. 每帖内部按纸张“从外到内”给出正反面左右页码；
4. 左装订（left）：最外张正面 = 末页/首页，背面 = 次页/倒数第二页，
   逐张向内递推；右装订（right）将左右页位镜像交换。

章节分帖（``split_signatures_by_chapters`` / ``impose_chapters``）
----
- 章节不可跨帖，相邻章节可合帖；每帖实际页数不超过 ``max_sheets * 4``；
- 分帖边界依次最小化：各帖补至 4 的倍数所需空白总数 → 帖数；
  仍相同则优先最早的分帖边界；
- 每帖各自在尾部补空白至 4 的倍数，再按规则 3/4 拼版。

补印复用（``plan_reprint``）
----
- 输入旧版与新版按阅读顺序排列的页面 ID 列表，沿用普通拼版（规则 1/2/3/4）
  分别分帖、补空白并把四个页位转换为页面 ID 或 ``None``；
- 仅当新版印张四个页位的 ID 与某张旧印张完全相同、且这四个页位均未改动时复用；
  匹配允许跨帖，每张旧印张最多被匹配一次；否则整张重印。
"""
from __future__ import annotations

from typing import List, Literal, Optional, Tuple, TypeVar

Binding = Literal["left", "right"]

# 单帖页位上的页面标识：普通拼版为页码（int），补印拼版为页面 ID（str）
T = TypeVar("T")

# 单张纸的一页描述：(全局页码或 None, 在帖内纸张上的位置)
# side: "front" 正面 / "back" 背面；position: "left" 左页 / "right" 右页


def split_signatures(total_pages: int, max_sheets: int) -> List[List[Optional[int]]]:
    """按原页顺序分帖，末帖补空白至 4 的倍数。

    返回二维列表：外层为帖（顺序），内层为该帖按原页顺序排列的页码，
    末帖补齐位置为 ``None``。
    """
    capacity = max_sheets * 4
    signatures: List[List[Optional[int]]] = []

    start = 1
    while start <= total_pages:
        end = min(start + capacity - 1, total_pages)
        pages: List[Optional[int]] = list(range(start, end + 1))
        # 仅末帖需要补齐（前面的帖都恰好装满，本身就是 4 的倍数）
        if len(pages) % 4 != 0:
            pages.extend([None] * (4 - len(pages) % 4))
        signatures.append(pages)
        start = end + 1

    return signatures


def impose_signature(
    pages: List[Optional[T]],
    binding: Binding,
) -> List[dict]:
    """对一个帖拼版，按纸张从外到内返回各张正反面的左右页位。

    ``pages`` 长度必须为 ``4s``（``s`` 为纸张数），元素可以是页码（int）或
    页面 ID（str）等任意页面标识；末帖补齐位置为 ``None``，对应页位返回 ``null``。
    """
    sheet_count = len(pages) // 4
    n = len(pages)  # 帖页数（含补齐的空白）
    sheets: List[dict] = []

    for k in range(sheet_count):
        # 左装订下，第 k 张（k=0 最外张）四个页位的帖内位置索引（0-based）：
        #   正面左 n-1-2k、正面右 2k
        #   背面左 2k+1、背面右 n-2-2k
        front_left = pages[n - 1 - 2 * k]
        front_right = pages[2 * k]
        back_left = pages[2 * k + 1]
        back_right = pages[n - 2 - 2 * k]

        if binding == "right":
            # 右装订：左右页位镜像交换
            front_left, front_right = front_right, front_left
            back_left, back_right = back_right, back_left

        sheets.append(
            {
                "sheet_index": k + 1,
                "front": {"left": front_left, "right": front_right},
                "back": {"left": back_left, "right": back_right},
            }
        )

    return sheets


def impose(total_pages: int, max_sheets: int, binding: Binding) -> List[dict]:
    """完整拼版：分帖并逐帖返回拼版结果。"""
    grouped = split_signatures(total_pages, max_sheets)
    result: List[dict] = []
    for index, pages in enumerate(grouped, start=1):
        result.append(
            {
                "signature_index": index,
                "sheet_count": len(pages) // 4,
                "page_count_padded": len(pages),
                "sheets": impose_signature(pages, binding),
            }
        )
    return result


def split_signatures_by_chapters(
    total_pages: int,
    max_sheets: int,
    chapter_starts: List[int],
) -> List[List[Optional[int]]]:
    """按章节边界分帖：章节不可跨帖，相邻章节可合帖。

    在满足“单帖实际页数 ≤ ``max_sheets * 4``”的分帖方案中，依次最小化：

    1. 各帖补至 4 的倍数所需空白页总数；
    2. 帖数；
    3. 仍相同则取最早的分帖边界（排在前面的帖尽量短）。

    每帖尾部补空白至 4 的倍数（``None``）。
    任一单章页数超过容量时抛 ``ValueError``。
    """
    capacity = max_sheets * 4
    starts = list(chapter_starts)
    ends = starts[1:] + [total_pages + 1]
    lengths = [end - start for start, end in zip(starts, ends)]
    for start, length in zip(starts, lengths):
        if length > capacity:
            raise ValueError(
                f"起始页为 {start} 的章节共 {length} 页，超过单帖容量 {capacity} 页"
            )

    m = len(lengths)
    # 章节页数前缀和，O(1) 求连续若干章的总页数
    prefix = [0] * (m + 1)
    for i, length in enumerate(lengths, 1):
        prefix[i] = prefix[i - 1] + length

    def blanks(count: int) -> int:
        # 补至 4 的倍数所需空白页数
        return (-count) % 4

    # 后缀 DP：best[i] = 章节 i..m（1-based）的最优 (空白总数, 帖数)。
    # 内层循环最多推进 capacity 章（每章至少 1 页），整体 O(m * capacity)。
    best: List[Tuple[int, int]] = [(0, 0)] * (m + 2)
    for i in range(m, 0, -1):
        best_cost: Optional[Tuple[int, int]] = None
        for j in range(i, m + 1):
            count = prefix[j] - prefix[i - 1]
            if count > capacity:
                break
            candidate = (blanks(count) + best[j + 1][0], 1 + best[j + 1][1])
            if best_cost is None or candidate < best_cost:
                best_cost = candidate
        # 单章必能成帖（前面已校验容量），best_cost 不会为 None
        assert best_cost is not None
        best[i] = best_cost

    # 重建：达到最优成本的边界中取最早者（每步选最小的 j）
    signatures: List[List[Optional[int]]] = []
    i = 1
    while i <= m:
        for j in range(i, m + 1):
            count = prefix[j] - prefix[i - 1]
            if count > capacity:
                break
            if (blanks(count) + best[j + 1][0], 1 + best[j + 1][1]) == best[i]:
                pages: List[Optional[int]] = list(
                    range(starts[i - 1], starts[i - 1] + count)
                )
                pages.extend([None] * blanks(count))
                signatures.append(pages)
                i = j + 1
                break
    return signatures


def impose_chapters(
    total_pages: int,
    max_sheets: int,
    binding: Binding,
    chapter_starts: List[int],
) -> List[dict]:
    """按章节分帖的完整拼版：每帖额外给出原页起止页码与空白数。"""
    grouped = split_signatures_by_chapters(total_pages, max_sheets, chapter_starts)
    result: List[dict] = []
    for index, pages in enumerate(grouped, start=1):
        real_pages = [p for p in pages if p is not None]
        result.append(
            {
                "signature_index": index,
                "sheet_count": len(pages) // 4,
                "page_count_padded": len(pages),
                "page_start": real_pages[0],
                "page_end": real_pages[-1],
                "blank_count": len(pages) - len(real_pages),
                "sheets": impose_signature(pages, binding),
            }
        )
    return result


def impose_ids(
    page_ids: List[Optional[str]], max_sheets: int, binding: Binding
) -> List[dict]:
    """以页面 ID 替代页码执行普通拼版。

    与 :func:`impose` 的分帖（顺序切分、每帖最多 ``max_sheets`` 张）、补空白
    （仅末帖尾部补 ``None``）和左右页位规则完全一致，仅把页码换成页面 ID。
    结果保留 ``signature_index`` / ``sheet_index`` / ``front`` / ``back``
    结构，页位值为页面 ID 或 ``None``。
    """
    # split_signatures 仅按长度分帖、末帖补 None；取其切分与补齐位置，
    # 保证与普通拼版规则 1/2 完全一致。
    grouped = split_signatures(len(page_ids), max_sheets)
    result: List[dict] = []
    for index, pages in enumerate(grouped, start=1):
        # pages 是从 1 开始的占位页码；真实页取 page_ids[i-1]，补齐位置为 None。
        sig_pages: List[Optional[str]] = [
            page_ids[pos - 1] if pos is not None else None for pos in pages
        ]
        result.append(
            {
                "signature_index": index,
                "sheet_count": len(sig_pages) // 4,
                "sheets": impose_signature(sig_pages, binding),
            }
        )
    return result


def _sheet_key(sheet: dict) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """印张四个页位的标识元组：(正面左, 正面右, 背面左, 背面右)。"""
    return (
        sheet["front"]["left"],
        sheet["front"]["right"],
        sheet["back"]["left"],
        sheet["back"]["right"],
    )
def plan_reprint(
    old_page_ids: List[str],
    new_page_ids: List[str],
    max_sheets: int,
    binding: Binding,
    changed_page_ids: List[str],
) -> dict:
    """补印复用规划：分别拼版旧/新版，按印张四页位匹配可复用的旧印张。

    复用条件（同时满足）：

    1. 新版印张四个页位的 ID（含同为空白的 ``None``）与某张旧印张完全相同；
    2. 这四个页位上的非空 ID 均不在改动集合中（空白位天然未改动）；
    3. 该旧印张尚未被其它新印张匹配（每张旧印张最多匹配一次）。

    匹配允许跨帖，按新版帖号、张号顺序贪心选取第一个满足条件的旧印张；
    其余新版印张标记为整张重印。
    """
    old_book = impose_ids(old_page_ids, max_sheets, binding)
    new_book = impose_ids(new_page_ids, max_sheets, binding)
    changed = set(changed_page_ids)

    # 旧印张按四页位标识索引：key -> 可用旧印张列表 [(帖号, 张号), ...]，
    # 匹配成功即弹出，保证每张旧印张最多匹配一次。
    available: dict = {}
    for signature in old_book:
        for sheet in signature["sheets"]:
            available.setdefault(_sheet_key(sheet), []).append(
                (signature["signature_index"], sheet["sheet_index"])
            )

    signatures: List[dict] = []
    reprint_sheet_count = 0
    for signature in new_book:
        sheets: List[dict] = []
        for sheet in signature["sheets"]:
            key = _sheet_key(sheet)
            positions = (
                sheet["front"]["left"],
                sheet["front"]["right"],
                sheet["back"]["left"],
                sheet["back"]["right"],
            )
            untouched = all(
                page_id is None or page_id not in changed for page_id in positions
            )
            candidates = available.get(key)
            match = candidates.pop(0) if untouched and candidates else None

            if match is not None:
                old_signature_index, old_sheet_index = match
                reused = True
                reprint = False
            else:
                old_signature_index = None
                old_sheet_index = None
                reused = False
                reprint = True
                reprint_sheet_count += 1

            sheets.append(
                {
                    "sheet_index": sheet["sheet_index"],
                    "reused": reused,
                    "reprint": reprint,
                    "old_signature_index": old_signature_index,
                    "old_sheet_index": old_sheet_index,
                    "front": sheet["front"],
                    "back": sheet["back"],
                }
            )

        signatures.append(
            {
                "signature_index": signature["signature_index"],
                "sheet_count": signature["sheet_count"],
                "sheets": sheets,
            }
        )

    return {
        "max_sheets_per_signature": max_sheets,
        "binding": binding,
        "signature_count": len(signatures),
        "reprint_sheet_count": reprint_sheet_count,
        "signatures": signatures,
    }
