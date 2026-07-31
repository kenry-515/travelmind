"""Deep check landmark issues."""
import json

with open("data/attractions.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# 1. Check 拙政园 - find the real one
print("=" * 60)
print("🔍 检查拙政园:")
for a in data["attractions"]:
    if "拙政" in a["name"] and a["city"] == "苏州":
        print(f"  {a['name']} ({a['city']})")
        print(f"    tags: {a.get('tags', [])}")
        print(f"    popularity: {a.get('popularity_score')}")
        print(f"    description: {a.get('description', '')[:80]}...")
        print()

# 2. Check 世界之窗 in 深圳
print("=" * 60)
print("🔍 检查深圳世界之窗:")
for a in data["attractions"]:
    if "世界之窗" in a["name"]:
        print(f"  {a['name']} ({a['city']})")
        print(f"    tags: {a.get('tags', [])}")
        print(f"    popularity: {a.get('popularity_score')}")
        print()

# 3. 检查故宫 tags 是否需要补充"文化"
print("=" * 60)
print("🔍 检查北京核心地标 tags:")
beijing_landmarks = ["故宫", "颐和园", "天坛", "圆明园"]
for name in beijing_landmarks:
    for a in data["attractions"]:
        if a["name"] == name:
            tags = a.get("tags", [])
            has_culture = "文化" in tags
            has_history = "历史" in tags
            print(f"  {name}: tags包含文化={has_culture}, 历史={has_history}")
            break
    else:
        print(f"  {name}: 未找到")
