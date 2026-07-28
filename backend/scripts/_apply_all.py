"""Apply ALL planning_agent fixes atomically."""
import re

path = 'app/agents/planning_agent.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

# 1. top_n 20 -> 30
c = c.replace('top_n = min(len(recommendations), 20)', 'top_n = min(len(recommendations), 30)')

# 2. last_error format string
c = c.replace('last_error = {"schema_errors": errors[:5]}', 'last_error = "; ".join(str(e)[:100] for e in errors[:3])')

# 3. POI dedup post-processing - add after weather report section
old_dedup = 'route_report["weather_notes"] = weather_notes\n                data["validation_report"] = route_report'
new_dedup = old_dedup + '\n\n            # Phase 13: POI dedup\n            try:\n                seen_poi = set()\n                for day in data.get("days", []):\n                    new_items = []\n                    for item in day.get("items", []):\n                        pname = item.get("poi", "")\n                        if pname and pname not in seen_poi:\n                            seen_poi.add(pname)\n                            new_items.append(item)\n                    day["items"] = new_items\n            except Exception:\n                pass'
c = c.replace(old_dedup, new_dedup)

# 4. Prompt rules 12-17 after rule 11
old_prompt = 'tips 中必须包含当季天气应对建议（遮阳/雨具/室内备选方案）"""'
new_prompt = old_prompt + '\n12.【POI名称不可重复】不同天之间不得出现相同的poi名称。每个景点在全行程中只出现一次。\n13.【标签大类多样性】景点应覆盖至少3个不同标签大类（自然/人文/美食/购物/娱乐/运动/艺术），避免全行程同质化。\n14.【极端预算场景】预算极低（经济/穷游/500元以下）时优先免费景点，餐饮路边摊/小吃，住宿青旅，交通步行公交。\n15.【矛盾需求处理】用户有矛盾需求时优先满足安全可行性，在tips中说明无法同时满足。\n16.【特殊人群】老人/小孩/孕妇：无剧烈运动、少阶梯、有空调、近医疗设施；tips包含专门建议。\n17.【极寒/极热】冬季极寒：户外项目不超60分钟室内外交替；夏季酷暦：午后仅排室内项目。\n"""'
c = c.replace(old_prompt, new_prompt)

# 5. Add error injection in retry loop and fallback in one block
old_retry_start = 'for attempt in range(MAX_RETRIES + 1):\n        logger.info(\n            f"Planning itinerary: {days}d from {len(places)} places"\n            + (f" (attempt {attempt + 1})" if attempt else "")\n        )\n        try:\n            data = await _call_llm(\n                _SYSTEM_PROMPT_FULL, prompt, tool_schema,'
new_retry_start = 'for attempt in range(MAX_RETRIES + 1):\n        logger.info(\n            f"Planning itinerary: {days}d from {len(places)} places"\n            + (f" (attempt {attempt + 1})" if attempt else "")\n        )\n        # Phase 13: inject prev error into prompt\n        cur_prompt = prompt\n        if attempt > 0 and last_error:\n            cur_prompt = prompt + "\\n\\n[Fix previous errors: " + str(last_error)[:200] + "]\\n"\n        try:\n            data = await _call_llm(\n                _SYSTEM_PROMPT_FULL, cur_prompt, tool_schema,'
c = c.replace(old_retry_start, new_retry_start)

# 6. Add fallback after last retry failure
old_fail = "    logger.error(\n        f\"Itinerary generation failed after {MAX_RETRIES + 1} attempts: {last_error}\"\n    )\n\n    return {}"
new_fail = '    logger.error(\n        f"Itinerary generation failed after {MAX_RETRIES + 1} attempts: {last_error}"\n    )\n\n    # Phase 13 fallback\n    try:\n        dc = profile.get("days", 3) or 3\n        dest = profile.get("destination", "") or ""\n        bl = profile.get("budget_level", "") or "mid"\n        names = []\n        seen = set()\n        for p in places:\n            nm = p.get("name") or (p.get("metadata") or {}).get("name", "")\n            if nm and nm not in seen:\n                seen.add(nm)\n                names.append(nm)\n        if names and dest:\n            from app.agents.itinerary_contract import inject_computed_fields, validate_itinerary, validate_day_continuity\n            pd = max(1, len(names) // dc)\n            fb_days = []\n            for d in range(min(dc, (len(names) + pd - 1) // pd)):\n                pool = names[d*pd:(d+1)*pd]\n                items = [{"poi": n, "time": ["09:00","12:00","15:00"][i%3], "note": "visit"} for i, n in enumerate(pool)]\n                fb_days.append({"day": d+1, "theme": "DAY " + str(d+1) + " . " + dest, "title": dest, "items": items, "eat": "local food"})\n            bmap = {"经济": 500, "mid": 800, "舒适": 1500, "高端": 3000}\n            bpd = bmap.get(bl, 800)\n            total = bpd * len(fb_days)\n            fb = {"trip": {"title": dest + " " + str(len(fb_days)) + "d", "city": dest, "stats": [{"label":"days","value":str(len(fb_days))}]}, "days": fb_days, "budget": [{"label":"ticket","amount":int(total*0.4)}], "checklist": [], "tips": []}\n            inject_computed_fields(fb)\n            errors = validate_itinerary(fb) + validate_day_continuity(fb)\n            if not errors:\n                logger.info("Fallback: " + str(len(fb_days)) + " days")\n                return fb\n    except Exception:\n        pass\n    return {}'
c = c.replace(old_fail, new_fail)

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
compile(c, path, 'exec')
print('ALL FIXES APPLIED OK')
