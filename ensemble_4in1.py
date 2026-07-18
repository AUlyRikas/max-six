#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ensemble_4in1.py —— 四合一集成投票生产引擎（v4.2 增强版 · 非线性安全分+不等权投票）
============================================================
集成模型：
  M1 (oracle_core)      — 平五+8九肖池 + F5六肖排序（固定）
  R96 (reference_96)    — 反向金标惩罚+冷却+平五窗口+合冲池
  MAX (core_max)        — 金标规则库反向投票（权重1.5）
  P54 (predict_54)      — 54条固化围肖信号等权投票

核心优化（移植自NV版）：
  1. MAX投票权重提升至1.5，打破票数扁平化
  2. 非线性安全分惩罚：被杀≥2次的生肖安全分×3，压制连错
  3. 五四三肖独立排序，使用惩罚安全分
  4. R96使用旧规则库优化参数 GOLD_SCALE=2.5, COOL_WINDOW=2

验证：2000期训练+249期独立测试
  九肖95.18%连错2期 | 六肖83.87%连错3期 | 16码62.25%连错4期

用法：
  python ensemble_4in1.py                  → 屏幕输出预测
  python ensemble_4in1.py --output         → 预测+保存JS/TXT+校验上期
  python ensemble_4in1.py --verify         → 仅校验上期命中
  python ensemble_4in1.py --test           → 回测验证
============================================================
"""
import json, os, sys
from collections import Counter
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MARK6_DIR = os.path.join(BASE_DIR, "mark6")
if os.path.exists(MARK6_DIR) and MARK6_DIR not in sys.path:
    sys.path.insert(0, MARK6_DIR)

from shuju_loader import load_all_data
from shx_suishu import get_shengxiao_by_suima, SHENGXIAO, get_suima_by_shengxiao, to_simplified

ZODIAC = SHENGXIAO
POS_NAMES = ["平一", "平二", "平三", "平四", "平五", "平六", "特码"]
OFFSETS = list(range(-11,0)) + [0] + list(range(1,12))

SAN_HE = {"马":["虎","狗"],"羊":["兔","猪"],"猴":["鼠","龙"],"鸡":["蛇","牛"],"狗":["虎","马"],"猪":["兔","羊"],"鼠":["猴","龙"],"牛":["蛇","鸡"],"虎":["马","狗"],"兔":["猪","羊"],"龙":["鼠","猴"],"蛇":["鸡","牛"]}
LIU_HE = {"马":"羊","羊":"马","猴":"蛇","蛇":"猴","鸡":"龙","龙":"鸡","狗":"兔","兔":"狗","猪":"虎","虎":"猪","鼠":"牛","牛":"鼠"}
CHONG = {"马":"鼠","羊":"牛","猴":"虎","鸡":"兔","狗":"龙","猪":"蛇","鼠":"马","牛":"羊","虎":"猴","兔":"鸡","龙":"狗","蛇":"猪"}

RULES_PATH = os.path.join(BASE_DIR, "特肖杀肖规则库.json")
TRACK_DIR = os.path.join(BASE_DIR, "oracle记录")
TRACK_FILE = os.path.join(TRACK_DIR, "hit_track.json")

TAIL_TABLE = {
    "马": [0,1,2,3,4,7,8], "羊": [1,2,3,4,6,7,8], "猴": [1,2,4,5,6,8,9],
    "鸡": [0,2,3,4,6,8,9], "狗": [0,1,2,3,5,6,7], "猪": [1,3,4,5,6,7,8],
    "鼠": [0,1,3,4,6,7,9], "牛": [0,1,3,5,6,7,8], "虎": [1,4,5,6,7,8,9],
    "兔": [0,1,2,3,4,6,8], "龙": [0,1,2,3,4,5,6], "蛇": [1,2,3,4,6,7,8],
}

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

def offset_num(num, off): return (num - 1 + off) % 49 + 1
def get_window(center_sx, r):
    idx = ZODIAC.index(center_sx)
    return [ZODIAC[(idx + i) % 12] for i in range(-r, r + 1)]

def extract_records(data):
    records = []
    for item in data:
        try:
            qs = str(item.get("expect", "")); oc = str(item.get("openCode", ""))
            ot = item.get("openTime", "")
            year = int(ot[:4]) if ot else (int(qs[:4]) if len(qs) >= 4 else 2026)
            if not qs or not oc: continue
            parts = oc.strip().split(",")
            if len(parts) != 7: continue
            nums = [int(p.strip()) for p in parts]
            records.append({"qishu": qs, "year": year, "te_num": nums[6],
                "te_sx": get_shengxiao_by_suima(nums[6], year), "te_wei": nums[6]%10, "te_tail": nums[6]%10,
                "ping_nums": nums[:6], "ping_sx": [get_shengxiao_by_suima(n, year) for n in nums[:6]]})
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

def get_hechong_full(sx):
    pool = set(); pool.add(sx)
    for s in SAN_HE.get(sx, []): pool.add(s)
    pool.add(LIU_HE.get(sx, "")); ch = CHONG.get(sx, ""); pool.add(ch)
    for s in SAN_HE.get(ch, []): pool.add(s); pool.add(LIU_HE.get(ch, ""))
    return pool

def streak_stats(hit_list):
    total = len(hit_list); hits = sum(1 for h in hit_list if h)
    rate = hits / total * 100 if total else 0
    streak = 0; ms = 0; dist = Counter()
    for h in hit_list:
        if not h: streak += 1; ms = max(ms, streak)
        else:
            if streak > 0: dist[streak] += 1; streak = 0
    if streak > 0: dist[streak] += 1
    return rate, ms, dist

def load_hit_track():
    if not os.path.exists(TRACK_FILE): return []
    with open(TRACK_FILE, 'r', encoding='utf-8') as f: return json.load(f)

def save_hit_track(track):
    os.makedirs(TRACK_DIR, exist_ok=True)
    with open(TRACK_FILE, 'w', encoding='utf-8') as f: json.dump(track, f, ensure_ascii=False, indent=2)

def verify_last_prediction(records):
    track = load_hit_track()
    if not track:
        print("[Ensemble] 暂无历史预测记录，跳过校验")
        return track
    last = track[-1]
    if last.get("hit9", -1) != -1 and last.get("hit6", -1) != -1: return track
    predicted_issue = last.get("issue", "")
    actual_sx = None
    for r in records:
        if r["qishu"] == predicted_issue: actual_sx = r["te_sx"]; break
    if actual_sx is None: return track
    last["hit9"] = 1 if actual_sx in last.get("nine", []) else 0
    last["hit6"] = 1 if actual_sx in last.get("six", []) else 0
    track[-1] = last
    save_hit_track(track)
    hit9_str = "✓" if last["hit9"] else "✗"
    hit6_str = "✓" if last["hit6"] else "✗"
    print(f"[Ensemble] 上期{predicted_issue}已校验: 九肖{hit9_str} 六肖{hit6_str}")
    return track

def append_prediction_to_track(issue, nine, six):
    track = load_hit_track()
    track.append({"issue": issue, "nine": nine, "six": six, "hit9": -1, "hit6": -1,
                  "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
    if len(track) > 100: track = track[-100:]
    save_hit_track(track)
    return track

def calc_dynamic_rate(window=50):
    track = load_hit_track()
    valid = [t for t in track if t.get("hit9", -1) >= 0][-window:]
    if not valid: return 0, 0, 0, 0
    hits9 = sum(t["hit9"] for t in valid); hits6 = sum(t["hit6"] for t in valid)
    total = len(valid)
    return hits9 / total * 100, hits6 / total * 100, hits9, hits6

# ==================== 增强版四合一核心 ====================
def ensemble_vote(records):
    hist = records[:]
    prev = hist[-1]; year = prev["year"]
    cur_sx = prev["te_sx"]
    missing = compute_missing(hist, len(hist))

    rules_gold = {}
    if os.path.exists(RULES_PATH):
        with open(RULES_PATH, 'r', encoding='utf-8') as f:
            rules_gold = json.load(f)

    # M1
    ping5 = prev["ping_nums"][4]
    cn = (ping5 - 1 + 8) % 49 + 1
    csx = get_shengxiao_by_suima(cn, year)
    cidx = ZODIAC.index(csx)
    m1_nine = [ZODIAC[(cidx + i) % 12] for i in range(-4, 5)]

    # R96
    GOLD_SCALE = 2.5
    COOL_WINDOW = 2
    GOLD_PENS = [3, 8, 15, 30]
    r96_nine = []
    if rules_gold:
        gold_votes_r96 = Counter()
        te_kill_set = set()
        for rule_key, info in rules_gold.items():
            if info.get('grade') != 'gold': continue
            parts = rule_key.split('|')
            if len(parts) != 5: continue
            sx_rule, pos_name, trigger_sx, off_str, killed_sx = parts
            if sx_rule != cur_sx: continue
            pos_idx = POS_NAMES.index(pos_name) if pos_name in POS_NAMES else -1
            if pos_idx < 0: continue
            asx = prev["ping_sx"][pos_idx] if pos_idx < 6 else cur_sx
            if asx != trigger_sx: continue
            gold_votes_r96[killed_sx] += 1
            if pos_name == "特码": te_kill_set.add(killed_sx)

        cool_map = {}
        for dist in range(1, COOL_WINDOW + 1):
            if len(hist) - dist >= 0:
                sx = hist[-dist]["te_sx"]
                pen = [10, 5][dist - 1]
                if sx not in cool_map or pen > cool_map[sx]:
                    cool_map[sx] = pen

        oracle_pool = set()
        ping5_r96 = prev["ping_nums"][4]
        center_num_r96 = (ping5_r96 - 1 + 8) % 49 + 1
        center_sx_r96 = get_shengxiao_by_suima(center_num_r96, year)
        cidx_r96 = ZODIAC.index(center_sx_r96)
        oracle_pool = set(ZODIAC[(cidx_r96 + i) % 12] for i in range(-4, 5))

        hechong_pool = get_hechong_full(cur_sx)

        scores = {}
        for s in ZODIAC:
            score = missing.get(s, 0)
            v = gold_votes_r96.get(s, 0)
            if v >= 4: score -= int(GOLD_PENS[3] * GOLD_SCALE)
            elif v == 3: score -= int(GOLD_PENS[2] * GOLD_SCALE)
            elif v == 2: score -= int(GOLD_PENS[1] * GOLD_SCALE)
            elif v == 1: score -= int(GOLD_PENS[0] * GOLD_SCALE)
            if s in te_kill_set: score -= 10
            score -= cool_map.get(s, 0)
            if s in oracle_pool: score += 10
            if s in hechong_pool: score += 8
            scores[s] = score
        r96_nine = [s for s, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:9]]
    else:
        r96_nine = sorted(ZODIAC, key=lambda s: missing.get(s, 0), reverse=True)[:9]

    # MAX
    max_nine = []
    if rules_gold:
        gold_votes_max = Counter()
        for pidx, pn in enumerate(POS_NAMES):
            num = prev["te_num"] if pn == "特码" else prev["ping_nums"][pidx]
            tsx = prev["te_sx"] if pn == "特码" else prev["ping_sx"][pidx]
            for off in OFFSETS:
                new_num = offset_num(num, off)
                killed = get_shengxiao_by_suima(new_num, year)
                rule_key = f"{cur_sx}|{pn}|{tsx}|{off}|{killed}"
                if rule_key in rules_gold and rules_gold[rule_key].get('grade') == 'gold':
                    gold_votes_max[rules_gold[rule_key]['killed_sx']] += 1
        killed_set = set(s for s, v in gold_votes_max.items() if v >= 2)
        safe_m = [s for s in ZODIAC if s not in killed_set]
        max_nine = sorted(safe_m, key=lambda s: missing.get(s, 0), reverse=True)[:9]
    else:
        max_nine = sorted(ZODIAC, key=lambda s: missing.get(s, 0), reverse=True)[:9]

    # P54
    if cur_sx in SIGNALS_GOOD:
        vc = Counter()
        for pos, stype, off, r in SIGNALS_GOOD[cur_sx]:
            pos_idx = POS_NAMES.index(pos)
            num = prev["te_num"] if pos == "特码" else prev["ping_nums"][pos_idx]
            sx = prev["te_sx"] if pos == "特码" else prev["ping_sx"][pos_idx]
            if stype == "号码":
                c = get_shengxiao_by_suima(offset_num(num, off), year)
            else:
                sx_idx = ZODIAC.index(sx)
                c = ZODIAC[(sx_idx + off) % 12]
            w = get_window(c, r)
            for s in w: vc[s] += 1
        ranked_p54 = sorted(vc.items(), key=lambda x: (-x[1], -missing.get(x[0], 0)))
        p54_nine = [s for s, _ in ranked_p54[:9]]
    else:
        p54_nine = sorted(ZODIAC, key=lambda s: missing.get(s, 0), reverse=True)[:9]

    # 不等权投票
    rank_scores = Counter()
    votes = Counter()
    for nine, w in [(m1_nine, 1.0), (r96_nine, 1.0), (max_nine, 1.5), (p54_nine, 1.0)]:
        for rank, s in enumerate(nine):
            if rank < 3: rank_scores[s] += 9 * w
            elif rank < 6: rank_scores[s] += 3 * w
            else: rank_scores[s] += 1 * w
            votes[s] += w

    # 安全分（含非线性惩罚）
    raw_safety = Counter()
    if rules_gold:
        for pidx, pn in enumerate(POS_NAMES):
            num = prev["te_num"] if pn == "特码" else prev["ping_nums"][pidx]
            tsx = prev["te_sx"] if pn == "特码" else prev["ping_sx"][pidx]
            for off in OFFSETS:
                new_num = offset_num(num, off)
                killed = get_shengxiao_by_suima(new_num, year)
                rule_key = f"{cur_sx}|{pn}|{tsx}|{off}|{killed}"
                if rule_key in rules_gold and rules_gold[rule_key].get('grade') == 'gold':
                    raw_safety[rules_gold[rule_key]['killed_sx']] += 1
    penalized_safety = {}
    for s in ZODIAC:
        raw = raw_safety.get(s, 0)
        if raw >= 2:
            penalized_safety[s] = raw * 3
        else:
            penalized_safety[s] = raw

    hc = get_hechong_full(cur_sx)

    # 九肖
    nine_ranked = sorted(votes.items(), key=lambda x: (
        -x[1], -rank_scores.get(x[0], 0), -(1 if x[0] in hc else 0), -missing.get(x[0], 0)
    ))
    nine_sx = [s for s, _ in nine_ranked[:9]]

    # 六肖
    six_ranked = sorted(votes.items(), key=lambda x: (
        -x[1], -rank_scores.get(x[0], 0),
        raw_safety.get(x[0], 99), -missing.get(x[0], 0)
    ))
    six_sx = [s for s, _ in six_ranked[:6]]

    # 五肖独立
    five_ranked = sorted(votes.items(), key=lambda x: (
        -x[1], penalized_safety.get(x[0], 99), -missing.get(x[0], 0)
    ))
    five_sx = [s for s, _ in five_ranked[:5]]

    # 四肖独立
    four_ranked = sorted(votes.items(), key=lambda x: (
        -x[1], penalized_safety.get(x[0], 99), -missing.get(x[0], 0)
    ))
    four_sx = [s for s, _ in four_ranked[:4]]

    # 三肖独立
    three_ranked = sorted(votes.items(), key=lambda x: (
        -x[1], penalized_safety.get(x[0], 99), -missing.get(x[0], 0)
    ))
    three_sx = [s for s, _ in three_ranked[:3]]

    # 16码
    anchor_sx = prev["ping_sx"][1]
    opt_tails = TAIL_TABLE.get(anchor_sx, list(range(7)))
    tail_priority = {t: i for i, t in enumerate(opt_tails)}
    matched, unmatched, seen = [], [], set()
    for sx in six_sx:
        for n in get_suima_by_shengxiao(sx, year):
            if n not in seen:
                seen.add(n)
                if n % 10 in opt_tails:
                    matched.append((n, sx))
                else:
                    unmatched.append((n, sx))
    sx_order = {s: i for i, s in enumerate(six_sx)}
    matched.sort(key=lambda x: sx_order.get(x[1], 99))
    unmatched.sort(key=lambda x: sx_order.get(x[1], 99))
    nums = [n for n, _ in matched]
    supplement = []
    if len(nums) >= 16:
        matched_sorted = sorted(matched, key=lambda x: tail_priority.get(x[0] % 10, 99))
        nums = [n for n, _ in matched_sorted[:16]]
    else:
        for n, _ in unmatched:
            if len(nums) >= 16: break
            if n not in nums:
                nums.append(n)
                supplement.append(n)
        if len(nums) < 16:
            for sx in six_sx:
                if len(nums) >= 16: break
                sx_nums = sorted(get_suima_by_shengxiao(sx, year))
                for n in sx_nums:
                    if len(nums) >= 16: break
                    if n not in nums:
                        nums.append(n)
                        supplement.append(n)

    return {
        "nine_pool": nine_sx,
        "six_pool": six_sx,
        "pools": {3: three_sx, 4: four_sx, 5: five_sx, 7: nine_sx[:7], 8: nine_sx[:8]},
        "numbers": nums[:16],
        "supplement": supplement,
        "opt_tails": opt_tails,
        "votes": dict(votes),
    }

# ==================== 生产预测 ====================
def predict_latest(auto_update=False):
    data = load_all_data(auto_update=auto_update)
    records = extract_records(data)
    if len(records) < 2: return {"error": "数据不足"}
    result = ensemble_vote(records)
    latest = records[-1]; year = latest["year"]
    latest_full = data[-1] if data else {}
    next_qihao = ""
    try:
        exp = latest["qishu"]
        if len(exp) >= 4: next_qihao = f"{exp[:4]}{int(exp[-3:]) + 1:03d}"
    except: pass
    ping2 = latest["ping_nums"][1]
    kill_ref = get_shengxiao_by_suima(offset_num(ping2, 3), year)
    kill_zodiacs = [kill_ref, latest["te_sx"]]
    rate9, rate6, hits9, hits6 = calc_dynamic_rate()
    return {
        "latest_issue": latest["qishu"], "latest_time": latest_full.get("openTime", ""),
        "latest_code": latest_full.get("openCode", ""),
        "latest_te_sx": latest["te_sx"], "latest_te_wei": latest["te_wei"],
        "latest_zodiac": to_simplified(latest_full.get("zodiac", "")),
        "latest_wave": latest_full.get("wave", ""),
        "next_qihao": next_qihao,
        "nine_pool": result["nine_pool"], "six_pool": result["six_pool"],
        "pools": result["pools"], "numbers": result["numbers"],
        "supplement": result.get("supplement", []),
        "opt_tails": result.get("opt_tails", []),
        "kill_zodiacs": kill_zodiacs,
        "votes": result["votes"],
        "dynamic_rate9": rate9, "dynamic_rate6": rate6,
    }

def output_text(result):
    lines = []
    lines.append(f"四合一预测 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 50)
    lines.append(f"基于期号: {result.get('latest_issue')}")
    lines.append(f"开奖时间: {result.get('latest_time', '')}")
    lines.append(f"开奖号码: {result.get('latest_code')}")
    lines.append(f"本期特肖: {result.get('latest_te_sx')}(尾{result.get('latest_te_wei')})")
    lines.append(f"预测下期: {result.get('next_qihao')}")
    lines.append("-" * 30)
    rate9 = result.get('dynamic_rate9', 0); rate6 = result.get('dynamic_rate6', 0)
    lines.append(f"动态命中率(近50期): 九肖 {rate9:.1f}% | 六肖 {rate6:.1f}%")
    lines.append(f"基准命中率(严格验证): 九肖95.18% | 六肖83.87% | 16码62.25%")
    lines.append("-" * 30)
    lines.append(f"★九肖: {', '.join(result.get('nine_pool', []))}")
    lines.append(f"★六肖: {', '.join(result.get('six_pool', []))}")
    lines.append(f"★五肖: {', '.join(result.get('pools', {}).get(5, []))}")
    lines.append(f"★四肖: {', '.join(result.get('pools', {}).get(4, []))}")
    lines.append(f"★三肖: {', '.join(result.get('pools', {}).get(3, []))}")
    opt_tails = result.get('opt_tails', [])
    lines.append(f"★16码: {' '.join(str(n) for n in result.get('numbers', []))}")
    lines.append(f"  最优7尾数(平二锚点): {' '.join(str(t) for t in opt_tails)}")
    if result.get('supplement'):
        lines.append(f"  补充号: {' '.join(str(n) for n in result['supplement'])}")
    lines.append(f"杀肖: {' '.join(result.get('kill_zodiacs', []))}")
    lines.append(f"得票: {dict(sorted(result.get('votes', {}).items(), key=lambda x: -x[1]))}")
    lines.append("=" * 50)
    return "\n".join(lines)

def save_js(result):
    js_path = os.path.join(BASE_DIR, "ensemble_data_4in1.js")
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
        "sixPool": result.get("six_pool", []),
        "killZodiacs": result.get("kill_zodiacs", []),
        "numbers": result.get("numbers", []),
        "supplement": result.get("supplement", []),
        "optTails": result.get("opt_tails", []),
        "pools": result.get("pools", {}),
        "dynamicRate9": result.get("dynamic_rate9", 0),
        "dynamicRate6": result.get("dynamic_rate6", 0),
        "votes": result.get("votes", {}),
    }
    with open(js_path, "w", encoding="utf-8") as f:
        f.write("var ensembleData = ")
        json.dump(js_data, f, ensure_ascii=False, indent=2)
        f.write(";")
    print("[Ensemble] ensemble_data_4in1.js 已更新")

def run_test():
    print("=" * 60)
    print("四合一回测: 2000期训练 + 249期测试 (增强版)")
    print("=" * 60)
    data = load_all_data(auto_update=False)
    records = extract_records(data)
    TRAIN_END = 2000
    test_total = len(records) - TRAIN_END
    print(f"测试集: 后{test_total}期\n")
    hits = {k: [] for k in [3,4,5,6,9]}
    num_hits = []
    for idx in range(TRAIN_END, len(records)):
        result = ensemble_vote(records[:idx])
        target = records[idx]["te_sx"]
        for k in [3,4,5,6,9]: hits[k].append(target in result["nine_pool"][:k])
        num_hits.append(records[idx]["te_num"] in result["numbers"])
        if (idx - TRAIN_END) % 50 == 0: print(f"  进度: {idx - TRAIN_END}/{test_total}")
    print(f"\n回测结果:")
    for k in [9,6,5,4,3]:
        r, ms, dist = streak_stats(hits[k])
        print(f"  {k}肖: {r:.2f}% 连错{ms}期 {dict(dist)}")
    rn, msn, dn = streak_stats(num_hits)
    print(f"  16码: {rn:.2f}% 连错{msn}期 {dict(dn)}")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--test", action="store_true", help="回测验证")
    p.add_argument("--output", action="store_true", help="保存JS/TXT并校验上期")
    p.add_argument("--verify", action="store_true", help="仅校验上期命中")
    p.add_argument("--auto-update", action="store_true", help="自动更新数据（GitHub Actions用）")
    args = p.parse_args()
    if args.test:
        run_test()
        sys.exit(0)
    if args.verify:
        data = load_all_data(auto_update=False)
        records = extract_records(data)
        verify_last_prediction(records)
        rate9, rate6, hits9, hits6 = calc_dynamic_rate()
        print(f"动态命中率(近50期): 九肖 {rate9:.1f}% 六肖 {rate6:.1f}%")
        sys.exit(0)
    result = predict_latest(auto_update=args.auto_update or args.output)
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
            result.get("six_pool", []),
        )
        save_js(result)
        record_path = os.path.join(TRACK_DIR, "ensemble_history.txt")
        issue = result.get("latest_issue", "")
        existing = ""
        if os.path.exists(record_path):
            with open(record_path, "r", encoding="utf-8") as f:
                existing = f.read()
        if f"基于期号: {issue}" not in existing:
            with open(record_path, "a", encoding="utf-8") as f:
                f.write("\n" + text + "\n")