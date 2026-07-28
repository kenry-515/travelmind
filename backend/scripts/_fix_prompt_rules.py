"""Add prompt rules 12-17 back to planning_agent.py."""
path = 'app/agents/planning_agent.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

old_marker = 'tips 中必须包含当季天气应对建议（遮阳/雨具/室内备选方案）"""'
new_rules = '''tips 中必须包含当季天气应对建议（遮阳/雨具/室内备选方案）
12.【POI名称不可重复】不同天之间不得出现相同的poi名称。每个景点在全行程中只出现一次。
13.【标签大类多样性】景点应覆盖至少3个不同标签大类（自然/人文/美食/购物/娱乐/运动/艺术），避免全行程同质化。
14.【极端预算场景】预算极低（经济/穷游/500元以下）时优先免费景点，餐饮路边摊/小吃，住宿青旅，交通步行公交。
15.【矛盾需求处理】用户有矛盾需求时优先满足安全可行性，在tips中说明无法同时满足。
16.【特殊人群】老人/小孩/孕妇：无剧烈运动、少阶梯、有空调、近医疗设施；tips包含专门建议。
17.【极寒/极热】冬季极寒：户外项目不超60分钟室内外交替；夏季酷暑：午后仅排室内项目。\""""

if old_marker in c:
    c = c.replace(old_marker, new_rules)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(c)
    print('OK: prompt rules 12-17 added')
else:
    print('FAIL: marker not found')
    # Debug
    idx = c.find('tips 中必须')
    if idx >= 0:
        print(f'Found at {idx}: {repr(c[idx:idx+80])}')
