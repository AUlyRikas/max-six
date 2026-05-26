#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
predict_54.py —— 54条围肖信号投票
============================================================
核心逻辑：
  54条正向条件围肖信号叠加投票，等权，冷号优先排序。
  信号来源：前1500期训练筛选的54条信号。

在集成投票中的角色：提供围肖信号投票的独立观点。
============================================================
"""
import os, sys
from collections import Counter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MARK6_DIR = os.path.join(BASE_DIR, "mark6") if os.path.exists(os.path.join(BASE_DIR, "mark6")) else BASE_DIR
if MARK6_DIR not in sys.path:
    sys.path.insert(0, MARK6_DIR)

from shuju_loader import load_all_data
from shx_suishu import get_shengxiao_by_suima, SHENGXIAO, to_simplified

ZODIAC = SHENGXIAO
POS_NAMES = ["平一", "平二", "平三", "平四", "平五", "平六", "特码"]

# 54条正向条件围肖信号（固化）
SIGNALS_GOOD = {
    "马": [("平一","号码",8,3), ("平三","号码",3,3), ("平四","生肖",-1,1), ("平五","号码",10,2), ("特码","生肖",6,4)],
    "羊": [("平一","号码",2,3), ("平三","号码",9,4), ("平五","号码",3,4)],
    "猴": [("平三","号码",8,2), ("平四","号码",0,2), ("平五","生肖",3,4), ("平六","号码",10,3)],
    "鸡": [("平二","生肖",-5,1), ("平三","生肖",2,2), ("平四","生肖",6,4), ("特码","生肖",-5,3)],
    "狗": [("平三","号码",2,4), ("平四","号码",8,2), ("平六","号码",2,2), ("特码","号码",2,4)],
    "猪": [("平一","生肖",-5,4), ("平二","号码",11,2), ("平三","号码",1,3), ("平四","号码",2,3), ("平五","号码",3,4)],
    "鼠": [("平一","号码",0,1), ("平二","生肖",4,4), ("平三","生肖",3,1), ("平四","号码",3,0)],
    "牛": [("平一","号码",5,3), ("平二","号码",9,4), ("平三","号码",2,1), ("平四","生肖",1,2), ("平五","生肖",5,4), ("平六","生肖",-4,2)],
    "虎": [("平一","号码",3,1), ("平三","号码",7,3), ("平四","号码",10,3), ("平六","号码",7,4), ("特码","号码",8,4)],
    "兔": [("平二","号码",6,1), ("平三","生肖",2,3), ("平五","号码",0,1), ("特码","生肖",6,4)],
    "龙": [("平一","生肖",3,1), ("平二","号码",5,3), ("平三","号码",10,4), ("平四","生肖",2,0), ("平五","号码",10,2), ("特码","生肖",4,1)],
    "蛇": [("平一","号码",10,3), ("平四","生肖",-5,2), ("平五","号码",6,4), ("特码","号码",3,2)],
}


def offset_num(num, off):
    return (num - 1 + off) % 49 + 1


def get_window(center_sx, r):
    idx = ZODIAC.index(center_sx)
    win = set()
    for d in range(-r, r + 1):
        win.add(ZODIAC[(idx + d) % 12])
    return win


def extract_records(data):
    records = []
    for item in data:
        try:
            qs = str(item.get("expect", ""))
            oc = str(item.get("openCode", ""))
            ot = item.get("openTime", "")
            year = int(ot[:4]) if ot else (int(qs[:4]) if len(qs) >= 4 else 2026)
            if not qs or not oc: continue
            parts = oc.strip().split(",")
            if len(parts) != 7: continue
            nums = [int(p.strip()) for p in parts]
            records.append({
                "qishu": qs, "year": year,
                "te_num": nums[6], "te_sx": get_shengxiao_by_suima(nums[6], year),
                "ping_nums": nums[:6],
                "ping_sx": [get_shengxiao_by_suima(n, year) for n in nums[:6]],
            })
        except: continue
    records.sort(key=lambda x: int(x["qishu"]))
    return records


def compute_missing(records, up_to):
    missing = {}
    for s in ZODIAC:
        streak = 0
        for i in range(up_to - 1, -1, -1):
            if records[i]["te_sx"] != s: streak += 1
            else: break
        missing[s] = streak
    return missing


def predict_54(records):
    """54条围肖信号投票预测"""
    if len(records) < 2:
        return None

    latest_idx = len(records)
    curr = records[latest_idx - 1]
    cur_sx = curr["te_sx"]
    year = curr["year"]

    if cur_sx not in SIGNALS_GOOD:
        return None

    sigs = SIGNALS_GOOD[cur_sx]
    missing = compute_missing(records, latest_idx)

    # 等权投票
    vc = Counter()
    for pos, stype, off, r in sigs:
        pos_idx = POS_NAMES.index(pos)
        num = curr["te_num"] if pos == "特码" else curr["ping_nums"][pos_idx]
        sx = curr["te_sx"] if pos == "特码" else curr["ping_sx"][pos_idx]
        if stype == "号码":
            c = get_shengxiao_by_suima(offset_num(num, off), year)
        else:
            # 生肖偏移
            sx_idx = ZODIAC.index(sx)
            c = ZODIAC[(sx_idx + off) % 12]
        w = get_window(c, r)
        for s in w:
            vc[s] += 1

    # 按票数降序，同票按遗漏值降序
    ranked = sorted(vc.items(), key=lambda x: (-x[1], -missing.get(x[0], 0)))
    nine = [s for s, _ in ranked[:9]]
    six = [s for s, _ in ranked[:6]]

    return six, nine


def main():
    data = load_all_data(auto_update=False)
    records = extract_records(data)
    result = predict_54(records)
    if result:
        six, nine = result
        print(f"九肖: {', '.join(nine)}")
        print(f"六肖: {', '.join(six)}")
    else:
        print("预测失败")


if __name__ == "__main__":
    main()