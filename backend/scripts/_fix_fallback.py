"""Add quality fallback using KB recommendation data."""
path = 'app/agents/planning_agent.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

old = '    return {}\n\n\nasync def regenerate_day('
new = '''    # Phase 13: fallback — build valid itinerary from KB recommendations
    try:
        days_cnt = profile.get("days", 3) or 3
        dest = profile.get("destination", "") or ""
        budget_lvl = profile.get("budget_level", "") or "适中"
        # Extract unique POI names from recommendations
        poi_names = []
        seen = set()
        for p in places:
            nm = p.get("name") or p.get("metadata", {}).get("name", "")
            if nm and nm not in seen:
                seen.add(nm)
                poi_names.append(nm)
        if poi_names and dest:
            from datetime import date, timedelta
            per_day = max(1, len(poi_names) // days_cnt)
            fb_days = []
            for d in range(min(days_cnt, (len(poi_names) + per_day - 1) // per_day)):
                pool = poi_names[d*per_day:(d+1)*per_day]
                items = [{"poi": n, "time": ["09:00", "12:00", "15:00"][i%3], "note": "游览"} for i, n in enumerate(pool)]
                fb_days.append({"day": d+1, "theme": f"DAY {d+1} . {dest}", "title": f"{dest}探索", "items": items, "eat": "当地美食"})
            budget_map = {"经济": 500, "适中": 800, "舒适": 1500, "高端": 3000, "奢华": 5000}
            bpd = budget_map.get(budget_lvl, 800)
            total = bpd * len(fb_days)
            fb = {
                "trip": {"title": f"{dest}之旅", "city": dest, "daysCount": len(fb_days), "stats": [{"label":"天数","value":f"{len(fb_days)}天"},{"label":"地点数","value":f"{sum(len(d[\"items\"]) for d in fb_days)}"}]},
                "days": fb_days,
                "budget": [{"label":"门票","amount":int(total*0.4),"percent":40},{"label":"餐饮","amount":int(total*0.3),"percent":30},{"label":"交通","amount":int(total*0.2),"percent":20}],
                "checklist": [{"text":"预订住宿","done":False},{"text":"查看天气","done":False}],
                "tips": [f"{dest}温度适宜，注意防晒补水"],
            }
            from app.agents.itinerary_contract import inject_computed_fields
            inject_computed_fields(fb)
            errors = validate_itinerary(fb) + validate_day_continuity(fb)
            if not errors:
                logger.info(f"Fallback itinerary generated: {len(fb_days)} days")
                return fb
            logger.warning(f"Fallback validation failed ({len(errors)} errors), returning empty")
    except Exception as e:
        logger.warning(f"Fallback construction failed: {e}")
    return {}


async def regenerate_day('

if old in c:
    c = c.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(c)
    import py_compile
    py_compile.compile(path, doraise=True)
    print('OK: fallback added, syntax OK')
else:
    print('FAIL: pattern not found')
