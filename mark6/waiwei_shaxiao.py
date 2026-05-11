# waiwei_shaxiao.py - 外围杀肖 最终版（三级并列，已移除L2）
import sys, os, re
from datetime import datetime
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shuju_loader import load_all_data
from shx_suishu import get_shengxiao_by_suima

POS_NAMES = ['平一', '平二', '平三', '平四', '平五', '平六']
ALL_ZODIAC = ['马', '蛇', '龙', '兔', '虎', '牛', '鼠', '猪', '狗', '鸡', '猴', '羊']
POS_MAP = {'平一': 0, '平二': 1, '平三': 2, '平四': 3, '平五': 4, '平六': 5}

def load_unique_data():
    all_data = load_all_data(auto_update=True)
    seen = set()
    unique = []
    for rec in all_data:
        exp = rec.get('expect')
        if exp and exp not in seen:
            seen.add(exp)
            unique.append(rec)
    unique.sort(key=lambda x: x.get('openTime', ''))
    return unique

def build_all_dual_rules(data):
    stats1 = defaultdict(lambda: defaultdict(int))
    stats2 = defaultdict(lambda: defaultdict(int))
    stats3 = defaultdict(lambda: defaultdict(int))
    stats4 = defaultdict(lambda: defaultdict(int))
    for i in range(len(data) - 1):
        curr, nxt = data[i], data[i+1]
        codes = curr.get('openCode','').split(',')
        nxt_codes = nxt.get('openCode','').split(',')
        if len(codes) < 7 or len(nxt_codes) < 7: continue
        curr_year = int(curr.get('openTime','')[:4]) if curr.get('openTime') else 2026
        nxt_te_sx = get_shengxiao_by_suima(int(nxt_codes[-1]),
                                           int(nxt.get('openTime','')[:4]) if nxt.get('openTime') else curr_year)
        cur_tail = int(codes[-1]) % 10
        cur_te_sx = get_shengxiao_by_suima(int(codes[-1]), curr_year)
        for idx, pos in enumerate(POS_NAMES):
            ping_num = int(codes[idx])
            ping_sx = get_shengxiao_by_suima(ping_num, curr_year)
            ping_tail = ping_num % 10
            stats1[(pos, ping_sx, cur_tail)][nxt_te_sx] += 1
            stats2[(cur_te_sx, pos, ping_tail)][nxt_te_sx] += 1
            stats3[(pos, ping_sx, cur_te_sx)][nxt_te_sx] += 1
            stats4[(pos, ping_tail, cur_tail)][nxt_te_sx] += 1

    def make_rules(stats_dict, rule_type, cond_func, min_samples=30):
        rules = []
        for key, count_map in stats_dict.items():
            total = sum(count_map.values())
            if total < min_samples: continue
            never = [z for z in ALL_ZODIAC if count_map.get(z, 0) == 0]
            top9 = [z for z, _ in sorted(count_map.items(), key=lambda x: x[1], reverse=True)[:9]]
            top9_hit = sum(count_map.get(z, 0) for z in top9)
            rules.append({
                '类型': rule_type,
                '条件': cond_func(key),
                '杀肖候选': never,
                '大范围9肖': top9,
                '大范围命中率': round(top9_hit / total * 100, 2),
                '样本量': total
            })
        return rules

    rules = []
    rules += make_rules(stats1, '平肖+特尾', lambda k: f"{k[0]}【{k[1]}】+特尾【{k[2]}】")
    rules += make_rules(stats2, '特肖+平尾', lambda k: f"特肖【{k[0]}】+{k[1]}尾【{k[2]}】")
    rules += make_rules(stats3, '平肖+特肖', lambda k: f"{k[0]}【{k[1]}】+特肖【{k[2]}】")
    rules += make_rules(stats4, '平尾+特尾', lambda k: f"{k[0]}尾【{k[1]}】+特尾【{k[2]}】")
    return rules

def match_dual_rules(all_rules, cur_codes, cur_year):
    matched, related = [], []
    cur_tail = int(cur_codes[-1]) % 10
    cur_special_z = get_shengxiao_by_suima(int(cur_codes[-1]), cur_year)

    for rule in all_rules:
        rule_type = rule['类型']
        cond = rule['条件']

        if rule_type == '平肖+特尾':
            m = re.search(r'(.?)【(.+?)】.特尾【(.+?)】', cond)
            if not m: continue
            r_pos, r_sx, r_tail = m.group(1), m.group(2), int(m.group(3))
            idx = POS_MAP.get(r_pos)
            if idx is None: continue
            cur_sx = get_shengxiao_by_suima(int(cur_codes[idx]), cur_year)
            match_count = (cur_sx == r_sx) + (cur_tail == r_tail)
            if match_count == 2: matched.append(rule)
            elif match_count == 1: related.append(rule)

        elif rule_type == '特肖+平尾':
            m = re.search(r'特肖【(.+?)】.(.+?)尾【(.+?)】', cond)
            if not m: continue
            r_sz, r_pos, r_tail = m.group(1), m.group(2), int(m.group(3))
            idx = POS_MAP.get(r_pos)
            if idx is None: continue
            cur_tail_val = int(cur_codes[idx]) % 10
            match_count = (cur_special_z == r_sz) + (cur_tail_val == r_tail)
            if match_count == 2: matched.append(rule)
            elif match_count == 1: related.append(rule)

        elif rule_type == '平肖+特肖':
            m = re.search(r'(.?)【(.+?)】.特肖【(.+?)】', cond)
            if not m: continue
            r_pos, r_sx, r_sz = m.group(1), m.group(2), m.group(3)
            idx = POS_MAP.get(r_pos)
            if idx is None: continue
            cur_sx = get_shengxiao_by_suima(int(cur_codes[idx]), cur_year)
            match_count = (cur_sx == r_sx) + (cur_special_z == r_sz)
            if match_count == 2: matched.append(rule)
            elif match_count == 1: related.append(rule)

        elif rule_type == '平尾+特尾':
            m = re.search(r'(.+)尾【(.+?)】.特尾【(.+?)】', cond)
            if not m: continue
            r_pos, r_ptail, r_ttail = m.group(1), int(m.group(2)), int(m.group(3))
            idx = POS_MAP.get(r_pos)
            if idx is None: continue
            cur_ptail = int(cur_codes[idx]) % 10
            match_count = (cur_ptail == r_ptail) + (cur_tail == r_ttail)
            if match_count == 2: matched.append(rule)
            elif match_count == 1: related.append(rule)

    related.sort(key=lambda x: x['大范围命中率'], reverse=True)
    return matched, related

def get_related_kill(all_rules, cur_codes, cur_year):
    matched, related = match_dual_rules(all_rules, cur_codes, cur_year)
    if matched:
        best = max(matched, key=lambda r: r['大范围命中率'])
        kills = best.get('杀肖候选', [])
        return ('L1', best['条件'], kills, best['大范围命中率'], best)
    qualified = [r for r in related if r['大范围命中率'] >= 93 and r['样本量'] >= 30]
    if qualified:
        best = qualified[0]
        kills = best.get('杀肖候选', [])
        return ('L2', best['条件'], kills, best['大范围命中率'], best)
    return (None, None, [], 0, None)

def compute_l3_dynamic_kill(data, cur_codes, cur_year):
    stats = defaultdict(lambda: {'total': 0, 'hit': 0})
    for i in range(len(data) - 1):
        curr, nxt = data[i], data[i+1]
        codes = curr.get('openCode','').split(',')
        nxt_codes = nxt.get('openCode','').split(',')
        if len(codes) < 7 or len(nxt_codes) < 7: continue
        cy = int(curr.get('openTime','')[:4]) if curr.get('openTime') else 2026
        nxt_sx = get_shengxiao_by_suima(int(nxt_codes[-1]),
                                        int(nxt.get('openTime','')[:4]) if nxt.get('openTime') else cy)
        for idx, pos in enumerate(POS_NAMES):
            ping_num = int(codes[idx])
            ping_sx = get_shengxiao_by_suima(ping_num, cy)
            for offset in range(1, 12):
                for dr, sign in [('+', 1), ('-', -1)]:
                    new_num = ping_num + sign * offset
                    if new_num > 49: new_num -= 49
                    elif new_num < 1: new_num += 49
                    new_sx = get_shengxiao_by_suima(new_num, cy)
                    key = (pos, dr, offset, ping_sx, new_sx)
                    stats[key]['total'] += 1
                    if new_sx != nxt_sx:
                        stats[key]['hit'] += 1
    rules = []
    for (pos, dr, offset, ping_sx, killed_sx), v in stats.items():
        if v['total'] >= 63:
            rules.append({
                '位置': pos, '偏移': f'{dr}{offset}', '平码生肖': ping_sx,
                '所得生肖': killed_sx, '样本量': v['total'],
                '命中率': round(v['hit'] / v['total'] * 100, 2)
            })
    if not rules:
        return None
    best = None
    for idx, pos in enumerate(POS_NAMES):
        ping_sx = get_shengxiao_by_suima(int(cur_codes[idx]), cur_year)
        for r in rules:
            if r['位置'] == pos and r['平码生肖'] == ping_sx:
                if not best or r['命中率'] > best['命中率'] or (r['命中率'] == best['命中率'] and r['样本量'] > best['样本量']):
                    best = r
    return best

def main():
    print("=" * 50)
    print("外围杀肖 最终版（三级并列）")
    print("=" * 50)

    data = load_unique_data()
    print(f"数据: {len(data)} 期")

    latest = data[-1]
    codes = latest.get('openCode', '').split(',')
    if len(codes) < 7:
        print("[错误] 号码格式异常"); return
    curr_year = int(latest.get('openTime','')[:4]) if latest.get('openTime') else 2026
    current_expect = latest.get('expect', '')
    print(f"本期: {current_expect} | {','.join(codes)}")

    next_qihao = "未知"
    if current_expect and len(current_expect) >= 4:
        try:
            next_num = int(current_expect[-3:]) + 1
            next_qihao = f"{current_expect[:4]}{next_num:03d}"
        except: pass

    result_lines = []

    all_dual_rules = build_all_dual_rules(data)
    match_level, match_cond, match_kills, match_rate, match_rule = get_related_kill(all_dual_rules, codes, curr_year)

    if match_level == 'L1':
        result_lines.append(f"一级匹配: {match_cond} (命中率: {match_rate}%)")
        result_lines.append(f"大范围9肖: {', '.join(match_rule['大范围9肖'])}")
        result_lines.append(f"⭐杀肖候选: {'、'.join(match_kills) if match_kills else '无'}")
    else:
        result_lines.append("一级匹配: 无精确匹配规则")

    if match_level == 'L2':
        result_lines.append(f"二级匹配: {match_cond} (命中率: {match_rate}%)")
        result_lines.append(f"大范围9肖: {', '.join(match_rule['大范围9肖'])}")
        result_lines.append(f"⭐杀肖候选: {'、'.join(match_kills) if match_kills else '无'}")
    else:
        result_lines.append("二级匹配: 无符合条件(命中率>=93%)的相关规则")

    best_disp = compute_l3_dynamic_kill(data, codes, curr_year)
    if best_disp:
        result_lines.append(f"L3动态位移杀肖: ⭐{best_disp['所得生肖']}--{best_disp['位置']}【{best_disp['平码生肖']}】{best_disp['偏移']} (命中率: {best_disp['命中率']}%)")
    else:
        result_lines.append("L3动态位移: 未触发")

    print(f"\n杀肖参考")
    for line in result_lines:
        print(line)

    base = os.path.dirname(os.path.abspath(__file__))
    rp = os.path.join(base, "waiwei_shaxiao_jilu.txt")
    hdr = f"基于期号: {current_expect}"
    if not os.path.exists(rp) or hdr not in open(rp, encoding='utf-8').read():
        with open(rp, 'a', encoding='utf-8') as f:
            f.write(f"{'='*50}\n预测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{hdr}\n开奖号码: {','.join(codes)}\n预测下期: {next_qihao}\n")
            for line in result_lines:
                f.write(f"{line}\n")
            f.write(f"{'='*50}\n\n")

if __name__ == '__main__':
    main()