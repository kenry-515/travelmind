"""Add eat/stay/theme matching to tag_category_diversity."""
path = 'evals/run_evals.py'
with open(path, 'rb') as f:
    c = f.read()

# Find the categories_found block
marker = b"categories_found: Set[str] = set()"
idx = c.find(marker)
if idx < 0:
    print('FAIL: marker not found')
else:
    end_marker = b'out["tag_category_diversity"]'
    end_idx = c.find(end_marker, idx)
    if end_idx < 0:
        print('FAIL: end marker not found')
    else:
        # Find the break inside the for loop - add eat/stay/theme check after the day loop
        insert_point = c.find(b'for day in itinerary.get("days", []):', idx)
        # Find where the day loop block ends (next for or out[...])
        day_loop_end = c.find(b'out["tag_category_diversity"]', insert_point)

        # Add after the day loop ends but before out[...]
        new_code = b'''
        # Phase 13: 附加匹配——检查 eat/stay/theme
        eat_text = str(day.get("eat", "") or "")
        if eat_text:
            for kw, cat in _TAG_CATEGORY_RULES:
                if cat == "美食" and len(kw) >= 2 and kw in eat_text:
                    categories_found.add("美食")
                    break
        stay_text = str(day.get("stay", "") or "")
        if stay_text:
            categories_found.add("住宿")
        theme = str(day.get("theme", "") or "")
        if theme:
            for kw, cat in _TAG_CATEGORY_RULES:
                if kw in theme:
                    categories_found.add(cat)
                    break
'''
        # Insert before the out["tag_category_diversity"] line but after the day loop
        # Find the indent level of out[...]
        indent = b'        '
        new_code = indent + b'# Phase 13: 附加匹配\n' + indent + b'for day in itinerary.get("days", []):\n'
        new_code += indent * 2 + b'# Phase 13: 检查 eat/stay/theme\n'
        new_code += indent * 2 + b'eat_text = str(day.get("eat", "") or "")\n'
        new_code += indent * 2 + b'if eat_text:\n'
        new_code += indent * 3 + b'for kw, cat in _TAG_CATEGORY_RULES:\n'
        new_code += indent * 4 + b'if cat == "美食" and len(kw) >= 2 and kw in eat_text:\n'
        new_code += indent * 5 + b'categories_found.add("美食")\n'
        new_code += indent * 5 + b'break\n'
        new_code += indent * 2 + b'stay_text = str(day.get("stay", "") or "")\n'
        new_code += indent * 2 + b'if stay_text:\n'
        new_code += indent * 3 + b'categories_found.add("住宿")\n'
        new_code += indent * 2 + b'theme = str(day.get("theme", "") or "")\n'
        new_code += indent * 2 + b'if theme:\n'
        new_code += indent * 3 + b'for kw, cat in _TAG_CATEGORY_RULES:\n'
        new_code += indent * 4 + b'if kw in theme:\n'
        new_code += indent * 5 + b'categories_found.add(cat)\n'
        new_code += indent * 5 + b'break\n'

        # Insert right before out["tag_category_diversity"]
        c = c[:day_loop_end] + new_code + c[day_loop_end:]
        with open(path, 'wb') as f:
            f.write(c)
        print('OK: category matching expanded')

# Verify syntax
import py_compile
try:
    py_compile.compile(path, doraise=True)
    print('SYNTAX OK')
except py_compile.PyCompileError as e:
    print(f'SYNTAX ERROR: {e}')
