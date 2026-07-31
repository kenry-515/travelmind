import json
data = json.load(open("data/attractions.json", "r", encoding="utf-8"))
attrs = data["attractions"]
total = len(attrs)
with_price = sum(1 for a in attrs if a.get("price_range") is not None)
with_amap = sum(1 for a in attrs if a.get("amap_id"))
with_wiki = sum(1 for a in attrs if a.get("wiki_article"))
with_wdid = sum(1 for a in attrs if a.get("wikidata_id"))
with_desc = sum(1 for a in attrs if a.get("description") and len(str(a.get("description", ""))) > 30)
free = sum(1 for a in attrs if a.get("price_range") and isinstance(a.get("price_range"), dict) and a["price_range"].get("max", 0) == 0)
print(f"Total: {total}")
print(f"With price: {with_price} (free={free})")
print(f"With amap_id: {with_amap}")
print(f"With wiki_article: {with_wiki}")
print(f"With wikidata_id: {with_wdid}")
print(f"With good desc: {with_desc}")

# Find attractions with interesting names for price fetching
print("\nSample attractions with amap_id:")
for a in attrs[:3]:
    pr = a.get("price_range")
    print(f"  {a['name']} ({a['city']}): price={pr}, amap_type={a.get('amap_type','')}, source={a.get('source','')}")

# List all amap types
types = {}
for a in attrs:
    t = a.get("amap_type", "") or ""
    types[t[:30]] = types.get(t[:30], 0) + 1
print(f"\nAmap type distribution (top 15):")
for t, c in sorted(types.items(), key=lambda x: -x[1])[:15]:
    print(f"  {t}: {c}")