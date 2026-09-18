"""Solar offset module（光伏电量抵扣）。

- 按户号 + 账期录入发电量抵扣，支持显式版本号更正、旧版只读保留；
- 计费顺序：先扣抵扣（净电量下限零）→ 净电量阶梯分段 → 最后套尖峰系数；
- 预览不落库；保存运行时把当次毛电量、净电量与账单合计写入 calc_runs。
"""

from app.modules.solar_offset.engine import bill_with_offset, deduct
from app.modules.solar_offset.exceptions import AccountNotFound, OffsetConflict
from app.modules.solar_offset.router import router

__all__ = [
    "router",
    "bill_with_offset",
    "deduct",
    "AccountNotFound",
    "OffsetConflict",
]
