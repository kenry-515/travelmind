"""Test month fix function directly."""
import sys
import re
sys.path.insert(0, '.')

# Import the fix function
from app.agents.planning_agent import _fix_month_references
from app.agents.itinerary_contract import month_inconsistency_errors

# Test data - simulate the error case
test_data = {
    "trip": {
        "title": "测试行程",
        "city": "成都",
        "dateStart": "7月30日",
        "dateEnd": "8月2日",
        "daysCount": 4,
        "stats": [
            {"value": "4天", "label": "天数"},
            {"value": "10个", "label": "景点数"}
        ]
    },
    "days": [
        {
            "day": 1,
            "theme": "Day 1",
            "title": "第一天",
            "items": [
                {
                    "time": "09:00",
                    "poi": "测试景点",
                    "note": "测试备注"
                }
            ],
            "eat": "早餐：X · 午餐：Y · 晚餐：Z"
        }
    ],
    "tips": [
        "⚠️ 7月30日-8月2日连续冰雹雷暴天气，所有行程已调整为100%室内项目",
        "其他提示"
    ],
    "checklist": []
}

print("原始数据:")
print(f"  tips: {test_data['tips']}")
print()

# Check for month errors before fix
errors_before = month_inconsistency_errors(test_data, 7)
print(f"修复前错误: {errors_before}")
print()

# Apply fix
replacements = _fix_month_references(test_data, 7)
print(f"修复数量: {replacements}")
print()

# Check after fix
errors_after = month_inconsistency_errors(test_data, 7)
print(f"修复后错误: {errors_after}")
print()

print("修复后数据:")
print(f"  tips: {test_data['tips']}")
