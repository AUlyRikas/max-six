#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ensemble_4in1.py —— 四模型集成投票生产引擎
============================================================
集成模型：
  模型1：oracle_core (M1)     — 平五+8号码偏移 ±4 围肖 + F5投票
  模型2：reference_96         — 多信号评分（遗漏值+金标+冷却+平五+合冲）
  模型3：predict_54           — 54条围肖信号叠加投票
  模型4：core_max (旧版MAX)    — 5191条全量金标规则匹配

投票机制：四模型等权投票，按得票降序取9肖/6肖。
平局决胜（方案ED·非线性）：票数降序 → 非线性排名得分降序 → 金标安全分升序 → 遗漏值降序
输出兼容：生成 ensemble_data.js 和 oracle记录/ensemble_history.txt

用法：
  python ensemble_4in1.py                  → 预测下一期（屏幕输出）
  python ensemble_4in1.py --output         → 预测+保存JS/TXT+校验上期+打开网页
  python ensemble_4in1.py --verify         → 仅校验上期命中
  python ensemble_4in1.py --test           → 组合对比测试
  python ensemble_4in1.py --output --auto-update  → GitHub Actions用
============================================================
"""
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MARK6_DIR = os.path.join(BASE_DIR, "mark6")
if os.path.exists(MARK6_DIR) and MARK6_DIR not in sys.path:
    sys.path.insert(0, MARK6_DIR)

from shuju_loader import load_all_data
from shx_suishu import get_shengxiao_by_suima, SHENGXIAO, to_simplified, get_suima_by_shengxiao

ZODIAC = SHENGXIAO
POS_NAMES = ["平一", "平二", "平三", "平四", "平五", "平六", "特码"]

# ==================== 工具函数 ====================
def offset_num(num, off):
    return (num - 1 + off) % 49 + 1

def compute_missing(records, up_to):
    missing = {}
    for s in ZODIAC:
        streak = 0
        for i in range(up_to - 1, -1, -1):
            if records[i]["te_sx"] != s: streak += 1
            else: break
        missing[s] = streak
    return missing

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
            records.append({
                "qishu": qs, "year": year,
                "te_num": nums[6], "te_sx": get_shengxiao_by_suima(nums[6], year),
                "te_tail": nums[6] % 10, "te_wei": nums[6] % 10,
                "ping_nums": nums[:6],
                "ping_sx": [get_shengxiao_by_suima(n, year) for n in nums[:6]]
            })
        except: continue
    records.sort(key=lambda x: int(x["qishu"]))
    return records

def compute_streak_stats(hit_list):
    total = len(hit_list); hits = sum(hit_list)
    rate = hits / total * 100 if total else 0
    streak = 0; ms = 0; dist = Counter()
    for h in hit_list:
        if not h: streak += 1
        else:
            if streak > 0: dist[streak] += 1; streak = 0
    if streak > 0: dist[streak] += 1
    if dist: ms = max(dist.keys())
    return rate, ms, dist

# 合冲关系
SAN_HE = {"马":["虎","狗"],"羊":["兔","猪"],"猴":["鼠","龙"],"鸡":["蛇","牛"],"狗":["虎","马"],"猪":["兔","羊"],"鼠":["猴","龙"],"牛":["蛇","鸡"],"虎":["马","狗"],"兔":["猪","羊"],"龙":["鼠","猴"],"蛇":["鸡","牛"]}
LIU_HE = {"马":"羊","羊":"马","猴":"蛇","蛇":"猴","鸡":"龙","龙":"鸡","狗":"兔","兔":"狗","猪":"虎","虎":"猪","鼠":"牛","牛":"鼠"}
CHONG = {"马":"鼠","羊":"牛","猴":"虎","鸡":"兔","狗":"龙","猪":"蛇","鼠":"马","牛":"羊","虎":"猴","兔":"鸡","龙":"狗","蛇":"猪"}

# ==================== 模型1：oracle_core (M1) ====================
def model_oracle(records):
    if len(records) < 2: return [], []
    latest = records[-1]; year = latest["year"]
    missing = compute_missing(records, len(records))
    ping5 = latest["ping_nums"][4]
    center_num = (ping5 - 1 + 8) % 49 + 1
    center_sx = get_shengxiao_by_suima(center_num, year)
    cidx = ZODIAC.index(center_sx)
    pool_9 = [ZODIAC[(cidx + i) % 12] for i in range(-4, 5)]
    outside = [s for s in ZODIAC if s not in pool_9]
    best_out = max(outside, key=lambda s: missing[s])
    worst_in = min(pool_9, key=lambda s: missing[s])
    diff = missing[best_out] - missing[worst_in]
    DYNAMIC_WINDOW = 50; threshold = 9
    if len(records) >= DYNAMIC_WINDOW + 1:
        recent_diffs = []
        for i in range(len(records) - DYNAMIC_WINDOW, len(records)):
            prev = records[i-1]
            pp = prev["ping_nums"][4]; pc = (pp - 1 + 8) % 49 + 1
            pcs = get_shengxiao_by_suima(pc, prev["year"]); pcidx = ZODIAC.index(pcs)
            ppool = [ZODIAC[(pcidx + j) % 12] for j in range(-4, 5)]
            pmissing = {}
            for s in ZODIAC:
                sstreak = 0
                for k in range(i-1, -1, -1):
                    if records[k]["te_sx"] != s: sstreak += 1
                    else: break
                pmissing[s] = sstreak
            pou = [s for s in ZODIAC if s not in ppool]
            if pou and ppool:
                pb = max(pou, key=lambda s: pmissing[s])
                pw = min(ppool, key=lambda s: pmissing[s])
                recent_diffs.append(pmissing[pb] - pmissing[pw])
        if recent_diffs:
            recent_diffs.sort()
            threshold = recent_diffs[int(len(recent_diffs) * 0.9)]
    if diff > threshold:
        final_nine = [best_out if s == worst_in else s for s in pool_9]
    else:
        final_nine = pool_9
    te_kill = latest["te_sx"]
    final_clean = list(final_nine)
    for i in range(len(final_clean)):
        if final_clean[i] == te_kill:
            cand = [x for x in ZODIAC if x not in final_clean and x != te_kill]
            if cand: final_clean[i] = max(cand, key=lambda x: missing[x])
    hechong_pool = set()
    hechong_pool.add(latest["te_sx"])
    for s in SAN_HE.get(latest["te_sx"],[]): hechong_pool.add(s)
    hechong_pool.add(LIU_HE.get(latest["te_sx"],""))
    chong_sx = CHONG.get(latest["te_sx"],"")
    hechong_pool.add(chong_sx)
    for s in SAN_HE.get(chong_sx,[]): hechong_pool.add(s)
    hechong_pool.add(LIU_HE.get(chong_sx,""))
    votes_f5 = Counter()
    for s in ZODIAC:
        if s in final_clean: votes_f5[s] += 3
        if s in hechong_pool: votes_f5[s] += 2
        if s != te_kill: votes_f5[s] += 1
        if missing.get(s,0) >= 20: votes_f5[s] += 2
        votes_f5[s] += int(missing.get(s,0)/10)
    sorted_nine = sorted(final_clean, key=lambda s: votes_f5.get(s,0), reverse=True)
    return sorted_nine, sorted_nine[:6]

# ==================== 模型2：reference_96（内嵌） ====================
OFFSETS = list(range(-11,0)) + [0] + list(range(1,12))
MIN_SAMPLES=5; MIN_KILL_RATE=95.0; MAX_STREAK=1
MISSING_WEIGHTS=(1.0,2.0,3.0); MISSING_THRESH=(8,20)
GOLD_PENS=[3,8,15,30]; COOL_PENS=[10,5,2]; L3_WEIGHT=5
FIXED_WEIGHT=15; TE_WEIGHT=10; PING5_WEIGHT=10; HECHONG_WEIGHT=8
CROSS_WEIGHT=0; USE_REPLACE=False; COOL_WINDOW=3; L3_MIN_RATE=93.0
_CACHED_RULES=None; _CACHED_GRADED=None; _CACHED_L3=None

def build_fixed_rules(records):
    global _CACHED_RULES, _CACHED_GRADED, _CACHED_L3
    if _CACHED_RULES is not None: return _CACHED_RULES, _CACHED_GRADED, _CACHED_L3
    total = len(records)
    if total < 1500:
        split = int(total*0.8); train=records[:split]; val=records[split:]
    else:
        train=records[:1300]; val=records[1300:1500]
    stats = {}
    for sx in ZODIAC:
        stats[sx]={}
        for pn in POS_NAMES: stats[sx][pn]={}
    for i in range(len(train)-1):
        curr,nxt=train[i],train[i+1]
        csx=curr["te_sx"]; yr=curr["year"]; nsx=nxt["te_sx"]
        for pidx,pn in enumerate(POS_NAMES):
            num=curr["ping_nums"][pidx] if pidx<6 else curr["te_num"]
            tsx=get_shengxiao_by_suima(num,yr)
            if tsx not in stats[csx][pn]: stats[csx][pn][tsx]={}
            for off in OFFSETS:
                new_num=offset_num(num,off); rsx=get_shengxiao_by_suima(new_num,yr)
                fk=(off,tsx,rsx)
                if fk not in stats[csx][pn][tsx]: stats[csx][pn][tsx][fk]={"total":0,"hit":0}
                stats[csx][pn][tsx][fk]["total"]+=1
                if rsx!=nsx: stats[csx][pn][tsx][fk]["hit"]+=1
    rules={}
    for sx in ZODIAC:
        rules[sx]={}
        for pn in POS_NAMES:
            rules[sx][pn]={}
            for tsx in stats[sx][pn]:
                for (off,_,killed),v in stats[sx][pn][tsx].items():
                    if v["total"]<MIN_SAMPLES: continue
                    rr=v["hit"]/v["total"]*100
                    if rr<MIN_KILL_RATE: continue
                    msf,cs=0,0; pidx=POS_NAMES.index(pn)
                    for j in range(len(train)-1):
                        if train[j]["te_sx"]!=sx: continue
                        yrj=train[j]["year"]; nj=train[j]["ping_nums"][pidx] if pidx<6 else train[j]["te_num"]
                        if get_shengxiao_by_suima(nj,yrj)!=tsx: continue
                        if train[j+1]["te_sx"]==killed: cs+=1; msf=max(msf,cs)
                        else: cs=0
                    if msf>MAX_STREAK: continue
                    if tsx not in rules[sx][pn]: rules[sx][pn][tsx]=[]
                    rules[sx][pn][tsx].append((off,killed,rr,v["total"],msf))
    for sx in rules:
        for pn in rules[sx]:
            for tsx in rules[sx][pn]: rules[sx][pn][tsx].sort(key=lambda x:x[2],reverse=True)
    graded={}
    for sx in rules:
        for pn in rules[sx]:
            pidx=POS_NAMES.index(pn)
            for tsx in rules[sx][pn]:
                for (off,killed,rr,samples,ts) in rules[sx][pn][tsx]:
                    th,tt,tst,tms=0,0,0,0
                    for j in range(len(val)-1):
                        if val[j]["te_sx"]!=sx: continue
                        yrj=val[j]["year"]; nj=val[j]["ping_nums"][pidx] if pidx<6 else val[j]["te_num"]
                        if get_shengxiao_by_suima(nj,yrj)!=tsx: continue
                        tt+=1
                        if val[j+1]["te_sx"]!=killed: th+=1; tst=0
                        else: tst+=1; tms=max(tms,tst)
                    tr=th/tt*100 if tt>0 else 0
                    g='discard'
                    if tt==0: pass
                    elif tr==100 and tms==0: g='gold'
                    elif tr>=95 and tms<=1: g='silver'
                    elif tr>=93 and tms<=2: g='bronze'
                    graded[(sx,pn,tsx,off,killed)]={'offset':off,'killed_sx':killed,'grade':g,'test_rate':tr,'samples':samples,'test_total':tt}
    def extract_l3_from_train(train_rec):
        stats_l3=defaultdict(lambda:{'total':0,'hit':0})
        for i in range(len(train_rec)-1):
            curr,nxt=train_rec[i],train_rec[i+1]; cy=curr["year"]; nsx=nxt["te_sx"]
            for idx,pos in enumerate(['平一','平二','平三','平四','平五','平六']):
                pnum=curr["ping_nums"][idx]; psx=get_shengxiao_by_suima(pnum,cy)
                for offset in range(1,12):
                    for dr,sign in [('+',1),('-',-1)]:
                        new_num=pnum+sign*offset
                        if new_num>49: new_num-=49
                        elif new_num<1: new_num+=49
                        nnsx=get_shengxiao_by_suima(new_num,cy)
                        key=(pos,dr,offset,psx,nnsx)
                        stats_l3[key]['total']+=1
                        if nnsx!=nsx: stats_l3[key]['hit']+=1
        rules_l3=[]
        for (pos,dr,offset,psx,ksx),v in stats_l3.items():
            if v['total']>=30:
                hr=round(v['hit']/v['total']*100,2)
                if hr>=L3_MIN_RATE: rules_l3.append({'位置':pos,'偏移':f'{dr}{offset}','平码生肖':psx,'所得生肖':ksx,'命中率':hr,'样本量':v['total']})
        if rules_l3:
            avg_s=sum(r['样本量'] for r in rules_l3)/len(rules_l3)
            return [r for r in rules_l3 if r['样本量']>=avg_s]
        return []
    l3=extract_l3_from_train(train)
    _CACHED_RULES=rules; _CACHED_GRADED=graded; _CACHED_L3=l3
    return rules,graded,l3

def model_reference96(records):
    if len(records)<2: return [],[]
    rules,graded,l3=build_fixed_rules(records)
    up_to=len(records); curr=records[up_to-1]; cur_sx=curr["te_sx"]; year=curr["year"]
    gold_votes=Counter(); te_kill_set=set()
    if cur_sx in rules:
        for pidx,pn in enumerate(POS_NAMES):
            if pn not in rules[cur_sx]: continue
            asx=curr["ping_sx"][pidx] if pidx<6 else cur_sx
            if asx not in rules[cur_sx][pn]: continue
            for (off,killed,_,_,_) in rules[cur_sx][pn][asx]:
                gi=graded.get((cur_sx,pn,asx,off,killed))
                if not gi: continue
                if gi['grade']=='gold': gold_votes[killed]+=1
                if pn=="特码" and gi['grade']=='gold': te_kill_set.add(killed)
    fixed_kill_set=set()
    p2=curr["ping_nums"][1]; fixed_kill_set.add(get_shengxiao_by_suima(offset_num(p2,3),year)); fixed_kill_set.add(cur_sx)
    missing=compute_missing(records,up_to)
    l3_kill_set=set()
    for rule in l3:
        pidx=POS_NAMES.index(rule['位置']) if rule['位置'] in POS_NAMES else -1
        if pidx<0: continue
        asx=curr["ping_sx"][pidx] if pidx<6 else cur_sx
        if asx==rule['平码生肖']: l3_kill_set.add(rule['所得生肖'])
    cool_map={}
    for dist in range(1,COOL_WINDOW+1):
        if up_to-dist>=0:
            sx=records[up_to-dist]["te_sx"]; pen=COOL_PENS[dist-1]
            if sx not in cool_map or pen>cool_map[sx]: cool_map[sx]=pen
    oracle_pool=set()
    if PING5_WEIGHT>0:
        p5=curr["ping_nums"][4]; cn=(p5-1+8)%49+1; csx=get_shengxiao_by_suima(cn,year); cidx=ZODIAC.index(csx)
        oracle_pool=set(ZODIAC[(cidx+i)%12] for i in range(-4,5))
    hechong_pool=set()
    if HECHONG_WEIGHT>0:
        hechong_pool.add(cur_sx)
        for s in SAN_HE.get(cur_sx,[]): hechong_pool.add(s)
        hechong_pool.add(LIU_HE.get(cur_sx,""))
        chong_sx=CHONG.get(cur_sx,""); hechong_pool.add(chong_sx)
        for s in SAN_HE.get(chong_sx,[]): hechong_pool.add(s)
        hechong_pool.add(LIU_HE.get(chong_sx,""))
    scores={}
    for s in ZODIAC:
        m=missing.get(s,0)
        if m>=MISSING_THRESH[1]: score=m*MISSING_WEIGHTS[2]
        elif m>=MISSING_THRESH[0]: score=m*MISSING_WEIGHTS[1]
        else: score=m*MISSING_WEIGHTS[0]
        v=gold_votes.get(s,0)
        if v>=4: score-=GOLD_PENS[3]
        elif v==3: score-=GOLD_PENS[2]
        elif v==2: score-=GOLD_PENS[1]
        elif v==1: score-=GOLD_PENS[0]
        if s in fixed_kill_set: score-=FIXED_WEIGHT
        if s in te_kill_set: score-=TE_WEIGHT
        if s in l3_kill_set: score-=L3_WEIGHT
        score-=cool_map.get(s,0)
        if s in oracle_pool: score+=PING5_WEIGHT
        if s in hechong_pool: score+=HECHONG_WEIGHT
        scores[s]=score
    sorted_all=sorted(scores.items(),key=lambda x:x[1],reverse=True)
    nine=[s for s,_ in sorted_all[:9]]
    six=sorted(nine,key=lambda s:scores.get(s,0),reverse=True)[:6]
    return nine, six

# ==================== 模型3：predict_54（内嵌） ====================
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
def model_predict54(records):
    if len(records)<2: return [],[]
    curr=records[-1]; cur_sx=curr["te_sx"]; year=curr["year"]
    if cur_sx not in SIGNALS_GOOD: return [],[]
    sigs=SIGNALS_GOOD[cur_sx]; missing=compute_missing(records,len(records))
    vc=Counter()
    for pos,stype,off,r in sigs:
        pos_idx=POS_NAMES.index(pos)
        num=curr["te_num"] if pos=="特码" else curr["ping_nums"][pos_idx]
        sx=curr["te_sx"] if pos=="特码" else curr["ping_sx"][pos_idx]
        if stype=="号码": c=get_shengxiao_by_suima(offset_num(num,off),year)
        else:
            sx_idx=ZODIAC.index(sx); c=ZODIAC[(sx_idx+off)%12]
        idx=ZODIAC.index(c); win=[ZODIAC[(idx+i)%12] for i in range(-r,r+1)]
        for s in win: vc[s]+=1
    ranked=sorted(vc.items(),key=lambda x:(-x[1],-missing.get(x[0],0)))
    nine=[s for s,_ in ranked[:9]]
    six=[s for s,_ in ranked[:6]]
    return nine, six

# ==================== 模型4：core_max（内嵌） ====================
RULES_PATH = os.path.join(BASE_DIR, "特肖杀肖规则库.json")
def model_max(records):
    if len(records)<2 or not os.path.exists(RULES_PATH): return [],[]
    with open(RULES_PATH,'r',encoding='utf-8') as f: SHAXIAO_RULES=json.load(f)
    up_to=len(records); curr=records[up_to-1]; cur_sx=curr["te_sx"]; year=curr["year"]
    gold_votes=Counter()
    for pos_idx,pos_name in enumerate(POS_NAMES):
        for off in OFFSETS:
            num=curr["ping_nums"][pos_idx] if pos_idx<6 else curr["te_num"]
            new_num=offset_num(num,off)
            trigger_sx=get_shengxiao_by_suima(num,year); result_sx=get_shengxiao_by_suima(new_num,year)
            rule_key=f"{cur_sx}|{pos_name}|{trigger_sx}|{off}|{result_sx}"
            if rule_key in SHAXIAO_RULES and SHAXIAO_RULES[rule_key]['grade']=='gold':
                gold_votes[SHAXIAO_RULES[rule_key]['killed_sx']]+=1
    killed=set(s for s,v in gold_votes.items() if v>=2)
    missing=compute_missing(records,up_to)
    safe=[s for s in ZODIAC if s not in killed]
    sorted_pool=sorted(safe, key=lambda s: missing.get(s,0), reverse=True)
    nine=sorted_pool[:9]
    if len(nine)<9:
        rem=sorted(killed,key=lambda s:gold_votes.get(s,0))
        for s in rem:
            if s not in nine: nine.append(s)
            if len(nine)>=9: break
    six=nine[:6]
    return nine, six

# ==================== 集成投票（方案ED·非线性） ====================
def ensemble_vote(records):
    n1, s1 = model_oracle(records)
    n2, s2 = model_reference96(records)
    n3, s3 = model_predict54(records)
    n4, s4 = model_max(records)

    votes_9 = Counter()
    for nine in [n1, n2, n3, n4]:
        for s in nine:
            votes_9[s] += 1
    votes_6 = Counter()
    for six in [s1, s2, s3, s4]:
        for s in six:
            votes_6[s] += 1

    # 非线性排名得分（前3名9分，4-6名3分，7-9名1分）
    rank_scores = Counter()
    for nine in [n1, n2, n3, n4]:
        for rank, s in enumerate(nine):
            if rank < 3:      # 前3名 → 9分
                rank_scores[s] += 9
            elif rank < 6:    # 4-6名 → 3分
                rank_scores[s] += 3
            else:             # 7-9名 → 1分
                rank_scores[s] += 1

    # 金标安全分
    gold_votes = Counter()
    if os.path.exists(RULES_PATH):
        with open(RULES_PATH, 'r', encoding='utf-8') as f:
            SHAXIAO_RULES = json.load(f)
        latest = records[-1]; cur_sx = latest["te_sx"]; year = latest["year"]
        for pos_idx, pos_name in enumerate(POS_NAMES):
            for off in OFFSETS:
                num = latest["ping_nums"][pos_idx] if pos_idx < 6 else latest["te_num"]
                new_num = offset_num(num, off)
                trigger_sx = get_shengxiao_by_suima(num, year)
                result_sx = get_shengxiao_by_suima(new_num, year)
                rule_key = f"{cur_sx}|{pos_name}|{trigger_sx}|{off}|{result_sx}"
                if rule_key in SHAXIAO_RULES and SHAXIAO_RULES[rule_key]['grade'] == 'gold':
                    gold_votes[SHAXIAO_RULES[rule_key]['killed_sx']] += 1

    # 遗漏值
    missing = compute_missing(records, len(records))

    # 方案ED·非线性：票数 → 非线性排名得分 → 金标安全分 → 遗漏值
    nine = [s for s, _ in sorted(votes_9.items(),
            key=lambda x: (-x[1], -rank_scores.get(x[0], 0), gold_votes.get(x[0], 0), -missing.get(x[0], 0)))[:9]]
    six = [s for s, _ in sorted(votes_6.items(),
            key=lambda x: (-x[1], -rank_scores.get(x[0], 0), gold_votes.get(x[0], 0), -missing.get(x[0], 0)))[:6]]

    return nine, six, votes_9, votes_6


# ==================== 生产预测 ====================
def predict_latest(auto_update=False):
    data = load_all_data(auto_update=auto_update)
    records = extract_records(data)
    if len(records) < 2:
        return {"error": "数据不足"}

    final_nine, final_six, votes_9, votes_6 = ensemble_vote(records)

    latest = records[-1]
    year = latest["year"]
    latest_full = data[-1] if data else {}

    # 动态尾数
    TAIL_WINDOW = 10
    tail_freq = Counter()
    for i in range(max(0, len(records) - TAIL_WINDOW - 1), len(records) - 1):
        tail_freq[records[i]["te_tail"]] += 1
    max_f = max(tail_freq.values()) if tail_freq else 1
    tail_scores = {t: max_f - tail_freq.get(t, 0) + 1 for t in range(10)}
    sorted_tails = sorted(tail_scores.items(), key=lambda x: x[1], reverse=True)
    top7_tails = [t for t, _ in sorted_tails[:7]]

    # 号码交集
    zodiac_nums = {s: get_suima_by_shengxiao(s, year) for s in ZODIAC}
    num_pool = []
    for s in final_six:
        best_n = None
        best_score = -1
        for n in zodiac_nums.get(s, []):
            if tail_scores.get(n % 10, 0) > best_score:
                best_score = tail_scores.get(n % 10, 0)
                best_n = n
        if best_n is not None and best_n not in num_pool:
            num_pool.append(best_n)
    for t, _ in sorted_tails:
        if len(num_pool) >= 12: break
        for s in final_six:
            if len(num_pool) >= 12: break
            for n in zodiac_nums.get(s, []):
                if n % 10 == t and n not in num_pool:
                    num_pool.append(n)
                    break
    final_numbers = num_pool[:12]

    zodiac_num_map = {}
    for n in final_numbers:
        z = get_shengxiao_by_suima(n, year)
        zodiac_num_map.setdefault(z, []).append(n)

    # 杀肖参考
    ping2 = latest["ping_nums"][1]
    new_num = ping2 + 3
    if new_num > 49: new_num -= 48
    kill_ref = get_shengxiao_by_suima(new_num, year)
    kill_zodiacs = [kill_ref, latest["te_sx"]]

    next_qihao = ""
    try:
        exp = latest["qishu"]
        if len(exp) >= 4:
            next_qihao = f"{exp[:4]}{int(exp[-3:]) + 1:03d}"
    except:
        pass

    return {
        "latest_issue": latest["qishu"],
        "latest_time": latest_full.get("openTime", ""),
        "latest_code": latest_full.get("openCode", ""),
        "latest_te_sx": latest["te_sx"],
        "latest_te_wei": latest["te_wei"],
        "latest_zodiac": to_simplified(latest_full.get("zodiac", "")),
        "latest_wave": latest_full.get("wave", ""),
        "next_qihao": next_qihao,
        "nine_pool": final_nine,
        "six_pool": final_six,
        "kill_zodiacs": kill_zodiacs,
        "range_zodiacs": final_nine,
        "numbers": final_numbers,
        "zodiac_num_map": zodiac_num_map,
        "top7_tails": top7_tails,
        "votes_9": dict(votes_9),
        "votes_6": dict(votes_6),
    }

# ==================== 输出文本 ====================
def output_text(result):
    lines = []
    lines.append(f"Ensemble_4in1预测 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 50)
    lines.append(f"基于期号: {result.get('latest_issue')}")
    lines.append(f"开奖时间: {result.get('latest_time', '')}")
    lines.append(f"开奖号码: {result.get('latest_code')}")
    lines.append(f"本期特肖: {result.get('latest_te_sx', '')}")
    lines.append(f"预测下期: {result.get('next_qihao')}")
    lines.append("-" * 30)

    lines.append(f"候选号码: {' '.join(str(n) for n in result.get('numbers', []))}")
    lines.append(f"大范围生肖: {' '.join(result.get('range_zodiacs', []))}")
    lines.append(f"重点候选生肖: {' '.join(result.get('six_pool', []))}")
    lines.append(f"杀肖: {' '.join(result.get('kill_zodiacs', []))}")
    for z, nums in result.get('zodiac_num_map', {}).items():
        lines.append(f"{z}: {','.join(str(n) for n in sorted(nums))}")
    lines.append(f"动态尾数: {' '.join(str(t) for t in result.get('top7_tails', []))}")
    lines.append("-" * 30)
    lines.append("四模型得票:")
    lines.append(f"  九肖: {dict(sorted(result.get('votes_9', {}).items(), key=lambda x: -x[1]))}")
    lines.append(f"  六肖: {dict(sorted(result.get('votes_6', {}).items(), key=lambda x: -x[1]))}")
    lines.append("=" * 50)
    # 九肖六肖放在末尾
    lines.append(f"★九肖预测: {', '.join(result.get('nine_pool', []))}")
    lines.append(f"★六肖预测: {', '.join(result.get('six_pool', []))}")
    return "\n".join(lines)

# ==================== 保存JS ====================
def save_js(result):
    js_path = os.path.join(BASE_DIR, "ensemble_data.js")
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
        "rangeZodiacs": result.get("range_zodiacs", []),
        "numbers": result.get("numbers", []),
        "zodiacNumMap": result.get("zodiac_num_map", {}),
        "top7Tails": result.get("top7_tails", []),
        "votes9": result.get("votes_9", {}),
        "votes6": result.get("votes_6", {}),
    }
    with open(js_path, "w", encoding="utf-8") as f:
        f.write("var ensembleData = ")
        json.dump(js_data, f, ensure_ascii=False, indent=2)
        f.write(";")
    print("[Ensemble] ensemble_data.js 已更新")

# ==================== 命中追踪 ====================
TRACK_DIR = os.path.join(BASE_DIR, "oracle记录")
TRACK_FILE = os.path.join(TRACK_DIR, "hit_track.json")

def load_hit_track():
    if not os.path.exists(TRACK_FILE):
        return []
    with open(TRACK_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_hit_track(track):
    os.makedirs(TRACK_DIR, exist_ok=True)
    with open(TRACK_FILE, "w", encoding="utf-8") as f:
        json.dump(track, f, ensure_ascii=False, indent=2)

def verify_last_prediction(records):
    track = load_hit_track()
    if not track:
        print("[Ensemble] 暂无历史预测记录，跳过校验")
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
    print(f"[Ensemble] 上期{predicted_issue}已校验: 九肖{hit9_str} 六肖{hit6_str}")
    return track

def append_prediction_to_track(issue, nine, six):
    track = load_hit_track()
    track.append({
        "issue": issue, "nine": nine, "six": six,
        "hit9": -1, "hit6": -1,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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

# ==================== 测试函数 ====================
def run_test():
    print("=" * 70)
    print("四模型集成投票 — 组合对比测试")
    print("=" * 70)
    data = load_all_data(auto_update=False)
    records = extract_records(data)
    TRAIN = 1500
    total_test = len(records) - TRAIN
    print(f"测试集: 第{TRAIN+1}~{len(records)}期，共{total_test}期\n")

    print("预生成预测...")
    all_nines = {"M1":[], "R96":[], "P54":[], "MAX":[]}
    all_sixes = {"M1":[], "R96":[], "P54":[], "MAX":[]}
    targets = []

    for idx in range(TRAIN, len(records)):
        hist = records[:idx]
        target = records[idx]["te_sx"]
        targets.append(target)

        n1, s1 = model_oracle(hist)
        n2, s2 = model_reference96(hist)
        n3, s3 = model_predict54(hist)
        n4, s4 = model_max(hist)

        all_nines["M1"].append(n1); all_sixes["M1"].append(s1)
        all_nines["R96"].append(n2); all_sixes["R96"].append(s2)
        all_nines["P54"].append(n3); all_sixes["P54"].append(s3)
        all_nines["MAX"].append(n4); all_sixes["MAX"].append(s4)

        if (idx - TRAIN) % 200 == 0:
            print(f"  进度: {idx - TRAIN}/{total_test}")

    combos = [
        ("M1单独", ["M1"]),
        ("M1+R96", ["M1", "R96"]),
        ("M1+R96+P54", ["M1", "R96", "P54"]),
        ("四模型全部", ["M1", "R96", "P54", "MAX"]),
    ]

    print(f"\n[组合投票结果]")
    for combo_name, model_names in combos:
        hit_9, hit_6 = [], []
        for i in range(total_test):
            target = targets[i]
            # 九肖投票
            votes_9 = Counter()
            for mn in model_names:
                for s in all_nines[mn][i]:
                    votes_9[s] += 1

            # 非线性排名得分
            rank_scores = Counter()
            for mn in model_names:
                for rank, s in enumerate(all_nines[mn][i]):
                    if rank < 3:
                        rank_scores[s] += 9
                    elif rank < 6:
                        rank_scores[s] += 3
                    else:
                        rank_scores[s] += 1

            # 遗漏值
            missing = compute_missing(records, TRAIN + i)

            # 金标安全分
            gold_votes = Counter()
            if os.path.exists(RULES_PATH):
                with open(RULES_PATH, 'r', encoding='utf-8') as f:
                    SHAXIAO_RULES = json.load(f)
                curr = records[TRAIN + i - 1]
                cur_sx = curr["te_sx"]
                year = curr["year"]
                for pos_idx, pos_name in enumerate(POS_NAMES):
                    for off in OFFSETS:
                        num = curr["ping_nums"][pos_idx] if pos_idx < 6 else curr["te_num"]
                        new_num = offset_num(num, off)
                        trigger_sx = get_shengxiao_by_suima(num, year)
                        result_sx = get_shengxiao_by_suima(new_num, year)
                        rule_key = f"{cur_sx}|{pos_name}|{trigger_sx}|{off}|{result_sx}"
                        if rule_key in SHAXIAO_RULES and SHAXIAO_RULES[rule_key]['grade'] == 'gold':
                            gold_votes[SHAXIAO_RULES[rule_key]['killed_sx']] += 1

            # 方案ED·非线性
            nine = [s for s, _ in sorted(votes_9.items(),
                    key=lambda x: (-x[1], -rank_scores.get(x[0], 0), gold_votes.get(x[0], 0), -missing.get(x[0], 0)))[:9]]

            # 六肖投票
            votes_6 = Counter()
            for mn in model_names:
                for s in all_sixes[mn][i]:
                    votes_6[s] += 1

            six = [s for s, _ in sorted(votes_6.items(),
                    key=lambda x: (-x[1], -rank_scores.get(x[0], 0), gold_votes.get(x[0], 0), -missing.get(x[0], 0)))[:6]]

            hit_9.append(target in nine)
            hit_6.append(target in six)

        rate9, ms9, _ = compute_streak_stats(hit_9)
        rate6, ms6, dist6 = compute_streak_stats(hit_6)
        print(f"  {combo_name:<20} 九肖:{rate9:.2f}%  六肖:{rate6:.2f}%  六肖最大连错:{ms6}期")

    print(f"\n[基线] M1单独九肖80.29% 六肖55.54%")

# ==================== 主入口 ====================
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--test", action="store_true", help="组合对比测试")
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

    # 生产预测
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

        import webbrowser
        hp = os.path.join(BASE_DIR, "index.html")
        if os.path.exists(hp):
            webbrowser.open(hp)