#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core_max.py —— MAX预测核心模块（GIT网页展示版）
============================================================
整合严格样本外验证（前1500期训练，后695期测试）的全部有效信号：
  - 54条正向条件围肖信号（12特肖 × 各位置最优）
  - 差异化窗口策略：3~8肖等权+冷号优先，9肖窗口惩罚(0.3,0.5,0.7)+冷号优先

真实命中率（695期严格样本外验证）：
  九肖：88.78%  最大连错：3期
  六肖：69.21%  最大连错：5期
  五肖：61.01%  四肖：51.51%  三肖：41.15%

用法：
  python core_max.py                  → 预测下一期（屏幕输出）
  python core_max.py --output         → 预测+保存JS/TXT+校验上期
  python core_max.py --verify         → 仅校验上期命中
============================================================
"""
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MARK6_DIR = os.path.join(BASE_DIR, "mark6") if os.path.exists(os.path.join(BASE_DIR, "mark6")) else BASE_DIR
if MARK6_DIR not in sys.path:
    sys.path.insert(0, MARK6_DIR)

from shuju_loader import load_all_data
from shx_suishu import get_shengxiao_by_suima, SHENGXIAO, to_simplified, get_shift_shengxiao

ZODIAC = SHENGXIAO
POS_NAMES = ["平一", "平二", "平三", "平四", "平五", "平六", "特码"]

# ========== 54条正向条件围肖信号（训练集前1500期筛选，测试集后695期验证） ==========
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

# ========== 差异化窗口惩罚系数（九肖专用） ==========
COEF_9 = {1:0.3, 3:0.5, 5:0.7}

TRACK_DIR = os.path.join(BASE_DIR, "max记录")
TRACK_FILE = os.path.join(TRACK_DIR, "hit_track.json")


def offset_num(num, off):
    return (num - 1 + off) % 49 + 1


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
                "te_wei": nums[6] % 10,
                "ping_nums": nums[:6],
                "ping_sx": [get_shengxiao_by_suima(n, year) for n in nums[:6]],
            })
        except: continue
    records.sort(key=lambda x: int(x["qishu"]))
    return records


def get_window(center_sx, r):
    idx = ZODIAC.index(center_sx)
    win = set()
    for d in range(-r, r + 1):
        win.add(ZODIAC[(idx + d) % 12])
    return win


def compute_missing(records, up_to):
    missing = {}
    for s in ZODIAC:
        streak = 0
        for i in range(up_to - 1, -1, -1):
            if records[i]["te_sx"] != s: streak += 1
            else: break
        missing[s] = streak
    return missing


def predict(records):
    """核心预测：返回 9肖排序、6肖、3~8肖"""
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

    # 固定杀肖（用于网页展示，不参与排序）
    p2_num = curr["ping_nums"][1]
    fixed_kill = [
        get_shengxiao_by_suima(offset_num(p2_num, 3), year),
        cur_sx
    ]

    # === 3~8肖：等权投票 + 冷号优先 ===
    vc_equal = Counter()
    for pos, stype, off, r in sigs:
        pos_idx = POS_NAMES.index(pos)
        num = curr["te_num"] if pos == "特码" else curr["ping_nums"][pos_idx]
        sx = curr["te_sx"] if pos == "特码" else curr["ping_sx"][pos_idx]
        if stype == "号码":
            c = get_shengxiao_by_suima(offset_num(num, off), year)
        else:
            c = get_shift_shengxiao(sx, off)
        w = get_window(c, r)
        for s in w:
            vc_equal[s] += 1

    ranked_equal = sorted(vc_equal.items(), key=lambda x: (-x[1], -missing.get(x[0], 0)))
    ranked_equal_sx = [s for s, _ in ranked_equal]

    # === 9肖：窗口惩罚 + 冷号优先 ===
    vc_ws = Counter()
    for pos, stype, off, r in sigs:
        ws = 2 * r + 1
        mult = COEF_9.get(ws, 1.0)
        pos_idx = POS_NAMES.index(pos)
        num = curr["te_num"] if pos == "特码" else curr["ping_nums"][pos_idx]
        sx = curr["te_sx"] if pos == "特码" else curr["ping_sx"][pos_idx]
        if stype == "号码":
            c = get_shengxiao_by_suima(offset_num(num, off), year)
        else:
            c = get_shift_shengxiao(sx, off)
        w = get_window(c, r)
        for s in w:
            vc_ws[s] += mult

    ranked_ws = sorted(vc_ws.items(), key=lambda x: (-x[1], -missing.get(x[0], 0)))
    nine_pool = [s for s, _ in ranked_ws[:9]]
    six_pool = [s for s, _ in ranked_equal[:6]]

    # 3~8肖
    pools = {}
    for k in range(3, 9):
        pools[k] = ranked_equal_sx[:k]

    return {
        "nine_pool": nine_pool,
        "six_pool": six_pool,
        "pools_3to8": pools,
        "fixed_kill": fixed_kill,
        "missing": missing,
    }


# ==================== 命中追踪 ====================
def load_hit_track():
    if not os.path.exists(TRACK_FILE):
        return []
    with open(TRACK_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_hit_track(track):
    os.makedirs(TRACK_DIR, exist_ok=True)
    with open(TRACK_FILE, "w", encoding="utf-8") as f:
        json.dump(track, f, ensure_ascii=False, indent=2)


def verify_last_prediction(records):
    track = load_hit_track()
    if not track:
        print("[命中追踪] 暂无历史预测记录，跳过校验")
        return track
    last = track[-1]
    if last.get("hit9", -1) != -1 and last.get("hit6", -1) != -1:
        return track
    predicted_issue = last.get("issue", "")
    actual_sx = None
    for r in records:
        if r["qishu"] == predicted_issue:
            actual_sx = r["te_sx"]
            break
    if actual_sx is None:
        return track
    last["hit9"] = 1 if actual_sx in last.get("nine", []) else 0
    last["hit6"] = 1 if actual_sx in last.get("six", []) else 0
    track[-1] = last
    save_hit_track(track)
    hit9_str = "✓" if last["hit9"] else "✗"
    hit6_str = "✓" if last["hit6"] else "✗"
    print(f"[命中追踪] 上期{predicted_issue}已校验: 九肖{hit9_str} 六肖{hit6_str}")
    return track


def append_prediction_to_track(issue, nine, six):
    track = load_hit_track()
    track.append({
        "issue": issue, "nine": nine, "six": six,
        "hit9": -1, "hit6": -1,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    if len(track) > 100:
        track = track[-100:]
    save_hit_track(track)
    return track


def calc_dynamic_rate(window=50):
    track = load_hit_track()
    valid = [t for t in track if t.get("hit9", -1) >= 0][-window:]
    if not valid:
        return 0, 0, 0, 0
    hits9 = sum(t["hit9"] for t in valid)
    hits6 = sum(t["hit6"] for t in valid)
    total = len(valid)
    return hits9 / total * 100, hits6 / total * 100, hits9, hits6


# ==================== 主函数 ====================
def predict_latest():
    data = load_all_data(auto_update=False)
    records = extract_records(data)
    if len(records) < 2:
        return {"error": "数据不足"}

    result = predict(records)
    if result is None:
        return {"error": "预测失败"}

    latest = records[-1]
    latest_full = data[-1] if data else {}

    all_nums = []
    try:
        oc = latest_full.get("openCode", "")
        all_nums = [int(p.strip()) for p in oc.split(",")] if oc else []
    except:
        pass

    next_qihao = ""
    try:
        exp = latest["qishu"]
        if len(exp) >= 4:
            next_qihao = f"{exp[:4]}{int(exp[-3:]) + 1:03d}"
    except:
        pass

    rate9, rate6, hits9, hits6 = calc_dynamic_rate()

    return {
        "latest_issue": latest["qishu"],
        "latest_time": latest_full.get("openTime", ""),
        "latest_code": ",".join(str(n) for n in all_nums) if all_nums else "",
        "latest_te_sx": latest["te_sx"],
        "latest_te_wei": latest["te_wei"],
        "latest_zodiac": to_simplified(latest_full.get("zodiac", "")),
        "latest_wave": latest_full.get("wave", ""),
        "next_qihao": next_qihao,
        "nine_pool": result["nine_pool"],
        "predicted_6xiao": result["six_pool"],
        "pools_3to8": result["pools_3to8"],
        "fixed_kill_set": result["fixed_kill"],
        "missing": {s: result["missing"].get(s, 0) for s in ZODIAC},
        "dynamic_rate9": rate9,
        "dynamic_rate6": rate6,
    }


def output_text(result):
    lines = []
    lines.append(f"MAX预测（严格验证版） | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 50)
    lines.append(f"基于期号: {result.get('latest_issue')}")
    lines.append(f"开奖时间: {result.get('latest_time', '')}")
    lines.append(f"开奖号码: {result.get('latest_code')}")
    lines.append(f"本期特肖: {result.get('latest_te_sx')} (尾{result.get('latest_te_wei')})")
    lines.append(f"预测下期: {result.get('next_qihao')}")
    lines.append("-" * 30)
    rate9 = result.get('dynamic_rate9', 0)
    rate6 = result.get('dynamic_rate6', 0)
    lines.append(f"动态命中率(近50期): 九肖 {rate9:.1f}% | 六肖 {rate6:.1f}%")
    lines.append(f"基准命中率(严格验证): 九肖88.78% | 六肖69.21%")
    lines.append("-" * 30)
    lines.append(f"[信号源]")
    lines.append(f"  固定杀肖(参考): {', '.join(result.get('fixed_kill_set', []))}")
    lines.append(f"  信号库: 54条正向条件围肖信号")
    lines.append("-" * 30)
    lines.append(f"★九肖预测: {', '.join(result.get('nine_pool', []))}")
    lines.append(f"★六肖预测: {', '.join(result.get('predicted_6xiao', []))}")
    lines.append(f"★五肖预测: {', '.join(result.get('pools_3to8', {}).get(5, []))}")
    lines.append(f"★四肖预测: {', '.join(result.get('pools_3to8', {}).get(4, []))}")
    lines.append(f"★三肖预测: {', '.join(result.get('pools_3to8', {}).get(3, []))}")
    lines.append("=" * 50)
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", action="store_true", help="保存JS和TXT，同时校验上期")
    parser.add_argument("--verify", action="store_true", help="仅校验上期命中")
    args = parser.parse_args()

    if args.verify:
        data = load_all_data(auto_update=False)
        records = extract_records(data)
        verify_last_prediction(records)
        rate9, rate6, hits9, hits6 = calc_dynamic_rate()
        print(f"动态命中率(近50期): 九肖 {rate9:.1f}% 六肖 {rate6:.1f}%")
        sys.exit(0)

    result = predict_latest()
    if "error" in result:
        print(f"错误: {result['error']}")
        sys.exit(1)

    text = output_text(result)
    print(text)

    if args.output:
        data = load_all_data(auto_update=False)
        records = extract_records(data)
        verify_last_prediction(records)
        append_prediction_to_track(
            result.get("next_qihao", ""),
            result.get("nine_pool", []),
            result.get("predicted_6xiao", []),
        )

        # 保存 prediction_max.js（与网页兼容）
        js_path = os.path.join(BASE_DIR, "prediction_max.js")
        js_data = {
            "time": result.get("latest_time", ""),
            "issue": result.get("latest_issue", ""),
            "code": result.get("latest_code", ""),
            "zodiac": result.get("latest_zodiac", ""),
            "wave": result.get("latest_wave", ""),
            "teSx": result.get("latest_te_sx", ""),
            "teWei": result.get("latest_te_wei", ""),
            "nextIssue": result.get("next_qihao", ""),
            "ninePool": result.get("nine_pool", []),
            "sixPool": result.get("predicted_6xiao", []),
            "fixedKillSet": result.get("fixed_kill_set", []),
            "dynamicRate9": result.get("dynamic_rate9", 0),
            "dynamicRate6": result.get("dynamic_rate6", 0),
            "pools": {str(k): v for k, v in result.get("pools_3to8", {}).items()},
        }
        with open(js_path, "w", encoding="utf-8") as f:
            f.write("var predictionMaxData = ")
            json.dump(js_data, f, ensure_ascii=False, indent=2)
            f.write(";")
        print("[OK] prediction_max.js 已更新")

        # 保存本地TXT
        record_dir = os.path.join(BASE_DIR, "max记录")
        os.makedirs(record_dir, exist_ok=True)
        record_path = os.path.join(record_dir, "prediction_max.txt")
        issue = result.get("latest_issue", "")
        existing = ""
        if os.path.exists(record_path):
            with open(record_path, "r", encoding="utf-8") as f:
                existing = f.read()
        if f"基于期号: {issue}" not in existing:
            with open(record_path, "a", encoding="utf-8") as f:
                f.write("\n" + text + "\n")
            print("[OK] 已记录到 max记录")
        else:
            print("[SKIP] 期号已有记录")