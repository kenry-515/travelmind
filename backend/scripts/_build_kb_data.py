"""Build KB with WebSearch-verified POI data."""
import json
from collections import Counter

with open('data/attractions.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
pois = data.get('attractions', data if isinstance(data, list) else [])
existing = {(p.get('name','').strip(), p.get('city','').strip()) for p in pois}

new_pois = [
    # 拉萨
    {'name':'曲水俊巴渔村','city':'拉萨','tags':['小众','文化','美食','自然'],'lat':29.32,'lon':90.78,'popularity_score':7,'price_level':2,'best_time':'夏季'},
    {'name':'拉鲁湿地','city':'拉萨','tags':['自然','摄影','休闲'],'lat':29.67,'lon':91.10,'popularity_score':6,'price_level':1,'best_time':'夏季'},
    {'name':'扎基寺','city':'拉萨','tags':['寺庙','历史','文化'],'lat':29.66,'lon':91.12,'popularity_score':7,'price_level':1,'best_time':'全年'},
    {'name':'南山半山观景台','city':'拉萨','tags':['摄影','地标','休闲'],'lat':29.63,'lon':91.13,'popularity_score':6,'price_level':1,'best_time':'全年'},
    # 大连
    {'name':'东关街','city':'大连','tags':['历史','建筑','打卡'],'lat':38.92,'lon':121.63,'popularity_score':7,'price_level':1,'best_time':'全年'},
    {'name':'俄罗斯风情街','city':'大连','tags':['建筑','打卡','摄影'],'lat':38.92,'lon':121.64,'popularity_score':6,'price_level':1,'best_time':'全年'},
    {'name':'东港威尼斯水城','city':'大连','tags':['建筑','摄影','休闲'],'lat':38.92,'lon':121.68,'popularity_score':8,'price_level':2,'best_time':'夏季'},
    {'name':'琥珀湾','city':'大连','tags':['自然','海岛','休闲'],'lat':38.86,'lon':121.70,'popularity_score':6,'price_level':1,'best_time':'夏季'},
    {'name':'瓜皮岛','city':'大连','tags':['自然','海岛','小众'],'lat':39.45,'lon':122.23,'popularity_score':5,'price_level':2,'best_time':'夏季'},
    {'name':'钻石湾滨海公园','city':'大连','tags':['自然','摄影','休闲'],'lat':38.95,'lon':121.62,'popularity_score':6,'price_level':1,'best_time':'夏季'},
    # 哈尔滨
    {'name':'老道外中华巴洛克','city':'哈尔滨','tags':['历史','建筑','摄影'],'lat':45.78,'lon':126.64,'popularity_score':7,'price_level':1,'best_time':'全年'},
    {'name':'伏尔加庄园','city':'哈尔滨','tags':['建筑','摄影','自然'],'lat':45.75,'lon':126.68,'popularity_score':7,'price_level':3,'best_time':'夏季'},
    {'name':'哈尔滨大剧院','city':'哈尔滨','tags':['建筑','艺术','地标'],'lat':45.80,'lon':126.57,'popularity_score':8,'price_level':2,'best_time':'全年'},
    {'name':'花园街黄房子咖啡','city':'哈尔滨','tags':['文艺','咖啡','打卡'],'lat':45.74,'lon':126.65,'popularity_score':6,'price_level':2,'best_time':'全年'},
    {'name':'红专街早市','city':'哈尔滨','tags':['美食','夜市','休闲'],'lat':45.77,'lon':126.62,'popularity_score':7,'price_level':1,'best_time':'全年'},
    # 福州
    {'name':'上下杭历史文化街区','city':'福州','tags':['历史','建筑','美食'],'lat':26.06,'lon':119.31,'popularity_score':7,'price_level':1,'best_time':'全年'},
    {'name':'烟台山历史风貌区','city':'福州','tags':['建筑','文艺','摄影'],'lat':26.04,'lon':119.31,'popularity_score':7,'price_level':1,'best_time':'全年'},
    {'name':'林浦村','city':'福州','tags':['历史','古镇','文化'],'lat':26.01,'lon':119.35,'popularity_score':5,'price_level':1,'best_time':'全年'},
    {'name':'海坛岛','city':'福州','tags':['自然','海岛','摄影'],'lat':25.50,'lon':119.79,'popularity_score':6,'price_level':2,'best_time':'夏季'},
    {'name':'福道','city':'福州','tags':['自然','休闲','摄影'],'lat':26.07,'lon':119.27,'popularity_score':7,'price_level':1,'best_time':'全年'},
    # 青岛
    {'name':'小青岛','city':'青岛','tags':['自然','摄影','海岛'],'lat':36.05,'lon':120.32,'popularity_score':7,'price_level':1,'best_time':'夏季'},
    {'name':'小麦岛公园','city':'青岛','tags':['自然','摄影','休闲'],'lat':36.05,'lon':120.40,'popularity_score':7,'price_level':1,'best_time':'夏季'},
    {'name':'沙子口海湾','city':'青岛','tags':['自然','摄影','休闲'],'lat':36.09,'lon':120.48,'popularity_score':6,'price_level':1,'best_time':'夏季'},
    {'name':'青山渔村','city':'青岛','tags':['古镇','自然','摄影'],'lat':36.16,'lon':120.67,'popularity_score':7,'price_level':2,'best_time':'夏季'},
    {'name':'齐东路十字街坊','city':'青岛','tags':['文艺','建筑','打卡'],'lat':36.07,'lon':120.33,'popularity_score':6,'price_level':1,'best_time':'全年'},
    # 昆明
    {'name':'麻园米轨公园','city':'昆明','tags':['文艺','历史','打卡'],'lat':25.06,'lon':102.70,'popularity_score':7,'price_level':1,'best_time':'全年'},
    {'name':'大墨雨村','city':'昆明','tags':['古镇','美食','文艺'],'lat':25.28,'lon':102.58,'popularity_score':5,'price_level':2,'best_time':'全年'},
    {'name':'小白龙森林公园','city':'昆明','tags':['自然','休闲','探险'],'lat':24.92,'lon':103.14,'popularity_score':6,'price_level':1,'best_time':'夏季'},
    {'name':'巡津街','city':'昆明','tags':['文艺','咖啡','打卡'],'lat':25.03,'lon':102.71,'popularity_score':6,'price_level':1,'best_time':'全年'},
    {'name':'百草村','city':'昆明','tags':['古镇','美食','文化'],'lat':24.83,'lon':102.64,'popularity_score':5,'price_level':2,'best_time':'全年'},
]

added = 0
for p in new_pois:
    key = (p['name'].strip(), p['city'].strip())
    if key not in existing:
        p['data_source'] = 'websearch_verified'
        p['name_normalized'] = p['name']
        p['confidence'] = 0.8
        p['source_id'] = ''
        pois.append(p)
        existing.add(key)
        added += 1

data['attractions'] = pois
with open('data/attractions.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

city_counts = Counter(p.get('city','') for p in pois)
print(f'KB: {len(pois)} POI（+{added} verified）')
print(f'缺坐标: {len([p for p in pois if not p.get("lat") or not p.get("lon")])}')
for c in ['拉萨','大连','哈尔滨','福州','青岛','昆明']:
    print(f'  {c}: {city_counts.get(c, 0)} POI')
