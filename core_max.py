#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core_max.py — 六肖预测核心模块（92.02% + 网页数据 + 繁转简）
"""
import json, os, sys
from collections import defaultdict, Counter
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MARK6_DIR = os.path.join(BASE_DIR, "mark6") if os.path.exists(os.path.join(BASE_DIR, "mark6")) else BASE_DIR
if MARK6_DIR not in sys.path: sys.path.insert(0, MARK6_DIR)

from shuju_loader import load_all_data
from shx_suishu import get_shengxiao_by_suima, SHENGXIAO, to_simplified

ZODIAC = SHENGXIAO
POS_NAMES = ["平一", "平二", "平三", "平四", "平五", "平六", "特码"]

RULES_PATH = os.path.join(BASE_DIR, "特肖杀肖规则库.json")
with open(RULES_PATH, 'r', encoding='utf-8') as f:
    SHAXIAO_RULES = json.load(f)


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


def predict_6xiao(records, up_to, freq_weight=0.3, rule_weight=0.7):
    cur_sx = records[up_to - 1]["te_sx"]
    kills = set()
    rule_scores = Counter()
    filled = []

    if cur_sx in SHAXIAO_RULES:
        for pos_idx, pos_name in enumerate(POS_NAMES):
            if pos_name not in SHAXIAO_RULES[cur_sx]: continue
            actual_sx = records[up_to - 1]["ping_sx"][pos_idx] if pos_idx < 6 else cur_sx
            if actual_sx in SHAXIAO_RULES[cur_sx][pos_name]:
                rules = SHAXIAO_RULES[cur_sx][pos_name][actual_sx]
                kills.add(rules[0][1])
                for r in rules: rule_scores[r[1]] -= r[2]

    remaining = [s for s in ZODIAC if s not in kills]
    if len(remaining) < 9:
        freq = Counter(r["te_sx"] for r in records[:up_to])
        for s, _ in freq.most_common(12):
            if s not in kills and s not in remaining:
                remaining.append(s)
                filled.append(s)
            if len(remaining) >= 9: break

    nine = remaining[:9]
    freq = Counter(r["te_sx"] for r in records[:up_to])
    max_f = max(freq.values()) if freq else 1

    final_scores = Counter()
    for s in nine:
        freq_score = freq.get(s, 0) / max_f * 100 * freq_weight
        rule_score = (rule_scores.get(s, 0) + 100) * rule_weight
        final_scores[s] = freq_score + rule_score

    sorted_sx = sorted(final_scores.items(), key=lambda x: x[1], reverse=True)
    six = [s for s, _ in sorted_sx[:6]]
    return six, kills, nine, filled


def predict_latest():
    data = load_all_data(auto_update=False)
    records = extract_records(data)
    if len(records) < 50: return {"error": "数据不足"}

    latest = records[-1]
    latest_full = data[-1] if data else {}
    latest_time = latest_full.get("openTime", "")
    latest_zodiac = to_simplified(latest_full.get("zodiac", ""))
    latest_wave = latest_full.get("wave", "")

    six, kills, nine, filled = predict_6xiao(records, len(records))

    all_nums = []
    try:
        oc = latest_full.get("openCode", "")
        all_nums = [int(p.strip()) for p in oc.split(",")] if oc else []
    except: pass

    next_qihao = ""
    try:
        exp = latest["qishu"]
        if len(exp) >= 4: next_qihao = f"{exp[:4]}{int(exp[-3:]) + 1:03d}"
    except: pass

    return {
        "latest_issue": latest["qishu"],
        "latest_time": latest_time,
        "latest_code": ",".join(str(n) for n in all_nums) if all_nums else "",
        "latest_te_sx": latest["te_sx"],
        "latest_te_wei": latest["te_wei"],
        "latest_zodiac": latest_zodiac,
        "latest_wave": latest_wave,
        "next_qihao": next_qihao,
        "killed_zodiacs": list(kills),
        "nine_pool": nine,
        "filled": filled,
        "predicted_6xiao": six,
    }


def output_text(result):
    lines = []
    lines.append(f"MAX六肖预测 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 50)
    lines.append(f"基于期号: {result.get('latest_issue')}")
    lines.append(f"开奖时间: {result.get('latest_time', '')}")
    lines.append(f"开奖号码: {result.get('latest_code')}")
    lines.append(f"本期特肖: {result.get('latest_te_sx')} (尾{result.get('latest_te_wei')})")
    lines.append(f"预测下期: {result.get('next_qihao')}")
    lines.append("-" * 30)
    lines.append(f"规则库杀肖: {', '.join(result.get('killed_zodiacs', []))}")

    nine = result.get('nine_pool', [])
    filled = result.get('filled', [])
    if filled:
        native = [s for s in nine if s not in filled]
        lines.append(f"规则库九肖: {', '.join(native)} [补: {', '.join(filled)}]")
    else:
        lines.append(f"规则库九肖: {', '.join(nine)}")

    six = result.get('predicted_6xiao', [])
    lines.append(f"★规则库六肖: {', '.join(six)}")

    if len(six) < 6:
        lines.append(f"★重点生肖: 规则覆盖不足，六肖候选池未满")
    lines.append("=" * 50)
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", action="store_true", help="输出预测文本并保存")
    args = parser.parse_args()

    result = predict_latest()
    text = output_text(result)
    print(text)

    if args.output:
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
            "kills": result.get("killed_zodiacs", []),
            "ninePool": result.get("nine_pool", []),
            "sixPool": result.get("predicted_6xiao", []),
            "filled": result.get("filled", []),
        }
        with open(js_path, 'w', encoding='utf-8') as f:
            f.write("var predictionMaxData = ")
            json.dump(js_data, f, ensure_ascii=False, indent=2)
            f.write(";")
        print(f"[OK] 已生成 prediction_max.js")

        out_path = os.path.join(BASE_DIR, "prediction_max.txt")
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(text + "\n")
        print(f"[OK] 已保存: {out_path}")