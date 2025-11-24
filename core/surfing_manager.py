"""
上网冲浪功能管理器
处理用户权限检查、使用次数统计等功能
"""

import json
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from astrbot.api import logger


class SurfingManager:
    """上网冲浪功能管理器"""
    
    def __init__(self, data_dir: str):
        """
        初始化管理器
        
        Args:
            data_dir: 数据存储目录
        """
        self.data_dir = data_dir
        self.usage_file = os.path.join(data_dir, "surfing_usage.json")
        self._ensure_data_dir()
        
        # 用户使用次数统计
        self.usage_data: Dict[str, Dict] = self._load_usage_data()
    
    def _ensure_data_dir(self):
        """确保数据目录存在"""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
    
    def _load_usage_data(self) -> Dict[str, Dict]:
        """加载使用次数数据"""
        try:
            if os.path.exists(self.usage_file):
                with open(self.usage_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"加载上网冲浪使用数据失败：{e}")
        
        return {}
    
    def _save_usage_data(self):
        """保存使用次数数据"""
        try:
            with open(self.usage_file, 'w', encoding='utf-8') as f:
                json.dump(self.usage_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存上网冲浪使用数据失败：{e}")
    
    def _get_today_date(self) -> str:
        """获取今天的日期字符串"""
        return datetime.now().strftime("%Y-%m-%d")
    
    def _cleanup_old_data(self):
        """清理过期的使用数据（保留最近30天的数据）"""
        cutoff_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        
        for user_id in list(self.usage_data.keys()):
            user_data = self.usage_data[user_id]
            # 删除过期的日期数据
            for date in list(user_data.keys()):
                if date < cutoff_date:
                    del user_data[date]
            
            # 如果用户没有有效数据，删除用户记录
            if not user_data:
                del self.usage_data[user_id]
        
        self._save_usage_data()
    
    def check_permission(self, user_id: str, config: Dict) -> tuple[bool, str]:
        """
        检查用户是否有权限使用上网冲浪功能
        
        Args:
            user_id: 用户QQ号
            config: 插件配置
            
        Returns:
            tuple[bool, str]: (是否有权限, 错误信息)
        """
        access_mode = config.get("surfing_access_mode", "所有人")
        
        # 检查访问模式
        if access_mode == "主人模式":
            master_qq = config.get("surfing_master_qq", "")
            if user_id != master_qq:
                return False, "❌ 此功能仅限主人使用"
        
        elif access_mode == "白名单":
            whitelist = config.get("surfing_whitelist", [])
            if user_id not in whitelist:
                return False, "❌ 您不在白名单中，无法使用此功能"
        
        # 检查每日使用次数限制
        daily_limit = config.get("surfing_daily_limit", 3)
        if daily_limit > 0:
            today_usage = self.get_today_usage(user_id)
            if today_usage >= daily_limit:
                return False, f"❌ 今日使用次数已达上限（{daily_limit}次），请明天再试"
        
        return True, ""
    
    def record_usage(self, user_id: str):
        """
        记录用户使用次数
        
        Args:
            user_id: 用户QQ号
        """
        today = self._get_today_date()
        
        if user_id not in self.usage_data:
            self.usage_data[user_id] = {}
        
        if today not in self.usage_data[user_id]:
            self.usage_data[user_id][today] = 0
        
        self.usage_data[user_id][today] += 1
        self._save_usage_data()
        
        # 定期清理过期数据
        if datetime.now().day == 1:  # 每月1号清理一次
            self._cleanup_old_data()
    
    def get_today_usage(self, user_id: str) -> int:
        """
        获取用户今日使用次数
        
        Args:
            user_id: 用户QQ号
            
        Returns:
            int: 今日使用次数
        """
        today = self._get_today_date()
        
        if user_id in self.usage_data and today in self.usage_data[user_id]:
            return self.usage_data[user_id][today]
        
        return 0
    
    def get_remaining_usage(self, user_id: str, config: Dict) -> int:
        """
        获取用户今日剩余使用次数
        
        Args:
            user_id: 用户QQ号
            config: 插件配置
            
        Returns:
            int: 剩余使用次数，-1表示无限制
        """
        daily_limit = config.get("surfing_daily_limit", 3)
        if daily_limit <= 0:
            return -1
        
        today_usage = self.get_today_usage(user_id)
        return max(0, daily_limit - today_usage)
    
    def get_usage_statistics(self, user_id: str) -> Dict:
        """
        获取用户使用统计信息
        
        Args:
            user_id: 用户QQ号
            
        Returns:
            Dict: 使用统计信息
        """
        if user_id not in self.usage_data:
            return {"total_usage": 0, "today_usage": 0, "recent_days": {}}
        
        user_data = self.usage_data[user_id]
        today = self._get_today_date()
        
        # 计算最近7天的使用情况
        recent_days = {}
        for i in range(7):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            recent_days[date] = user_data.get(date, 0)
        
        return {
            "total_usage": sum(user_data.values()),
            "today_usage": user_data.get(today, 0),
            "recent_days": recent_days
        }
    
    def reset_user_usage(self, user_id: str):
        """
        重置用户使用次数
        
        Args:
            user_id: 用户QQ号
        """
        if user_id in self.usage_data:
            del self.usage_data[user_id]
            self._save_usage_data()
    
    def get_all_users_usage(self) -> Dict[str, Dict]:
        """
        获取所有用户的使用统计
        
        Returns:
            Dict[str, Dict]: 用户使用统计
        """
        return self.usage_data.copy()