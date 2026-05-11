# kill_XY.py - 整合版杀肖引擎（按期号去重 + 四种双条件规则，关联优先排序）
import json, os, re
from collections import defaultdict
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

from shx_suishu import get_shengxiao_by_suima
from shuju_loader import update_year_data, get_latest_record

DATA_DIR = CURRENT_DIR
MIN_SAMPLES = 30
SECONDARY_THRESHOLD = 93          # 二级匹配最低阈值
RULES_FILE_1 = os.path.join(CURRENT_DIR, "kill_rules_stats.json")
RULES_FILE_2 = os.path.join(CURRENT_DIR, "kill_rules_reverse.json")
RECORD_FILE = os.path.join(CURRENT_DIR, "肖尾记录.txt")
YEARS = [2020, 2021, 2022, 2023, 2024, 2025, 2026]

ALL_ZODIAC = ['马', '羊', '猴', '鸡', '狗', '猪', '鼠', '牛', '虎', '兔', '龙', '蛇']
POS_MAP = {'平一': 0, '平二': 1, '平三': 2, '平四': 3, '平五': 4, '平六': 5}


def load_all_data(data_dir, years):
    all_data, seen = [], set()
    for year in years:
        fp = os.path.join(data_dir, f"{year}.json")
        if os.path.exists(fp):
            with open(fp, 'r', encoding='utf-8') as f:
                records = json.load(f).get('data', [])
                for r in records:
                    exp = r.get('expect')
                    if exp and exp not in seen:
                        seen.add(exp)
                        r['_year'] = year
                        all_data.append(r)
    all_data.sort(key=lambda x: x.get('openTime', ''))
    return all_data


def make_rules(flat_stats, rule_type, cond_func, min_samples=MIN_SAMPLES):
    rules = []
    for key, count_map in flat_stats.items():
        total = sum(count_map.values())
        if total < min_samples:
            continue
        sorted_items = sorted(count_map.items(), key=lambda x: x[1], reverse=True)
        never = [z for z in ALL_ZODIAC if count_map.get(z, 0) == 0]
        top9 = [z for z, _ in sorted_items[:9]]
        top9_coverage = sum(cnt for _, cnt in sorted_items[:9]) / total * 100
        rules.append({
            '类型': rule_type,
            '条件': cond_func(key),
            '样本量': total,
            '杀肖候选': never,
            '大范围9肖': top9,
            '大范围命中率': round(top9_coverage, 1)
        })
    return rules


def generate_rules_type1(all_data):
    """【平肖+特尾】"""
    print("\n正在生成【平肖+特尾】规则...")
    stats = defaultdict(lambda: defaultdict(int))
    for i in range(len(all_data) - 1):
        cur, nxt = all_data[i], all_data[i+1]
        cur_codes = cur.get('openCode', '').split(',')
        nxt_codes = nxt.get('openCode', '').split(',')
        if len(cur_codes) < 7 or len(nxt_codes) < 7: continue
        cur_year = int(cur.get('openTime', '')[:4])
        nxt_year = nxt.get('_year', cur_year)
        cur_tail = int(cur_codes[-1]) % 10
        nxt_z = get_shengxiao_by_suima(int(nxt_codes[-1]), nxt_year)
        for pos_name, idx in POS_MAP.items():
            ping_z = get_shengxiao_by_suima(int(cur_codes[idx]), cur_year)
            key = (pos_name, ping_z, cur_tail)
            stats[key][nxt_z] += 1

    def cond_func(key):
        pos_name, ping_z, tail = key
        return f"{pos_name}【{ping_z}】+特尾【{tail}】"

    rules = make_rules(stats, '平肖+特尾', cond_func)
    with open(RULES_FILE_1, 'w', encoding='utf-8') as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)
    print(f"  生成 {len(rules)} 条规则")
    return rules


def generate_rules_type2(all_data):
    """【特肖+平尾】"""
    print("\n正在生成【特肖+平尾】规则...")
    stats = defaultdict(lambda: defaultdict(int))
    for i in range(len(all_data) - 1):
        cur, nxt = all_data[i], all_data[i+1]
        cur_codes = cur.get('openCode', '').split(',')
        nxt_codes = nxt.get('openCode', '').split(',')
        if len(cur_codes) < 7 or len(nxt_codes) < 7: continue
        cur_year = int(cur.get('openTime', '')[:4])
        nxt_year = nxt.get('_year', cur_year)
        cur_special_z = get_shengxiao_by_suima(int(cur_codes[-1]), cur_year)
        nxt_z = get_shengxiao_by_suima(int(nxt_codes[-1]), nxt_year)
        for pos_name, idx in POS_MAP.items():
            ping_tail = int(cur_codes[idx]) % 10
            key = (cur_special_z, pos_name, ping_tail)
            stats[key][nxt_z] += 1

    def cond_func(key):
        sz, pos_name, tail = key
        return f"特肖【{sz}】+{pos_name}尾【{tail}】"

    rules = make_rules(stats, '特肖+平尾', cond_func)
    with open(RULES_FILE_2, 'w', encoding='utf-8') as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)
    print(f"  生成 {len(rules)} 条规则")
    return rules


def generate_rules_type3(all_data):
    """【平肖+特肖】"""
    print("\n正在生成【平肖+特肖】规则...")
    stats = defaultdict(lambda: defaultdict(int))
    for i in range(len(all_data) - 1):
        cur, nxt = all_data[i], all_data[i+1]
        cur_codes = cur.get('openCode', '').split(',')
        nxt_codes = nxt.get('openCode', '').split(',')
        if len(cur_codes) < 7 or len(nxt_codes) < 7: continue
        cur_year = int(cur.get('openTime', '')[:4])
        nxt_year = nxt.get('_year', cur_year)
        cur_special_z = get_shengxiao_by_suima(int(cur_codes[-1]), cur_year)
        nxt_z = get_shengxiao_by_suima(int(nxt_codes[-1]), nxt_year)
        for pos_name, idx in POS_MAP.items():
            ping_z = get_shengxiao_by_suima(int(cur_codes[idx]), cur_year)
            key = (pos_name, ping_z, cur_special_z)
            stats[key][nxt_z] += 1

    def cond_func(key):
        pos_name, ping_z, te_z = key
        return f"{pos_name}【{ping_z}】+特肖【{te_z}】"

    rules = make_rules(stats, '平肖+特肖', cond_func)
    print(f"  生成 {len(rules)} 条规则")
    return rules


def generate_rules_type4(all_data):
    """【平尾+特尾】"""
    print("\n正在生成【平尾+特尾】规则...")
    stats = defaultdict(lambda: defaultdict(int))
    for i in range(len(all_data) - 1):
        cur, nxt = all_data[i], all_data[i+1]
        cur_codes = cur.get('openCode', '').split(',')
        nxt_codes = nxt.get('openCode', '').split(',')
        if len(cur_codes) < 7 or len(nxt_codes) < 7: continue
        cur_year = int(cur.get('openTime', '')[:4])
        nxt_year = nxt.get('_year', cur_year)
        cur_tail = int(cur_codes[-1]) % 10
        nxt_z = get_shengxiao_by_suima(int(nxt_codes[-1]), nxt_year)
        for pos_name, idx in POS_MAP.items():
            ping_tail = int(cur_codes[idx]) % 10
            key = (pos_name, ping_tail, cur_tail)
            stats[key][nxt_z] += 1

    def cond_func(key):
        pos_name, ping_tail, te_tail = key
        return f"{pos_name}尾【{ping_tail}】+特尾【{te_tail}】"

    rules = make_rules(stats, '平尾+特尾', cond_func)
    print(f"  生成 {len(rules)} 条规则")
    return rules


def match_rules(all_rules, cur_codes, cur_time, cur_year):
    """与 waiwei_shaxiao.py 完全一致的匹配逻辑，并对 related 进行关联度排序"""
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

    # 新的排序规则：先展示有核心特征（特肖或特尾）匹配的规则，再展示仅平码特征匹配的规则
    # 核心特征匹配指：规则中包含了本期特肖或特尾
    core_related = []
    other_related = []
    for rule in related:
        cond = rule['条件']
        has_core = False
        if f'特肖【{cur_special_z}】' in cond or f'特尾【{cur_tail}】' in cond:
            has_core = True
        
        if has_core:
            core_related.append(rule)
        else:
            other_related.append(rule)
    
    core_related.sort(key=lambda x: x['大范围命中率'], reverse=True)
    other_related.sort(key=lambda x: x['大范围命中率'], reverse=True)
    
    # 合并：核心相关 > 其他相关
    related = core_related + other_related
    # 只保留命中率>=93%的
    related = [r for r in related if r['大范围命中率'] >= SECONDARY_THRESHOLD]
    return matched, related


def save_record(expect, cur_codes, matched, related):
    if not os.path.exists(RECORD_FILE):
        with open(RECORD_FILE, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n肖尾记录\n" + "=" * 80 + "\n\n")
    with open(RECORD_FILE, 'r', encoding='utf-8') as f:
        if f"期号: {expect}" in f.read():
            print(f"\n[跳过] 期号 {expect} 已有记录，不重复保存")
            return
    lines = ["=" * 80, f"期号: {expect}", f"开奖号码: {','.join(cur_codes)}",
             f"记录时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "-" * 40]
    if matched:
        lines.append("【匹配规则】")
        for rule in matched:
            lines.append(f"  {rule['类型']}: {rule['条件']}")
            lines.append(f"    样本量: {rule['样本量']}  大范围9肖: {', '.join(rule['大范围9肖'])} (命中率: {rule['大范围命中率']}%)")
            if rule['杀肖候选']: lines.append(f"    杀肖候选: {', '.join(rule['杀肖候选'])}")
    else:
        lines.append("【相关规则】（仅显示命中率≥93%，关联度优先排序）")
        if related:
            for rule in related:
                lines.append(f"  {rule['类型']}: {rule['条件']}")
                lines.append(f"    样本量: {rule['样本量']}  大范围9肖: {', '.join(rule['大范围9肖'])} (命中率: {rule['大范围命中率']}%)")
                if rule['杀肖候选']: lines.append(f"    杀肖候选: {', '.join(rule['杀肖候选'])}")
        else:
            lines.append("  无符合条件(命中率>=93%)的相关规则")
    lines.append("=" * 80 + "\n")
    with open(RECORD_FILE, 'a', encoding='utf-8') as f:
        f.write("\n".join(lines))
    print(f"\n记录已保存到 {RECORD_FILE}")


def main():
    print("=" * 70)
    print("整合版杀肖引擎 (kill_XY.py) · 四种双条件规则 | 二级匹配阈值93% | 关联度优先")
    print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    print("\n[1] 更新开奖数据...")
    for year in YEARS:
        update_year_data(year)
    print("\n[2] 加载全部历史数据...")
    all_data = load_all_data(DATA_DIR, YEARS)
    print(f"  去重后总数据量: {len(all_data)} 期")
    print("\n[3] 重新生成规则（样本量≥30）...")
    rules1 = generate_rules_type1(all_data)
    rules2 = generate_rules_type2(all_data)
    rules3 = generate_rules_type3(all_data)
    rules4 = generate_rules_type4(all_data)
    all_rules = rules1 + rules2 + rules3 + rules4
    print(f"\n  总计: {len(all_rules)} 条规则")
    print("\n[4] 获取最新开奖...")
    latest = get_latest_record()
    if not latest:
        print("  无法获取最新开奖数据"); return
    cur_codes = latest.get('openCode', '').split(',')
    cur_time = latest.get('openTime', '')
    if len(cur_codes) < 7 or not cur_time:
        print("  数据格式异常"); return
    cur_year = int(cur_time[:4])
    expect = latest.get('expect')
    print(f"\n最新期号: {expect}")
    print(f"开奖号码: {','.join(cur_codes)}")
    print("-" * 70)
    print("\n[5] 匹配规则...")
    matched, related = match_rules(all_rules, cur_codes, cur_time, cur_year)
    if matched:
        print("\n匹配到以下规则：")
        for i, rule in enumerate(matched, 1):
            print(f"\n{i}. 【{rule['类型']}】{rule['条件']}")
            print(f"   样本量: {rule['样本量']}  大范围9肖: {', '.join(rule['大范围9肖'])} (命中率: {rule['大范围命中率']}%)")
            if rule['杀肖候选']: print(f"   杀肖候选: {', '.join(rule['杀肖候选'])}")
    else:
        print("\n未匹配到任何规则")
        print("\n本期相关杀肖数据（仅显示命中率≥93%，关联度优先排序）:")
        if related:
            for i, rule in enumerate(related, 1):
                print(f"\n{i}. 【{rule['类型']}】{rule['条件']}")
                print(f"   样本量: {rule['样本量']}  大范围9肖: {', '.join(rule['大范围9肖'])} (命中率: {rule['大范围命中率']}%)")
                if rule['杀肖候选']: print(f"   杀肖候选: {', '.join(rule['杀肖候选'])}")
        else:
            print("  无符合条件(命中率>=93%)的相关规则")
    save_record(expect, cur_codes, matched, related)
    print("\n" + "=" * 70)
    print("说明: 杀肖候选=历史样本中从未出现过的生肖 | 大范围9肖=概率最高的9个生肖")
    print("=" * 70)


if __name__ == "__main__":
    main()