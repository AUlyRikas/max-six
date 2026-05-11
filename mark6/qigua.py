# qigua.py - 完整京房八宫纳支版（包含内部成卦函数）
BAGUA_YAO = {
    1:[1,1,1],2:[1,1,0],3:[1,0,1],4:[1,0,0],
    5:[0,1,1],6:[0,1,0],7:[0,0,1],8:[0,0,0]
}
DIZHI_SX = {"子":"鼠","丑":"牛","寅":"虎","卯":"兔","辰":"龙","巳":"蛇","午":"马","未":"羊","申":"猴","酉":"鸡","戌":"狗","亥":"猪"}

PURE_GUA_NAZHI = {
    "乾":["子","寅","辰","午","申","戌"],
    "震":["子","寅","辰","午","申","戌"],
    "坎":["寅","辰","午","申","戌","子"],
    "艮":["辰","午","申","戌","子","寅"],
    "坤":["未","巳","卯","丑","亥","酉"],
    "巽":["丑","亥","酉","未","巳","卯"],
    "离":["卯","丑","亥","酉","未","巳"],
    "兑":["巳","卯","丑","亥","酉","未"]
}

GONG_MAP = {"乾为天":"乾","震为雷":"震","坎为水":"坎","艮为山":"艮","坤为地":"坤","巽为风":"巽","离为火":"离","兑为泽":"兑"}

GUA_NAMES = {}
_RAW = {
    1:{1:"乾为天",2:"泽天夬",3:"火天大有",4:"雷天大壮",5:"风天小畜",6:"水天需",7:"山天大畜",8:"地天泰"},
    2:{1:"天泽履",2:"兑为泽",3:"火泽睽",4:"雷泽归妹",5:"风泽中孚",6:"水泽节",7:"山泽损",8:"地泽临"},
    3:{1:"天火同人",2:"泽火革",3:"离为火",4:"雷火丰",5:"风火家人",6:"水火既济",7:"山火贲",8:"地火明夷"},
    4:{1:"天雷无妄",2:"泽雷随",3:"火雷噬嗑",4:"震为雷",5:"风雷益",6:"水雷屯",7:"山雷颐",8:"地雷复"},
    5:{1:"天风姤",2:"泽风大过",3:"火风鼎",4:"雷风恒",5:"巽为风",6:"水风井",7:"山风蛊",8:"地风升"},
    6:{1:"天水讼",2:"泽水困",3:"火水未济",4:"雷水解",5:"风水涣",6:"坎为水",7:"山水蒙",8:"地水师"},
    7:{1:"天山遁",2:"泽山咸",3:"火山旅",4:"雷山小过",5:"风山渐",6:"水山蹇",7:"艮为山",8:"地山谦"},
    8:{1:"天地否",2:"泽地萃",3:"火地晋",4:"雷地豫",5:"风地观",6:"水地比",7:"山地剥",8:"坤为地"}
}
for s,r in _RAW.items():
    for x,n in r.items():
        GUA_NAMES[(s,x)] = n

def _find_gua_name_by_yao(yao_list):
    if len(yao_list)!=6: return None
    xia_yao = yao_list[:3]; shang_yao = yao_list[3:]
    def _num(yao):
        for num,seq in BAGUA_YAO.items():
            if seq==yao: return num
        return None
    xn = _num(xia_yao); sn = _num(shang_yao)
    if xn is None or sn is None: return None
    return GUA_NAMES.get((sn,xn))

def generate_full_nazhi():
    PURE_YAO = {"乾":[1,1,1,1,1,1],"震":[1,0,0,1,0,0],"坎":[0,1,0,0,1,0],"艮":[0,0,1,0,0,1],
                "坤":[0,0,0,0,0,0],"巽":[0,1,1,0,1,1],"离":[1,0,1,1,0,1],"兑":[1,1,0,1,1,0]}
    nazhi_full = {}
    handled = set()
    for gong_name, pure_name in [("乾","乾为天"),("震","震为雷"),("坎","坎为水"),("艮","艮为山"),
                                 ("坤","坤为地"),("巽","巽为风"),("离","离为火"),("兑","兑为泽")]:
        base_zhi = PURE_GUA_NAZHI[gong_name]
        pure_yao = PURE_YAO[gong_name].copy()
        nazhi_full[pure_name] = base_zhi.copy()
        handled.add(pure_name)
        current_yao = pure_yao.copy()
        for shi in range(1,6):
            idx = shi-1
            current_yao[idx] = 1 - current_yao[idx]
            name = _find_gua_name_by_yao(current_yao)
            if name and name not in handled:
                nazhi_full[name] = base_zhi.copy()
                handled.add(name)
            else:
                break
        wushi_yao = pure_yao.copy()
        for idx in range(5): wushi_yao[idx] = 1 - wushi_yao[idx]
        youhun_yao = wushi_yao.copy()
        youhun_yao[3] = 1 - youhun_yao[3]
        name = _find_gua_name_by_yao(youhun_yao)
        if name and name not in handled:
            nazhi_full[name] = base_zhi.copy()
            handled.add(name)
        guihun_yao = youhun_yao.copy()
        for idx in range(3): guihun_yao[idx] = 1 - guihun_yao[idx]
        name = _find_gua_name_by_yao(guihun_yao)
        if name and name not in handled:
            nazhi_full[name] = base_zhi.copy()
            handled.add(name)
    for (s,x), name in GUA_NAMES.items():
        if name not in nazhi_full:
            nazhi_full[name] = PURE_GUA_NAZHI["乾"]
    return nazhi_full

NAZHI_TABLE = generate_full_nazhi()

def get_nazhi(gua_name, yao_pos):
    if gua_name not in NAZHI_TABLE: return None
    return NAZHI_TABLE[gua_name][yao_pos-1]

def numbers_from_record(record):
    code = record.get("openCode","")
    parts = code.split(",")
    nums = []
    for p in parts:
        if p.strip().isdigit(): nums.append(int(p.strip()))
    if len(nums) < 7: return None
    return nums

def _single_gua_from_numbers(xia_num, shang_num, dong_yao):
    """核心成卦函数：输入下卦数、上卦数、动爻位，返回预测生肖"""
    if xia_num not in BAGUA_YAO or shang_num not in BAGUA_YAO: return None
    ben_yao = BAGUA_YAO[xia_num] + BAGUA_YAO[shang_num]
    bian_yao = ben_yao.copy()
    idx = dong_yao-1
    bian_yao[idx] = 1 - bian_yao[idx]
    def _num(yao):
        for n,seq in BAGUA_YAO.items():
            if seq==yao: return n
        return None
    bx = _num(bian_yao[:3])
    bs = _num(bian_yao[3:])
    if bx is None or bs is None: return None
    bg_name = GUA_NAMES.get((bs,bx))
    if not bg_name: return None
    dizhi = get_nazhi(bg_name, dong_yao)
    if not dizhi: return None
    return DIZHI_SX.get(dizhi)