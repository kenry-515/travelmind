"""Add fallback to planning_agent.py."""
path = 'app/agents/planning_agent.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

old = '    return {}\n\n\nasync def regenerate_day('
new = '''    # Phase 13: fallback from KB recommendations
    try:
        dc = profile.get("days", 3) or 3
        dest = profile.get("destination", "") or ""
        bl = profile.get("budget_level", "") or "mid"
        names = []
        seen = set()
        for p in places:
            nm = p.get("name") or (p.get("metadata") or {}).get("name", "")
            if nm and nm not in seen:
                seen.add(nm)
                names.append(nm)
        if names and dest:
            from app.agents.itinerary_contract import inject_computed_fields, validate_itinerary, validate_day_continuity
            pd = max(1, len(names) // max(dc, 1))
            fb_days = []
            for d in range(min(dc, max(1, (len(names) + pd - 1) // pd))):
                pool = names[d*pd:(d+1)*pd]
                items = [{"poi": n, "time": ["09:00","12:00","15:00"][i%3], "note": "visit"} for i, n in enumerate(pool)]
                fb_days.append({"day": d+1, "theme": "DAY " + str(d+1) + " . " + dest, "title": dest, "items": items, "eat": "local food"})
            bmap = {"经济": 500, "mid": 800, "舒适": 1500, "高端": 3000}
            bpd = bmap.get(bl, 800)
            total = bpd * len(fb_days)
            fb = {"trip": {"title": dest + " " + str(len(fb_days)) + "d", "city": dest, "stats": [{"label":"days","value":str(len(fb_days))}]}, "days": fb_days, "budget": [{"label":"ticket","amount":int(total*0.4)}], "checklist": [], "tips": []}
            inject_computed_fields(fb)
            errs = validate_itinerary(fb) + validate_day_continuity(fb)
            if not errs:
                logger.info("Fallback: " + str(len(fb_days)) + " days")
                return fb
    except Exception:
        pass
    return {}

async def regenerate_day('

if old in c:
    c = c.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(c)
    compile(c, path, 'exec')
    print('OK: fallback added, syntax OK')
else:
    print('FAIL: pattern not found')
    idx = c.find('return {}')
    print(f'return {{}} at {idx}')
