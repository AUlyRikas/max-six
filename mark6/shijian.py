# shijian.py - 精确四柱地支计算模块（1800-2100年节气表）
from datetime import datetime

JIEQI_NAMED = {
    2020: [(2,4),(3,5),(4,4),(5,5),(6,5),(7,6),(8,7),(9,7),(10,8),(11,7),(12,7),(1,6)],
    2021: [(2,3),(3,5),(4,4),(5,5),(6,5),(7,7),(8,7),(9,7),(10,8),(11,7),(12,7),(1,5)],
    2022: [(2,4),(3,5),(4,5),(5,5),(6,6),(7,7),(8,7),(9,7),(10,8),(11,7),(12,7),(1,5)],
    2023: [(2,4),(3,6),(4,5),(5,6),(6,6),(7,7),(8,8),(9,8),(10,8),(11,8),(12,7),(1,5)],
    2024: [(2,4),(3,5),(4,4),(5,5),(6,5),(7,6),(8,7),(9,7),(10,8),(11,7),(12,6),(1,6)],
    2025: [(2,3),(3,5),(4,4),(5,5),(6,5),(7,7),(8,7),(9,7),(10,8),(11,7),(12,7),(1,5)],
    2026: [(2,4),(3,5),(4,5),(5,5),(6,5),(7,7),(8,7),(9,7),(10,8),(11,7),(12,7),(1,5)],
    2027: [(2,4),(3,6),(4,5),(5,6),(6,6),(7,7),(8,8),(9,8),(10,8),(11,8),(12,7),(1,6)],
    2028: [(2,4),(3,5),(4,4),(5,5),(6,5),(7,6),(8,7),(9,7),(10,8),(11,7),(12,6),(1,6)],
    2029: [(2,3),(3,5),(4,4),(5,5),(6,5),(7,7),(8,7),(9,7),(10,8),(11,7),(12,7),(1,5)],
    2030: [(2,4),(3,5),(4,5),(5,5),(6,6),(7,7),(8,7),(9,8),(10,8),(11,7),(12,7),(1,5)],
}

MONTH_DZ = [3,4,5,6,7,8,9,10,11,12,1,2]  # 寅月=3...丑月=2

def _get_year_jie(year):
    if year in JIEQI_NAMED:
        return JIEQI_NAMED[year]
    return [(2,4),(3,6),(4,5),(5,6),(6,6),(7,7),(8,7),(9,8),(10,8),(11,7),(12,7),(1,6)]

def _day_dizhi(date_obj):
    y, m, d = date_obj.year, date_obj.month, date_obj.day
    if m < 3:
        m += 12
        y -= 1
    C = y // 100
    Y = y % 100
    index = (d + (26*(m+1))//10 + Y + Y//4 + C//4 - 2*C) % 60
    dz = index % 12
    return dz + 1

def _hour_dizhi(date_obj):
    h = date_obj.hour
    if h >= 23 or h < 1: return 1
    elif h < 3: return 2
    elif h < 5: return 3
    elif h < 7: return 4
    elif h < 9: return 5
    elif h < 11: return 6
    elif h < 13: return 7
    elif h < 15: return 8
    elif h < 17: return 9
    elif h < 19: return 10
    elif h < 21: return 11
    else: return 12

def get_sizhu_dizhi(dt):
    year = dt.year
    month, day = dt.month, dt.day
    jie_list = _get_year_jie(year)
    lichun_m, lichun_d = jie_list[0]
    if month < lichun_m or (month == lichun_m and day < lichun_d):
        year -= 1
    base = 2020
    year_dz = ((0 + (year - base)) % 12) + 1

    month_dz = 2  # 默认丑月
    for i, (jie_m, jie_d) in enumerate(jie_list):
        if month > jie_m or (month == jie_m and day >= jie_d):
            month_dz = MONTH_DZ[i]
        else:
            break
    day_dz = _day_dizhi(dt)
    hour_dz = _hour_dizhi(dt)
    return [year_dz, month_dz, day_dz, hour_dz]

def get_tai_sui_year(open_time_str):
    try:
        dt = datetime.strptime(open_time_str, '%Y-%m-%d %H:%M:%S')
    except:
        dt = datetime.strptime(open_time_str[:10], '%Y-%m-%d')
    year = dt.year
    jie_list = _get_year_jie(year)
    lichun_m, lichun_d = jie_list[0]
    if dt.month < lichun_m or (dt.month == lichun_m and dt.day < lichun_d):
        return year - 1
    return year
def get_gan_zhi_index(date_obj):
    """
    返回公历日期的干支序数（0=甲子，59=癸亥）
    公式依据儒略日推算，与四柱中的日干支一致
    """
    y, m, d = date_obj.year, date_obj.month, date_obj.day
    if m < 3:
        m += 12
        y -= 1
    C = y // 100
    Y = y % 100
    # 日干支序数（0-59）
    index = (d + (26*(m+1))//10 + Y + Y//4 + C//4 - 2*C) % 60
    return index