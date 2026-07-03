"""小企业会计准则官方报表计算(会小企 01/02/03 表)。

按官方模板行次,将 81 个科目映射为:
- 资产负债表(会小企01):期末余额 / 年初余额
- 利润表(会小企02):本期金额 / 本年累计 / 上年金额(按报表类型取列)
- 现金流量表(会小企03):对方科目归类法推导

所有金额基于凭证分录实时聚合,不做月末结转。
"""
from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from . import models

ZERO = Decimal("0")
CASH_CODES = {"1001", "1002", "1012"}  # 货币资金:库存资金/银行存款/其他货币资金


# ---------------------------------------------------------------------------
# 周期解析
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Period:
    """报表周期。

    report_type: month(月报)/ quarter(季报)/ year(年报)
    cur_start/cur_end: 本期区间(月报=当月,季报=当季,年报=全年)
    ytd_start/ytd_end: 本年累计区间(年初至本期末)
    prev_start/prev_end: 上年同期(年报=上一年度全年)
    period_end: 资产负债表期末日
    year_begin: 本年度 1 月 1 日(用于"年初余额")
    """
    report_type: str
    year: int
    label: str
    cur_start: date
    cur_end: date
    ytd_start: date
    ytd_end: date
    prev_start: date
    prev_end: date
    period_end: date
    year_begin: date


def _month_end(year: int, month: int) -> date:
    return date(year, month, monthrange(year, month)[1])


def build_period(report_type: str, year: int, month: int | None,
                 quarter: int | None) -> Period:
    year_begin = date(year, 1, 1)
    if report_type == "month":
        m = month or 1
        cur_start, cur_end = date(year, m, 1), _month_end(year, m)
        label = f"{year}年{m:02d}月(月报)"
    elif report_type == "quarter":
        q = quarter or 1
        start_m = (q - 1) * 3 + 1
        cur_start, cur_end = date(year, start_m, 1), _month_end(year, start_m + 2)
        label = f"{year}年第{q}季度(季报)"
    else:  # year
        report_type = "year"
        cur_start, cur_end = year_begin, date(year, 12, 31)
        label = f"{year}年度(年报)"

    return Period(
        report_type=report_type, year=year, label=label,
        cur_start=cur_start, cur_end=cur_end,
        ytd_start=year_begin, ytd_end=cur_end,
        prev_start=date(year - 1, 1, 1), prev_end=date(year - 1, 12, 31),
        period_end=cur_end, year_begin=year_begin,
    )


# ---------------------------------------------------------------------------
# 科目余额 / 发生额
# ---------------------------------------------------------------------------
def _movement(db: Session, start: date | None, end: date | None) -> dict[str, Decimal]:
    """区间内各科目净发生额(借方-贷方),按科目编码返回。"""
    stmt = (
        select(
            models.Account.code,
            func.coalesce(func.sum(models.VoucherEntry.debit), 0)
            - func.coalesce(func.sum(models.VoucherEntry.credit), 0),
        )
        .join(models.VoucherEntry, models.VoucherEntry.account_id == models.Account.id)
        .join(models.Voucher, models.Voucher.id == models.VoucherEntry.voucher_id)
        .group_by(models.Account.code)
    )
    if start:
        stmt = stmt.where(models.Voucher.voucher_date >= start)
    if end:
        stmt = stmt.where(models.Voucher.voucher_date <= end)
    return {code: Decimal(v) for code, v in db.execute(stmt).all()}


class Balances:
    """某一时点的科目累计余额(借方-贷方口径)。"""
    def __init__(self, data: dict[str, Decimal]):
        self._d = data

    def net_debit(self, *codes: str) -> Decimal:
        """借方净额:资产为正常余额;负债/权益取相反数。"""
        return sum((self._d.get(c, ZERO) for c in codes), ZERO)

    def net_credit(self, *codes: str) -> Decimal:
        return -self.net_debit(*codes)


def balances_asof(db: Session, as_of: date) -> Balances:
    return Balances(_movement(db, None, as_of))


# ---------------------------------------------------------------------------
# 资产负债表(会小企01)
# ---------------------------------------------------------------------------
def balance_sheet(db: Session, period: Period) -> dict:
    end_bal = balances_asof(db, period.period_end)
    # 年初余额 = 上年末余额 = 本年 1 月 1 日前一日
    begin_bal = balances_asof(db, date(period.year - 1, 12, 31))

    def side(bal: Balances) -> tuple[dict[int, Decimal], dict[int, Decimal]]:
        a = _asset_lines(bal)
        r = _right_lines(bal, _profit_net(bal))
        return a, r

    end_a, end_r = side(end_bal)
    beg_a, beg_r = side(begin_bal)

    assets = [
        {**row, "end": float(end_a.get(row["line"], ZERO)),
         "begin": float(beg_a.get(row["line"], ZERO))}
        if row["line"] else {**row, "end": None, "begin": None}
        for row in _ASSET_TEMPLATE
    ]
    rights = [
        {**row, "end": float(end_r.get(row["line"], ZERO)),
         "begin": float(beg_r.get(row["line"], ZERO))}
        if row["line"] else {**row, "end": None, "begin": None}
        for row in _RIGHT_TEMPLATE
    ]
    return {
        "assets": assets, "rights": rights,
        "asset_total": float(end_a.get(30, ZERO)),
        "right_total": float(end_r.get(53, ZERO)),
        "balanced": end_a.get(30, ZERO) == end_r.get(53, ZERO),
    }


def _profit_net(bal: Balances) -> Decimal:
    """损益类科目累计净额(贷-借)= 未分配利润的当期来源。"""
    codes = ["6001", "6051", "6101", "6111", "6301",
             "6401", "6402", "6403", "6601", "6602", "6603",
             "6701", "6711", "6801", "6901"]
    return bal.net_credit(*codes)


def _asset_lines(b: Balances) -> dict[int, Decimal]:
    v: dict[int, Decimal] = {}
    v[1] = b.net_debit("1001", "1002", "1012")            # 货币资金
    v[2] = b.net_debit("1101")                             # 短期投资
    v[3] = b.net_debit("1121")                             # 应收票据
    v[4] = b.net_debit("1122", "1231")                     # 应收账款(减坏账准备)
    v[5] = b.net_debit("1123")                             # 预付账款
    v[6] = b.net_debit("1131")                             # 应收股利
    v[7] = b.net_debit("1132")                             # 应收利息
    v[8] = b.net_debit("1221")                             # 其他应收款
    v[9] = b.net_debit("1401", "1403", "1404", "1405", "1406",
                        "1407", "1408", "1411", "1471")     # 存货
    v[10] = b.net_debit("1403")                            # 其中:原材料
    v[11] = b.net_debit("5001")                            # 在产品(生产成本)
    v[12] = b.net_debit("1405")                            # 库存商品
    v[13] = b.net_debit("1411")                            # 周转材料
    v[14] = ZERO                                           # 其他流动资产
    v[15] = sum((v[i] for i in (1, 2, 3, 4, 5, 6, 7, 8, 9, 14)), ZERO)  # 流动资产合计
    v[16] = b.net_debit("1501", "1503")                   # 长期债券投资
    v[17] = b.net_debit("1511")                            # 长期股权投资
    v[18] = b.net_debit("1601")                            # 固定资产原价
    v[19] = -b.net_debit("1602")                           # 减:累计折旧(正数列示)
    v[20] = v[18] - v[19]                                  # 固定资产账面价值
    v[21] = b.net_debit("1604")                            # 在建工程
    v[22] = b.net_debit("1605")                            # 工程物资
    v[23] = b.net_debit("1606")                            # 固定资产清理
    v[24] = ZERO                                           # 生产性生物资产
    v[25] = b.net_debit("1701", "1702", "1703")           # 无形资产(净)
    v[26] = b.net_debit("5301")                            # 开发支出
    v[27] = b.net_debit("1801")                            # 长期待摊费用
    v[28] = b.net_debit("1521", "1531", "1811", "1901")   # 其他非流动资产
    v[29] = sum((v[i] for i in (16, 17, 20, 21, 22, 23, 24, 25, 26, 27, 28)), ZERO)
    v[30] = v[15] + v[29]                                  # 资产合计
    return v


def _right_lines(b: Balances, profit_net: Decimal) -> dict[int, Decimal]:
    v: dict[int, Decimal] = {}
    v[31] = b.net_credit("2001")                           # 短期借款
    v[32] = b.net_credit("2201")                           # 应付票据
    v[33] = b.net_credit("2202")                           # 应付账款
    v[34] = b.net_credit("2203")                           # 预收账款
    v[35] = b.net_credit("2211")                           # 应付职工薪酬
    v[36] = b.net_credit("2221")                           # 应交税费
    v[37] = b.net_credit("2231")                           # 应付利息
    v[38] = b.net_credit("2232")                           # 应付利润
    v[39] = b.net_credit("2241")                           # 其他应付款
    v[40] = b.net_credit("2101", "2401")                   # 其他流动负债
    v[41] = sum((v[i] for i in range(31, 41)), ZERO)       # 流动负债合计
    v[42] = b.net_credit("2501")                           # 长期借款
    v[43] = b.net_credit("2701")                           # 长期应付款
    v[44] = ZERO                                           # 递延收益
    v[45] = b.net_credit("2502", "2711", "2901")           # 其他非流动负债
    v[46] = sum((v[i] for i in (42, 43, 44, 45)), ZERO)    # 非流动负债合计
    v[47] = v[41] + v[46]                                  # 负债合计
    v[48] = b.net_credit("4001")                           # 实收资本
    v[49] = b.net_credit("4002")                           # 资本公积
    v[50] = b.net_credit("4101")                           # 盈余公积
    v[51] = b.net_credit("4103", "4104") + profit_net      # 未分配利润
    v[52] = sum((v[i] for i in (48, 49, 50, 51)), ZERO)    # 所有者权益合计
    v[53] = v[47] + v[52]                                  # 负债和所有者权益总计
    return v


# 资产负债表模板行(左侧资产 / 右侧负债权益);line=None 表示分组标题或空行
_ASSET_TEMPLATE = [
    {"label": "流动资产:", "line": None, "style": "header"},
    {"label": "货币资金", "line": 1, "style": "item"},
    {"label": "短期投资", "line": 2, "style": "item"},
    {"label": "应收票据", "line": 3, "style": "item"},
    {"label": "应收账款", "line": 4, "style": "item"},
    {"label": "预付账款", "line": 5, "style": "item"},
    {"label": "应收股利", "line": 6, "style": "item"},
    {"label": "应收利息", "line": 7, "style": "item"},
    {"label": "其他应收款", "line": 8, "style": "item"},
    {"label": "存货", "line": 9, "style": "item"},
    {"label": "  其中:原材料", "line": 10, "style": "subitem"},
    {"label": "        在产品", "line": 11, "style": "subitem"},
    {"label": "        库存商品", "line": 12, "style": "subitem"},
    {"label": "        周转材料", "line": 13, "style": "subitem"},
    {"label": "其他流动资产", "line": 14, "style": "item"},
    {"label": "流动资产合计", "line": 15, "style": "total"},
    {"label": "非流动资产:", "line": None, "style": "header"},
    {"label": "长期债券投资", "line": 16, "style": "item"},
    {"label": "长期股权投资", "line": 17, "style": "item"},
    {"label": "固定资产原价", "line": 18, "style": "item"},
    {"label": "减:累计折旧", "line": 19, "style": "item"},
    {"label": "固定资产账面价值", "line": 20, "style": "item"},
    {"label": "在建工程", "line": 21, "style": "item"},
    {"label": "工程物资", "line": 22, "style": "item"},
    {"label": "固定资产清理", "line": 23, "style": "item"},
    {"label": "生产性生物资产", "line": 24, "style": "item"},
    {"label": "无形资产", "line": 25, "style": "item"},
    {"label": "开发支出", "line": 26, "style": "item"},
    {"label": "长期待摊费用", "line": 27, "style": "item"},
    {"label": "其他非流动资产", "line": 28, "style": "item"},
    {"label": "非流动资产合计", "line": 29, "style": "total"},
    {"label": "资产合计", "line": 30, "style": "grand"},
]

_RIGHT_TEMPLATE = [
    {"label": "流动负债:", "line": None, "style": "header"},
    {"label": "短期借款", "line": 31, "style": "item"},
    {"label": "应付票据", "line": 32, "style": "item"},
    {"label": "应付账款", "line": 33, "style": "item"},
    {"label": "预收账款", "line": 34, "style": "item"},
    {"label": "应付职工薪酬", "line": 35, "style": "item"},
    {"label": "应交税费", "line": 36, "style": "item"},
    {"label": "应付利息", "line": 37, "style": "item"},
    {"label": "应付利润", "line": 38, "style": "item"},
    {"label": "其他应付款", "line": 39, "style": "item"},
    {"label": "其他流动负债", "line": 40, "style": "item"},
    {"label": "流动负债合计", "line": 41, "style": "total"},
    {"label": "非流动负债:", "line": None, "style": "header"},
    {"label": "长期借款", "line": 42, "style": "item"},
    {"label": "长期应付款", "line": 43, "style": "item"},
    {"label": "递延收益", "line": 44, "style": "item"},
    {"label": "其他非流动负债", "line": 45, "style": "item"},
    {"label": "非流动负债合计", "line": 46, "style": "total"},
    {"label": "负债合计", "line": 47, "style": "total"},
    {"label": "所有者权益(或股东权益):", "line": None, "style": "header"},
    {"label": "实收资本(或股本)", "line": 48, "style": "item"},
    {"label": "资本公积", "line": 49, "style": "item"},
    {"label": "盈余公积", "line": 50, "style": "item"},
    {"label": "未分配利润", "line": 51, "style": "item"},
    {"label": "所有者权益(或股东权益)合计", "line": 52, "style": "total"},
    {"label": "负债和所有者权益(或股东权益)总计", "line": 53, "style": "grand"},
    {"label": "", "line": None, "style": "blank"},
    {"label": "", "line": None, "style": "blank"},
    {"label": "", "line": None, "style": "blank"},
    {"label": "", "line": None, "style": "blank"},
    {"label": "", "line": None, "style": "blank"},
    {"label": "", "line": None, "style": "blank"},
]


# ---------------------------------------------------------------------------
# 利润表(会小企02)
# ---------------------------------------------------------------------------
def _income_values(mv: dict[str, Decimal]) -> dict[int, Decimal]:
    b = Balances(mv)
    v: dict[int, Decimal] = {i: ZERO for i in range(1, 33)}
    v[1] = b.net_credit("6001", "6051")                    # 营业收入
    v[2] = b.net_debit("6401", "6402")                     # 营业成本
    v[3] = b.net_debit("6403")                             # 税金及附加
    v[11] = b.net_debit("6601")                            # 销售费用
    v[14] = b.net_debit("6602")                            # 管理费用
    v[18] = b.net_debit("6603")                            # 财务费用
    v[20] = b.net_credit("6111", "6101")                   # 投资收益
    v[21] = v[1] - v[2] - v[3] - v[11] - v[14] - v[18] + v[20]  # 营业利润
    v[22] = b.net_credit("6301")                           # 营业外收入
    v[24] = b.net_debit("6711")                            # 营业外支出
    v[30] = v[21] + v[22] - v[24]                          # 利润总额
    v[31] = b.net_debit("6801")                            # 所得税费用
    v[32] = v[30] - v[31]                                  # 净利润
    return v


_INCOME_TEMPLATE = [
    ("一、营业收入", 1, "head"),
    ("减:营业成本", 2, "item"),
    ("    税金及附加", 3, "item"),
    ("      其中:消费税", 4, "sub"),
    ("            营业税", 5, "sub"),
    ("            城市维护建设税", 6, "sub"),
    ("            资源税", 7, "sub"),
    ("            土地增值税", 8, "sub"),
    ("            城镇土地使用税、房产税、车船税、印花税", 9, "sub"),
    ("            教育费附加、矿产资源补偿费、排污费", 10, "sub"),
    ("    销售费用", 11, "item"),
    ("      其中:商品维修费", 12, "sub"),
    ("            广告费和业务宣传费", 13, "sub"),
    ("    管理费用", 14, "item"),
    ("      其中:开办费", 15, "sub"),
    ("            业务招待费", 16, "sub"),
    ("            研究费用", 17, "sub"),
    ("    财务费用", 18, "item"),
    ("      其中:利息费用(收入以“-”号填列)", 19, "sub"),
    ("加:投资收益(损失以“-”号填列)", 20, "item"),
    ("二、营业利润(亏损以“-”号填列)", 21, "head"),
    ("加:营业外收入", 22, "item"),
    ("    其中:政府补助", 23, "sub"),
    ("减:营业外支出", 24, "item"),
    ("    其中:坏账损失", 25, "sub"),
    ("          无法收回的长期债券投资损失", 26, "sub"),
    ("          无法收回的长期股权投资损失", 27, "sub"),
    ("          自然灾害等不可抗力因素造成的损失", 28, "sub"),
    ("          税收滞纳金", 29, "sub"),
    ("三、利润总额(亏损总额以“-”号填列)", 30, "head"),
    ("减:所得税费用", 31, "item"),
    ("四、净利润(净亏损以“-”号填列)", 32, "head"),
]


def income_statement(db: Session, period: Period) -> dict:
    cur = _income_values(_movement(db, period.cur_start, period.cur_end))
    ytd = _income_values(_movement(db, period.ytd_start, period.ytd_end))
    prev = _income_values(_movement(db, period.prev_start, period.prev_end))
    return _assemble(period, _INCOME_TEMPLATE, cur, ytd, prev)


# ---------------------------------------------------------------------------
# 现金流量表(会小企03)—— 对方科目归类法
# ---------------------------------------------------------------------------
# 对方科目编码 -> 现金流量表行次(inflow 行, outflow 行)
_CF_INFLOW = {
    # 经营
    "6001": 1, "6051": 1, "1122": 1, "1121": 1, "2203": 1,
    "6301": 2, "2241": 2, "2211": 2, "2221": 2,
    # 投资
    "1101": 8, "1501": 8, "1503": 8, "1511": 8,
    "6111": 9, "1131": 9, "1132": 9,
    "1601": 10, "1701": 10, "1606": 10,
    # 筹资
    "2001": 14, "2501": 14,
    "4001": 15, "4002": 15,
}
_CF_OUTFLOW = {
    # 经营
    "1401": 3, "1403": 3, "1405": 3, "1411": 3, "1406": 3,
    "6401": 3, "6402": 3, "2202": 3, "1123": 3,
    "2211": 4,
    "2221": 5, "6403": 5, "6801": 5,
    "6601": 6, "6602": 6, "6603": 6, "6711": 6, "2241": 6,
    # 投资
    "1101": 11, "1501": 11, "1503": 11, "1511": 11,
    "1601": 12, "1604": 12, "1605": 12, "1701": 12, "1801": 12,
    # 筹资
    "2001": 16, "2501": 16,
    "2231": 17,
    "2232": 18, "4104": 18,
}


def _cashflow_values(db: Session, start: date, end: date,
                     cash_begin: Decimal) -> dict[int, Decimal]:
    v: dict[int, Decimal] = {i: ZERO for i in range(1, 23)}

    # 取区间内所有涉及现金科目的凭证
    voucher_ids = set(db.scalars(
        select(models.Voucher.id)
        .join(models.VoucherEntry, models.VoucherEntry.voucher_id == models.Voucher.id)
        .join(models.Account, models.Account.id == models.VoucherEntry.account_id)
        .where(models.Account.code.in_(CASH_CODES),
               models.Voucher.voucher_date >= start,
               models.Voucher.voucher_date <= end)
    ).all())

    for vid in voucher_ids:
        entries = db.scalars(
            select(models.VoucherEntry)
            .join(models.Account, models.Account.id == models.VoucherEntry.account_id)
            .where(models.VoucherEntry.voucher_id == vid)
        ).all()
        rows = [(e, db.get(models.Account, e.account_id)) for e in entries]
        cash_delta = sum(
            ((e.debit - e.credit) for e, a in rows if a.code in CASH_CODES), ZERO)
        if cash_delta == 0:
            continue
        inflow = cash_delta > 0
        for e, a in rows:
            if a.code in CASH_CODES:
                continue
            amt = e.debit + e.credit
            if amt == 0:
                continue
            line = (_CF_INFLOW.get(a.code, 2) if inflow
                    else _CF_OUTFLOW.get(a.code, 6))
            v[line] += amt

    # 小计与合计
    v[7] = v[1] + v[2] - v[3] - v[4] - v[5] - v[6]          # 经营净额
    v[13] = v[8] + v[9] + v[10] - v[11] - v[12]             # 投资净额
    v[19] = v[14] + v[15] - v[16] - v[17] - v[18]           # 筹资净额
    v[20] = v[7] + v[13] + v[19]                            # 现金净增加额
    v[21] = cash_begin                                     # 期初现金余额
    v[22] = cash_begin + v[20]                             # 期末现金余额
    return v


_CASHFLOW_TEMPLATE = [
    ("一、经营活动产生的现金流量:", None, "head"),
    ("销售产成品、商品、提供劳务收到的现金", 1, "item"),
    ("收到其他与经营活动有关的现金", 2, "item"),
    ("购买原材料、商品、接受劳务支付的现金", 3, "item"),
    ("支付的职工薪酬", 4, "item"),
    ("支付的税费", 5, "item"),
    ("支付其他与经营活动有关的现金", 6, "item"),
    ("    经营活动产生的现金流量净额", 7, "total"),
    ("二、投资活动产生的现金流量:", None, "head"),
    ("收回短期投资、长期债券投资和长期股权投资收到的现金", 8, "item"),
    ("取得投资收益收到的现金", 9, "item"),
    ("处置固定资产、无形资产和其他非流动资产收回的现金净额", 10, "item"),
    ("短期投资、长期债券投资和长期股权投资支付的现金", 11, "item"),
    ("购建固定资产、无形资产和其他非流动资产支付的现金", 12, "item"),
    ("    投资活动产生的现金流量净额", 13, "total"),
    ("三、筹资活动产生的现金流量:", None, "head"),
    ("取得借款收到的现金", 14, "item"),
    ("吸收投资者投资收到的现金", 15, "item"),
    ("偿还借款本金支付的现金", 16, "item"),
    ("偿还借款利息支付的现金", 17, "item"),
    ("分配利润支付的现金", 18, "item"),
    ("    筹资活动产生的现金流量净额", 19, "total"),
    ("四、现金净增加额", 20, "head"),
    ("加:期初现金余额", 21, "item"),
    ("五、期末现金余额", 22, "head"),
]


def cashflow_statement(db: Session, period: Period) -> dict:
    # 本期现金期初 = 本期开始前一日余额
    cash_begin_cur = _cash_balance_before(db, period.cur_start)
    cur = _cashflow_values(db, period.cur_start, period.cur_end, cash_begin_cur)

    cash_begin_ytd = _cash_balance_before(db, period.ytd_start)
    ytd = _cashflow_values(db, period.ytd_start, period.ytd_end, cash_begin_ytd)

    cash_begin_prev = _cash_balance_before(db, period.prev_start)
    prev = _cashflow_values(db, period.prev_start, period.prev_end, cash_begin_prev)

    return _assemble(period, _CASHFLOW_TEMPLATE, cur, ytd, prev)


def _cash_balance_before(db: Session, day: date) -> Decimal:
    from datetime import timedelta
    return balances_asof(db, day - timedelta(days=1)).net_debit(*CASH_CODES)


# ---------------------------------------------------------------------------
# 组装(利润表/现金流量表通用):按报表类型决定两列语义
# ---------------------------------------------------------------------------
def _assemble(period: Period, template, cur: dict[int, Decimal],
              ytd: dict[int, Decimal], prev: dict[int, Decimal]) -> dict:
    if period.report_type == "year":
        col1_label, col2_label = "本年累计金额", "上年金额"
        col1, col2 = ytd, prev
    else:
        col1_label, col2_label = "本期金额", "本年累计金额"
        col1, col2 = cur, ytd

    rows = []
    for label, line, style in template:
        if line is None:
            rows.append({"label": label, "line": None, "style": style,
                         "col1": None, "col2": None})
        else:
            rows.append({
                "label": label, "line": line, "style": style,
                "col1": float(col1.get(line, ZERO)),
                "col2": float(col2.get(line, ZERO)),
            })
    return {"rows": rows, "col1_label": col1_label, "col2_label": col2_label}
