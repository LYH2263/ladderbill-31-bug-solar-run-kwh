import json


def loads_blob(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def billed_kwh(result: dict, payload: dict):
    """运行记录列表与户详情共用的“电量”口径：一律取落库快照中的计费电量。

    光伏运行取净电量（保存当时快照里的值；当次抵扣量超过毛电量时，引擎已把
    净电量裁剪为 0），因此同一条运行在两处展示必然相同，且不随事后新录入的
    抵扣而变化。其余运行取 kwh；老数据缺字段时回退到输入负载。
    """
    if "net_kwh" in result:
        return float(result["net_kwh"])
    if "kwh" in result:
        return result["kwh"]
    return payload.get("kwh")
