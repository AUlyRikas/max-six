#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core_update_rules.py — 特肖动态杀肖规则库 更新脚本
============================================================
用途：每次数据更新后运行，重新提取≥95%+连错≤1的规则
用法：
  python core_update_rules.py
  → 输出 d:\lottery_ai\特肖杀肖规则库.json
============================================================
"""
import json, os, sys
from collections import defaultdict, Counter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MARK6_DIR = os.path.join(BASE_DIR, "mark6") if os.path.exists(os.path.join(BASE_DIR, "mark6")) else BASE_DIR
if MARK6_DIR not in sys.path: sys.path.insert(0, MARK6_DIR)

from shuju_loader import load_all_data
from shx_suishu import get_shengxiao_by_suima, SHENGXIAO

ZODIAC = SHENGXIAO
POS_NAMES = ["平一", "平二", "平三", "平四", "平五", "平六", "特码"]
OUTPUT_PATH = os.path.join(BASE_DIR, "特肖杀肖规则库.json")

MIN_SAMPLES = 5
MIN_KILL_RATE = 95.0
MAX_STREAK = 1


def offset_num(num, offset):
    return (num - 1 + offset) % 49 + 1


def build_rules(records, min_samples=MIN_SAMPLES, min_rate=MIN_KILL_RATE, max_streak=MAX_STREAK):
    stats = defaultdict(lambda: defaultdict(lambda: {"total": 0, "hit": 0, "result_sx": None}))

    for i in range(len(records) - 1):
        curr, nxt = records[i], records[i + 1]
        curr_sx = curr["te_sx"]
        year = curr["year"]
        nxt_sx = nxt["te_sx"]

        for pos_idx, pos_name in enumerate(POS_NAMES):
            num = curr["ping_nums"][pos_idx] if pos_idx < 6 else curr["te_num"]
            trigger_sx = get_shengxiao_by_suima(num, year)

            for off in range(12):
                new_num = offset_num(num, off)
                result_sx = get_shengxiao_by_suima(new_num, year)
                key = (pos_name, off, trigger_sx)
                stats[curr_sx][key]["total"] += 1
                stats[curr_sx][key]["result_sx"] = result_sx
                if result_sx != nxt_sx:
                    stats[curr_sx][key]["hit"] += 1

    rules = {}
    for sx in ZODIAC:
        if sx not in stats:
            continue
        rules[sx] = {}
        for (pos_name, off, trigger_sx), v in stats[sx].items():
            if v["total"] < min_samples:
                continue
            kill_rate = v["hit"] / v["total"] * 100
            if kill_rate < min_rate:
                continue

            max_streak_found = 0
            cur_streak = 0
            for i in range(len(records) - 1):
                if records[i]["te_sx"] != sx:
                    continue
                year_i = records[i]["year"]
                pos_idx = POS_NAMES.index(pos_name)
                num = records[i]["ping_nums"][pos_idx] if pos_idx < 6 else records[i]["te_num"]
                actual_sx = get_shengxiao_by_suima(num, year_i)
                if actual_sx != trigger_sx:
                    continue

                killed_sx = get_shengxiao_by_suima(offset_num(num, off), year_i)
                if records[i + 1]["te_sx"] == killed_sx:
                    cur_streak += 1
                    max_streak_found = max(max_streak_found, cur_streak)
                else:
                    cur_streak = 0

            if max_streak_found > max_streak:
                continue

            if pos_name not in rules[sx]:
                rules[sx][pos_name] = {}
            if trigger_sx not in rules[sx][pos_name]:
                rules[sx][pos_name][trigger_sx] = []

            rules[sx][pos_name][trigger_sx].append(
                (off, v["result_sx"], round(kill_rate, 2), v["total"], max_streak_found)
            )

    for sx in rules:
        for pos in rules[sx]:
            for tri in rules[sx][pos]:
                rules[sx][pos][tri].sort(key=lambda x: x[2], reverse=True)

    return rules


def main():
    print("=" * 55)
    print("core_update_rules.py — 规则库更新")
    print("=" * 55)

    print("加载数据...")
    data = load_all_data(auto_update=False)
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
            })
        except: continue
    records.sort(key=lambda x: int(x["qishu"]))
    print(f"记录数: {len(records)}")

    print("提取规则...")
    rules = build_rules(records)

    # 备份旧文件
    if os.path.exists(OUTPUT_PATH):
        backup = OUTPUT_PATH + ".bak"
        os.replace(OUTPUT_PATH, backup)
        print(f"已备份旧规则库 → {backup}")

    # 保存
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)

    print(f"✅ 已保存: {OUTPUT_PATH}")
    total_rules = sum(
        len(rules[sx][pos][tri])
        for sx in rules for pos in rules[sx] for tri in rules[sx][pos]
    )
    print(f"   {len(rules)}个生肖, {total_rules}条规则")
    for sx in rules:
        cnt = sum(len(rules[sx][p][t]) for p in rules[sx] for t in rules[sx][p])
        print(f"   {sx}: {len(rules[sx])}个位置, {cnt}条规则")

    # ===== 预警 =====
    if os.path.exists(OUTPUT_PATH + ".bak"):
        with open(OUTPUT_PATH + ".bak", 'r', encoding='utf-8') as f:
            old_rules = json.load(f)
        old_total = sum(len(old_rules[sx][p][t]) for sx in old_rules for p in old_rules[sx] for t in old_rules[sx][p])
        change = (total_rules - old_total) / old_total * 100 if old_total > 0 else 0

        print(f"\n[规则库变化]")
        print(f"  上次: {old_total}条 → 本次: {total_rules}条 ({change:+.1f}%)")

        for sx in ZODIAC:
            old_cnt = sum(len(old_rules.get(sx,{}).get(p,{}).get(t,[])) for p in old_rules.get(sx,{}) for t in old_rules.get(sx,{}).get(p,{}))
            new_cnt = sum(len(rules.get(sx,{}).get(p,{}).get(t,[])) for p in rules.get(sx,{}) for t in rules.get(sx,{}).get(p,{}))
            if old_cnt > 0:
                sx_change = (new_cnt - old_cnt) / old_cnt * 100
                flag = "🔴" if sx_change <= -30 else "⚠️" if sx_change <= -15 else "✅"
                print(f"  {flag} {sx}: {old_cnt}→{new_cnt}条 ({sx_change:+.1f}%)")
            elif new_cnt == 0:
                print(f"  🔴 {sx}: 无规则!")

        if total_rules == 0:
            print(f"\n🔴🔴🔴 警告: 规则库为空!")

    for sx in ZODIAC:
        cnt = sum(len(rules.get(sx,{}).get(p,{}).get(t,[])) for p in rules.get(sx,{}) for t in rules.get(sx,{}).get(p,{}))
        if cnt < 5:
            print(f"🔴 {sx}: 规则不足5条({cnt}条)，覆盖不足!")

    print(f"\n===== 更新完成 =====")


if __name__ == "__main__":
    main()