# zhengshi_yuce.py - 正式预测（九肖 + 卦象，精简版）
import sys, os
from collections import Counter, defaultdict
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shuju_loader import load_all_data
from qigua_duogua import build_two_period_multi_gua
from qigua import numbers_from_record, _single_gua_from_numbers
from shijian import get_sizhu_dizhi

ALL_ZODIAC = ['马', '蛇', '龙', '兔', '虎', '牛', '鼠', '猪', '狗', '鸡', '猴', '羊']
ZODIAC_IDX = {z: i for i, z in enumerate(ALL_ZODIAC)}

# ==================== 数据加载 ====================
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

# ==================== 九肖核心 ====================
def zodiac_by_num(num): return ALL_ZODIAC[(num - 1) % 12]
def te_zodiac(rec):
    codes = rec.get('openCode', '').split(',')
    return zodiac_by_num(int(codes[-1])) if len(codes) >= 7 else None
def second_zodiac(rec):
    codes = rec.get('openCode', '').split(',')
    return zodiac_by_num(int(codes[1])) if len(codes) >= 2 else None
def shift(z, steps): return ALL_ZODIAC[(ZODIAC_IDX[z] + steps) % 12]

def get_jiuxiao(train_data, prev_record):
    cur_z = te_zodiac(prev_record)
    p_z = te_zodiac(train_data[-2]) if len(train_data) >= 2 else None
    second_z = second_zodiac(prev_record)
    kill_set = {shift(second_z, 3)} if second_z else set()
    kill_set.add(cur_z)

    def m_basic(data):
        t = defaultdict(lambda: defaultdict(int)); total = defaultdict(int)
        for i in range(len(data)-1):
            a, b = te_zodiac(data[i]), te_zodiac(data[i+1])
            if a and b: t[a][b] += 1; total[a] += 1
        return {k: {n: round(v/total[k]*100,2) for n,v in d.items()} for k,d in t.items()}
    def m_weighted(data):
        t = defaultdict(lambda: defaultdict(float)); total = defaultdict(float)
        for i in range(len(data)-1):
            a, b = te_zodiac(data[i]), te_zodiac(data[i+1])
            if not a or not b: continue
            w = 1.5 if len(data)-1-i <= 12 else (1.2 if len(data)-1-i <= 24 else 1.0)
            t[a][b] += w; total[a] += w
        return {k: {n: round(v/total[k]*100,2) for n,v in d.items()} for k,d in t.items()}
    def m_second(data):
        t = defaultdict(lambda: defaultdict(int)); total = defaultdict(int)
        for i in range(len(data)-2):
            a,b,c = te_zodiac(data[i]),te_zodiac(data[i+1]),te_zodiac(data[i+2])
            if a and b and c: t[(a,b)][c] += 1; total[(a,b)] += 1
        return {k: {n: round(v/total[k]*100,2) for n,v in d.items()} for k,d in t.items()}
    def m_number(data):
        t = defaultdict(lambda: defaultdict(int)); total = defaultdict(int)
        for i in range(len(data)-1):
            codes = data[i].get('openCode','').split(',')
            if len(codes)<7: continue
            nxt = te_zodiac(data[i+1])
            if nxt: t[int(codes[-1])][nxt] += 1; total[int(codes[-1])] += 1
        return {k: {n: round(v/total[k]*100,2) for n,v in d.items()} for k,d in t.items()}

    mA, mB, mC, mD = m_basic(train_data), m_weighted(train_data), m_second(train_data), m_number(train_data)
    te_num = int(prev_record.get('openCode','').split(',')[-1]) if len(prev_record.get('openCode','').split(','))>=7 else 0
    scores = defaultdict(float)
    for z in ALL_ZODIAC:
        if z in kill_set: continue
        scores[z] = round(mA.get(cur_z,{}).get(z,0)*0.30 + mB.get(cur_z,{}).get(z,0)*0.30 + mC.get((p_z,cur_z),{}).get(z,0)*0.20 + mD.get(te_num,{}).get(z,0)*0.20, 2)
    return [z for z, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:9]]

# ==================== 卦象 ====================
def build_time_guas(prev_record, curr_record):
    ot = curr_record.get('openTime')
    if not ot: return [None, None]
    try: dt = datetime.strptime(ot, '%Y-%m-%d %H:%M:%S')
    except: return [None, None]
    y,m,d,h = get_sizhu_dizhi(dt)
    pn = numbers_from_record(prev_record); cn = numbers_from_record(curr_record)
    if not pn or not cn: return [None, None]
    dy = (pn[-1]+cn[-1])%6 or 6
    def sg(a,b):
        a=a%8 or 8; b=b%8 or 8
        return _single_gua_from_numbers(a,b,dy)
    return [sg(y,m), sg(d,h)]

def build_nayin_gua(prev_record, curr_record):
    pn=numbers_from_record(prev_record); cn=numbers_from_record(curr_record)
    if not pn or not cn: return None
    def ht(n):
        t=n%10
        return 1 if t in(1,6) else 2 if t in(2,7) else 3 if t in(3,8) else 4 if t in(4,9) else 5
    dy=(pn[-1]+cn[-1])%6 or 6
    return _single_gua_from_numbers(ht(pn[-1])%8 or 8, ht(cn[-1])%8 or 8, dy)

def build_yun_gua(prev_record, curr_record):
    pn=numbers_from_record(prev_record); cn=numbers_from_record(curr_record)
    if not pn or not cn: return None
    dy=(pn[-1]+cn[-1])%6 or 6
    return _single_gua_from_numbers(3,3,dy)

# ==================== 主程序 ====================
def main():
    print("=" * 50)
    print("正式预测（九肖 + 卦象）")
    print("=" * 50)
    data = load_unique_data()
    print(f"数据: {len(data)} 期")
    prev_prev, prev_rec, curr_rec = data[-3], data[-2], data[-1]
    print(f"本期: {curr_rec.get('expect')} | {curr_rec.get('openCode')}")

    # 九肖
    jx = get_jiuxiao(data, curr_rec)
    print(f"\n九肖(76.11%): {' '.join(jx)}")

    # 卦象
    preds = build_two_period_multi_gua(prev_prev, prev_rec)
    tg = build_time_guas(prev_prev, prev_rec)
    ng = build_nayin_gua(prev_prev, prev_rec)
    yg = build_yun_gua(prev_prev, prev_rec)
    preds_all = preds + [p for p in tg + [ng, yg] if p]
    freq = Counter([p for p in preds_all if p in jx]).most_common()
    u15_jx = set(preds_all) & set(jx)
    top1 = freq[0][0] if freq else None
    cand2 = [s for s,c in freq if c>=2]
    cand3 = [s for s,c in freq if c>=3]
    u15_sorted = [s for s,c in freq if s in u15_jx]
    print(f"并集∩九肖(~40%): {' '.join(u15_sorted) if u15_sorted else '无'}")
    print(f"≥2票共振(27%): {' '.join(cand2) if cand2 else '无'}")
    print(f"≥3票共振(16%): {' '.join(cand3) if cand3 else '无'}")
    print(f"Top1(10%): {top1 or '无'}")

    # 写入记录
    base = os.path.dirname(os.path.abspath(__file__))
    next_qh = "未知"
    ce = curr_rec.get('expect','')
    if ce and len(ce)>=4:
        try: next_qh = f"{ce[:4]}{int(ce[-3:])+1:03d}"
        except: pass
    rp = os.path.join(base, "yuce_jilu.txt")
    hdr = f"预测下期: {next_qh}"
    if not os.path.exists(rp) or hdr not in open(rp, encoding='utf-8').read():
        with open(rp, 'a', encoding='utf-8') as f:
            f.write(f"{'='*50}\n预测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n基于期号: {ce}\n开奖号码: {curr_rec.get('openCode')}\n{hdr}\n九肖: {' '.join(jx)}\n并集∩九肖: {' '.join(u15_sorted) if u15_sorted else '无'}\n≥2票: {' '.join(cand2) if cand2 else '无'}\n≥3票: {' '.join(cand3) if cand3 else '无'}\nTop1: {top1 or '无'}\n{'='*50}\n\n")

if __name__ == '__main__':
    main()