"""财务报表导出模板格式回归验证。"""
from datetime import date

import xlrd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pathlib import Path

from app.database import Base
from app import models, report_excel, reports_cn
from app.tenant import install_tenant_isolation, set_current_tenant

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "app" / "report_templates"


def _new_db():
    eng = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def _book_for(report_type: str):
    db = _new_db()
    set_current_tenant(1)
    db.add(models.CompanyInfo(
        id=1,
        name="测试有限公司",
        tax_number="91310000TEST000001",
    ))
    db.commit()
    period = reports_cn.build_period(report_type, 2026, 9, 3)
    content = report_excel.build_report_workbook(db, period)
    set_current_tenant(None)
    db.close()
    return xlrd.open_workbook(file_contents=content, formatting_info=True)


def run():
    install_tenant_isolation()
    failures = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            failures.append(name)

    month_book = _book_for("month")
    check("月季报 sheet 完全匹配模板",
          month_book.sheet_names() == ["资产负债表", "利润表_月季报", "现金流量表_月季报"])
    bs = month_book.sheet_by_name("资产负债表")
    check("月季报资产负债表行列尺寸", (bs.nrows, bs.ncols) == (37, 10))
    check("月季报资产负债表标题", bs.cell_value(0, 1) == "资产负债表（适用执行小企业会计准则的企业）")
    check("纳税人识别号写入模板 D3", bs.cell_value(2, 3) == "91310000TEST000001")
    check("纳税人名称写入模板 H3", bs.cell_value(2, 7) == "测试有限公司")
    check("所属期起止写入模板", bs.cell_value(3, 3) == "2026-09-01" and bs.cell_value(3, 7) == "2026-09-30")
    income = month_book.sheet_by_name("利润表_月季报")
    check("月季报利润表列头", income.cell_value(4, 3) == "本期金额" and income.cell_value(4, 4) == "本年累计金额")
    check("月季报静态模板结构一致",
          _same_static_template(month_book, TEMPLATE_DIR / "month_quarter_report.xls"))

    year_book = _book_for("year")
    check("年报 sheet 完全匹配模板",
          year_book.sheet_names() == ["资产负债表", "利润表_年", "现金流量表_年"])
    y_income = year_book.sheet_by_name("利润表_年")
    check("年报利润表列头", y_income.cell_value(4, 3) == "本年累计金额" and y_income.cell_value(4, 4) == "上年金额")
    check("年报不包含科目汇总表", "科目汇总表" not in year_book.sheet_names())
    check("年报静态模板结构一致",
          _same_static_template(year_book, TEMPLATE_DIR / "annual_report.xls"))

    print("\n结果:" + ("全部通过" if not failures else f"{len(failures)} 项失败: {failures}"))
    if failures:
        raise SystemExit(1)


def _same_static_template(book, template_path: Path) -> bool:
    template = xlrd.open_workbook(str(template_path), formatting_info=True)
    if book.sheet_names() != template.sheet_names():
        return False
    for name in template.sheet_names():
        actual = book.sheet_by_name(name)
        expected = template.sheet_by_name(name)
        if (actual.nrows, actual.ncols) != (expected.nrows, expected.ncols):
            return False
        if sorted(actual.merged_cells) != sorted(expected.merged_cells):
            return False
        for row in range(expected.nrows):
            for col in range(expected.ncols):
                if _is_fill_cell(expected, row, col):
                    continue
                if actual.cell_value(row, col) != expected.cell_value(row, col):
                    return False
    return True


def _is_fill_cell(sheet, row: int, col: int) -> bool:
    if sheet.name == "资产负债表":
        if (row, col) in {(2, 3), (2, 7), (3, 3), (3, 7)}:
            return True
        return col in {3, 4, 7, 8} and row >= 6
    if (row, col) in {(2, 3), (2, 5), (3, 3), (3, 5)}:
        return True
    return col in {3, 4} and row >= 5


if __name__ == "__main__":
    run()
