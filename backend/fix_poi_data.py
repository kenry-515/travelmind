"""Fix POI tags and popularity scores for key landmarks."""
import json

with open("data/attractions.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Fixes to apply
fixes = {
    # 北京核心地标 - 添加"文化"标签
    "故宫": {
        "add_tags": ["文化", "古迹", "皇家"],
        "popularity_score": 10
    },
    "颐和园": {
        "add_tags": ["文化", "古迹", "皇家", "园林"],
        "popularity_score": 10
    },
    "天坛": {
        "add_tags": ["文化", "古迹", "皇家"],
        "popularity_score": 9
    },
    "圆明园": {
        "add_tags": ["文化", "古迹", "历史遗址"],
        "popularity_score": 9
    },
    # 苏州拙政园
    "拙政园": {
        "add_tags": ["文化", "古迹", "5A"],
        "popularity_score": 10
    },
    # 深圳世界之窗
    "世界之窗 (深圳)": {
        "add_tags": ["主题乐园", "5A", "文化"],
        "popularity_score": 9
    },
}

fixed_count = 0
for a in data["attractions"]:
    name = a["name"]
    
    # Match by name (handle special cases)
    if name == "故宫":
        a["tags"] = list(set(a.get("tags", []) + fixes["故宫"]["add_tags"]))
        a["popularity_score"] = fixes["故宫"]["popularity_score"]
        fixed_count += 1
        print(f"✅ 修复: {name} - 添加文化标签, popularity=10")
        
    elif name == "颐和园":
        a["tags"] = list(set(a.get("tags", []) + fixes["颐和园"]["add_tags"]))
        a["popularity_score"] = fixes["颐和园"]["popularity_score"]
        fixed_count += 1
        print(f"✅ 修复: {name} - 添加文化标签, popularity=10")
        
    elif name == "天坛":
        a["tags"] = list(set(a.get("tags", []) + fixes["天坛"]["add_tags"]))
        a["popularity_score"] = fixes["天坛"]["popularity_score"]
        fixed_count += 1
        print(f"✅ 修复: {name} - 添加文化标签, popularity=9")
        
    elif name == "圆明园":
        a["tags"] = list(set(a.get("tags", []) + fixes["圆明园"]["add_tags"]))
        a["popularity_score"] = fixes["圆明园"]["popularity_score"]
        fixed_count += 1
        print(f"✅ 修复: {name} - 添加文化标签, popularity=9")
        
    elif name == "拙政园" and a["city"] == "苏州" and a.get("popularity_score") is None:
        # Only fix the real 拙政园 (not the restaurant)
        if "园林" in a.get("tags", []):
            a["tags"] = list(set(a.get("tags", []) + fixes["拙政园"]["add_tags"]))
            a["popularity_score"] = fixes["拙政园"]["popularity_score"]
            fixed_count += 1
            print(f"✅ 修复: {name} - 添加文化/古迹/5A标签, popularity=10")
            
    elif name == "世界之窗" and a["city"] == "深圳":
        a["tags"] = list(set(a.get("tags", []) + fixes["世界之窗 (深圳)"]["add_tags"]))
        a["popularity_score"] = fixes["世界之窗 (深圳)"]["popularity_score"]
        fixed_count += 1
        print(f"✅ 修复: {name} - 添加主题乐园/5A标签, popularity=9")

# Save
with open("data/attractions.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"\n📊 共修复 {fixed_count} 个 POI")
