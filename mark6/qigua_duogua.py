# qigua_duogua.py - 两期交错多卦阵生成模块（11卦版）
from qigua import (numbers_from_record, BAGUA_YAO, GUA_NAMES, NAZHI_TABLE, DIZHI_SX, _single_gua_from_numbers)

def _cuogua_xia_shang_num(xia_num, shang_num):
    xia_yao = BAGUA_YAO.get(xia_num)
    shang_yao = BAGUA_YAO.get(shang_num)
    if xia_yao is None or shang_yao is None: return None,None
    all_yao = xia_yao + shang_yao
    cuo_yao = [1-y for y in all_yao]
    def _num(yao):
        for n,seq in BAGUA_YAO.items():
            if seq==yao: return n
        return 8
    return _num(cuo_yao[:3]), _num(cuo_yao[3:])

def build_two_period_multi_gua(prev_record, curr_record):
    prev_nums = numbers_from_record(prev_record)
    curr_nums = numbers_from_record(curr_record)
    if not prev_nums or not curr_nums: return []
    P_prev = prev_nums[:6]; T_prev = prev_nums[6]
    P_curr = curr_nums[:6]; T_curr = curr_nums[6]
    dong_yao = (T_prev + T_curr) % 6
    if dong_yao == 0: dong_yao = 6
    predictions = []
    # 卦1
    s1 = sum(P_prev)%8; s2 = sum(P_curr)%8
    s1=8 if s1==0 else s1; s2=8 if s2==0 else s2
    predictions.append(_single_gua_from_numbers(s1,s2,dong_yao))
    # 卦2
    s1 = sum(P_prev[3:])%8; s2 = sum(P_curr[:3])%8
    s1=8 if s1==0 else s1; s2=8 if s2==0 else s2
    predictions.append(_single_gua_from_numbers(s1,s2,dong_yao))
    # 卦3
    s1 = sum(P_prev[:3])%8; s2 = sum(P_curr[3:])%8
    s1=8 if s1==0 else s1; s2=8 if s2==0 else s2
    predictions.append(_single_gua_from_numbers(s1,s2,dong_yao))
    # 卦4-9
    for i in range(6):
        n1 = P_prev[i]%8; n2 = P_curr[i]%8
        n1=8 if n1==0 else n1; n2=8 if n2==0 else n2
        predictions.append(_single_gua_from_numbers(n1,n2,dong_yao))
    # 卦10
    t1 = T_prev%8; t2 = T_curr%8
    t1=8 if t1==0 else t1; t2=8 if t2==0 else t2
    predictions.append(_single_gua_from_numbers(t1,t2,dong_yao))
    # 卦11
    cx,cs = _cuogua_xia_shang_num(t1,t2)
    if cx is not None and cs is not None:
        predictions.append(_single_gua_from_numbers(cx,cs,dong_yao))
    else:
        predictions.append(None)
    return [p for p in predictions if p is not None]