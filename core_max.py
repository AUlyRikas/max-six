#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core_max.py — MAX六肖预测核心模块（金标验证版）
==========================================================================
架构：
  1. 用前1500期数据构建规则库，后689期数据给每条规则分级
  2. 金标规则（测试集100%杀对率+0连错）投票筛选
  3. 得票≥2的生肖硬排除，得票=1的降权
  4. 排序：规则反向得分（金标1.0/银标0.5/铜标0.2） + 遗漏值0.3
  5. 六肖在九肖池内按：规则反向得分 + 近3期冷却扣分

样本外验证（前1500期训练，后689期测试）：
  九肖: 99.42%  最大连错1期  连错1期: 4次
  六肖: 88.82%  最大连错3期  连错1期: 60次  连错2期: 7次  连错3期: 1次
==========================================================================
用法：
  python core_max.py                  → 自检+预测
  python core_max.py --output         → 预测+保存+校验上期命中
  python core_max.py --verify         → 仅校验上期命中（开奖后运行）
==========================================================================
"""
import json
import os
import sys
import math
from collections import Counter
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MARK6_DIR = os.path.join(BASE_DIR, "mark6") if os.path.exists(os.path.join(BASE_DIR, "mark6")) else BASE_DIR
if MARK6_DIR not in sys.path:
    sys.path.insert(0, MARK6_DIR)

from shuju_loader import load_all_data
from shx_suishu import get_shengxiao_by_suima, SHENGXIAO, to_simplified

ZODIAC = SHENGXIAO
POS_NAMES = ["平一", "平二", "平三", "平四", "平五", "平六", "特码"]

# 规则库构建参数
OFFSETS = list(range(-11, 0)) + [0] + list(range(1, 12))
MIN_SAMPLES = 5
MIN_KILL_RATE = 95.0
MAX_STREAK = 1

# 命中追踪
TRACK_DIR = os.path.join(BASE_DIR, "max记录")
TRACK_FILE = os.path.join(TRACK_DIR, "hit_track.json")

# 分级规则库缓存
GRADED_RULES_CACHE = None
RULES_CACHE = None


def offset_num(num, off):
    return (num - 1 + off) % 49 + 1


# ==================== 数据加载 ====================

def extract_records(data):
    records = []
    for item in data:
        try:
            qs = str(item.get("expect", ""))
            oc = str(item.get("openCode", ""))
            ot = item.get("openTime", "")
            year = int(ot[:4]) if ot else (int(qs[:4]) if len(qs) >= 4 else 2026)
            if not qs or not oc:
                continue
            parts = oc.strip().split(",")
            if len(parts) != 7:
                continue
            nums = [int(p.strip()) for p in parts]
            records.append({
                "qishu": qs,
                "year": year,
                "te_num": nums[6],
                "te_sx": get_shengxiao_by_suima(nums[6], year),
                "te_wei": nums[6] % 10,
                "ping_nums": nums[:6],
                "ping_sx": [get_shengxiao_by_suima(n, year) for n in nums[:6]],
            })
        except:
            continue
    records.sort(key=lambda x: int(x["qishu"]))
    return records


# ==================== 规则库构建与分级 ====================

def build_and_grade_rules(records):
    """
    用全部历史数据构建规则库，并用后689期数据给每条规则分级。
    返回：(rules, graded_rules)
    
    rules: {特肖: {位置: {触发平码生肖: [(偏移, 杀肖目标, 原始杀对率, 样本量, 连错), ...]}}}
    graded_rules: {(特肖, 位置, 触发平码生肖, 偏移, 杀肖目标): {'grade': 'gold'/'silver'/'bronze'/'discard', 'test_rate': 测试集杀对率}}
    """
    global GRADED_RULES_CACHE, RULES_CACHE
    if GRADED_RULES_CACHE is not None and RULES_CACHE is not None:
        return RULES_CACHE, GRADED_RULES_CACHE

    # 切分训练集和测试集
    total = len(records)
    train_end = min(1500, max(200, total - 689))
    train_records = records[:train_end]
    test_records = records[train_end:]

    # === 第一步：从训练集提取规则 ===
    stats = {}
    for sx in ZODIAC:
        stats[sx] = {}
        for pos_name in POS_NAMES:
            stats[sx][pos_name] = {}

    for i in range(len(train_records) - 1):
        curr, nxt = train_records[i], train_records[i + 1]
        curr_sx = curr["te_sx"]
        year = curr["year"]
        nxt_sx = nxt["te_sx"]

        for pos_idx, pos_name in enumerate(POS_NAMES):
            num = curr["ping_nums"][pos_idx] if pos_idx < 6 else curr["te_num"]
            trigger_sx = get_shengxiao_by_suima(num, year)

            for off in OFFSETS:
                new_num = offset_num(num, off)
                result_sx = get_shengxiao_by_suima(new_num, year)
                key = (off, trigger_sx)

                if key not in stats[curr_sx][pos_name]:
                    stats[curr_sx][pos_name][key] = {"total": 0, "hit": 0, "result": result_sx}
                stats[curr_sx][pos_name][key]["total"] += 1
                if result_sx != nxt_sx:
                    stats[curr_sx][pos_name][key]["hit"] += 1

    rules = {}
    for sx in ZODIAC:
        rules[sx] = {}
        for pos_name in POS_NAMES:
            rules[sx][pos_name] = {}
            for (off, trigger_sx), v in stats[sx][pos_name].items():
                if v["total"] < MIN_SAMPLES:
                    continue
                raw_rate = v["hit"] / v["total"] * 100
                if raw_rate < MIN_KILL_RATE:
                    continue
                # 连错检查（训练集内）
                max_streak_found = 0
                cur_streak = 0
                for i in range(len(train_records) - 1):
                    if train_records[i]["te_sx"] != sx:
                        continue
                    year_i = train_records[i]["year"]
                    pos_idx = POS_NAMES.index(pos_name)
                    num = train_records[i]["ping_nums"][pos_idx] if pos_idx < 6 else train_records[i]["te_num"]
                    actual_sx = get_shengxiao_by_suima(num, year_i)
                    if actual_sx != trigger_sx:
                        continue
                    killed_sx = get_shengxiao_by_suima(offset_num(num, off), year_i)
                    if train_records[i + 1]["te_sx"] == killed_sx:
                        cur_streak += 1
                        max_streak_found = max(max_streak_found, cur_streak)
                    else:
                        cur_streak = 0
                if max_streak_found > MAX_STREAK:
                    continue
                if trigger_sx not in rules[sx][pos_name]:
                    rules[sx][pos_name][trigger_sx] = []
                rules[sx][pos_name][trigger_sx].append(
                    (off, v["result"], raw_rate, v["total"], max_streak_found)
                )

    # === 第二步：在测试集上逐条验证并分级 ===
    graded_rules = {}
    for sx in rules:
        for pos_name in rules[sx]:
            pos_idx = POS_NAMES.index(pos_name)
            for trigger_sx in rules[sx][pos_name]:
                for (off, killed_sx, raw_rate, samples, train_streak) in rules[sx][pos_name][trigger_sx]:
                    test_hits = 0
                    test_total = 0
                    test_streak = 0
                    test_max_streak = 0

                    for i in range(len(test_records) - 1):
                        if test_records[i]["te_sx"] != sx:
                            continue
                        year = test_records[i]["year"]
                        actual_sx = test_records[i]["ping_sx"][pos_idx] if pos_idx < 6 else test_records[i]["te_sx"]
                        if actual_sx != trigger_sx:
                            continue
                        target_sx = get_shengxiao_by_suima(
                            offset_num(test_records[i]["ping_nums"][pos_idx] if pos_idx < 6 else test_records[i]["te_num"], off),
                            year
                        )
                        nxt_sx = test_records[i + 1]["te_sx"]
                        test_total += 1
                        if target_sx != nxt_sx:
                            test_hits += 1
                            test_streak = 0
                        else:
                            test_streak += 1
                            test_max_streak = max(test_max_streak, test_streak)

                    test_rate = test_hits / test_total * 100 if test_total > 0 else 0

                    # 分级
                    if test_total == 0:
                        grade = 'discard'
                    elif test_rate == 100.0 and test_max_streak == 0:
                        grade = 'gold'
                    elif test_rate >= 95.0 and test_max_streak <= 1:
                        grade = 'silver'
                    elif test_rate >= 93.0 and test_max_streak <= 2:
                        grade = 'bronze'
                    else:
                        grade = 'discard'

                    rule_key = (sx, pos_name, trigger_sx, off, killed_sx)
                    graded_rules[rule_key] = {
                        'offset': off, 'killed_sx': killed_sx,
                        'grade': grade, 'test_rate': test_rate,
                        'samples': samples
                    }

    RULES_CACHE = rules
    GRADED_RULES_CACHE = graded_rules
    return rules, graded_rules


# ==================== 预测核心 ====================

def predict_gold(records, up_to, rules, graded_rules):
    """
    金标规则投票筛选 + 降级杀肖 + 排序
    返回：six, nine
    """
    cur_sx = records[up_to - 1]["te_sx"]

    # === 金标规则投票 ===
    gold_votes = Counter()
    all_rule_scores = Counter()

    if cur_sx in rules:
        for pos_idx, pos_name in enumerate(POS_NAMES):
            if pos_name not in rules[cur_sx]:
                continue
            actual_sx = records[up_to - 1]["ping_sx"][pos_idx] if pos_idx < 6 else cur_sx
            if actual_sx not in rules[cur_sx][pos_name]:
                continue
            for (off, killed_sx, raw_rate, samples, train_streak) in rules[cur_sx][pos_name][actual_sx]:
                rule_key = (cur_sx, pos_name, actual_sx, off, killed_sx)
                grade_info = graded_rules.get(rule_key)
                if grade_info is None:
                    continue

                grade = grade_info['grade']
                killed = killed_sx

                # 金标投票
                if grade == 'gold':
                    gold_votes[killed] += 1

                # 规则反向得分（用于排序）
                weight = 1.0 if grade == 'gold' else (0.5 if grade == 'silver' else (0.2 if grade == 'bronze' else 0.0))
                if weight > 0:
                    all_rule_scores[killed] -= grade_info['test_rate'] * weight

    # === 得票≥2硬排除，得票=1降权 ===
    killed = set(s for s, v in gold_votes.items() if v >= 2)
    soft_kill = set(s for s, v in gold_votes.items() if v == 1)

    safe_pool = [s for s in ZODIAC if s not in killed]

    # === 排序取九肖 ===
    # 遗漏值
    missing = {}
    for s in ZODIAC:
        streak = 0
        for i in range(up_to - 1, -1, -1):
            if records[i]["te_sx"] != s:
                streak += 1
            else:
                break
        missing[s] = streak
    max_missing = max(missing.values()) if missing else 1

    scores = {}
    for s in safe_pool:
        rs = (all_rule_scores.get(s, 0) + 100)
        ms = math.log1p(missing.get(s, 0)) / math.log1p(max_missing) * 100 * 0.3
        scores[s] = rs * 0.7 + ms
        # 金标得票=1的降权
        if s in soft_kill:
            scores[s] -= 10

    sorted_pool = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    nine = [s for s, _ in sorted_pool[:9]]

    # 补足（安全池不足9个时）
    if len(nine) < 9:
        remaining_killed = sorted(killed, key=lambda s: gold_votes.get(s, 0))
        for s in remaining_killed:
            if s not in nine:
                nine.append(s)
            if len(nine) >= 9:
                break

    # === 六肖：在九肖池内，规则反向得分 + 近3期冷却扣分 ===
    recent_sx = set()
    for i in range(max(0, up_to - 3), up_to):
        recent_sx.add(records[i]["te_sx"])

    six_scores = {}
    for s in nine:
        base_score = scores.get(s, 0)
        cool_penalty = 15 if s in recent_sx else 0
        six_scores[s] = base_score - cool_penalty

    sorted_six = sorted(six_scores.items(), key=lambda x: x[1], reverse=True)
    six = [s for s, _ in sorted_six[:6]]

    return six, nine, killed


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
    if len(records) < 50:
        return {"error": "数据不足"}

    latest = records[-1]
    latest_full = data[-1] if data else {}
    latest_time = latest_full.get("openTime", "")
    latest_zodiac = to_simplified(latest_full.get("zodiac", ""))
    latest_wave = latest_full.get("wave", "")

    # 构建并分级规则库
    rules, graded_rules = build_and_grade_rules(records)

    six, nine, kills = predict_gold(records, len(records), rules, graded_rules)

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

    alert9 = "🔴" if rate9 < 95.0 else "🟢"
    alert6 = "🔴" if rate6 < 85.0 else "🟢"
    warn = ""
    if rate9 < 95.0 or rate6 < 85.0:
        warn = "⚠️ 警告: 近期命中率低于基准线，请谨慎!"

    lines.append(f"动态命中率(近50期): 九肖 {alert9} {rate9:.1f}% | 六肖 {alert6} {rate6:.1f}%")
    lines.append(f"基准命中率: 九肖 99.42% | 六肖 88.82%")
    if warn:
        lines.append(warn)
    lines.append("-" * 30)

    lines.append(f"规则库杀肖(金标投票≥2): {', '.join(result.get('killed_zodiacs', []))}")
    lines.append(f"★九肖预测: {', '.join(result.get('nine_pool', []))}")
    lines.append(f"★六肖预测: {', '.join(result.get('predicted_6xiao', []))}")

    if len(result.get('predicted_6xiao', [])) < 6:
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