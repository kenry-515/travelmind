"""
Quick smoke test for the Kimi vision provider.

Usage (from backend/):
    python scripts/test_vision.py path/to/photo.jpg

Requires MOONSHOT_API_KEY in backend/.env
"""

import asyncio
import json
import sys
from pathlib import Path

# Windows GBK 控制台兼容：stdout 强制 UTF-8，避免中文输出乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.vision_service import get_vision_provider  # noqa: E402

MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_vision.py <image_path>")
        sys.exit(1)

    image_path = Path(sys.argv[1])
    media_type = MEDIA_TYPES.get(image_path.suffix.lower())
    if media_type is None:
        print(f"Unsupported image format: {image_path.suffix} (use png/jpeg/webp/gif)")
        sys.exit(1)

    provider = get_vision_provider()
    data_url = provider.encode_image_bytes(image_path.read_bytes(), media_type)

    print(f"Model: {provider.model} — analyzing {image_path.name} ...")
    result = await provider.analyze_image(data_url)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
