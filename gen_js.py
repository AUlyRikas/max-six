import json, os, re

with open('prediction_max.txt', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.rfind('基于期号')
if idx == -1:
    print('ERROR: 找不到基于期号')
    exit(1)

last_block = text[idx:]

def extract(key):
    m = re.search(rf'{key}\s*[:：]\s*(.+)', last_block)
    return m.group(1).strip() if m else ''

latest_issue = extract('基于期号')
latest_time = extract('开奖时间')
latest_code = extract('开奖号码').replace(' ', '')
te_sx = extract('本期特肖').split('(')[0].strip()
te_wei_match = extract('本期特肖')
te_wei = '0'
if '尾' in te_wei_match:
    te_wei = te_wei_match.split('尾')[1].split(')')[0].strip()
next_issue = extract('预测下期')
kills_str = extract('规则库杀肖')
kills = [s.strip() for s in kills_str.split(',') if s.strip()]
nine_raw = extract('规则库九肖')
if '[' in nine_raw:
    nine = [s.strip() for s in nine_raw.split('[')[0].strip().rstrip(',').split(',') if s.strip()]
else:
    nine = [s.strip() for s in nine_raw.split(',') if s.strip()]
six = [s.strip() for s in extract('★规则库六肖').split(',') if s.strip()]

raw_codes = [c.strip() for c in latest_code.split(',') if c.strip()]
if not raw_codes:
    raw_codes = ['0','0','0','0','0','0','0']
code_nums = [int(n) for n in raw_codes]

red_set = {1,2,7,8,12,13,18,19,23,24,29,30,34,35,40,45,46}
blue_set = {3,4,9,10,14,15,20,25,26,31,36,37,41,42,47,48}
waves = ['red' if n in red_set else 'blue' if n in blue_set else 'green' for n in code_nums]
zodiac_list = ['马','蛇','龙','兔','虎','牛','鼠','猪','狗','鸡','猴','羊']
zodiacs = [zodiac_list[(n-1)%12] for n in code_nums]

js = f'''var predictionMaxData = {{
  "time": "{latest_time}",
  "issue": "{latest_issue}",
  "code": "{latest_code}",
  "zodiac": "{','.join(zodiacs)}",
  "wave": "{','.join(waves)}",
  "teSx": "{te_sx}",
  "teWei": {int(te_wei) if te_wei.isdigit() else 0},
  "nextIssue": "{next_issue}",
  "kills": {json.dumps(kills, ensure_ascii=False)},
  "ninePool": {json.dumps(nine, ensure_ascii=False)},
  "sixPool": {json.dumps(six, ensure_ascii=False)},
  "filled": []
}};
'''

with open('prediction_max.js', 'w', encoding='utf-8') as f:
    f.write(js)
print('prediction_max.js generated successfully')
