"""Check tags of key landmarks."""
import json

with open("data/attractions.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Check key landmarks
landmarks = ["故宫", "拙政园", "世界之窗", "宽窄巷子", "锦里"]

for landmark in landmarks:
    found = False
    for a in data["attractions"]:
        if landmark in a["name"]:
            found = True
            print(f"📍 {a['name']} ({a['city']})")
            print(f"   tags: {a.get('tags', [])}")
            print(f"   popularity: {a.get('popularity_score', 'N/A')}")
            print(f"   price: {a.get('price_level', 'N/A')}")
            print()
            break
    if not found:
        print(f"❌ {landmark} 未找到")
        print()
