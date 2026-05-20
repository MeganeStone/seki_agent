import re
import gc
import zipfile
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
from lxml import etree as ET
from langchain_core.tools import ToolException
from translate_text import translate_text
from dotenv import load_dotenv
load_dotenv()
import os
from pathlib import Path

# 获取当前脚本所在目录的父级目录（即 SIS_Agent 根目录）
SIS_AGENT_ROOT = Path(__file__).parent.parent

DEFAULT_INPUT_DIR = os.getenv("TRANSLATE_INPUT_DIR") or str(SIS_AGENT_ROOT / "translate" / "input")
DEFAULT_OUTPUT_DIR = os.getenv("TRANSLATE_OUTPUT_DIR") or str(SIS_AGENT_ROOT / "translate" / "output")
DEFAULT_TARGET_LANG = os.getenv("TRANSLATE_TARGET_LANG") or "日语"
DEFAULT_DELAY = float(os.getenv("TRANSLATE_DELAY") or 1.2)
MAX_WORKERS = int(os.getenv("MAX_WORKERS") or 6)

def _is_meaningful_text(text: str) -> bool:
    text = text.strip()
    if len(text) <= 1:
        return False
    if text.isdigit():
        return False
    if all(c in '，。！？；：""''《》【】（）,.!?;:\'"`~@#$%^&*()_+=-' for c in text):
        return False
    return True

def _translate_drawing_file(drawing_path, target_lang, delay, context):
    print(f"[DEBUG] 开始处理 drawing 文件: {drawing_path}")
    try:
        parser = ET.XMLParser(remove_blank_text=True)
        tree = ET.parse(drawing_path, parser)
        root = tree.getroot()
        a_uri = None
        for prefix, uri in root.nsmap.items():
            if prefix == 'a':
                a_uri = uri
                break
        if not a_uri:
            a_uri = 'http://schemas.openxmlformats.org/drawingml/2006/main'
        tag_p = f"{{{a_uri}}}p"
        tag_r = f"{{{a_uri}}}r"
        tag_t = f"{{{a_uri}}}t"
        modified_count = 0
        for p in root.iter(tag_p):
            runs = [r for r in p if r.tag == tag_r]
            if not runs:
                continue
            orig_text = ''
            for r in runs:
                t_elem = r.find(tag_t)
                if t_elem is not None and t_elem.text:
                    orig_text += t_elem.text
            orig_text = orig_text.strip()
            if not orig_text or not _is_meaningful_text(orig_text):
                continue
            translated = translate_text(orig_text, target_lang, delay, context)
            if not translated or translated == orig_text:
                continue
            first_run = runs[0]
            t_elem = first_run.find(tag_t)
            if t_elem is None:
                t_elem = ET.Element(tag_t)
                first_run.append(t_elem)
            t_elem.text = translated
            for r in runs[1:]:
                p.remove(r)
            modified_count += 1
        print(f"[DEBUG] 共修改了 {modified_count} 个段落")
        tree.write(drawing_path, encoding='utf-8', xml_declaration=True, pretty_print=False)
        return modified_count
    except Exception as e:
        print(f"[ERROR] 处理 drawing 文件出错 {drawing_path}: {e}")
        import traceback
        traceback.print_exc()
        return 0

def _collect_si_tasks(xml_path):
    tasks = []
    tree = ET.parse(xml_path)
    root = tree.getroot()
    for si in root.iter():
        if si.tag.endswith('}si'):
            # 收集所有直接子元素 <r>
            runs = [child for child in si if child.tag.endswith('}r')]
            if runs:
                orig_text = ''.join(
                    (r.find('./{*}t').text or '') if r.find('./{*}t') is not None else ''
                    for r in runs
                ).strip()
                if orig_text and _is_meaningful_text(orig_text):
                    tasks.append((si, runs, orig_text))
            else:
                # 没有 <r>，可能是直接 <t>
                t_elem = si.find('./{*}t')
                if t_elem is not None and t_elem.text and _is_meaningful_text(t_elem.text.strip()):
                    tasks.append((si, [t_elem], t_elem.text.strip()))
    return tasks, tree

def _translate_si_group(tasks_group, target_lang, delay, base_context, group_id):
    ctx = {
        "file_name": base_context["file_name"],
        "slide_num": 0,
        "total_slides": base_context["total_slides"],
        "translated_segments": [],
        "term_requirements": base_context["term_requirements"]
    }
    results = []
    for index, (si, elements, original) in enumerate(tasks_group):
        try:
            translated = translate_text(original, target_lang, delay, context=ctx)
            if not translated:
                translated = original
            results.append((si, elements, translated))
            ctx["translated_segments"].append(f"原文：{original} | 译文：{translated}")
            if len(ctx["translated_segments"]) > 5:
                ctx["translated_segments"].pop(0)
        except Exception as exc:
            print(f"sharedStrings 组 {group_id} 第 {index+1} 个单元翻译失败: {exc}")
    return results

def _collect_inline_string_tasks(xml_path):
    tasks = []
    tree = ET.parse(xml_path)
    root = tree.getroot()
    for cell in root.iter():
        if not cell.tag.endswith('}c'):
            continue
        cell_type = cell.get('t')
        if cell_type == 'inlineStr':
            inline = next((child for child in cell if child.tag.endswith('}is')), None)
            if inline is None:
                continue
            runs = [child for child in inline if child.tag.endswith('}r')]
            if runs:
                original = ''.join(
                    (run.find('./{*}t').text or '') if run.find('./{*}t') is not None else ''
                    for run in runs
                ).strip()
                if original and _is_meaningful_text(original):
                    tasks.append((inline, runs, original))
            else:
                text_elem = inline.find('./{*}t')
                if text_elem is not None and text_elem.text and _is_meaningful_text(text_elem.text.strip()):
                    tasks.append((inline, [text_elem], text_elem.text.strip()))
        elif cell_type == 'str':
            value_elem = next((child for child in cell if child.tag.endswith('}v')), None)
            if value_elem is not None and value_elem.text and _is_meaningful_text(value_elem.text.strip()):
                tasks.append((cell, [value_elem], value_elem.text.strip()))
    return tasks, tree

def _translate_worksheet_group(tasks_group, target_lang, delay, base_context, group_id):
    ctx = {
        "file_name": base_context["file_name"],
        "slide_num": 0,
        "total_slides": base_context["total_slides"],
        "translated_segments": [],
        "term_requirements": base_context["term_requirements"]
    }
    results = []
    for index, (container, elements, original) in enumerate(tasks_group):
        try:
            translated = translate_text(original, target_lang, delay, context=ctx)
            if not translated:
                translated = original
            results.append((container, elements, translated))
            ctx["translated_segments"].append(f"原文：{original} | 译文：{translated}")
            if len(ctx["translated_segments"]) > 5:
                ctx["translated_segments"].pop(0)
        except Exception as exc:
            print(f"worksheet 组 {group_id} 第 {index+1} 个单元翻译失败: {exc}")
    return results

def _write_text_results(group_results):
    modified_count = 0
    for grp_res in group_results:
        for container, elements, translated in grp_res:
            if elements and elements[0].tag.endswith('}r'):
                first_run = elements[0]
                text_elem = first_run.find('./{*}t')
                if text_elem is None:
                    text_elem = ET.Element(f"{{{first_run.nsmap.get('', '')}}}t")
                    first_run.append(text_elem)
                text_elem.text = translated
                for run in elements[1:]:
                    container.remove(run)
            elif elements and (elements[0].tag.endswith('}t') or elements[0].tag.endswith('}v')):
                elements[0].text = translated
            modified_count += 1
    return modified_count

def translate_excel_xml_based(input_path, output_path, target_lang, delay):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        with zipfile.ZipFile(input_path, 'r') as zf:
            zf.extractall(tmp_path)

        base_context = {
            "file_name": Path(input_path).name,
            "slide_num": 0,
            "total_slides": 0,
            "translated_segments": [],
            "term_requirements": "TBOX译为TBOX、TSU译为TSU、CAN总线译为CANバス（日语）/CAN Bus（英语），公司名称不翻译"
        }

        xl_dir = tmp_path / "xl"
        shared = xl_dir / "sharedStrings.xml"
        total_modified = 0

        if shared.exists():
            print("[DEBUG] 开始处理 sharedStrings.xml...")
            tasks, tree = _collect_si_tasks(shared)
            if tasks:
                total = len(tasks)
                group_size = (total + MAX_WORKERS - 1) // MAX_WORKERS
                groups = [tasks[i:i+group_size] for i in range(0, total, group_size)]
                print(f"[DEBUG] 共 {total} 个字符串单元，分为 {len(groups)} 组并行翻译...")
                group_results = [None] * len(groups)
                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    futures = {executor.submit(_translate_si_group, group, target_lang, delay, base_context, idx): idx
                               for idx, group in enumerate(groups)}
                    for future in as_completed(futures):
                        idx = futures[future]
                        try:
                            group_results[idx] = future.result()
                        except Exception as e:
                            print(f"组 {idx+1} 翻译失败: {e}")
                            group_results[idx] = []
                total_modified += _write_text_results(group_results)
                tree.write(shared, encoding='utf-8', xml_declaration=True, pretty_print=False)
                print("[DEBUG] sharedStrings.xml 处理完成")
            else:
                print("[DEBUG] sharedStrings.xml 无可翻译的文本")
        else:
            print("[DEBUG] 未找到 sharedStrings.xml，将继续检查 worksheet inlineStr 文本")

        worksheets_dir = xl_dir / "worksheets"
        worksheet_files = sorted(worksheets_dir.glob("sheet*.xml")) if worksheets_dir.exists() else []
        worksheet_task_count = 0
        for worksheet_path in worksheet_files:
            tasks, tree = _collect_inline_string_tasks(worksheet_path)
            if not tasks:
                continue
            worksheet_task_count += len(tasks)
            base_context["total_slides"] = len(tasks)
            group_size = (len(tasks) + MAX_WORKERS - 1) // MAX_WORKERS
            groups = [tasks[i:i+group_size] for i in range(0, len(tasks), group_size)]
            print(f"[DEBUG] {worksheet_path.name} 共 {len(tasks)} 个 inlineStr/str 文本单元，分为 {len(groups)} 组并行翻译...")
            group_results = [None] * len(groups)
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {executor.submit(_translate_worksheet_group, group, target_lang, delay, base_context, idx): idx
                           for idx, group in enumerate(groups)}
                for future in as_completed(futures):
                    idx = futures[future]
                    try:
                        group_results[idx] = future.result()
                    except Exception as e:
                        print(f"worksheet 组 {idx+1} 翻译失败: {e}")
                        group_results[idx] = []
            total_modified += _write_text_results(group_results)
            tree.write(worksheet_path, encoding='utf-8', xml_declaration=True, pretty_print=False)
        if worksheet_task_count == 0:
            print("[DEBUG] worksheet 中未找到 inlineStr/str 文本")

        # 并行处理 drawing 和 chart
        files_to_process = []
        drawings_dir = xl_dir / "drawings"
        if drawings_dir.exists():
            files_to_process.extend(drawings_dir.glob("drawing*.xml"))
        charts_dir = xl_dir / "charts"
        if charts_dir.exists():
            files_to_process.extend(charts_dir.glob("chart*.xml"))

        if files_to_process:
            print(f"[DEBUG] 共找到 {len(files_to_process)} 个 drawing/chart 文件，开始并行处理...")
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                future_to_file = {}
                for file_path in files_to_process:
                    ctx = copy.deepcopy(base_context)
                    future = executor.submit(_translate_drawing_file, file_path, target_lang, delay, ctx)
                    future_to_file[future] = file_path
                for future in as_completed(future_to_file):
                    file_path = future_to_file[future]
                    try:
                        total_modified += future.result()
                        print(f"[DEBUG] 完成处理: {file_path.name}")
                    except Exception as e:
                        print(f"[ERROR] 处理文件 {file_path} 出错: {e}")
        else:
            print("[DEBUG] 未找到 drawings/charts 目录，形状/图表文本将不会被翻译")

        if total_modified == 0:
            raise ToolException("未找到可翻译的 Excel 文本内容，未生成翻译结果")

        # 重新打包
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file_path in tmp_path.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(tmp_path)
                    zf.write(file_path, arcname)

def translate_excel_file(file_name: str, workspace_dir: str = DEFAULT_INPUT_DIR,
                         target_lang: str = DEFAULT_TARGET_LANG,
                         delay: float = DEFAULT_DELAY) -> str:
    input_path = Path(workspace_dir) / file_name
    if not input_path.exists():
        raise ToolException(f"Excel文件不存在: {input_path}")
    output_path = Path(workspace_dir) / f"{input_path.stem}_{target_lang}{input_path.suffix}"

    translate_excel_xml_based(str(input_path), str(output_path), target_lang, delay)

    gc.collect()
    return f"Excel翻译完成！输出路径: {output_path}"
