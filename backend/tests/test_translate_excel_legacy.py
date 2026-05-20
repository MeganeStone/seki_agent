import importlib.util
import sys
import zipfile
from pathlib import Path

from openpyxl import Workbook


def load_translate_excel_module():
    legacy_dir = Path(__file__).resolve().parents[1] / "legacy"
    if str(legacy_dir) not in sys.path:
        sys.path.insert(0, str(legacy_dir))

    module_path = legacy_dir / "translate_excel.py"
    spec = importlib.util.spec_from_file_location("legacy_translate_excel", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load translate_excel.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_translate_excel_handles_inline_string_cells(tmp_path: Path, monkeypatch) -> None:
    module = load_translate_excel_module()

    def fake_translate_text(text: str, target_lang: str, delay: float, context: dict) -> str:
        return f"{text}_{target_lang}"

    monkeypatch.setattr(module, "translate_text", fake_translate_text)

    source = tmp_path / "场景.xlsx"
    output = tmp_path / "场景_日语.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet["A1"] = "时间同步场景"
    workbook.save(source)

    module.translate_excel_xml_based(str(source), str(output), "日语", 0)

    assert output.exists()
    with zipfile.ZipFile(output, "r") as archive:
        worksheet_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "时间同步场景_日语" in worksheet_xml


def test_translate_excel_continues_when_one_cell_fails(tmp_path: Path, monkeypatch) -> None:
    module = load_translate_excel_module()

    def fake_translate_text(text: str, target_lang: str, delay: float, context: dict) -> str:
        if text == "失败文本":
            raise RuntimeError("boom")
        return f"{text}_{target_lang}"

    monkeypatch.setattr(module, "translate_text", fake_translate_text)

    source = tmp_path / "场景.xlsx"
    output = tmp_path / "场景_日语.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet["A1"] = "成功文本"
    sheet["A2"] = "失败文本"
    workbook.save(source)

    module.translate_excel_xml_based(str(source), str(output), "日语", 0)

    with zipfile.ZipFile(output, "r") as archive:
        worksheet_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "成功文本_日语" in worksheet_xml
    assert "失败文本" in worksheet_xml
