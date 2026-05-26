import re
import os

env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Remove ai_filter_* lines
    content = re.sub(r'(?im)^AI_FILTER_.*?$?\n?', '', content)

    # Add missing V0.3 configs if not present
    if "USER_PERSONA" not in content:
        content += "\nUSER_PERSONA=我是一名关注 AI 发展的技术人员，偏好开源项目和硬核技术解析，不看软文。\n"
    if "TITLE_SIMILARITY_THRESHOLD" not in content:
        content += "TITLE_SIMILARITY_THRESHOLD=0.85\n"
    if "CONTEXT_LOOKBACK_DAYS" not in content:
        content += "CONTEXT_LOOKBACK_DAYS=3\n"
    if "CONTEXT_MAX_ITEMS" not in content:
        content += "CONTEXT_MAX_ITEMS=45\n"
    if "CLEANUP_RETENTION_DAYS" not in content:
        content += "CLEANUP_RETENTION_DAYS=7\n"
    if "CLEANUP_HOUR" not in content:
        content += "CLEANUP_HOUR=3\n"
    if "CLEANUP_MINUTE" not in content:
        content += "CLEANUP_MINUTE=0\n"

    with open(env_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Updated .env successfully.")
