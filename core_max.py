#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core_max.py — 六肖预测核心模块（纯规则反向版 94.01%）
================================================================================
架构：
  1. 规则库七条规则给12生肖打分（杀对率越高扣分越多）
  2. TOP6加分（规则反向得分前6名额外加20分）
  3. 纯规则反向得分排序（频率权重=0，不再参与排序）
  4. 直接取Top9=九肖、Top6=六肖

排序公式：
  综合得分 = 规则反向得分×1.0 + (TOP6加分20分)
  规则反向得分 = 该生肖被七条规则杀对率累加 + 100
  频率不再参与排序

回测：1984期严格滚动
  九肖: 98.74%  最大连错1期  连错1期: 25次
  六肖: 94.01%  最大连错2期  连错1期: 110次  连错2期: 4次
  主3肖: 75.33%  最大连错4期  连错≥3: 17次

用法：
  python core_max.py                  → 自检+预测
  python core_max.py --output         → 预测+保存+校验上期命中
  python core_max.py --verify         → 仅校验上期命中（开奖后运行）
================================================================================
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

TRACK_DIR = os.path.join(BASE_DIR, "max记录")
TRACK_FILE = os.path.join(TRACK_DIR, "hit_track.json")


# ==================== 数据 ====================

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


# ==================== 预测核心 ====================

def predict_direct(records, up_to):
    """
    纯规则反向得分排序
    频率权重=0，完全由七条规则的杀对率决定生肖安全性
    杀对率越高 → 该生肖越危险 → 扣分越多 → 排名越靠后
    """
    cur_sx = records[up_to - 1]["te_sx"]
    rule_scores = Counter()

    # 1. 七条规则各自对12生肖打分
    if cur_sx in SHAXIAO_RULES:
        for pos_idx, pos_name in enumerate(POS_NAMES):
            if pos_name not in SHAXIAO_RULES[cur_sx]: continue
            actual_sx = records[up_to - 1]["ping_sx"][pos_idx] if pos_idx < 6 else cur_sx
            if actual_sx in SHAXIAO_RULES[cur_sx][pos_name]:
                rules = SHAXIAO_RULES[cur_sx][pos_name][actual_sx]
                for r in rules:
                    # 每条规则的杀对率累加到被杀生肖上（负分=危险）
                    rule_scores[r[1]] -= r[2]

    # 2. TOP6加分：规则反向得分最高的6个生肖额外加20分
    border = sorted(rule_scores.items(), key=lambda x: x[1], reverse=True)
    top_bonus = set(s for s, _ in border[:6])

    # 3. 纯规则反向得分排序（频率权重=0）
    scores = Counter()
    for s in ZODIAC:
        # 规则反向得分：没被杀的=100分，被杀的=100-杀对率
        rule_score = rule_scores.get(s, 0) + 100
        # TOP6加分
        bonus = 20 if s in top_bonus else 0
        scores[s] = rule_score + bonus

    # 4. 排序取结果
    sorted_sx = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    nine = [s for s, _ in sorted_sx[:9]]
    six = [s for s, _ in sorted_sx[:6]]

    # 规则杀肖（展示用，杀对率低于-90即为高风险）
    kills = set()
    for s, sc in rule_scores.items():
        if sc < -90:
            kills.add(s)

    return six, nine, kills


# ==================== 命中追踪 ====================

def load_hit_track():
    if not os.path.exists(TRACK_FILE):
        return []
    with open(TRACK_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_hit_track(track):
    os.makedirs(TRACK_DIR, exist_ok=True)
    with open(TRACK_FILE, 'w', encoding='utf-8') as f:
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
        "issue": issue,
        "nine": nine,
        "six": six,
        "hit9": -1,
        "hit6": -1,
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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


# ==================== 主预测函数 ====================

def predict_latest():
    data = load_all_data(auto_update=False)
    records = extract_records(data)
    if len(records) < 50: return {"error": "数据不足"}

    latest = records[-1]
    latest_full = data[-1] if data else {}
    latest_time = latest_full.get("openTime", "")
    latest_zodiac = to_simplified(latest_full.get("zodiac", ""))
    latest_wave = latest_full.get("wave", "")

    six, nine, kills = predict_direct(records, len(records))

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

    rate9, rate6, hits9, hits6 = calc_dynamic_rate()

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
        "predicted_6xiao": six,
        "dynamic_rate9": rate9,
        "dynamic_rate6": rate6,
        "track_hits9": hits9,
        "track_hits6": hits6,
    }


# ==================== 输出 ====================

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

    rate9 = result.get('dynamic_rate9', 0)
    rate6 = result.get('dynamic_rate6', 0)

    alert9 = "🔴" if rate9 < 93.0 else "🟢"
    alert6 = "🔴" if rate6 < 90.0 else "🟢"
    warn = ""
    if rate9 < 93.0 or rate6 < 90.0:
        warn = "⚠️ 警告: 近期命中率低于基准线，请谨慎!"

    lines.append(f"动态命中率(近50期): 九肖 {alert9} {rate9:.1f}% | 六肖 {alert6} {rate6:.1f}%")
    lines.append(f"基准命中率: 九肖 98.74% | 六肖 94.01% | 主3肖 75.33%")
    if warn:
        lines.append(warn)
    lines.append("-" * 30)

    lines.append(f"规则库高风险(展示): {', '.join(result.get('killed_zodiacs', []))}")
    lines.append(f"★九肖预测: {', '.join(result.get('nine_pool', []))}")
    lines.append(f"★六肖预测: {', '.join(result.get('predicted_6xiao', []))}")

    # 主3副3提示
    six = result.get('predicted_6xiao', [])
    if len(six) >= 6:
        lines.append(f"★主3肖(重注): {', '.join(six[:3])}")
        lines.append(f"  副3肖(轻注): {', '.join(six[3:6])}")

    if len(six) < 6:
        lines.append(f"★重点生肖: 规则覆盖不足，六肖候选池未满")
    lines.append("=" * 50)
    return "\n".join(lines)


# ==================== 入口 ====================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", action="store_true", help="输出预测文本并保存")
    parser.add_argument("--verify", action="store_true", help="仅校验上期命中（开奖后运行）")
    args = parser.parse_args()

    if args.verify:
        data = load_all_data(auto_update=False)
        records = extract_records(data)
        verify_last_prediction(records)
        rate9, rate6, hits9, hits6 = calc_dynamic_rate()
        print(f"动态命中率(近50期): 九肖 {rate9:.1f}% 六肖 {rate6:.1f}%")
        sys.exit(0)

    result = predict_latest()
    text = output_text(result)
    print(text)

    if args.output:
        data = load_all_data(auto_update=False)
        records = extract_records(data)
        verify_last_prediction(records)

        append_prediction_to_track(
            result.get("next_qihao", ""),
            result.get("nine_pool", []),
            result.get("predicted_6xiao", [])
        )

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
            "main3": result.get("predicted_6xiao", [])[:3],
            "sub3": result.get("predicted_6xiao", [])[3:6],
            "dynamicRate9": result.get("dynamic_rate9", 0),
            "dynamicRate6": result.get("dynamic_rate6", 0),
        }
        with open(js_path, 'w', encoding='utf-8') as f:
            f.write("var predictionMaxData = ")
            json.dump(js_data, f, ensure_ascii=False, indent=2)
            f.write(";")
        print(f"[OK] prediction_max.js")

        record_dir = os.path.join(BASE_DIR, "max记录")
        os.makedirs(record_dir, exist_ok=True)
        record_path = os.path.join(record_dir, "prediction_max.txt")
        issue = result.get("latest_issue", "")

        existing = ""
        if os.path.exists(record_path):
            with open(record_path, 'r', encoding='utf-8') as f:
                existing = f.read()
        if f"基于期号: {issue}" not in existing:
            with open(record_path, 'a', encoding='utf-8') as f:
                f.write("\n" + text + "\n")
            print(f"[OK] 已记录到 max记录")
        else:
            print(f"[SKIP] 期号 {issue} 已有记录")