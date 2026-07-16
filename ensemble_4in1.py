#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ensemble_4in1.py —— 四合一集成投票生产引擎（v4.1 正式版 · 16码尾数交集优化）
============================================================
集成模型：
  M1 (oracle_core)      — 平五+8九肖池 + F5六肖排序（固定）
  R96 (reference_96)    — 纯遗漏值取前9/前6（固定）
  MAX (core_max)        — 金标规则库反向投票（固定规则库）
  P54 (predict_54)      — 54条信号等权投票 + 滚动最优窗口半径

投票机制：四模型九肖等权投票
排序：非线性排名得分 + 合冲优先 + 遗漏值
输出：3~9肖 + 16码（六肖∩平二锚点7尾数交集优先，验证提升至60.35%）

验证：2000期训练+227期独立测试
  九肖91.26%连错2期 | 六肖74.27%连错3期 | 16码60.35%连错4期

用法：
  python ensemble_4in1.py                  → 屏幕输出预测
  python ensemble_4in1.py --output         → 预测+保存JS/TXT+校验上期+打开网页
  python ensemble_4in1.py --verify         → 仅校验上期命中
  python ensemble_4in1.py --test           → 回测验证
  python ensemble_4in1.py --output --auto-update  → GitHub Actions用
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
from shx_suishu import get_shengxiao_by_suima, SHENGXIAO, get_shift_shengxiao, get_suima_by_shengxiao, to_simplified

ZODIAC = SHENGXIAO
POS_NAMES = ["平一", "平二", "平三", "平四", "平五", "平六", "特码"]
NUM_OFFSETS = list(range(12))
SX_SHIFTS = list(range(-5, 7))
OFFSETS = list(range(-11,0)) + [0] + list(range(1,12))

SAN_HE = {"马":["虎","狗"],"羊":["兔","猪"],"猴":["鼠","龙"],"鸡":["蛇","牛"],"狗":["虎","马"],"猪":["兔","羊"],"鼠":["猴","龙"],"牛":["蛇","鸡"],"虎":["马","狗"],"兔":["猪","羊"],"龙":["鼠","猴"],"蛇":["鸡","牛"]}
LIU_HE = {"马":"羊","羊":"马","猴":"蛇","蛇":"猴","鸡":"龙","龙":"鸡","狗":"兔","兔":"狗","猪":"虎","虎":"猪","鼠":"牛","牛":"鼠"}
CHONG = {"马":"鼠","羊":"牛","猴":"虎","鸡":"兔","狗":"龙","猪":"蛇","鼠":"马","牛":"羊","虎":"猴","兔":"鸡","龙":"狗","蛇":"猪"}

RULES_PATH = os.path.join(BASE_DIR, "特肖杀肖规则库.json")
TRACK_DIR = os.path.join(BASE_DIR, "oracle记录")
TRACK_FILE = os.path.join(TRACK_DIR, "hit_track.json")

# ---------- 16码固定尾数表（2000期训练冻结） ----------
TAIL_TABLE = {
    "马": [0,1,2,3,4,7,8], "羊": [1,2,3,4,6,7,8], "猴": [1,2,4,5,6,8,9],
    "鸡": [0,2,3,4,6,8,9], "狗": [0,1,2,3,5,6,7], "猪": [1,3,4,5,6,7,8],
    "鼠": [0,1,3,4,6,7,9], "牛": [0,1,3,5,6,7,8], "虎": [1,4,5,6,7,8,9],
    "兔": [0,1,2,3,4,6,8], "龙": [0,1,2,3,4,5,6], "蛇": [1,2,3,4,6,7,8],
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


# ==================== 命中追踪 ====================
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


# ==================== 四合一核心 ====================
def ensemble_vote(records):
    hist = records[:]
    prev = hist[-1]; year = prev["year"]
    missing = compute_missing(hist, len(hist))

    # M1
    ping5 = prev["ping_nums"][4]
    cn = (ping5 - 1 + 8) % 49 + 1
    csx = get_shengxiao_by_suima(cn, year)
    cidx = ZODIAC.index(csx)
    m1_nine = [ZODIAC[(cidx + i) % 12] for i in range(-4, 5)]

    # R96
    r96_nine = sorted(ZODIAC, key=lambda s: missing.get(s, 0), reverse=True)[:9]

    # MAX
    max_nine = []
    if os.path.exists(RULES_PATH):
        with open(RULES_PATH, 'r', encoding='utf-8') as f:
            SHAXIAO_RULES = json.load(f)
        gold_votes = Counter()
        cur_sx = prev["te_sx"]
        for pidx, pn in enumerate(POS_NAMES):
            num = prev["te_num"] if pn == "特码" else prev["ping_nums"][pidx]
            tsx = prev["te_sx"] if pn == "特码" else prev["ping_sx"][pidx]
            for off in OFFSETS:
                new_num = offset_num(num, off)
                killed = get_shengxiao_by_suima(new_num, year)
                rule_key = f"{cur_sx}|{pn}|{tsx}|{off}|{killed}"
                if rule_key in SHAXIAO_RULES and SHAXIAO_RULES[rule_key].get('grade') == 'gold':
                    gold_votes[SHAXIAO_RULES[rule_key]['killed_sx']] += 1
        killed_set = set(s for s, v in gold_votes.items() if v >= 2)
        safe_m = [s for s in ZODIAC if s not in killed_set]
        max_nine = sorted(safe_m, key=lambda s: missing.get(s, 0), reverse=True)[:9]
    else:
        max_nine = sorted(ZODIAC, key=lambda s: missing.get(s, 0), reverse=True)[:9]

    # P54滚动窗口
    best_r = 2; best_rate = 0
    for r in [2, 3, 4]:
        hits_p = 0
        for i in range(1, len(hist)):
            prv, cur = hist[i-1], hist[i]
            tgt = cur["te_sx"]; yr = prv["year"]
            miss = compute_missing(hist, i)
            vc = Counter()
            for pi, pn in enumerate(POS_NAMES):
                nm = prv["te_num"] if pn == "特码" else prv["ping_nums"][pi]
                sx = prv["te_sx"] if pn == "特码" else prv["ping_sx"][pi]
                for of in NUM_OFFSETS:
                    c = get_shengxiao_by_suima(offset_num(nm, of), yr)
                    for s in get_window(c, r): vc[s] += 1
                for sf in SX_SHIFTS:
                    c = get_shift_shengxiao(sx, sf)
                    for s in get_window(c, r): vc[s] += 1
            rk = sorted(vc.items(), key=lambda x: (-x[1], -miss.get(x[0], 0)))
            if tgt in [s for s, _ in rk[:9]]: hits_p += 1
        rate = hits_p / (len(hist) - 1) * 100 if len(hist) > 1 else 0
        if rate > best_rate: best_rate = rate; best_r = r

    vc = Counter()
    for pi, pn in enumerate(POS_NAMES):
        nm = prev["te_num"] if pn == "特码" else prev["ping_nums"][pi]
        sx = prev["te_sx"] if pn == "特码" else prev["ping_sx"][pi]
        for of in NUM_OFFSETS:
            c = get_shengxiao_by_suima(offset_num(nm, of), year)
            for s in get_window(c, best_r): vc[s] += 1
        for sf in SX_SHIFTS:
            c = get_shift_shengxiao(sx, sf)
            for s in get_window(c, best_r): vc[s] += 1
    ranked_p = sorted(vc.items(), key=lambda x: (-x[1], -missing.get(x[0], 0)))
    p54_nine = [s for s, _ in ranked_p[:9]]

    # 非线性排名得分
    rank_scores = Counter()
    for nine in [m1_nine, r96_nine, max_nine, p54_nine]:
        for rank, s in enumerate(nine):
            if rank < 3: rank_scores[s] += 9
            elif rank < 6: rank_scores[s] += 3
            else: rank_scores[s] += 1

    # 投票
    votes = Counter()
    for nine in [m1_nine, r96_nine, max_nine, p54_nine]:
        for s in nine: votes[s] += 1

    hc = get_hechong_full(prev["te_sx"])
    ranked = sorted(votes.items(), key=lambda x: (-x[1], -rank_scores.get(x[0], 0), -(1 if x[0] in hc else 0), -missing.get(x[0], 0)))
    ranked_sx = [s for s, _ in ranked]

    # 六肖
    six_sx = ranked_sx[:6]

    # ===== 16码：平二生肖锚点7尾数 + 六肖交集（尾数交集优化版） =====
    anchor_sx = prev["ping_sx"][1]
    opt_tails = TAIL_TABLE.get(anchor_sx, list(range(7)))
    tail_priority = {t: i for i, t in enumerate(opt_tails)}

    matched = []
    unmatched = []
    seen = set()
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
        "nine_pool": ranked_sx[:9],
        "six_pool": six_sx,
        "pools": {k: ranked_sx[:k] for k in [3,4,5,7,8]},
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
    lines.append(f"基准命中率(严格验证): 九肖91.26% | 六肖74.27% | 16码60.35%")
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


# ==================== 回测 ====================
def run_test():
    print("=" * 60)
    print("四合一回测: 2000期训练 + 227期测试 (16码尾数交集优化)")
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


# ==================== 主入口 ====================
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