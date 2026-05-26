#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reference_96.py —— 多信号评分参考版（无未来函数）
============================================================
核心逻辑：
  1. 规则库构建与分级仅使用前1500期训练数据（前1300建，1301-1500验）
  2. L3规则仅从训练集提取
  3. 多信号评分：遗漏值分段 + 金标投票 + 冷却 + 平五窗口 + 合冲归属
  4. 参数固定，不随数据增加而漂移

在集成投票中的角色：提供多信号评分的独立观点。
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
from shx_suishu import get_shengxiao_by_suima, SHENGXIAO, to_simplified

ZODIAC = SHENGXIAO
POS_NAMES = ["平一", "平二", "平三", "平四", "平五", "平六", "特码"]

# ========== 参数（固定） ==========
OFFSETS = list(range(-11, 0)) + [0] + list(range(1, 12))
MIN_SAMPLES = 5
MIN_KILL_RATE = 95.0
MAX_STREAK = 1

MISSING_WEIGHTS = (1.0, 2.0, 3.0)
MISSING_THRESH = (8, 20)
GOLD_PENS = [3, 8, 15, 30]
COOL_PENS = [10, 5, 2]
L3_WEIGHT = 5
FIXED_WEIGHT = 15
TE_WEIGHT = 10
PING5_WEIGHT = 10
HECHONG_WEIGHT = 8
CROSS_WEIGHT = 0
USE_REPLACE = False
COOL_WINDOW = 3
L3_MIN_RATE = 93.0

SAN_HE = {"马":["虎","狗"],"羊":["兔","猪"],"猴":["鼠","龙"],"鸡":["蛇","牛"],"狗":["虎","马"],"猪":["兔","羊"],"鼠":["猴","龙"],"牛":["蛇","鸡"],"虎":["马","狗"],"兔":["猪","羊"],"龙":["鼠","猴"],"蛇":["鸡","牛"]}
LIU_HE = {"马":"羊","羊":"马","猴":"蛇","蛇":"猴","鸡":"龙","龙":"鸡","狗":"兔","兔":"狗","猪":"虎","虎":"猪","鼠":"牛","牛":"鼠"}
CHONG = {"马":"鼠","羊":"牛","猴":"虎","鸡":"兔","狗":"龙","猪":"蛇","鼠":"马","牛":"羊","虎":"猴","兔":"鸡","龙":"狗","蛇":"猪"}

OUTPUT_DIR = os.path.join(BASE_DIR, "max记录")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "参考.txt")

_CACHED_RULES = None
_CACHED_GRADED = None
_CACHED_L3 = None


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


def build_fixed_rules(records):
    """训练集构建规则并分级，缓存后不再变动"""
    global _CACHED_RULES, _CACHED_GRADED, _CACHED_L3
    if _CACHED_RULES is not None:
        return _CACHED_RULES, _CACHED_GRADED, _CACHED_L3

    total = len(records)
    if total < 1500:
        split = int(total * 0.8)
        train = records[:split]
        val = records[split:]
    else:
        train = records[:1300]
        val = records[1300:1500]

    stats = {}
    for sx in ZODIAC:
        stats[sx] = {}
        for pos_name in POS_NAMES:
            stats[sx][pos_name] = {}
    for i in range(len(train) - 1):
        curr, nxt = train[i], train[i + 1]
        curr_sx, year, nxt_sx = curr["te_sx"], curr["year"], nxt["te_sx"]
        for pos_idx, pos_name in enumerate(POS_NAMES):
            num = curr["ping_nums"][pos_idx] if pos_idx < 6 else curr["te_num"]
            trigger_sx = get_shengxiao_by_suima(num, year)
            for off in OFFSETS:
                new_num = offset_num(num, off)
                result_sx = get_shengxiao_by_suima(new_num, year)
                full_key = (off, trigger_sx, result_sx)
                if trigger_sx not in stats[curr_sx][pos_name]:
                    stats[curr_sx][pos_name][trigger_sx] = {}
                if full_key not in stats[curr_sx][pos_name][trigger_sx]:
                    stats[curr_sx][pos_name][trigger_sx][full_key] = {"total": 0, "hit": 0}
                stats[curr_sx][pos_name][trigger_sx][full_key]["total"] += 1
                if result_sx != nxt_sx:
                    stats[curr_sx][pos_name][trigger_sx][full_key]["hit"] += 1

    rules = {}
    for sx in ZODIAC:
        rules[sx] = {}
        for pos_name in POS_NAMES:
            rules[sx][pos_name] = {}
            for trigger_sx in stats[sx][pos_name]:
                for (off, _, killed_sx), v in stats[sx][pos_name][trigger_sx].items():
                    if v["total"] < MIN_SAMPLES: continue
                    raw_rate = v["hit"] / v["total"] * 100
                    if raw_rate < MIN_KILL_RATE: continue
                    max_streak, cur = 0, 0
                    pos_idx = POS_NAMES.index(pos_name)
                    for j in range(len(train) - 1):
                        if train[j]["te_sx"] != sx: continue
                        num_j = train[j]["ping_nums"][pos_idx] if pos_idx < 6 else train[j]["te_num"]
                        if get_shengxiao_by_suima(num_j, train[j]["year"]) != trigger_sx: continue
                        if train[j + 1]["te_sx"] == killed_sx:
                            cur += 1; max_streak = max(max_streak, cur)
                        else: cur = 0
                    if max_streak > MAX_STREAK: continue
                    if trigger_sx not in rules[sx][pos_name]:
                        rules[sx][pos_name][trigger_sx] = []
                    rules[sx][pos_name][trigger_sx].append((off, killed_sx, raw_rate, v["total"], max_streak))
    for sx in rules:
        for pos_name in rules[sx]:
            for trigger_sx in rules[sx][pos_name]:
                rules[sx][pos_name][trigger_sx].sort(key=lambda x: x[2], reverse=True)

    graded = {}
    for sx in rules:
        for pos_name in rules[sx]:
            pos_idx = POS_NAMES.index(pos_name)
            for trigger_sx in rules[sx][pos_name]:
                for (off, killed_sx, raw_rate, samples, ts) in rules[sx][pos_name][trigger_sx]:
                    thits, ttotal, tstreak, tmax = 0, 0, 0, 0
                    for j in range(len(val) - 1):
                        if val[j]["te_sx"] != sx: continue
                        num_j = val[j]["ping_nums"][pos_idx] if pos_idx < 6 else val[j]["te_num"]
                        if get_shengxiao_by_suima(num_j, val[j]["year"]) != trigger_sx: continue
                        ttotal += 1
                        if val[j + 1]["te_sx"] != killed_sx:
                            thits += 1; tstreak = 0
                        else:
                            tstreak += 1; tmax = max(tmax, tstreak)
                    trate = thits / ttotal * 100 if ttotal > 0 else 0
                    grade = 'discard'
                    if ttotal == 0: pass
                    elif trate == 100.0 and tmax == 0: grade = 'gold'
                    elif trate >= 95.0 and tmax <= 1: grade = 'silver'
                    elif trate >= 93.0 and tmax <= 2: grade = 'bronze'
                    graded[(sx, pos_name, trigger_sx, off, killed_sx)] = {
                        'offset': off, 'killed_sx': killed_sx,
                        'grade': grade, 'test_rate': trate,
                        'samples': samples, 'test_total': ttotal
                    }

    def extract_l3_from_train(train_records):
        POS_NAMES_L3 = ['平一', '平二', '平三', '平四', '平五', '平六']
        stats_l3 = defaultdict(lambda: {'total': 0, 'hit': 0})
        for i in range(len(train_records) - 1):
            curr, nxt = train_records[i], train_records[i+1]
            cy = curr["year"]
            nxt_sx = nxt["te_sx"]
            for idx, pos in enumerate(POS_NAMES_L3):
                ping_num = curr["ping_nums"][idx]
                ping_sx = get_shengxiao_by_suima(ping_num, cy)
                for offset in range(1, 12):
                    for dr, sign in [('+', 1), ('-', -1)]:
                        new_num = ping_num + sign * offset
                        if new_num > 49: new_num -= 49
                        elif new_num < 1: new_num += 49
                        new_sx = get_shengxiao_by_suima(new_num, cy)
                        key = (pos, dr, offset, ping_sx, new_sx)
                        stats_l3[key]['total'] += 1
                        if new_sx != nxt_sx: stats_l3[key]['hit'] += 1
        rules_l3 = []
        for (pos, dr, offset, ping_sx, killed_sx), v in stats_l3.items():
            if v['total'] >= 30:
                hit_rate = round(v['hit'] / v['total'] * 100, 2)
                if hit_rate >= L3_MIN_RATE:
                    rules_l3.append({
                        '位置': pos, '偏移': f'{dr}{offset}', '平码生肖': ping_sx,
                        '所得生肖': killed_sx, '命中率': hit_rate, '样本量': v['total']
                    })
        if rules_l3:
            avg_samples = sum(r['样本量'] for r in rules_l3) / len(rules_l3)
            return [r for r in rules_l3 if r['样本量'] >= avg_samples]
        return []

    l3_rules = extract_l3_from_train(train)
    _CACHED_RULES = rules
    _CACHED_GRADED = graded
    _CACHED_L3 = l3_rules
    return rules, graded, l3_rules


def predict_gold(records, up_to, rules, graded, l3_good):
    curr = records[up_to - 1]
    cur_sx = curr["te_sx"]
    year = curr["year"]

    gold_votes = Counter()
    te_kill_set = set()
    if cur_sx in rules:
        for pos_idx, pos_name in enumerate(POS_NAMES):
            if pos_name not in rules[cur_sx]: continue
            asx = curr["ping_sx"][pos_idx] if pos_idx < 6 else cur_sx
            if asx not in rules[cur_sx][pos_name]: continue
            for (off, killed, _, _, _) in rules[cur_sx][pos_name][asx]:
                gi = graded.get((cur_sx, pos_name, asx, off, killed))
                if not gi: continue
                if gi['grade'] == 'gold':
                    gold_votes[killed] += 1
                if pos_name == "特码" and gi['grade'] == 'gold':
                    te_kill_set.add(killed)

    fixed_kill_set = set()
    p2_num = curr["ping_nums"][1]
    fixed_kill_set.add(get_shengxiao_by_suima(offset_num(p2_num, 3), year))
    fixed_kill_set.add(cur_sx)

    missing = {}
    for s in ZODIAC:
        streak = 0
        for i in range(up_to - 1, -1, -1):
            if records[i]["te_sx"] != s: streak += 1
            else: break
        missing[s] = streak

    l3_kill_set = set()
    for rule in l3_good:
        pos_idx = POS_NAMES.index(rule['位置']) if rule['位置'] in POS_NAMES else -1
        if pos_idx < 0: continue
        actual_sx = curr["ping_sx"][pos_idx] if pos_idx < 6 else cur_sx
        if actual_sx == rule['平码生肖']:
            l3_kill_set.add(rule['所得生肖'])

    cool_map = {}
    for dist in range(1, COOL_WINDOW + 1):
        if up_to - dist >= 0:
            sx = records[up_to - dist]["te_sx"]
            pen = COOL_PENS[dist - 1]
            if sx not in cool_map or pen > cool_map[sx]:
                cool_map[sx] = pen

    oracle_pool = set()
    if PING5_WEIGHT > 0:
        ping5 = curr["ping_nums"][4]
        center_num = (ping5 - 1 + 8) % 49 + 1
        center_sx = get_shengxiao_by_suima(center_num, year)
        center_idx = ZODIAC.index(center_sx)
        oracle_pool = set(ZODIAC[(center_idx + i) % 12] for i in range(-4, 5))
        if USE_REPLACE and len(oracle_pool) < 12:
            outside = [s for s in ZODIAC if s not in oracle_pool]
            best_out = max(outside, key=lambda s: missing[s])
            worst_in = min(oracle_pool, key=lambda s: missing[s])
            if missing[best_out] > missing[worst_in]:
                oracle_pool.discard(worst_in)
                oracle_pool.add(best_out)

    hechong_pool = set()
    if HECHONG_WEIGHT > 0:
        hechong_pool.add(cur_sx)
        for s in SAN_HE.get(cur_sx, []): hechong_pool.add(s)
        hechong_pool.add(LIU_HE.get(cur_sx, ""))
        chong_sx = CHONG.get(cur_sx, "")
        hechong_pool.add(chong_sx)
        for s in SAN_HE.get(chong_sx, []): hechong_pool.add(s)
        hechong_pool.add(LIU_HE.get(chong_sx, ""))

    cross_bonus = Counter()
    if CROSS_WEIGHT > 0:
        W = 30
        freq = defaultdict(int)
        start = max(0, up_to - W)
        for i in range(start, up_to - 1):
            prev_curr = records[i]
            for pos_idx in range(6):
                freq[(prev_curr["te_sx"], prev_curr["ping_nums"][pos_idx] % 10)] += 1
        for pos_idx in range(6):
            cnt = freq.get((cur_sx, curr["ping_nums"][pos_idx] % 10), 0)
            cross_bonus[curr["ping_sx"][pos_idx]] += -cnt * CROSS_WEIGHT

    scores = {}
    for s in ZODIAC:
        m = missing.get(s, 0)
        if m >= MISSING_THRESH[1]:
            score = m * MISSING_WEIGHTS[2]
        elif m >= MISSING_THRESH[0]:
            score = m * MISSING_WEIGHTS[1]
        else:
            score = m * MISSING_WEIGHTS[0]

        v = gold_votes.get(s, 0)
        if v >= 4: score -= GOLD_PENS[3]
        elif v == 3: score -= GOLD_PENS[2]
        elif v == 2: score -= GOLD_PENS[1]
        elif v == 1: score -= GOLD_PENS[0]

        if s in fixed_kill_set: score -= FIXED_WEIGHT
        if s in te_kill_set: score -= TE_WEIGHT
        if s in l3_kill_set: score -= L3_WEIGHT
        score -= cool_map.get(s, 0)
        if s in oracle_pool: score += PING5_WEIGHT
        if s in hechong_pool: score += HECHONG_WEIGHT
        score += cross_bonus.get(s, 0)
        scores[s] = score

    sorted_all = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    nine = [s for s, _ in sorted_all[:9]]
    six = sorted(nine, key=lambda s: scores.get(s, 0), reverse=True)[:6]

    return six, nine, gold_votes, missing, scores, fixed_kill_set, te_kill_set, l3_kill_set, oracle_pool, hechong_pool


def output_text(latest_record, next_qihao, six, nine, gold_votes, missing, scores,
                fixed_kill_set, te_kill_set, l3_kill_set, oracle_pool, hechong_pool):
    lines = []
    lines.append(f"MAX严格验证参考版 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 50)
    lines.append(f"基于期号: {latest_record['qishu']}")
    lines.append(f"开奖号码: {','.join(str(n) for n in latest_record['ping_nums'])},特{latest_record['te_num']}")
    lines.append(f"本期特肖: {latest_record['te_sx']} (尾{latest_record['te_wei']})")
    lines.append(f"预测下期: {next_qihao}")
    lines.append("-" * 30)
    lines.append(f"[信号源]")
    lines.append(f"  固定杀肖: {', '.join(fixed_kill_set)}")
    lines.append(f"  特码金标杀肖: {', '.join(te_kill_set)}")
    lines.append(f"  L3优质杀肖(训练集提取): {', '.join(l3_kill_set) if l3_kill_set else '无'}")
    lines.append(f"  平五+8窗口: {', '.join(oracle_pool)}")
    lines.append(f"  合冲池: {', '.join(hechong_pool)}")
    lines.append(f"  金标高风险(≥2票): {', '.join([s for s,v in gold_votes.items() if v >= 2])}")
    lines.append("-" * 30)
    lines.append(f"[详细数据]")
    lines.append(f"  完整金标得票: {dict(sorted(gold_votes.items(), key=lambda x: x[1]))}")
    lines.append(f"  前9遗漏值: {', '.join([f'{s}({v})' for s,v in sorted(missing.items(), key=lambda x: x[1], reverse=True)[:9]])}")
    lines.append("-" * 30)
    lines.append(f"★九肖预测: {', '.join(nine)}")
    lines.append(f"★六肖预测: {', '.join(six)}")
    lines.append("=" * 50)
    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", action="store_true", help="保存到本地TXT")
    args = parser.parse_args()

    data = load_all_data(auto_update=False)
    records = extract_records(data)
    if len(records) < 50:
        print("数据不足")
        return

    rules, graded, l3_good = build_fixed_rules(records)

    latest = records[-1]
    next_qihao = ""
    try:
        exp = latest["qishu"]
        if len(exp) >= 4:
            next_qihao = f"{exp[:4]}{int(exp[-3:]) + 1:03d}"
    except:
        pass

    six, nine, gold_votes, missing, scores, fixed_kill_set, te_kill_set, l3_kill_set, oracle_pool, hechong_pool = \
        predict_gold(records, len(records), rules, graded, l3_good)

    text = output_text(latest, next_qihao, six, nine, gold_votes, missing, scores,
                       fixed_kill_set, te_kill_set, l3_kill_set, oracle_pool, hechong_pool)
    print(text)

    if args.output:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        existing = ""
        if os.path.exists(OUTPUT_FILE):
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                existing = f.read()
        issue = latest["qishu"]
        if f"基于期号: {issue}" not in existing:
            with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
                f.write("\n" + text + "\n")
            print(f"[OK] 已保存到 {OUTPUT_FILE}")
        else:
            print(f"[SKIP] 期号 {issue} 已有记录，跳过保存")


if __name__ == "__main__":
    main()