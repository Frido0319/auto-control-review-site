from __future__ import annotations

import html
import json
import math
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = ROOT / "raw_sources"
PPT_PDF_DIR = ROOT / "tmp" / "ppt_pdf"
TEXT_DIR = ROOT / "source_text" / "extracted_text"
ASSET_DIR = ROOT / "assets"
SOURCE_PAGE_DIR = ASSET_DIR / "source_pages"
HOMEWORK_PAGE_DIR = ASSET_DIR / "homework_pages"
ANSWER_PAGE_DIR = ASSET_DIR / "answer_pages"


@dataclass(frozen=True)
class Source:
    id: str
    title: str
    original_relative: str
    pdf_path: Path
    role: str
    chapter: str


def read_source_map() -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / "source_map.json").read_text(encoding="utf-8-sig"))


def source_pdf_path(item: dict[str, Any]) -> Path:
    sid = item["id"]
    if item["extension"].lower() == ".pdf":
        return RAW_DIR / f"{sid}.pdf"
    return PPT_PDF_DIR / f"{sid}.pdf"


def classify_source(item: dict[str, Any]) -> tuple[str, str, str]:
    name = item["original_relative"]
    sid = item["id"]
    if sid in {"src_002", "src_021", "src_022", "src_024"} or "作业安排" in name:
        return "homework", "作业安排", item["original_name"].replace(".ppt", "")
    if sid == "src_023":
        return "answer", "第三章", "第三章参考答案"
    if sid in {"src_001", "src_016"}:
        return "lecture", "第一章", "第1章 绪论"
    if sid == "src_017":
        return "lecture", "第二章", "第2章 数学模型"
    if sid == "src_018":
        return "lecture", "第三章", "第3章 时域分析"
    if sid in {"src_003", "src_004", "src_005", "src_006", "src_007", "src_008", "src_009", "src_010", "src_011", "src_012"}:
        return "lecture", "第五章", item["original_name"].replace(".ppt", "")
    if sid in {"src_013", "src_014"}:
        return "lecture", "第六章", item["original_name"].replace(".ppt", "")
    if sid == "src_019":
        return "lecture", "第八章", "第八章 非线性控制系统"
    if sid == "src_020":
        return "lecture", "第九章", "第九章 状态空间分析"
    if sid == "src_015":
        return "review", "总复习", "总复习课"
    return "lecture", "未分类", item["original_name"]


def load_sources() -> list[Source]:
    sources: list[Source] = []
    for item in read_source_map():
        pdf_path = source_pdf_path(item)
        role, chapter, title = classify_source(item)
        sources.append(
            Source(
                id=item["id"],
                title=title,
                original_relative=item["original_relative"],
                pdf_path=pdf_path,
                role=role,
                chapter=chapter,
            )
        )
    return sources


def ensure_dirs() -> None:
    for directory in [TEXT_DIR, SOURCE_PAGE_DIR, HOMEWORK_PAGE_DIR, ANSWER_PAGE_DIR, DATA_DIR]:
        directory.mkdir(parents=True, exist_ok=True)


def write_favicon() -> None:
    icon_path = ROOT / "favicon.ico"
    image = Image.new("RGBA", (32, 32), "#24362f")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, 30, 30), radius=7, outline="#b8872c", width=2)
    draw.line((7, 22, 13, 11, 18, 17, 24, 8), fill="#f7f3ea", width=3)
    draw.ellipse((20, 5, 26, 11), fill="#a9422b")
    image.save(icon_path, format="ICO")


def normalize_text(text: str) -> str:
    text = text.replace("\u2028", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text_and_manifest(sources: list[Source]) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for source in sources:
        if not source.pdf_path.exists():
            manifest.append(
                {
                    "id": source.id,
                    "title": source.title,
                    "original_relative": source.original_relative,
                    "role": source.role,
                    "chapter": source.chapter,
                    "page_count": 0,
                    "missing": True,
                }
            )
            continue
        doc = fitz.open(source.pdf_path)
        pages: list[dict[str, Any]] = []
        all_text: list[str] = []
        for index, page in enumerate(doc, start=1):
            text = normalize_text(page.get_text("text") or "")
            all_text.append(f"===== Page {index} =====\n{text}")
            pages.append(
                {
                    "page": index,
                    "text_preview": text[:220],
                    "has_text": bool(text),
                }
            )
        (TEXT_DIR / f"{source.id}.txt").write_text("\n\n".join(all_text), encoding="utf-8")
        manifest.append(
            {
                "id": source.id,
                "title": source.title,
                "original_relative": source.original_relative,
                "role": source.role,
                "chapter": source.chapter,
                "page_count": len(doc),
                "pdf_asset": str(source.pdf_path.relative_to(ROOT)).replace("\\", "/"),
                "text_file": str((TEXT_DIR / f"{source.id}.txt").relative_to(ROOT)).replace("\\", "/"),
                "pages": pages,
            }
        )
    return manifest


def render_pdf_page(pdf_path: Path, out_path: Path, page_number: int, zoom: float = 1.45) -> None:
    if out_path.exists() and out_path.stat().st_size > 0:
        return
    doc = fitz.open(pdf_path)
    page = doc[page_number - 1]
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pix.save(out_path)


def render_source_pages(sources: list[Source], manifest: list[dict[str, Any]], important_pages: dict[str, set[int]], double_pages: dict[str, set[int]]) -> list[dict[str, Any]]:
    page_records: list[dict[str, Any]] = []
    manifest_by_id = {entry["id"]: entry for entry in manifest}
    for source in sources:
        entry = manifest_by_id.get(source.id, {})
        page_count = int(entry.get("page_count", 0))
        if page_count == 0 or not source.pdf_path.exists():
            continue
        if source.role == "homework":
            out_dir = HOMEWORK_PAGE_DIR
        elif source.role == "answer":
            out_dir = ANSWER_PAGE_DIR
        else:
            out_dir = SOURCE_PAGE_DIR
        if source.role in {"homework", "answer"}:
            selected = range(1, page_count + 1)
        else:
            selected = select_lecture_pages(source, page_count, important_pages.get(source.id, set()))
        for page_number in selected:
            name = f"{source.id}_p{page_number:03d}.png"
            out_path = out_dir / name
            render_pdf_page(source.pdf_path, out_path, page_number)
            rel = str(out_path.relative_to(ROOT)).replace("\\", "/")
            page_records.append(
                {
                    "source_id": source.id,
                    "source_title": source.title,
                    "chapter": source.chapter,
                    "role": source.role,
                    "page": page_number,
                    "image": rel,
                    "important": page_number in important_pages.get(source.id, set()),
                    "double_important": page_number in double_pages.get(source.id, set()),
                }
            )
    return page_records


def select_lecture_pages(source: Source, page_count: int, forced: set[int]) -> list[int]:
    if source.role == "review":
        base = set(range(1, min(page_count, 15) + 1))
    elif source.id in {"src_001", "src_016"}:
        base = {1, 4, 5, 6, 7, 8, 9, 13, 18, 24, 30, 35, 41, 47}
    elif source.id == "src_017":
        base = {1, 4, 5, 8, 9, 14, 18, 22, 27, 32, 40, 45, 53, 62, 70, 76, 83, 89}
    elif source.id == "src_018":
        base = {1, 2, 4, 8, 11, 15, 19, 23, 28, 35, 43, 50, 58, 64, 73, 82, 91, 100, 105}
    elif source.id == "src_020":
        base = {1, 2, 6, 10, 16, 22, 28, 35, 43, 50, 58, 66, 75, 84, 92, 101, 112, 124, 138, 152, 164}
    else:
        base = set(range(1, min(page_count, 8) + 1))
        base.update(range(max(1, page_count - 2), page_count + 1))
    base.update(forced)
    return sorted(page for page in base if 1 <= page <= page_count)


def read_text(source_id: str) -> str:
    path = TEXT_DIR / f"{source_id}.txt"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def pages_matching(source_id: str, patterns: list[str]) -> set[int]:
    text = read_text(source_id)
    matches: set[int] = set()
    for block in re.split(r"===== Page (\d+) =====\n", text):
        pass
    parts = re.split(r"===== Page (\d+) =====\n", text)
    for idx in range(1, len(parts), 2):
        page = int(parts[idx])
        body = parts[idx + 1]
        if any(pattern in body for pattern in patterns):
            matches.add(page)
    return matches


def build_priority_pages() -> tuple[dict[str, set[int]], dict[str, set[int]]]:
    important: dict[str, set[int]] = {
        "src_002": {1, 2, 3, 4, 5},
        "src_021": {1, 2, 3, 4, 5},
        "src_022": {2, 3, 4, 5, 6},
        "src_024": {2, 3, 4, 5, 6},
        "src_023": {1, 2, 3},
        "src_015": {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15},
    }
    keyword_map = {
        "src_017": ["传递函数", "结构图", "方框图", "梅逊", "Laplace", "反变换", "信号流图"],
        "src_018": ["超调", "峰值时间", "调节时间", "稳态误差", "劳斯", "Routh", "二阶系统", "静态误差"],
        "src_003": ["频率特性", "幅频", "相频", "频率响应"],
        "src_004": ["典型环节", "幅相特性", "比例环节", "惯性环节", "积分环节", "微分环节"],
        "src_005": ["开环系统", "幅相特性", "Nyquist"],
        "src_006": ["Bode", "对数频率", "典型环节"],
        "src_007": ["Bode", "开环系统", "转折频率"],
        "src_008": ["奈奎斯特", "稳定判据", "Nyquist", "-1"],
        "src_009": ["对数频域", "稳定判据", "穿越频率"],
        "src_010": ["稳定裕度", "相角裕度", "幅值裕度"],
        "src_011": ["开环对数幅频", "系统性能", "低频段", "中频段", "高频段"],
        "src_012": ["闭环系统", "频域性能指标", "谐振峰值", "带宽"],
        "src_013": ["超前校正", "最大超前角", "校正"],
        "src_014": ["滞后校正", "校正"],
        "src_019": ["非线性", "描述函数", "相平面", "极限环"],
        "src_020": ["状态空间", "可控性", "可观测性", "状态反馈", "李雅普诺夫"],
    }
    for sid, patterns in keyword_map.items():
        important.setdefault(sid, set()).update(pages_matching(sid, patterns))
    double_important = {
        "src_015": {2, 3, 4, 5, 6, 7, 8, 9},
        "src_022": {2, 3, 4, 5, 6},
        "src_024": {2, 3, 4, 5, 6},
        "src_002": {1, 2, 3, 4, 5},
        "src_021": {1, 2, 3, 4, 5},
        "src_023": {1, 2, 3},
    }
    return important, double_important


def page_images(page_records: list[dict[str, Any]], source_id: str, pages: list[int] | None = None) -> list[str]:
    selected = []
    for record in page_records:
        if record["source_id"] != source_id:
            continue
        if pages is not None and record["page"] not in pages:
            continue
        selected.append(record["image"])
    return selected


def source_page_refs(page_records: list[dict[str, Any]], source_id: str, pages: list[int] | None = None) -> list[dict[str, Any]]:
    return [
        record
        for record in page_records
        if record["source_id"] == source_id and (pages is None or record["page"] in pages)
    ]


def math_block(lines: list[str]) -> str:
    body = "\n".join(f"<div>{html.escape(line)}</div>" for line in lines)
    return f'<div class="math-block">{body}</div>'


def build_knowledge_map(page_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": "k1_intro",
            "chapter": "第一章 绪论",
            "title": "自动控制系统的基本组成与反馈思想",
            "beginner": "先把系统看成“比较目标和输出，再自动修正偏差”的闭环。能分清输入、输出、扰动、反馈、控制器和被控对象，是后面列传递函数与画框图的前置条件。",
            "prerequisites": ["函数与信号的输入输出关系", "反馈的正负号", "稳态与动态的直观含义"],
            "must_know": [
                "闭环控制的核心是用反馈量与给定量比较得到偏差，再由控制器产生控制作用。",
                "评价控制系统通常看稳定性、快速性、准确性。",
                "开环结构简单但抗扰能力弱；闭环能修正偏差，但必须额外关注稳定性。",
            ],
            "formulas": [],
            "common_mistakes": ["只背定义不看信号流向，导致后面方框图等效变换时符号出错。"],
            "source_pages": source_page_refs(page_records, "src_016", [1, 4, 5, 6, 7, 8, 9]),
            "related_homework": [],
        },
        {
            "id": "k2_laplace",
            "chapter": "第二章 数学模型",
            "title": "Laplace 变换与反变换",
            "beginner": "第二章作业先考基本变换。要先熟悉常见函数的 Laplace 变换，再用线性性质、位移性质和部分分式展开做反变换。",
            "prerequisites": ["指数、三角函数基本形式", "复数与极点", "部分分式展开"],
            "must_know": [
                "微分方程可以通过 Laplace 变换转为代数方程。",
                "反变换常用部分分式展开；遇到二阶因子时先配方，再对应衰减正弦/余弦。",
                "初始条件会进入输出响应计算，不能默认全为零。",
            ],
            "formulas": [
                math_block(["L{e^{-a t}} = 1 / (s + a)", "L{e^{-a t} cos wt} = (s + a) / ((s + a)^2 + w^2)", "L{e^{-a t} sin wt} = w / ((s + a)^2 + w^2)"]),
            ],
            "common_mistakes": ["把 s 平移写反，例如 e^{-a t} 对应 s+a，不是 s-a。"],
            "source_pages": source_page_refs(page_records, "src_017", [1, 4, 5, 8, 9, 14, 18]),
            "related_homework": ["HW2-2", "HW2-6", "HW2-7"],
        },
        {
            "id": "k2_transfer",
            "chapter": "第二章 数学模型",
            "title": "传递函数、结构图与信号流图",
            "beginner": "传递函数描述零初始条件下输出与输入的比值。框图化简和梅逊公式是把复杂连接关系转成闭环传递函数的工具。",
            "prerequisites": ["Laplace 变换", "代数方程消元", "负反馈公式"],
            "must_know": [
                "典型负反馈闭环传递函数：前向通道除以一加开环环路传递函数。",
                "系统型别由开环传递函数中原点极点个数决定。",
                "信号流图用前向通路、回路和不接触回路计算总传递函数。",
            ],
            "formulas": [
                math_block(["Phi(s) = G(s) / (1 + G(s)H(s))", "Mason: T = sum(P_k Delta_k) / Delta"]),
            ],
            "common_mistakes": ["把闭环极点当成开环极点；判断稳定性应看闭环特征方程。"],
            "source_pages": source_page_refs(page_records, "src_017", [22, 27, 32, 40, 45, 53, 62, 70, 76, 83, 89]),
            "related_homework": ["HW2-8", "HW2-11", "HW2-12", "HW2-14"],
        },
        {
            "id": "k3_first_second_order",
            "chapter": "第三章 时域分析",
            "title": "一阶、二阶系统的时间响应指标",
            "beginner": "第三章作业的核心是从响应曲线或传递函数读出自然频率、阻尼比、超调量、峰值时间和调节时间。",
            "prerequisites": ["传递函数", "极点与响应形式", "指数衰减与正弦振荡"],
            "must_know": [
                "标准二阶系统由自然频率和阻尼比决定动态性能。",
                "欠阻尼时会出现超调和振荡；阻尼比越大，超调越小。",
                "调节时间常按 5% 或 2% 误差带近似，做题时要看教材或题目约定。",
            ],
            "formulas": [
                math_block(["G(s) = wn^2 / (s^2 + 2 zeta wn s + wn^2)", "wd = wn sqrt(1 - zeta^2)", "sigma% = exp(-zeta pi / sqrt(1 - zeta^2)) x 100%", "tp = pi / wd", "ts ≈ 3 / (zeta wn)  (5% criterion)"]),
            ],
            "common_mistakes": ["把阻尼振荡频率 wd 和自然频率 wn 混用。"],
            "source_pages": source_page_refs(page_records, "src_018", [1, 2, 8, 11, 15, 19, 23, 28, 35, 43]),
            "related_homework": ["HW3-1", "HW3-2", "HW3-3"],
        },
        {
            "id": "k3_stability_error",
            "chapter": "第三章 时域分析",
            "title": "稳定性、劳斯判据与稳态误差",
            "beginner": "稳定性看闭环极点是否都在左半平面；稳态误差看系统型别和静态误差系数。先会写闭环特征方程，再套劳斯表和终值定理。",
            "prerequisites": ["闭环特征方程", "极点位置", "终值定理"],
            "must_know": [
                "劳斯判据通过首列符号判断右半平面根个数。",
                "稳态误差通常用终值定理计算，也可用位置、速度、加速度误差系数快速判断。",
                "输入类型不同，稳态误差结论不同：阶跃、斜坡、抛物线不能混用。",
            ],
            "formulas": [
                math_block(["ess = lim_{s -> 0} s E(s)", "Kp = lim_{s -> 0} G(s)H(s)", "Kv = lim_{s -> 0} s G(s)H(s)", "Ka = lim_{s -> 0} s^2 G(s)H(s)"]),
            ],
            "common_mistakes": ["用开环稳定替代闭环稳定；静态误差系数没有按系统型别判断。"],
            "source_pages": source_page_refs(page_records, "src_018", [50, 58, 64, 73, 82, 91, 100, 105]),
            "related_homework": ["HW3-4", "HW3-5", "HW3-6", "HW3-7", "HW3-8", "HW3-9"],
        },
        {
            "id": "k5_frequency",
            "chapter": "第五章 频域分析",
            "title": "频率特性、幅相曲线与 Bode 图",
            "beginner": "频域分析把 s 换成 jw，研究不同频率正弦输入下系统输出幅值和相位如何变化。Bode 图本质是把幅频和相频用对数坐标画出来。",
            "prerequisites": ["复数模与幅角", "传递函数", "对数坐标和 dB"],
            "must_know": [
                "幅频特性是 |G(jw)|，相频特性是 angle G(jw)。",
                "Bode 幅值图由低频基准线和各典型环节转折频率叠加得到。",
                "积分环节给 -20 dB/dec 和 -90° 相位；一阶惯性环节过转折频率后斜率再降 -20 dB/dec。",
            ],
            "formulas": [
                math_block(["G(jw) = G(s)|_{s = jw}", "L(w) = 20 log10 |G(jw)|"]),
            ],
            "common_mistakes": ["画 Bode 图时没有先化成尾 1 标准型，导致转折频率和增益错位。"],
            "source_pages": source_page_refs(page_records, "src_003") + source_page_refs(page_records, "src_004") + source_page_refs(page_records, "src_006"),
            "related_homework": [],
        },
        {
            "id": "k5_nyquist_margin",
            "chapter": "第五章 频域分析",
            "title": "Nyquist 判据、对数稳定判据与稳定裕度",
            "beginner": "频域稳定性不是只看曲线形状，而是看开环频率特性怎样绕过临界点 -1。稳定裕度则衡量离临界失稳还有多远。",
            "prerequisites": ["复平面", "开环传递函数", "闭环稳定的特征方程"],
            "must_know": [
                "Nyquist 判据通过开环频率特性包围 -1 点的情况判断闭环稳定。",
                "相角裕度和幅值裕度分别从穿越频率读出。",
                "裕度越大通常稳定余量越充分，但过大可能牺牲快速性。",
            ],
            "formulas": [
                math_block(["gamma = 180° + phase G(j wc)", "Kg = 1 / |G(j wg)|"]),
            ],
            "common_mistakes": ["把幅值穿越频率和相位穿越频率互换。"],
            "source_pages": source_page_refs(page_records, "src_008") + source_page_refs(page_records, "src_009") + source_page_refs(page_records, "src_010"),
            "related_homework": [],
        },
        {
            "id": "k5_performance",
            "chapter": "第五章 频域分析",
            "title": "由开环/闭环频域指标分析系统性能",
            "beginner": "低频段影响稳态精度，中频段影响动态性能，高频段影响抗噪。复习时要能把曲线形态和性能语言互相转换。",
            "prerequisites": ["Bode 图", "稳定裕度", "时域性能指标"],
            "must_know": [
                "低频增益高通常稳态误差小。",
                "中频段斜率和穿越频率影响快速性与稳定裕度。",
                "闭环频域指标包括谐振峰值、谐振频率和带宽。",
            ],
            "formulas": [
                math_block(["Mr = max |Phi(jw)|", "wb: |Phi(jw)| drops to 0.707 of low-frequency value"]),
            ],
            "common_mistakes": ["只提高增益追求精度，却忽略稳定裕度下降。"],
            "source_pages": source_page_refs(page_records, "src_011") + source_page_refs(page_records, "src_012"),
            "related_homework": [],
        },
        {
            "id": "k6_correction",
            "chapter": "第六章 校正",
            "title": "超前校正与滞后校正",
            "beginner": "校正是在原系统性能不满足要求时增加环节。超前校正常用于增加相角裕度和改善动态性能；滞后校正常用于改善稳态精度并尽量少破坏中频段。",
            "prerequisites": ["Bode 图", "稳定裕度", "稳态误差系数"],
            "must_know": [
                "超前校正提供正相角，通常把最大超前角放在新的穿越频率附近。",
                "滞后校正提高低频增益，转折频率要放在较低频段。",
                "设计题必须按指标反推参数，而不是随意添加环节。",
            ],
            "formulas": [
                math_block(["Gc_lead(s) = (T s + 1) / (alpha T s + 1), 0 < alpha < 1", "Gc_lag(s) = (beta T s + 1) / (T s + 1), beta > 1"]),
            ],
            "common_mistakes": ["超前/滞后参数条件记反。"],
            "source_pages": source_page_refs(page_records, "src_013") + source_page_refs(page_records, "src_014"),
            "related_homework": [],
        },
        {
            "id": "k8_nonlinear",
            "chapter": "第八章 非线性",
            "title": "非线性系统与描述函数法",
            "beginner": "非线性系统不能简单套叠加原理。描述函数法用近似频域方法分析某些非线性环节引起的自振或极限环。",
            "prerequisites": ["频率响应", "相平面基本概念", "线性化近似"],
            "must_know": [
                "常见非线性包括饱和、死区、继电、滞环等。",
                "描述函数法是近似方法，适合特定非线性和近似正弦运动。",
                "非线性系统可能有多个平衡点和极限环。",
            ],
            "formulas": [],
            "common_mistakes": ["把非线性系统当作普通线性系统直接叠加。"],
            "source_pages": source_page_refs(page_records, "src_019"),
            "related_homework": [],
        },
        {
            "id": "k9_state_space",
            "chapter": "第九章 状态空间",
            "title": "状态空间描述、可控性与可观测性",
            "beginner": "状态空间用一组一阶微分方程描述系统内部状态，适合多输入多输出系统。先会选状态变量，再写 A、B、C、D 矩阵。",
            "prerequisites": ["矩阵乘法", "线性代数秩", "微分方程"],
            "must_know": [
                "标准形式：x_dot = A x + B u，y = C x + D u。",
                "可控性看可控矩阵秩；可观测性看可观测矩阵秩。",
                "状态反馈和状态观测器建立在可控、可观测条件上。",
            ],
            "formulas": [
                math_block(["x_dot = A x + B u", "y = C x + D u", "Qc = [B, AB, ..., A^{n-1}B]", "Qo = [C; CA; ...; CA^{n-1}]"]),
            ],
            "common_mistakes": ["只写传递函数，不会转换成状态变量形式；矩阵维度不匹配。"],
            "source_pages": source_page_refs(page_records, "src_020"),
            "related_homework": [],
        },
    ]


def build_question_bank(page_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hw2_imgs = page_images(page_records, "src_024", [2, 3, 4, 5, 6]) or page_images(page_records, "src_022", [2, 3, 4, 5, 6])
    hw3_imgs = page_images(page_records, "src_021", [1, 2, 3, 4, 5]) or page_images(page_records, "src_002", [1, 2, 3, 4, 5])
    answer_imgs = page_images(page_records, "src_023", [1, 2, 3])
    return [
        {
            "id": "HW1",
            "chapter": "第一章 绪论",
            "title": "第一章绪论",
            "prompt": "作业安排页标注：第一章绪论，无。",
            "prompt_images": page_images(page_records, "src_024", [1]) or page_images(page_records, "src_022", [1]),
            "knowledge_ids": ["k1_intro"],
            "answer_status": "无作业",
            "answer_images": [],
            "answer_text": "第一章没有布置书面作业；复习时掌握闭环控制基本概念、系统组成和性能指标即可。",
        },
        {
            "id": "HW2-2",
            "chapter": "第二章 数学模型",
            "title": "《孔》P39 2-2：求 Laplace 变换",
            "prompt": "作业安排要求完成 2-2 的 (1)、(3)、(5)、(7)，其中页面给出部分函数示例。",
            "prompt_images": hw2_imgs[:2],
            "knowledge_ids": ["k2_laplace"],
            "answer_status": "待官方答案核对",
            "answer_images": [],
            "answer_text": "按常见函数表、线性性质和 s 域平移性质逐题计算。建议先写出对应公式，再代入参数；不要把 e^{-a t} 的平移方向写反。",
        },
        {
            "id": "HW2-6",
            "chapter": "第二章 数学模型",
            "title": "《孔》P39 2-6：求 Laplace 反变换",
            "prompt": "作业安排要求完成 2-6 的 (1)、(3)、(5)、(7)。",
            "prompt_images": hw2_imgs[:3],
            "knowledge_ids": ["k2_laplace"],
            "answer_status": "待官方答案核对",
            "answer_images": [],
            "answer_text": "先做部分分式展开；若出现不可约二阶项，配成 (s+a)^2 + w^2，再对应衰减正弦或余弦项。",
        },
        {
            "id": "HW2-7",
            "chapter": "第二章 数学模型",
            "title": "《胡》P78 2-7：由传递函数和初始条件求阶跃响应",
            "prompt": "题面给出传递函数、初始条件和单位阶跃输入，要求输出响应 c(t)。",
            "prompt_images": hw2_imgs[:3],
            "knowledge_ids": ["k2_laplace", "k2_transfer"],
            "answer_status": "待官方答案核对",
            "answer_images": [],
            "answer_text": "解题路线：写出 C(s)=G(s)R(s)，把初始条件带入由微分方程得到的 s 域表达式，做部分分式展开后反变换得到 c(t)。",
        },
        {
            "id": "HW2-8",
            "chapter": "第二章 数学模型",
            "title": "《胡》P78 2-8：系统数学模型与响应",
            "prompt": "作业安排页列为第二章作业内容，具体题面见截图。",
            "prompt_images": hw2_imgs[2:4],
            "knowledge_ids": ["k2_transfer"],
            "answer_status": "待官方答案核对",
            "answer_images": [],
            "answer_text": "先从物理或框图关系建立输入输出方程，再通过 Laplace 变换得到传递函数或响应。",
        },
        {
            "id": "HW2-11",
            "chapter": "第二章 数学模型",
            "title": "《胡》P79 2-11：结构图/传递函数",
            "prompt": "作业安排要求完成 2-11。重点通常是从结构图或连接关系化简得到传递函数。",
            "prompt_images": hw2_imgs[3:],
            "knowledge_ids": ["k2_transfer"],
            "answer_status": "待官方答案核对",
            "answer_images": [],
            "answer_text": "从最内层反馈开始化简，串联相乘、并联相加、反馈用 G/(1±GH)。每一步都保留符号，最后再合并。",
        },
        {
            "id": "HW2-12",
            "chapter": "第二章 数学模型",
            "title": "《孔》P46 2-12：结构图化简",
            "prompt": "作业安排要求完成 2-12。题目与结构图等效变换相关。",
            "prompt_images": hw2_imgs[3:],
            "knowledge_ids": ["k2_transfer"],
            "answer_status": "待官方答案核对",
            "answer_images": [],
            "answer_text": "建议在草稿上标出每个比较点与引出点移动后的等效增益，避免跨越方框移动时漏乘或漏除传递函数。",
        },
        {
            "id": "HW2-14",
            "chapter": "第二章 数学模型",
            "title": "《孔》P48 2-14：信号流图与梅逊公式",
            "prompt": "作业安排要求完成 2-14。重点是用信号流图或梅逊公式求总传递函数。",
            "prompt_images": hw2_imgs[4:],
            "knowledge_ids": ["k2_transfer"],
            "answer_status": "待官方答案核对",
            "answer_images": [],
            "answer_text": "列出所有前向通路、单独回路和互不接触回路，计算 Delta 和各 Delta_k，再代入梅逊公式。",
        },
        {
            "id": "HW3-1",
            "chapter": "第三章 时域分析",
            "title": "3.1 由二阶系统单位阶跃响应求超调量、峰值时间、调节时间",
            "prompt": "已知二阶系统单位阶跃响应，求超调量、峰值时间和调节时间。",
            "prompt_images": hw3_imgs[:1],
            "knowledge_ids": ["k3_first_second_order"],
            "answer_status": "第三章参考答案",
            "answer_images": answer_imgs[:1],
            "answer_text": "从响应式读出衰减指数和阻尼振荡频率，先求 zeta wn 和 wd，再由 wd = wn sqrt(1-zeta^2) 得到 wn、zeta，最后代入超调量、峰值时间和调节时间公式。",
        },
        {
            "id": "HW3-2",
            "chapter": "第三章 时域分析",
            "title": "3.2 求系统自然频率和阻尼比",
            "prompt": "题目要求由给定系统求自然频率 wn 和阻尼比 zeta。",
            "prompt_images": hw3_imgs[:1],
            "knowledge_ids": ["k3_first_second_order"],
            "answer_status": "第三章参考答案",
            "answer_images": answer_imgs[:1],
            "answer_text": "把闭环传递函数分母化为 s^2 + 2 zeta wn s + wn^2 的标准形式，对比系数即可。",
        },
        {
            "id": "HW3-3",
            "chapter": "第三章 时域分析",
            "title": "3.3 图示控制系统综合指标计算",
            "prompt": "已知 K=125，要求系统阶次、类型、开环/闭环传递函数、零极点、自然频率、阻尼比、阻尼振荡频率、调节时间、最大超调量、静态误差系数和给定输入下的稳态误差。",
            "prompt_images": hw3_imgs[1:2],
            "knowledge_ids": ["k2_transfer", "k3_first_second_order", "k3_stability_error"],
            "answer_status": "第三章参考答案",
            "answer_images": answer_imgs[:2],
            "answer_text": "先由框图写开环 G(s)H(s)，再用 1+G(s)H(s)=0 得闭环特征方程。阶次看闭环分母最高次数，型别看开环原点极点个数；动态指标由二阶标准型读出，稳态误差由误差系数求。",
        },
        {
            "id": "HW3-4",
            "chapter": "第三章 时域分析",
            "title": "3.4 由系统结构求稳定性或性能指标",
            "prompt": "第三章作业后续题，题面见作业截图。",
            "prompt_images": hw3_imgs[2:3],
            "knowledge_ids": ["k3_stability_error"],
            "answer_status": "第三章参考答案",
            "answer_images": answer_imgs[1:],
            "answer_text": "优先写闭环特征方程，再根据题目要求判断稳定性、求动态指标或稳态误差。",
        },
        {
            "id": "HW3-5",
            "chapter": "第三章 时域分析",
            "title": "3.5 第三章时域分析题",
            "prompt": "题面见第三章作业截图。",
            "prompt_images": hw3_imgs[2:3],
            "knowledge_ids": ["k3_first_second_order", "k3_stability_error"],
            "answer_status": "第三章参考答案",
            "answer_images": answer_imgs[1:],
            "answer_text": "题目属于第三章核心训练，按“建闭环模型 -> 化标准型/列劳斯表 -> 求指标或误差”的顺序处理。",
        },
        {
            "id": "HW3-6",
            "chapter": "第三章 时域分析",
            "title": "3.6 稳定性与参数范围",
            "prompt": "题面见第三章作业截图。",
            "prompt_images": hw3_imgs[3:4],
            "knowledge_ids": ["k3_stability_error"],
            "answer_status": "第三章参考答案",
            "answer_images": answer_imgs[1:],
            "answer_text": "如果题目含未知参数，建立特征方程后列劳斯表，让首列元素同号得到参数范围。",
        },
        {
            "id": "HW3-7",
            "chapter": "第三章 时域分析",
            "title": "3.7 稳态误差计算",
            "prompt": "题面见第三章作业截图。",
            "prompt_images": hw3_imgs[3:4],
            "knowledge_ids": ["k3_stability_error"],
            "answer_status": "第三章参考答案",
            "answer_images": answer_imgs[1:],
            "answer_text": "先判断输入类型和系统型别，再选 Kp、Kv 或 Ka；也可以从 E(s) 使用终值定理直接计算。",
        },
        {
            "id": "HW3-8",
            "chapter": "第三章 时域分析",
            "title": "3.8 第三章综合题",
            "prompt": "题面见第三章作业截图。",
            "prompt_images": hw3_imgs[4:5],
            "knowledge_ids": ["k3_first_second_order", "k3_stability_error"],
            "answer_status": "第三章参考答案",
            "answer_images": answer_imgs[2:],
            "answer_text": "综合题通常同时考模型、稳定性和误差。建议每问单独列公式，避免把中间结果挤在一行里。",
        },
        {
            "id": "HW3-9",
            "chapter": "第三章 时域分析",
            "title": "3.9 第三章综合题",
            "prompt": "题面见第三章作业截图。",
            "prompt_images": hw3_imgs[4:5],
            "knowledge_ids": ["k3_stability_error"],
            "answer_status": "第三章参考答案",
            "answer_images": answer_imgs[2:],
            "answer_text": "先确认闭环是否稳定；只有稳定时终值定理计算的稳态误差才有意义。",
        },
    ]


def image_button(src: str, alt: str, classes: str = "") -> str:
    return (
        f'<button class="page-thumb {classes}" data-src="{html.escape(src)}" data-alt="{html.escape(alt)}">'
        f'<img src="{html.escape(src)}" alt="{html.escape(alt)}" loading="lazy">'
        "</button>"
    )


def render_gallery(title: str, records: list[dict[str, Any]]) -> str:
    if not records:
        return ""
    thumbs = []
    for record in records:
        cls = "double-important" if record.get("double_important") else "important" if record.get("important") else ""
        alt = f"{record['source_title']} 第 {record['page']} 页"
        thumbs.append(
            f'<figure class="source-figure">{image_button(record["image"], alt, cls)}'
            f'<figcaption>{html.escape(record["source_title"])} · P{record["page"]}</figcaption></figure>'
        )
    return f"<details class='gallery-block' open><summary>{html.escape(title)} <span>{len(records)} 页</span></summary><div class='gallery-grid'>{''.join(thumbs)}</div></details>"


def render_knowledge_card(item: dict[str, Any]) -> str:
    prereq = "".join(f"<li>{html.escape(x)}</li>" for x in item["prerequisites"])
    must = "".join(f"<li>{html.escape(x)}</li>" for x in item["must_know"])
    mistakes = "".join(f"<li>{html.escape(x)}</li>" for x in item["common_mistakes"])
    formulas = "".join(item.get("formulas", []))
    related = "".join(f'<a href="#q-{html.escape(q)}">{html.escape(q)}</a>' for q in item.get("related_homework", []))
    gallery = render_gallery("对应讲义截图", item.get("source_pages", []))
    return f"""
    <article class="knowledge-card searchable" id="{html.escape(item['id'])}" data-search="{html.escape(' '.join([item['chapter'], item['title'], item['beginner'], ' '.join(item.get('related_homework', []))]))}">
      <div class="card-head">
        <span class="chapter-pill">{html.escape(item['chapter'])}</span>
        <h3>{html.escape(item['title'])}</h3>
      </div>
      <p class="beginner">{html.escape(item['beginner'])}</p>
      <div class="two-col">
        <section><h4>前置知识</h4><ul>{prereq}</ul></section>
        <section><h4>必须掌握</h4><ul>{must}</ul></section>
      </div>
      {f'<section><h4>公式/算式</h4>{formulas}</section>' if formulas else ''}
      <section><h4>易错点</h4><ul>{mistakes}</ul></section>
      {f'<div class="related-links"><span>关联作业</span>{related}</div>' if related else ''}
      {gallery}
    </article>
    """


def render_question_card(item: dict[str, Any], knowledge_by_id: dict[str, dict[str, Any]]) -> str:
    prompt_imgs = "".join(image_button(src, f"{item['id']} 题目截图", "important") for src in item.get("prompt_images", []))
    answer_imgs = "".join(image_button(src, f"{item['id']} 答案截图", "double-important") for src in item.get("answer_images", []))
    links = "".join(
        f'<a href="#{html.escape(kid)}">{html.escape(knowledge_by_id.get(kid, {}).get("title", kid))}</a>'
        for kid in item.get("knowledge_ids", [])
    )
    return f"""
    <article class="question-card searchable" id="q-{html.escape(item['id'])}" data-search="{html.escape(' '.join([item['id'], item['chapter'], item['title'], item['prompt'], item['answer_text']]))}">
      <div class="card-head">
        <span class="question-id">{html.escape(item['id'])}</span>
        <h3>{html.escape(item['title'])}</h3>
      </div>
      <p class="prompt">{html.escape(item['prompt'])}</p>
      {f'<div class="image-strip">{prompt_imgs}</div>' if prompt_imgs else ''}
      <div class="answer-panel">
        <div class="answer-status">{html.escape(item['answer_status'])}</div>
        {f'<div class="image-strip answer-images">{answer_imgs}</div>' if answer_imgs else ''}
        <p>{html.escape(item['answer_text'])}</p>
      </div>
      <div class="related-links"><span>对应知识</span>{links}</div>
    </article>
    """


def render_html(knowledge: list[dict[str, Any]], questions: list[dict[str, Any]], page_records: list[dict[str, Any]], manifest: list[dict[str, Any]]) -> str:
    knowledge_by_id = {item["id"]: item for item in knowledge}
    chapters = []
    seen = set()
    for item in knowledge:
        if item["chapter"] not in seen:
            seen.add(item["chapter"])
            chapters.append(item["chapter"])
    chapter_nav = "".join(f'<a href="#chapter-{html.escape(ch)}">{html.escape(ch)}</a>' for ch in chapters)
    q_nav = "".join(f'<a href="#q-{html.escape(q["id"])}">{html.escape(q["id"])}</a>' for q in questions)
    sections = []
    for chapter in chapters:
        ks = [item for item in knowledge if item["chapter"] == chapter]
        qs = [item for item in questions if item["chapter"] == chapter]
        sections.append(
            f"""
            <section class="chapter-section" id="chapter-{html.escape(chapter)}">
              <header class="section-head">
                <span>Chapter</span>
                <h2>{html.escape(chapter)}</h2>
              </header>
              <div class="knowledge-list">{''.join(render_knowledge_card(item) for item in ks)}</div>
              {f'<div class="question-list"><h3 class="subhead">作业题号索引</h3>{"".join(render_question_card(item, knowledge_by_id) for item in qs)}</div>' if qs else ''}
            </section>
            """
        )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in page_records:
        grouped.setdefault(record["source_title"], []).append(record)
    gallery_html = "".join(render_gallery(title, records) for title, records in grouped.items())
    manifest_rows = "".join(
        f"<tr><td>{html.escape(entry['id'])}</td><td>{html.escape(entry['title'])}</td><td>{html.escape(entry['role'])}</td><td>{entry.get('page_count', 0)}</td></tr>"
        for entry in manifest
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>自动控制原理复习网站</title>
  <link rel="icon" href="favicon.ico" type="image/x-icon">
  <style>
    :root {{
      --ink: #17201a;
      --muted: #5b655e;
      --paper: #f7f3ea;
      --panel: #fffdf8;
      --line: #d7d0c3;
      --accent: #0f6b5c;
      --accent-2: #a9422b;
      --gold: #b8872c;
      --shadow: 0 14px 34px rgba(37, 30, 18, 0.12);
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: var(--paper);
      font-family: "Microsoft YaHei", "Noto Sans CJK SC", "PingFang SC", sans-serif;
      line-height: 1.68;
    }}
    body.locked main, body.locked aside {{ display: none; }}
    .gate {{
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
      background: #ebe2d2;
    }}
    .gate-box {{
      width: min(420px, 100%);
      background: var(--panel);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      padding: 28px;
      border-radius: 8px;
    }}
    .gate-box h1 {{ margin: 0 0 10px; font-size: 28px; letter-spacing: 0; }}
    .gate-box input {{
      width: 100%;
      height: 42px;
      border: 1px solid var(--line);
      padding: 0 12px;
      font-size: 16px;
      border-radius: 6px;
      background: #fff;
    }}
    .gate-box button, .tool-btn {{
      border: 0;
      background: var(--accent);
      color: white;
      min-height: 40px;
      padding: 0 14px;
      border-radius: 6px;
      cursor: pointer;
      font-weight: 700;
    }}
    .gate-box button {{ margin-top: 12px; width: 100%; }}
    .layout {{
      display: grid;
      grid-template-columns: 292px 1fr;
      min-height: 100vh;
    }}
    aside {{
      position: sticky;
      top: 0;
      height: 100vh;
      overflow: auto;
      background: #24362f;
      color: #f7f3ea;
      padding: 18px;
      border-right: 1px solid #172820;
    }}
    aside h1 {{ font-size: 20px; line-height: 1.25; margin: 0 0 14px; letter-spacing: 0; }}
    aside .meta {{ color: #cbd7d0; font-size: 13px; margin-bottom: 14px; }}
    .search-box {{ display: grid; gap: 8px; margin-bottom: 16px; }}
    .search-box input {{
      width: 100%;
      height: 38px;
      border-radius: 6px;
      border: 1px solid rgba(255,255,255,.22);
      background: rgba(255,255,255,.08);
      color: #fff;
      padding: 0 10px;
    }}
    .search-box input::placeholder {{ color: #cbd7d0; }}
    .nav-block {{ margin: 16px 0; }}
    .nav-block h2 {{ font-size: 13px; color: #bfd1ca; margin: 0 0 8px; }}
    .nav-links {{ display: grid; gap: 5px; }}
    .nav-links a {{
      color: #fff;
      text-decoration: none;
      border: 1px solid rgba(255,255,255,.13);
      border-radius: 6px;
      padding: 7px 9px;
      font-size: 14px;
      background: rgba(255,255,255,.05);
    }}
    main {{ padding: 26px clamp(18px, 4vw, 52px) 60px; }}
    .hero {{
      border-bottom: 2px solid var(--ink);
      padding-bottom: 18px;
      margin-bottom: 22px;
    }}
    .hero h1 {{ margin: 0; font-size: clamp(30px, 4vw, 52px); line-height: 1.08; letter-spacing: 0; }}
    .hero p {{ max-width: 920px; color: var(--muted); margin: 12px 0 0; }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin: 18px 0 26px;
    }}
    .stat {{
      background: var(--panel);
      border: 1px solid var(--line);
      padding: 12px;
      border-radius: 8px;
    }}
    .stat strong {{ display: block; font-size: 24px; }}
    .section-head {{
      display: flex;
      align-items: baseline;
      gap: 12px;
      margin: 28px 0 12px;
      border-top: 2px solid var(--ink);
      padding-top: 14px;
    }}
    .section-head span {{ color: var(--accent-2); font-weight: 800; text-transform: uppercase; font-size: 12px; }}
    .section-head h2 {{ margin: 0; font-size: 28px; letter-spacing: 0; }}
    .knowledge-card, .question-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: clamp(14px, 2vw, 22px);
      margin: 14px 0;
      box-shadow: 0 6px 20px rgba(37, 30, 18, 0.06);
      scroll-margin-top: 14px;
    }}
    .card-head {{
      display: flex;
      gap: 10px;
      align-items: flex-start;
      flex-wrap: wrap;
      border-bottom: 1px solid var(--line);
      padding-bottom: 10px;
      margin-bottom: 12px;
    }}
    .card-head h3 {{ margin: 0; font-size: 20px; line-height: 1.35; letter-spacing: 0; }}
    .chapter-pill, .question-id, .answer-status {{
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 2px 9px;
      border-radius: 999px;
      font-size: 13px;
      font-weight: 800;
      background: #e5f0ec;
      color: #0f6b5c;
      border: 1px solid #bad7cf;
      white-space: nowrap;
    }}
    .question-id {{ background: #f3e4de; color: var(--accent-2); border-color: #d6b2a7; }}
    .beginner, .prompt {{ font-size: 16px; color: #28332d; }}
    .two-col {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }}
    h4 {{ margin: 12px 0 6px; font-size: 15px; }}
    ul {{ margin: 6px 0 10px 20px; padding: 0; }}
    li {{ margin: 4px 0; }}
    .math-block {{
      margin: 10px 0;
      padding: 12px 14px;
      background: #fbf8f1;
      border-left: 4px solid var(--gold);
      font-family: "Cambria Math", "Times New Roman", serif;
      font-size: 18px;
      line-height: 1.8;
      overflow-x: auto;
      white-space: nowrap;
    }}
    .related-links {{
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
      margin: 12px 0;
    }}
    .related-links span {{ color: var(--muted); font-size: 13px; font-weight: 800; }}
    .related-links a {{
      color: var(--accent);
      border: 1px solid #bad7cf;
      background: #eef7f4;
      border-radius: 999px;
      padding: 3px 9px;
      text-decoration: none;
      font-size: 13px;
      font-weight: 700;
    }}
    .answer-panel {{
      margin-top: 10px;
      padding: 12px;
      border: 1px solid #e0c6bd;
      background: #fff7f2;
      border-radius: 8px;
    }}
    .answer-panel p {{ margin: 10px 0 0; }}
    .image-strip, .gallery-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
      gap: 10px;
      margin: 10px 0;
    }}
    .page-thumb {{
      display: block;
      width: 100%;
      padding: 0;
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 6px;
      cursor: zoom-in;
      overflow: hidden;
      aspect-ratio: 4 / 3;
    }}
    .page-thumb img {{
      width: 100%;
      height: 100%;
      object-fit: contain;
      display: block;
      background: white;
    }}
    .page-thumb.important {{ border: 4px solid #d21f1f; }}
    .page-thumb.double-important {{
      border: 4px solid #d21f1f;
      box-shadow: 0 0 0 5px #fff, 0 0 0 9px #d21f1f;
      margin: 9px;
      width: calc(100% - 18px);
    }}
    .gallery-block {{
      margin-top: 12px;
      border-top: 1px solid var(--line);
      padding-top: 8px;
    }}
    .gallery-block summary {{
      cursor: pointer;
      font-weight: 800;
      color: var(--accent);
    }}
    .gallery-block summary span {{ color: var(--muted); font-size: 13px; }}
    .source-figure {{ margin: 0; }}
    figcaption {{ color: var(--muted); font-size: 12px; margin-top: 4px; }}
    .subhead {{ margin-top: 18px; }}
    .source-table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    .source-table th, .source-table td {{
      border-bottom: 1px solid var(--line);
      padding: 8px;
      text-align: left;
      font-size: 13px;
    }}
    .modal {{
      position: fixed;
      inset: 0;
      background: rgba(8, 12, 10, .88);
      display: none;
      z-index: 99;
      align-items: center;
      justify-content: center;
      padding: 54px 70px;
    }}
    .modal.open {{ display: flex; }}
    .modal img {{
      max-width: 100%;
      max-height: 100%;
      background: #fff;
      object-fit: contain;
      box-shadow: 0 20px 60px rgba(0,0,0,.45);
    }}
    .modal button {{
      position: absolute;
      border: 1px solid rgba(255,255,255,.3);
      background: rgba(255,255,255,.12);
      color: #fff;
      cursor: pointer;
      border-radius: 999px;
      width: 46px;
      height: 46px;
      font-size: 26px;
    }}
    .modal .close {{ top: 14px; right: 18px; }}
    .modal .prev {{ left: 18px; top: 50%; transform: translateY(-50%); }}
    .modal .next {{ right: 18px; top: 50%; transform: translateY(-50%); }}
    .modal-caption {{
      position: absolute;
      left: 70px;
      right: 70px;
      bottom: 16px;
      color: #fff;
      text-align: center;
      font-size: 14px;
    }}
    .hidden-by-search {{ display: none !important; }}
    @media (max-width: 900px) {{
      .layout {{ grid-template-columns: 1fr; }}
      aside {{ position: relative; height: auto; }}
      .stats, .two-col {{ grid-template-columns: 1fr; }}
      .modal {{ padding: 52px 48px; }}
    }}
  </style>
</head>
<body class="locked">
  <div class="gate" id="gate">
    <form class="gate-box" id="gateForm">
      <h1>自动控制原理复习</h1>
      <p>输入访问密码后进入。</p>
      <input id="passwordInput" type="password" autocomplete="current-password" placeholder="访问密码">
      <button type="submit">进入复习网站</button>
      <p id="gateMsg" aria-live="polite"></p>
    </form>
  </div>
  <div class="layout">
    <aside>
      <h1>自动控制原理<br>章节复习索引</h1>
      <div class="meta">章节知识为主入口，作业题号用于快速定位。</div>
      <div class="search-box">
        <input id="searchInput" type="search" placeholder="搜索知识点 / 题号 / 关键词">
        <button class="tool-btn" id="clearSearch" type="button">清除搜索</button>
        <div id="matchCount" class="meta"></div>
      </div>
      <div class="nav-block"><h2>章节目录</h2><nav class="nav-links">{chapter_nav}</nav></div>
      <div class="nav-block"><h2>作业题号</h2><nav class="nav-links">{q_nav}</nav></div>
      <div class="nav-block"><h2>资料</h2><nav class="nav-links"><a href="#source-gallery">PDF/PPT 截图总览</a><a href="#source-manifest">源文件清单</a></nav></div>
    </aside>
    <main>
      <header class="hero">
        <h1>自动控制原理复习网站</h1>
        <p>根据本地讲义 PDF/PPT、作业安排和第三章参考答案整理。页面保留原讲义截图，重点页使用红框，作业和参考答案截图尽量紧贴题目；没有官方答案的题目明确标注“待官方答案核对”。</p>
      </header>
      <section class="stats">
        <div class="stat"><strong>{len(chapters)}</strong><span>章节入口</span></div>
        <div class="stat"><strong>{len(knowledge)}</strong><span>知识卡片</span></div>
        <div class="stat"><strong>{len(questions)}</strong><span>作业条目</span></div>
        <div class="stat"><strong>{len(page_records)}</strong><span>可放大截图</span></div>
      </section>
      {''.join(sections)}
      <section id="source-gallery" class="chapter-section">
        <header class="section-head"><span>Gallery</span><h2>PDF/PPT 截图总览</h2></header>
        {gallery_html}
      </section>
      <section id="source-manifest" class="chapter-section">
        <header class="section-head"><span>Sources</span><h2>源文件清单</h2></header>
        <table class="source-table"><thead><tr><th>ID</th><th>标题</th><th>类型</th><th>页数</th></tr></thead><tbody>{manifest_rows}</tbody></table>
      </section>
    </main>
  </div>
  <div class="modal" id="imageModal" aria-hidden="true">
    <button class="close" type="button" aria-label="关闭">×</button>
    <button class="prev" type="button" aria-label="上一张">‹</button>
    <img id="modalImg" alt="">
    <button class="next" type="button" aria-label="下一张">›</button>
    <div class="modal-caption" id="modalCaption"></div>
  </div>
  <script>
    const PASS = '123';
    const gate = document.getElementById('gate');
    const gateForm = document.getElementById('gateForm');
    const passwordInput = document.getElementById('passwordInput');
    const gateMsg = document.getElementById('gateMsg');
    function unlock() {{
      document.body.classList.remove('locked');
      gate.style.display = 'none';
      sessionStorage.setItem('autoControlReviewUnlocked', '1');
    }}
    if (sessionStorage.getItem('autoControlReviewUnlocked') === '1') unlock();
    gateForm.addEventListener('submit', (event) => {{
      event.preventDefault();
      if (passwordInput.value.trim() === PASS) unlock();
      else gateMsg.textContent = '密码不正确';
    }});

    const searchInput = document.getElementById('searchInput');
    const clearSearch = document.getElementById('clearSearch');
    const matchCount = document.getElementById('matchCount');
    const searchable = Array.from(document.querySelectorAll('.searchable'));
    function resolveHashTarget(hash) {{
      if (!hash || !hash.startsWith('#')) return null;
      return document.getElementById(decodeURIComponent(hash.slice(1)));
    }}
    function applySearch() {{
      const q = searchInput.value.trim().toLowerCase();
      let visible = 0;
      searchable.forEach((el) => {{
        const text = (el.dataset.search || el.textContent).toLowerCase();
        const hit = !q || text.includes(q);
        el.classList.toggle('hidden-by-search', !hit);
        if (hit) visible += 1;
      }});
      matchCount.textContent = q ? `匹配 ${{visible}} 条` : '';
    }}
    function handleHashNavigation(hash) {{
      const target = resolveHashTarget(hash || location.hash);
      if (!target) return;
      if (searchInput.value) {{
        searchInput.value = '';
        applySearch();
      }}
      target.scrollIntoView({{ block: 'start', behavior: 'smooth' }});
    }}
    searchInput.addEventListener('input', applySearch);
    clearSearch.addEventListener('click', () => {{ searchInput.value = ''; applySearch(); }});
    document.querySelectorAll('aside a[href^="#"]').forEach((link) => {{
      link.addEventListener('click', (event) => {{
        const hash = link.getAttribute('href');
        const target = resolveHashTarget(hash);
        if (!target) return;
        event.preventDefault();
        history.pushState(null, '', hash);
        handleHashNavigation(hash);
      }});
    }});
    window.addEventListener('hashchange', () => handleHashNavigation(location.hash));
    if (location.hash) {{
      handleHashNavigation(location.hash);
    }}

    const thumbs = Array.from(document.querySelectorAll('.page-thumb'));
    const modal = document.getElementById('imageModal');
    const modalImg = document.getElementById('modalImg');
    const modalCaption = document.getElementById('modalCaption');
    let currentIndex = 0;
    function showImage(index) {{
      if (!thumbs.length) return;
      currentIndex = (index + thumbs.length) % thumbs.length;
      const btn = thumbs[currentIndex];
      modalImg.src = btn.dataset.src;
      modalImg.alt = btn.dataset.alt || '';
      modalCaption.textContent = `${{currentIndex + 1}} / ${{thumbs.length}} · ${{modalImg.alt}}`;
      modal.classList.add('open');
      modal.setAttribute('aria-hidden', 'false');
    }}
    thumbs.forEach((btn, index) => btn.addEventListener('click', () => showImage(index)));
    function closeModal() {{
      modal.classList.remove('open');
      modal.setAttribute('aria-hidden', 'true');
      modalImg.src = '';
    }}
    modal.querySelector('.close').addEventListener('click', closeModal);
    modal.querySelector('.prev').addEventListener('click', () => showImage(currentIndex - 1));
    modal.querySelector('.next').addEventListener('click', () => showImage(currentIndex + 1));
    modal.addEventListener('click', (event) => {{ if (event.target === modal) closeModal(); }});
    window.addEventListener('keydown', (event) => {{
      if (!modal.classList.contains('open')) return;
      if (event.key === 'Escape') closeModal();
      if (event.key === 'ArrowLeft') showImage(currentIndex - 1);
      if (event.key === 'ArrowRight') showImage(currentIndex + 1);
    }});
  </script>
</body>
</html>
"""


def write_readme(manifest: list[dict[str, Any]], knowledge: list[dict[str, Any]], questions: list[dict[str, Any]]) -> None:
    readme = f"""# 自动控制原理复习网站

这是根据 `C:/Users/33563/Desktop/1大学作业/自动控制原理` 的课程资料生成的独立静态网站。

- 入口文件：`index.html`
- 访问方式：静态页面内置简易密码门，密码由维护者单独告知使用者。
- 知识点数量：{len(knowledge)}
- 作业条目数量：{len(questions)}
- 源文件数量：{len(manifest)}

生成目录独立存放，不会覆盖数电网站。

## 内容状态

- `自控第三章(1).pdf` 已按第三章参考答案处理，截图放入相关第三章题目。
- 第二章作业目前没有官方答案文件，因此答案区标注为“待官方答案核对”。
- 页面截图来自生成目录内的相对路径，不暴露本机课程原始路径。
"""
    (ROOT / "README.md").write_text(readme, encoding="utf-8")


def write_outline(knowledge: list[dict[str, Any]], questions: list[dict[str, Any]]) -> None:
    lines = ["# 自动控制原理复习网站目录", ""]
    current = None
    for item in knowledge:
        if item["chapter"] != current:
            current = item["chapter"]
            lines.append(f"## {current}")
        lines.append(f"- {item['title']}")
        related = [q for q in questions if q["chapter"] == current]
        if related:
            lines.append("  - 作业：" + "、".join(q["id"] for q in related))
    (ROOT / "outline.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def copy_raw_pdfs_for_traceability(sources: list[Source]) -> None:
    public_pdf_dir = ASSET_DIR / "source_pdfs"
    public_pdf_dir.mkdir(parents=True, exist_ok=True)
    for source in sources:
        if not source.pdf_path.exists():
            continue
        target = public_pdf_dir / f"{source.id}.pdf"
        if not target.exists():
            shutil.copy2(source.pdf_path, target)


def main() -> None:
    ensure_dirs()
    write_favicon()
    sources = load_sources()
    manifest = extract_text_and_manifest(sources)
    important, double_important = build_priority_pages()
    page_records = render_source_pages(sources, manifest, important, double_important)
    copy_raw_pdfs_for_traceability(sources)
    knowledge = build_knowledge_map(page_records)
    questions = build_question_bank(page_records)
    (DATA_DIR / "source_manifest.json").write_text(json.dumps({"sources": manifest, "pages": page_records}, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "knowledge_map.json").write_text(json.dumps(knowledge, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "question_bank.json").write_text(json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "index.html").write_text(render_html(knowledge, questions, page_records, manifest), encoding="utf-8")
    write_readme(manifest, knowledge, questions)
    write_outline(knowledge, questions)
    print(f"Generated {len(knowledge)} knowledge cards, {len(questions)} questions, {len(page_records)} page images.")


if __name__ == "__main__":
    main()
