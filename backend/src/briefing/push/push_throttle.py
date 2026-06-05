"""滑动窗口防抖推送控制器。"""

import threading
import time
import logging
from collections import defaultdict
from briefing.config import get_settings

logger = logging.getLogger(__name__)

# 内存锁（进程级单例）
_push_log: dict[str, list[float]] = defaultdict(list)
_lock = threading.Lock()


def should_push(tags: list[str]) -> bool:
    """判断是否应该推送。返回 False 表示触发熔断。"""
    if not tags:
        return True
        
    settings = get_settings()
    now = time.time()
    
    with _lock:
        for tag in tags:
            # 清理过期记录
            _push_log[tag] = [t for t in _push_log[tag] if now - t < settings.push_throttle_window]
            if len(_push_log[tag]) >= settings.push_throttle_max:
                logger.warning("Tag '%s' 触发防抖熔断 (%d 秒内已推送 %d 次)", tag, settings.push_throttle_window, len(_push_log[tag]))
                return False
    return True


def record_push(tags: list[str]):
    """记录一次推送事件。"""
    if not tags:
        return
        
    now = time.time()
    with _lock:
        for tag in tags:
            _push_log[tag].append(now)
