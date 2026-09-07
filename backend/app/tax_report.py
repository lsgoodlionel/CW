"""税务报表生成:企业所得税预缴(季报 A200000)与年度汇算(年报 A100000)主表。

依据国家税务总局表式,取账套数据(利润表口径)自动计算主表行次;优惠、预缴、
纳税调整、总分机构分摊等无法从账套自动取得的行次默认 0,可在生成的 Excel 中
手工调整后报送。行次的上下级关系以缩进呈现:子行次(如 1.1、9.1)相对父行次
缩进一级。
"""
import io
from calendar import monthrange
from datetime import date
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, reports_cn

RATE = Decimal("0.25")           # 法定税率 25%
# 小型微利企业优惠:应纳税所得额减按 25% 计入、按 20% 征收(实际税负 5%),
# 相对法定 25% 的减免率 = 25% - 5% = 20%(简化按全额适用,不分 300 万档)
SMALL_MICRO_RELIEF = Decimal("0.20")


def _is_small_micro(db: Session) -> bool:
    c = db.get(models.CompanyInfo, 1)
    return bool(c and c.is_small_micro)
_Q_TITLE = "中华人民共和国企业所得税月(季)度预缴纳税申报表(A类)"
_A_TITLE = "中华人民共和国企业所得税年度纳税申报表(A类)"
Z = Decimal("0")

# 行(行次, [类别,] 项目, 金额, 层级)。层级 0 为主行次,1 为子行次(缩进一级)。


def _quarter_end(year: int, quarter: int) -> date:
    month = quarter * 3
    return date(year, month, monthrange(year, month)[1])


def _level(line_no: str) -> int:
    """行次层级:主行次(整数)为 0;子行次(含"."或以 FZ 开头)为 1。"""
    if line_no.startswith("FZ"):
        return 1
    return line_no.count(".")


def _core_amounts(db: Session, start: date, end: date) -> dict:
    """按利润表口径从账套汇总核心金额(利润总额及其构成)。"""
    b = reports_cn.Balances(reports_cn._movement(db, start, end))
    a = {
        "revenue": b.net_credit("6001", "6051"),
        "cost": b.net_debit("6401", "6402"),
        "tax_surcharge": b.net_debit("6403"),
        "sell": b.net_debit("6601"),
        "admin": b.net_debit("6602"),
        "rd": Z,                       # 研发费用:小企业多并入管理费用,无独立科目
        "fin": b.net_debit("6603"),
        "invest": b.net_credit("6111"),
        "fair_value": b.net_credit("6101"),
        "asset_impair": b.net_debit("6701"),
        "non_op_income": b.net_credit("6301"),
        "non_op_expense": b.net_debit("6711"),
    }
    a["op_profit"] = (a["revenue"] - a["cost"] - a["tax_surcharge"] - a["sell"]
                      - a["admin"] - a["rd"] - a["fin"] + a["fair_value"]
                      + a["invest"] - a["asset_impair"])
    a["total_profit"] = a["op_profit"] + a["non_op_income"] - a["non_op_expense"]
    return a


# ---------- 季报 A200000 ----------

def compute_rows(db: Session, year: int, quarter: int):
    """季报主表:返回 (行次, 项目, 金额, 层级) 列表。"""
    start, end = date(year, 1, 1), _quarter_end(year, quarter)
    a = _core_amounts(db, start, end)
    taxable = a["total_profit"] if a["total_profit"] > 0 else Z    # 简化:暂无纳税调整
    tax_payable = (taxable * RATE).quantize(Decimal("0.01"))
    real_profit = a["total_profit"]                               # 实际利润额=利润总额(无调整)
    relief = (taxable * SMALL_MICRO_RELIEF).quantize(Decimal("0.01")) if _is_small_micro(db) else Z
    after_relief = tax_payable - relief                          # 27-28
    rows = [
        ("1", "营业收入", a["revenue"]),
        ("1.1", "其中:自营出口收入", Z),
        ("1.2", "委托出口收入", Z),
        ("1.3", "出口代理费收入", Z),
        ("2", "减:营业成本", a["cost"]),
        ("3", "减:税金及附加", a["tax_surcharge"]),
        ("4", "减:销售费用", a["sell"]),
        ("5", "减:管理费用", a["admin"]),
        ("6", "减:研发费用", a["rd"]),
        ("7", "减:财务费用", a["fin"]),
        ("8", "加:其他收益", Z),
        ("9", "加:投资收益(9.1+9.2)(损失以-号填列)", a["invest"]),
        ("9.1", "其中:股权投资确认的处置收益", Z),
        ("9.2", "其他投资收益", Z),
        ("10", "加:净敞口套期收益(损失以-号填列)", Z),
        ("11", "加:公允价值变动收益(损失以-号填列)", a["fair_value"]),
        ("12", "加:信用减值损失(损失以-号填列)", Z),
        ("13", "加:资产减值损失(损失以-号填列)", -a["asset_impair"]),
        ("14", "加:资产处置收益(损失以-号填列)", Z),
        ("15", "营业利润(亏损以-号填列)", a["op_profit"]),
        ("16", "加:营业外收入", a["non_op_income"]),
        ("17", "减:营业外支出", a["non_op_expense"]),
        ("18", "利润总额(15+16-17)", a["total_profit"]),
        ("19", "加:特定业务计算的应纳税所得额", Z),
        ("19.1", "其中:销售未完工产品的收入", Z),
        ("20", "减:不征税收入", Z),
        ("21", "减:资产加速折旧、摊销(扣除)调减额(填写A201020)", Z),
        ("22", "减:免税收入、减计收入、加计扣除(22.1+22.2+…)", Z),
        ("23", "减:所得减免(23.1+23.2+……)", Z),
        ("24", "减:弥补以前年度亏损", Z),
        ("25", "实际利润额(18+19-20-21-22-23-24)", real_profit),
        ("26", "税率(25%)", RATE),
        ("27", "应纳所得税额(25×26)", tax_payable),
        ("28", "减:减免所得税额(28.1+28.2+……)", relief),
        ("28.1", "其中:符合条件的小型微利企业减免企业所得税", relief),
        ("29", "减:抵免所得税额", Z),
        ("30", "减:本年累计已预缴所得税额", Z),
        ("31", "减:特定业务预缴(征)所得税额", Z),
        ("32", "本期应补(退)所得税额(27-28-29-30-31)", after_relief),
    ]
    return [(n, lb, v, _level(n)) for n, lb, v in rows]


# ---------- 年报 A100000 ----------

def compute_annual_rows(db: Session, year: int):
    """年报主表:返回 (行次, 类别, 项目, 金额, 层级) 列表。类别仅在该类首行填写。"""
    start, end = date(year, 1, 1), date(year, 12, 31)
    a = _core_amounts(db, start, end)
    profit = a["total_profit"]
    # 20/21 纳税调整增加/减少额,来自 A105000 合计(行46)的调增/调减
    a105 = compute_a105000(db, year)
    _, _, _, _, adj_add, adj_reduce, _, _ = a105[-1]
    adj_after = profit + adj_add - adj_reduce             # 24 纳税调整后所得(19/22/23=0)
    loss_offset = a106_offset_total(db, year)             # 26 弥补以前年度亏损(A106000)
    taxable = adj_after - loss_offset                     # 28 应纳税所得额(25/27=0)
    taxable = taxable if taxable > 0 else Z
    tax_amount = (taxable * RATE).quantize(Decimal("0.01"))   # 30 应纳所得税额
    relief = (taxable * SMALL_MICRO_RELIEF).quantize(Decimal("0.01")) if _is_small_micro(db) else Z
    payable = tax_amount - relief                         # 33 应纳税额=36 实际应纳(32/34/35=0)
    C1, C2 = "利润总额计算", "应纳税所得额计算"
    C3, C4 = "应纳税额计算", "实际应补(退)税额计算"
    rows = [
        ("1", C1, "营业收入(填写A101010/101020/103000)", a["revenue"]),
        ("2", "", "减:营业成本(填写A102010/102020/103000)", a["cost"]),
        ("3", "", "减:税金及附加", a["tax_surcharge"]),
        ("4", "", "减:销售费用(填写A104000)", a["sell"]),
        ("5", "", "减:管理费用(填写A104000)", a["admin"]),
        ("6", "", "减:研发费用(填写A104000)", a["rd"]),
        ("7", "", "减:财务费用(填写A104000)", a["fin"]),
        ("8", "", "加:其他收益", Z),
        ("9", "", "加:投资收益(损失以-号填列)", a["invest"]),
        ("10", "", "加:净敞口套期收益(损失以-号填列)", Z),
        ("11", "", "加:公允价值变动收益(损失以-号填列)", a["fair_value"]),
        ("12", "", "加:信用减值损失(损失以-号填列)", Z),
        ("13", "", "加:资产减值损失(损失以-号填列)", -a["asset_impair"]),
        ("14", "", "加:资产处置收益(损失以-号填列)", Z),
        ("15", "", "二、营业利润(亏损以-号填列)", a["op_profit"]),
        ("16", "", "加:营业外收入(填写A101010/101020/103000)", a["non_op_income"]),
        ("17", "", "减:营业外支出(填写A102010/102020/103000)", a["non_op_expense"]),
        ("18", "", "三、利润总额(15+16-17)", profit),
        ("19", C2, "减:境外所得(填写A108010)", Z),
        ("20", "", "加:纳税调整增加额(填写A105000)", adj_add),
        ("21", "", "减:纳税调整减少额(填写A105000)", adj_reduce),
        ("22", "", "减:免税、减计收入及加计扣除(填写A107010)", Z),
        ("23", "", "加:境外应税所得抵减境内亏损(填写A108000)", Z),
        ("24", "", "四、纳税调整后所得(18-19+20-21-22+23)", adj_after),
        ("25", "", "减:所得减免(填写A107020)", Z),
        ("26", "", "减:弥补以前年度亏损(填写A106000)", loss_offset),
        ("27", "", "减:抵扣应纳税所得额(填写A107030)", Z),
        ("28", "", "五、应纳税所得额(24-25-26-27)", taxable),
        ("29", C3, "税率(25%)", RATE),
        ("30", "", "六、应纳所得税额(28×29)", tax_amount),
        ("31", "", "减:减免所得税额(填写A107040)", relief),
        ("32", "", "减:抵免所得税额(填写A107050)", Z),
        ("33", "", "七、应纳税额(30-31-32)", payable),
        ("34", "", "加:境外所得应纳所得税额(填写A108000)", Z),
        ("35", "", "减:境外所得抵免所得税额(填写A108000)", Z),
        ("36", "", "八、实际应纳所得税额(33+34-35)", payable),
        ("37", C4, "减:本年累计预缴所得税额", Z),
        ("38", "", "九、本年应补(退)所得税额(36-37)", payable),
        ("39", "", "其中:总机构分摊本年应补(退)所得税额(填写A109000)", Z),
        ("40", "", "财政集中分配本年应补(退)所得税额(填写A109000)", Z),
        ("41", "", "总机构主体生产经营部门分摊本年应补(退)所得税额(填写A109000)", Z),
        ("45", "", "十、本年实际应补(退)所得税额", payable),
    ]
    return [(n, cat, lb, v, _level(n)) for n, cat, lb, v in rows]


# ---------- 附表 A101010 一般企业收入明细表 ----------

def compute_a101010(db: Session, year: int):
    """收入明细:返回 (行次, 项目, 金额, 层级)。主营/其他/营业外收入自动取数。"""
    start, end = date(year, 1, 1), date(year, 12, 31)
    b = reports_cn.Balances(reports_cn._movement(db, start, end))
    main = b.net_credit("6001")       # 主营业务收入
    other = b.net_credit("6051")      # 其他业务收入
    nonop = b.net_credit("6301")      # 营业外收入
    return [
        ("1", "一、营业收入(2+9)", main + other, 0),
        ("2", "(一)主营业务收入(3+5+6+7+8)", main, 1),
        ("3", "1.销售商品收入", main, 2),
        ("4", "其中:非货币性资产交换收入", Z, 3),
        ("5", "2.提供劳务收入", Z, 2),
        ("6", "3.建造合同收入", Z, 2),
        ("7", "4.让渡资产使用权收入", Z, 2),
        ("8", "5.其他", Z, 2),
        ("9", "(二)其他业务收入(10+12+13+14+15)", other, 1),
        ("10", "1.销售材料收入", Z, 2),
        ("11", "其中:非货币性资产交换收入", Z, 3),
        ("12", "2.出租固定资产收入", Z, 2),
        ("13", "3.出租无形资产收入", Z, 2),
        ("14", "4.出租包装物和商品收入", Z, 2),
        ("15", "5.其他", other, 2),
        ("16", "二、营业外收入(17+18+…+26)", nonop, 0),
        ("17", "(一)非流动资产处置利得", Z, 1),
        ("18", "(二)非货币性资产交换利得", Z, 1),
        ("19", "(三)债务重组利得", Z, 1),
        ("20", "(四)政府补助利得", Z, 1),
        ("21", "(五)盘盈利得", Z, 1),
        ("22", "(六)捐赠利得", Z, 1),
        ("23", "(七)罚没利得", Z, 1),
        ("24", "(八)确实无法偿付的应付款项", Z, 1),
        ("25", "(九)汇兑收益", Z, 1),
        ("26", "(十)其他", nonop, 1),
    ]


# ---------- 附表 A102010 一般企业成本支出明细表 ----------

def compute_a102010(db: Session, year: int):
    """成本支出明细:返回 (行次, 项目, 金额, 层级)。主营/其他/营业外支出自动取数。"""
    start, end = date(year, 1, 1), date(year, 12, 31)
    b = reports_cn.Balances(reports_cn._movement(db, start, end))
    main = b.net_debit("6401")        # 主营业务成本
    other = b.net_debit("6402")       # 其他业务成本
    nonop = b.net_debit("6711")       # 营业外支出
    return [
        ("1", "一、营业成本(2+9)", main + other, 0),
        ("2", "(一)主营业务成本(3+5+6+7+8)", main, 1),
        ("3", "1.销售商品成本", main, 2),
        ("4", "其中:非货币性资产交换成本", Z, 3),
        ("5", "2.提供劳务成本", Z, 2),
        ("6", "3.建造合同成本", Z, 2),
        ("7", "4.让渡资产使用权成本", Z, 2),
        ("8", "5.其他", Z, 2),
        ("9", "(二)其他业务成本(10+12+13+14+15)", other, 1),
        ("10", "1.材料销售成本", Z, 2),
        ("11", "其中:非货币性资产交换成本", Z, 3),
        ("12", "2.出租固定资产成本", Z, 2),
        ("13", "3.出租无形资产成本", Z, 2),
        ("14", "4.包装物出租成本", Z, 2),
        ("15", "5.其他", other, 2),
        ("16", "二、营业外支出(17+18+…+26)", nonop, 0),
        ("17", "(一)非流动资产处置损失", Z, 1),
        ("18", "(二)非货币性资产交换损失", Z, 1),
        ("19", "(三)债务重组损失", Z, 1),
        ("20", "(四)非常损失", Z, 1),
        ("21", "(五)捐赠支出", Z, 1),
        ("22", "(六)赞助支出", Z, 1),
        ("23", "(七)罚没支出", Z, 1),
        ("24", "(八)坏账损失", Z, 1),
        ("25", "(九)无法收回的债券股权投资损失", Z, 1),
        ("26", "(十)其他", nonop, 1),
    ]


# ---------- 附表 A104000 期间费用明细表 ----------

# (行次, 项目, 归集关键字);关键字命中二级科目名称即归入该行。空关键字为兜底「其他」。
_A104_ROWS = [
    ("1", "一、职工薪酬", ("薪酬", "工资", "社保", "公积金", "福利", "五险")),
    ("2", "二、劳务费", ("劳务",)),
    ("3", "三、咨询顾问费", ("咨询", "顾问")),
    ("4", "四、业务招待费", ("招待",)),
    ("5", "五、广告费和业务宣传费", ("广告", "宣传")),
    ("6", "六、佣金和手续费", ("佣金", "手续费")),
    ("7", "七、资产折旧摊销费", ("折旧", "摊销")),
    ("8", "八、财产损耗、盘亏及毁损损失", ("盘亏", "毁损", "损耗")),
    ("9", "九、办公费", ("办公",)),
    ("10", "十、董事会费", ("董事会",)),
    ("11", "十一、租赁费", ("租赁", "房租", "租金")),
    ("12", "十二、诉讼费", ("诉讼",)),
    ("13", "十三、差旅费", ("差旅",)),
    ("14", "十四、保险费", ("保险",)),
    ("15", "十五、运输、仓储费", ("运输", "仓储", "物流")),
    ("16", "十六、修理费", ("修理", "维修")),
    ("17", "十七、包装费", ("包装",)),
    ("18", "十八、技术转让费", ("技术转让",)),
    ("19", "十九、研究费用", ("研究", "研发")),
    ("20", "二十、各项税费", ("税费", "印花", "税金")),
    ("21", "二十一、利息收支", ("利息",)),
    ("22", "二十二、汇兑差额", ("汇兑",)),
    ("23", "二十三、现金折扣", ("折扣",)),
    ("24", "二十四、党组织工作经费", ("党组织", "党费", "党建")),
    ("25", "二十五、其他", ()),
]
_A104_FEE_CODES = ("6601", "6602", "6603")   # 销售 / 管理 / 财务费用


def _a104_classify(name: str) -> str:
    for rno, _label, kws in _A104_ROWS:
        if kws and any(k in name for k in kws):
            return rno
    return "25"


def compute_a104000(db: Session, year: int):
    """期间费用明细:返回 (行次, 项目, 销售费用, 管理费用, 财务费用)。
    按二级科目名称关键字归集到标准行,未匹配或无二级的差额计入「其他」,列合计=各费用发生额。"""
    start, end = date(year, 1, 1), date(year, 12, 31)
    mv = reports_cn._movement(db, start, end)
    sub = reports_cn._movement_by_sub(db, start, end)
    totals = {code: mv.get(code, Z) for code in _A104_FEE_CODES}
    grid = {rno: {c: Z for c in _A104_FEE_CODES} for rno, _l, _k in _A104_ROWS}
    matched = {c: Z for c in _A104_FEE_CODES}
    for (code, subname), (d, c) in sub.items():
        if code not in _A104_FEE_CODES:
            continue
        amt = d - c
        rno = _a104_classify(subname)
        grid[rno][code] += amt
        matched[code] += amt
    # 无二级或未归集的差额并入「其他」,保证列合计 = 费用发生额
    for code in _A104_FEE_CODES:
        diff = totals[code] - matched[code]
        if diff != 0:
            grid["25"][code] += diff
    rows = [(rno, label, grid[rno]["6601"], grid[rno]["6602"], grid[rno]["6603"])
            for rno, label, _k in _A104_ROWS]
    rows.append(("26", "合计(1+2+3+…24+25)",
                 totals["6601"], totals["6602"], totals["6603"]))
    return rows


# ---------- 附表 A105000 纳税调整项目明细表 ----------

# (行次, 项目, 层级, 类型)。sum=小计/合计(自动汇总),detail=可录入且计入小计,
# memo=「其中」行(可录入,不计入小计)。
_A105_ROWS = [
    ("1", "一、收入类调整项目(2+3+…8+10+11)", 0, "sum"),
    ("2", "(一)视同销售收入(填写A105010)", 1, "detail"),
    ("3", "(二)未按权责发生制原则确认的收入(填写A105020)", 1, "detail"),
    ("4", "(三)投资收益(填写A105030)", 1, "detail"),
    ("5", "(四)按权益法核算长期股权投资对初始投资成本调整确认收益", 1, "detail"),
    ("6", "(五)交易性金融资产初始投资调整", 1, "detail"),
    ("7", "(六)公允价值变动净损益", 1, "detail"),
    ("8", "(七)不征税收入", 1, "detail"),
    ("9", "其中:专项用途财政性资金(填写A105040)", 2, "memo"),
    ("10", "(八)销售折扣、折让和退回", 1, "detail"),
    ("11", "(九)其他", 1, "detail"),
    ("12", "二、扣除类调整项目(13+14+…24+26+27+28+29+30)", 0, "sum"),
    ("13", "(一)视同销售成本(填写A105010)", 1, "detail"),
    ("14", "(二)职工薪酬(填写A105050)", 1, "detail"),
    ("15", "(三)业务招待费支出", 1, "detail"),
    ("16", "(四)广告费和业务宣传费支出(填写A105060)", 1, "detail"),
    ("17", "(五)捐赠支出(填写A105070)", 1, "detail"),
    ("18", "(六)利息支出", 1, "detail"),
    ("19", "(七)罚金、罚款和被没收财物的损失", 1, "detail"),
    ("20", "(八)税收滞纳金、加收利息", 1, "detail"),
    ("21", "(九)赞助支出", 1, "detail"),
    ("22", "(十)与未实现融资收益相关在当期确认的财务费用", 1, "detail"),
    ("23", "(十一)佣金和手续费支出(保险企业填写A105060)", 1, "detail"),
    ("24", "(十二)不征税收入用于支出所形成的费用", 1, "detail"),
    ("25", "其中:专项用途财政性资金用于支出所形成的费用(填写A105040)", 2, "memo"),
    ("26", "(十三)跨期扣除项目", 1, "detail"),
    ("27", "(十四)与取得收入无关的支出", 1, "detail"),
    ("28", "(十五)境外所得分摊的共同支出", 1, "detail"),
    ("29", "(十六)党组织工作经费", 1, "detail"),
    ("30", "(十七)其他", 1, "detail"),
    ("31", "三、资产类调整项目(32+33+34+35)", 0, "sum"),
    ("32", "(一)资产折旧、摊销(填写A105080)", 1, "detail"),
    ("33", "(二)资产减值准备金", 1, "detail"),
    ("34", "(三)资产损失(填写A105090)", 1, "detail"),
    ("35", "(四)其他", 1, "detail"),
    ("36", "四、特殊事项调整项目(37+38+…+43)", 0, "sum"),
    ("37", "(一)企业重组及递延纳税事项(填写A105100)", 1, "detail"),
    ("38", "(二)政策性搬迁(填写A105110)", 1, "detail"),
    ("39", "(三)特殊行业准备金", 1, "sum"),
    ("39.1", "1.保险公司保险保障基金", 2, "detail"),
    ("39.2", "2.保险公司准备金", 2, "detail"),
    ("39.3", "其中:已发生未报案未决赔款准备金", 3, "memo"),
    ("39.4", "3.证券行业准备金", 2, "detail"),
    ("39.5", "4.期货行业准备金", 2, "detail"),
    ("39.6", "5.中小企业融资(信用)担保机构准备金", 2, "detail"),
    ("39.7", "6.金融企业、小额贷款公司准备金(填写A105120)", 2, "detail"),
    ("40", "(四)房地产开发企业特定业务计算的纳税调整额(填写A105010)", 1, "detail"),
    ("41", "(五)合伙企业法人合伙人应分得的应纳税所得额", 1, "detail"),
    ("42", "(六)发行永续债利息支出", 1, "detail"),
    ("43", "(七)其他", 1, "detail"),
    ("44", "五、特别纳税调整应税所得", 0, "detail"),
    ("45", "六、其他", 0, "detail"),
    ("46", "合计(1+12+31+36+44+45)", 0, "sum"),
]

# 小计计算(按依赖顺序:先子小计 39,再顶层小计,最后合计 46)
_A105_SUBTOTALS = [
    ("1", ["2", "3", "4", "5", "6", "7", "8", "10", "11"]),
    ("12", ["13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23",
            "24", "26", "27", "28", "29", "30"]),
    ("31", ["32", "33", "34", "35"]),
    ("39", ["39.1", "39.2", "39.4", "39.5", "39.6", "39.7"]),
    ("36", ["37", "38", "39", "40", "41", "42", "43"]),
    ("46", ["1", "12", "31", "36", "44", "45"]),
]
_A105_COLS = ("book", "tax", "add", "reduce")


def compute_a105000(db: Session, year: int):
    """纳税调整明细:返回 (行次, 项目, 账载, 税收, 调增, 调减, 层级, 可录入)。
    明细行取用户录入值,小计/合计自动汇总。"""
    recs = {r.line_no: r for r in db.scalars(
        select(models.TaxAdjustment).where(models.TaxAdjustment.year == year)).all()}
    vals: dict[str, dict] = {}
    for ln, _item, _lv, kind in _A105_ROWS:
        r = recs.get(ln)
        if kind in ("detail", "memo") and r is not None:
            vals[ln] = {"book": r.book_amount, "tax": r.tax_amount,
                        "add": r.add_amount, "reduce": r.reduce_amount}
        else:
            vals[ln] = {k: Z for k in _A105_COLS}
    for total, members in _A105_SUBTOTALS:
        for k in _A105_COLS:
            vals[total][k] = sum((vals[m][k] for m in members), Z)
    return [(ln, item, vals[ln]["book"], vals[ln]["tax"], vals[ln]["add"],
             vals[ln]["reduce"], lv, kind in ("detail", "memo"))
            for ln, item, lv, kind in _A105_ROWS]


# ---------- 附表 A106000 企业所得税弥补亏损明细表 ----------

# 行1..10 前十..前一年度,行11 本年度,行12 合计。
_A106_ITEMS = [
    ("1", "前十年度"), ("2", "前九年度"), ("3", "前八年度"), ("4", "前七年度"),
    ("5", "前六年度"), ("6", "前五年度"), ("7", "前四年度"), ("8", "前三年度"),
    ("9", "前二年度"), ("10", "前一年度"), ("11", "本年度"),
]


def compute_a106000(db: Session, report_year: int):
    """弥补亏损明细:返回 (行次, 项目, 所属年度, 当年亏损额, 当年待弥补额, 本年弥补额, 可结转以后年度, 可录入)。
    行1..10 为以前年度(可弥补),行11 本年度,行12 合计。主表行26=以前年度本年弥补额合计。"""
    recs = {r.line_no: r for r in db.scalars(
        select(models.TaxLossCarryover).where(
            models.TaxLossCarryover.report_year == report_year)).all()}
    rows = []
    sum_loss = sum_pending = sum_offset = sum_carry = Z
    for idx, (ln, item) in enumerate(_A106_ITEMS):
        occur_year = report_year - (11 - idx)   # 行1→-10 … 行10→-1,行11→本年
        r = recs.get(ln)
        loss = r.loss_amount if r else Z
        pending = r.pending_amount if r else Z
        offset = r.offset_amount if r else Z
        carry = pending - offset                # 可结转以后年度弥补
        rows.append((ln, item, occur_year, loss, pending, offset, carry, True))
        if ln != "11":                          # 本年度不计入"以前年度弥补"合计
            sum_offset += offset
        sum_loss += loss
        sum_pending += pending
        sum_carry += carry
    rows.append(("12", "可结转以后年度弥补的亏损额合计", None,
                 sum_loss, sum_pending, sum_offset, sum_carry, False))
    return rows


def a106_offset_total(db: Session, report_year: int) -> Decimal:
    """以前年度用本年度所得弥补的亏损额合计(供主表行26联动)。"""
    return compute_a106000(db, report_year)[-1][5]


# ---------- Excel 渲染 ----------

def _write_kv(ws, title: str, company, period: str,
              rows: list, has_category: bool) -> None:
    """通用「行次 / [类别] / 项目(按层级缩进) / 金额」表渲染到给定 worksheet。"""
    thin = Side(style="thin", color="BBBBBB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center")
    last_col = 4 if has_category else 3

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws.cell(1, 1, title)
    ws.cell(1, 1).font = Font(size=14, bold=True)
    ws.cell(1, 1).alignment = center
    ws.row_dimensions[1].height = 30

    meta = [
        f"税款所属期间:{period}",
        f"纳税人识别号(统一社会信用代码):{(company.tax_number if company else '') or ''}",
        f"纳税人名称:{(company.name if company else '') or ''}    金额单位:人民币元(列至角分)",
    ]
    r = 2
    for m in meta:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=last_col)
        ws.cell(r, 1, m).alignment = left
        r += 1

    header_fill = PatternFill("solid", fgColor="1F6FEB")
    head = ["行次", "类别", "项目", "本年金额"] if has_category else ["行次", "项目", "本年累计金额"]
    for c, h in enumerate(head, start=1):
        cell = ws.cell(r, c, h)
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
        cell.alignment = center
        cell.border = border
    r += 1

    for row in rows:
        if has_category:
            line_no, category, label, amount, level = row
        else:
            line_no, label, amount, level = row
            category = None
        col = 1
        ws.cell(r, col, line_no).alignment = center
        col += 1
        if has_category:
            ws.cell(r, col, category or "").alignment = center
            col += 1
        # 项目列:按层级缩进(子行次相对父行次缩进一级)
        lbl_cell = ws.cell(r, col, label)
        lbl_cell.alignment = Alignment(horizontal="left", vertical="center",
                                       wrap_text=True, indent=level * 2)
        col += 1
        # 金额列:税率行显示百分比,其余显示数值
        if str(label).startswith("税率"):
            vcell = ws.cell(r, col, f"{amount * 100:.0f}%")
            vcell.alignment = center
        else:
            vcell = ws.cell(r, col, round(float(amount), 2))
            vcell.alignment = right
        for c in range(1, last_col + 1):
            ws.cell(r, c).border = border
        r += 1

    note = ("本表由系统按账套利润表口径自动计算,纳税调整/优惠/预缴/总分机构分摊等"
            "行次默认 0,请核对并按实际情况调整后报送。")
    ws.merge_cells(start_row=r + 1, start_column=1, end_row=r + 1, end_column=last_col)
    ws.cell(r + 1, 1, note).alignment = left

    if has_category:
        ws.column_dimensions["A"].width = 8
        ws.column_dimensions["B"].width = 16
        ws.column_dimensions["C"].width = 52
        ws.column_dimensions["D"].width = 20
    else:
        ws.column_dimensions["A"].width = 8
        ws.column_dimensions["B"].width = 52
        ws.column_dimensions["C"].width = 20


def _write_a104(ws, title: str, company, period: str, rows: list) -> None:
    """A104000 期间费用明细表:行次 / 项目 / 销售费用 / 管理费用 / 财务费用。"""
    thin = Side(style="thin", color="BBBBBB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center")
    last_col = 5

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws.cell(1, 1, title)
    ws.cell(1, 1).font = Font(size=14, bold=True)
    ws.cell(1, 1).alignment = center
    ws.row_dimensions[1].height = 30

    meta = [
        f"税款所属期间:{period}",
        f"纳税人名称:{(company.name if company else '') or ''}    金额单位:人民币元(列至角分)",
    ]
    r = 2
    for m in meta:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=last_col)
        ws.cell(r, 1, m).alignment = left
        r += 1

    header_fill = PatternFill("solid", fgColor="1F6FEB")
    head = ["行次", "项目", "销售费用", "管理费用", "财务费用"]
    for c, h in enumerate(head, start=1):
        cell = ws.cell(r, c, h)
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
        cell.alignment = center
        cell.border = border
    r += 1

    for line_no, label, sell, admin, fin in rows:
        ws.cell(r, 1, line_no).alignment = center
        ws.cell(r, 2, label).alignment = left
        for c, val in ((3, sell), (4, admin), (5, fin)):
            ws.cell(r, c, round(float(val), 2)).alignment = right
        for c in range(1, last_col + 1):
            ws.cell(r, c).border = border
        r += 1

    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 34
    for col in ("C", "D", "E"):
        ws.column_dimensions[col].width = 16


def _write_a105(ws, title: str, company, period: str, rows: list) -> None:
    """A105000 纳税调整明细表:行次 / 项目(按层级缩进) / 账载 / 税收 / 调增 / 调减。"""
    thin = Side(style="thin", color="BBBBBB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center")
    last_col = 6

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws.cell(1, 1, title)
    ws.cell(1, 1).font = Font(size=14, bold=True)
    ws.cell(1, 1).alignment = center
    ws.row_dimensions[1].height = 30

    meta = [
        f"税款所属期间:{period}",
        f"纳税人名称:{(company.name if company else '') or ''}    金额单位:人民币元(列至角分)",
    ]
    r = 2
    for m in meta:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=last_col)
        ws.cell(r, 1, m).alignment = left
        r += 1

    header_fill = PatternFill("solid", fgColor="1F6FEB")
    for c, h in enumerate(["行次", "项目", "账载金额", "税收金额", "调增金额", "调减金额"], start=1):
        cell = ws.cell(r, c, h)
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
        cell.alignment = center
        cell.border = border
    r += 1

    for line_no, label, book, tax, add, reduce_, level, _editable in rows:
        ws.cell(r, 1, line_no).alignment = center
        ws.cell(r, 2, label).alignment = Alignment(
            horizontal="left", vertical="center", wrap_text=True, indent=level * 2)
        for c, val in ((3, book), (4, tax), (5, add), (6, reduce_)):
            ws.cell(r, c, round(float(val), 2)).alignment = right
        for c in range(1, last_col + 1):
            ws.cell(r, c).border = border
        r += 1

    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 44
    for col in ("C", "D", "E", "F"):
        ws.column_dimensions[col].width = 15


def _write_a106(ws, title: str, company, period: str, rows: list) -> None:
    """A106000 弥补亏损明细表:行次 / 项目 / 所属年度 / 当年亏损额 / 当年待弥补额 / 本年弥补额 / 可结转以后年度。"""
    thin = Side(style="thin", color="BBBBBB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center")
    last_col = 7

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws.cell(1, 1, title)
    ws.cell(1, 1).font = Font(size=14, bold=True)
    ws.cell(1, 1).alignment = center
    ws.row_dimensions[1].height = 30
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_col)
    ws.cell(2, 1, f"税款所属期间:{period}    金额单位:人民币元(列至角分)").alignment = left

    header_fill = PatternFill("solid", fgColor="1F6FEB")
    head = ["行次", "项目", "所属年度", "当年亏损额", "当年待弥补的亏损额",
            "用本年度所得额弥补的以前年度亏损额", "当年可结转以后年度弥补的亏损额"]
    r = 3
    for c, h in enumerate(head, start=1):
        cell = ws.cell(r, c, h)
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
        cell.alignment = center
        cell.border = border
    r += 1

    for line_no, item, occur_year, loss, pending, offset, carry, _ed in rows:
        ws.cell(r, 1, line_no).alignment = center
        ws.cell(r, 2, item).alignment = left
        ws.cell(r, 3, occur_year if occur_year is not None else "").alignment = center
        for c, val in ((4, loss), (5, pending), (6, offset), (7, carry)):
            ws.cell(r, c, round(float(val), 2)).alignment = right
        for c in range(1, last_col + 1):
            ws.cell(r, c).border = border
        r += 1

    for col, w in (("A", 8), ("B", 24), ("C", 12), ("D", 14), ("E", 18), ("F", 24), ("G", 24)):
        ws.column_dimensions[col].width = w


def build_cit_quarterly_xlsx(db: Session, year: int, quarter: int) -> bytes:
    company = db.get(models.CompanyInfo, 1)
    start, end = date(year, 1, 1), _quarter_end(year, quarter)
    period = f"{start:%Y-%m-%d} 至 {end:%Y-%m-%d}"
    wb = Workbook()
    ws = wb.active
    ws.title = "A200000"
    _write_kv(ws, _Q_TITLE, company, period, compute_rows(db, year, quarter),
              has_category=False)
    return _save(wb)


def build_cit_annual_xlsx(db: Session, year: int) -> bytes:
    """年报导出:A100000 主表 + A101010/A102010/A104000 附表(多 sheet)。"""
    company = db.get(models.CompanyInfo, 1)
    period = f"{year}-01-01 至 {year}-12-31"
    wb = Workbook()
    ws = wb.active
    ws.title = "A100000"
    _write_kv(ws, _A_TITLE, company, period, compute_annual_rows(db, year),
              has_category=True)
    _write_kv(wb.create_sheet("A101010"), "A101010 一般企业收入明细表",
              company, period, compute_a101010(db, year), has_category=False)
    _write_kv(wb.create_sheet("A102010"), "A102010 一般企业成本支出明细表",
              company, period, compute_a102010(db, year), has_category=False)
    _write_a104(wb.create_sheet("A104000"), "A104000 期间费用明细表",
                company, period, compute_a104000(db, year))
    _write_a105(wb.create_sheet("A105000"), "A105000 纳税调整项目明细表",
                company, period, compute_a105000(db, year))
    _write_a106(wb.create_sheet("A106000"), "A106000 企业所得税弥补亏损明细表",
                company, period, compute_a106000(db, year))
    return _save(wb)


def _save(wb) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
