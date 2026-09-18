"""Solar offset billing engine.

计费顺序固定：
1. 先从毛电量扣抵扣量得到净电量，净电量下限为零；
2. 再对净电量做阶梯分段；
3. 最后才套尖峰系数（系数只作用于净额分段单价）。
"""

from app.engines.helpers import kwh_qty
from app.engines.tier_progressive import calc_bill


def deduct(gross_kwh: float, offset_kwh: float) -> tuple[float, float, float, bool]:
    """返回 (毛电量, 实际抵扣量, 净电量, 是否因超出毛电量被裁剪)，净电量恒 >= 0。"""
    gross_f, offset_f = float(gross_kwh), float(offset_kwh)
    if gross_f < 0:
        raise ValueError("gross_kwh must be non-negative")
    if offset_f < 0:
        raise ValueError("offset_kwh must be non-negative")
    applied_f = min(gross_f, offset_f)
    clipped = offset_f - applied_f > 1e-9
    return (
        kwh_qty(gross_f),
        kwh_qty(applied_f),
        kwh_qty(gross_f - applied_f),
        clipped,
    )


def bill_with_offset(
    gross_kwh: float,
    offset_kwh: float,
    tiers: list[dict],
    peak_factor: float = 1.0,
) -> dict:
    """tiers: [{up_to, price}]，最后一段 up_to 可为 None。"""
    gross, applied, net, clipped = deduct(gross_kwh, offset_kwh)
    pf = float(peak_factor)

    # 第二步：净电量阶梯分段（先取阶梯原价）；第三步：对同一分段套尖峰系数。
    plain = calc_bill(net, tiers, 1.0)
    peaked = calc_bill(net, tiers, pf)

    # 同系数下“毛电量全额计费”的对照口径，用于毛/净并列对比与抵扣节省金额。
    gross_peaked = calc_bill(gross, tiers, pf)

    segments = []
    for base_seg, peak_seg in zip(plain["segments"], peaked["segments"]):
        segments.append(
            {
                "from_kwh": base_seg["from_kwh"],
                "to_kwh": base_seg["to_kwh"],
                "qty": base_seg["qty"],
                "base_price": base_seg["price"],
                "peak_factor": pf,
                "price": peak_seg["price"],
                "base_amount": base_seg["amount"],
                "amount": peak_seg["amount"],
            }
        )

    return {
        "gross_kwh": gross,
        "offset_kwh": applied,
        "offset_record_kwh": kwh_qty(offset_kwh),
        "offset_clipped": clipped,
        "net_kwh": net,
        "peak_factor": pf,
        "segments": segments,
        "total_plain": plain["total"],
        "total": peaked["total"],
        "gross_total": gross_peaked["total"],
        "saving": round(gross_peaked["total"] - peaked["total"], 2),
    }
