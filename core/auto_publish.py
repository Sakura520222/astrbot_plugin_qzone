import asyncio
import random
import time
import zoneinfo
from typing import Dict, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.star.context import Context

from .llm_action import LLMAction
from .post import Post
from .qzone_api import Qzone


class AutoPublish:
    """
    自动发说说任务类
    """

    def __init__(
        self,
        context: Context,
        config: AstrBotConfig,
        qzone: Qzone,
        llm: LLMAction,
    ):
        self.qzone = qzone
        self.llm = llm

        self.per_qzone_num = config.get("per_qzone_num", 5)

        tz = context.get_config().get("timezone")
        self.timezone = (
            zoneinfo.ZoneInfo(tz) if tz else zoneinfo.ZoneInfo("Asia/Shanghai")
        )

        self.scheduler = AsyncIOScheduler(timezone=self.timezone)
        self.scheduler.start()
        cron_cfg = config.get("publish_cron", "45 1 * * *")
        self.register_task(cron_cfg)
        
        # 性能监控统计
        self.stats = {
            "total_runs": 0,
            "successful_runs": 0,
            "failed_runs": 0,
            "filtered_content": 0,
            "total_execution_time": 0.0,
            "last_run_time": None,
            "retry_attempts": 0
        }

        logger.info(f"[AutoPublish] 已启动，任务周期：{cron_cfg}")


    def register_task(self, cron_expr: str):
        """
        注册一个 cron 任务，例如 "45 1 * * *"
        """
        try:
            trigger = CronTrigger.from_crontab(cron_expr)
            self.scheduler.add_job(
                func=self.run_once,
                trigger=trigger,
                name="qzone_auto_publish",
                max_instances=1,
            )
        except Exception as e:
            logger.error(f"[AutoPublish] Cron 格式错误：{e}")

    async def run_once(self):
        """
        计划任务执行一次自动发说说
        """
        logger.info("[AutoPublish] 执行自动发说说任务")
        
        # 性能监控：记录开始时间
        start_time = asyncio.get_event_loop().time()
        self.stats["total_runs"] += 1
        
        try:
            # 随机选择写作风格
            styles = ["default", "poetic", "humorous", "philosophical", "casual"]
            selected_style = random.choice(styles)
            
            # 随机选择主题（可选）
            topics = ["生活感悟", "科技发展", "情感交流", "学习心得", "娱乐休闲", None]
            selected_topic = random.choice(topics)
            
            # 随机决定是否使用多群聊模式（30%概率）
            use_multi_group = random.random() < 0.3
            
            # 50%概率生成图片
            generate_images = random.random() < 0.5
            
            # 生成说说内容、图片，并进行情感话题分析
            text, images, sentiment, topic_analysis = await self.llm.generate_diary_with_analysis(
                style=selected_style, 
                topic=selected_topic,
                max_length=500,
                multi_group=use_multi_group,
                max_groups=random.randint(2, 4),
                generate_images=generate_images
            )
            
            # 检查内容是否被过滤
            if "内容包含敏感信息" in text or "内容质量不符合要求" in text or "内容过短" in text:
                logger.warning("[AutoPublish] 内容被过滤，跳过本次发布")
                self.stats["filtered_content"] += 1
                self._update_stats(start_time, success=False)
                return
                
            # 创建Post对象并设置图片
            post = Post(text=text, status="approved")
            if images:
                post.images = images
            
            succ, data = await self.qzone.publish(post)
            if not succ:
                logger.error(f"[AutoPublish] 发说说失败：{data}")
                self.stats["failed_runs"] += 1
                self._update_stats(start_time, success=False)
                
                # 根据错误类型决定是否重试
                if self._should_retry(data):
                    await self._retry_publish()
                return
                
            # 性能监控：计算执行时间
            execution_time = asyncio.get_event_loop().time() - start_time
            self.stats["successful_runs"] += 1
            self._update_stats(start_time, success=True)
            
            mode_info = "多群聊" if use_multi_group else "单群聊"
            image_info = f"，配图：{len(images)}张" if images else "，纯文本"
            logger.info(f"[AutoPublish] 说说发布成功（风格：{selected_style}，主题：{selected_topic}，模式：{mode_info}{image_info}，情感：{sentiment}，话题：{topic_analysis}，耗时：{execution_time:.2f}s）")
            
        except Exception as e:
            # 性能监控：记录异常时间
            execution_time = asyncio.get_event_loop().time() - start_time
            logger.error(f"[AutoPublish] 执行任务异常：{e}，耗时：{execution_time:.2f}s")
            self.stats["failed_runs"] += 1
            self._update_stats(start_time, success=False)
            
            # 根据异常类型决定重试策略
            if self._is_retryable_error(e):
                await self._retry_publish()
            else:
                logger.error("[AutoPublish] 遇到不可重试错误，跳过本次任务")
    
    def _should_retry(self, error_data: dict) -> bool:
        """判断是否应该重试"""
        # 网络错误、超时错误等可以重试
        retryable_errors = ["timeout", "network", "connection", "服务器", "网络"]
        error_str = str(error_data).lower()
        
        for error_keyword in retryable_errors:
            if error_keyword in error_str:
                return True
        
        # 内容错误、权限错误等不应该重试
        non_retryable_errors = ["permission", "auth", "content", "敏感", "违规"]
        for error_keyword in non_retryable_errors:
            if error_keyword in error_str:
                return False
        
        # 默认情况下重试
        return True
    
    def _is_retryable_error(self, exception: Exception) -> bool:
        """判断异常是否可重试"""
        # 网络相关异常可以重试
        retryable_exceptions = [
            "TimeoutError", "ConnectionError", "NetworkError", 
            "asyncio.TimeoutError", "aiohttp.ClientError"
        ]
        
        exception_name = type(exception).__name__
        exception_str = str(exception).lower()
        
        # 检查异常类型
        for retryable_exception in retryable_exceptions:
            if retryable_exception in exception_name:
                return True
        
        # 检查异常消息中的关键词
        retryable_keywords = ["timeout", "connection", "network", "服务器", "网络"]
        for keyword in retryable_keywords:
            if keyword in exception_str:
                return True
        
        # 内容相关异常不应该重试
        non_retryable_keywords = ["content", "sensitive", "permission", "auth"]
        for keyword in non_retryable_keywords:
            if keyword in exception_str:
                return False
        
        # 默认情况下重试
        return True
    
    async def _retry_publish(self, max_retries: int = 3):
        """重试发布机制"""
        for attempt in range(max_retries):
            try:
                logger.info(f"[AutoPublish] 重试发布，第{attempt + 1}次尝试")
                
                # 指数退避策略
                wait_time = min(2 ** attempt, 60)  # 最大等待60秒
                await asyncio.sleep(wait_time)
                
                # 使用更简单的风格重试，不生成图片
                text = await self.llm.generate_diary(
                    style="casual", 
                    topic=None,
                    max_length=300
                )
                
                if "内容包含敏感信息" not in text:
                    post = Post(text=text, status="approved")
                    succ, data = await self.qzone.publish(post)
                    if succ:
                        logger.info(f"[AutoPublish] 重试发布成功")
                        return
                    else:
                        logger.error(f"[AutoPublish] 重试发布失败：{data}")
                        
                        # 如果错误不可重试，提前退出
                        if not self._should_retry(data):
                            logger.warning("[AutoPublish] 遇到不可重试错误，停止重试")
                            break
                else:
                    logger.warning("[AutoPublish] 重试内容被过滤")
                    
            except Exception as e:
                logger.error(f"[AutoPublish] 重试异常：{e}")
                
                # 如果异常不可重试，提前退出
                if not self._is_retryable_error(e):
                    logger.warning("[AutoPublish] 遇到不可重试异常，停止重试")
                    break
        
        logger.error(f"[AutoPublish] 重试{max_retries}次后仍失败")
    
    def _update_stats(self, start_time: float, success: bool):
        """更新性能统计"""
        execution_time = asyncio.get_event_loop().time() - start_time
        self.stats["total_execution_time"] += execution_time
        self.stats["last_run_time"] = time.time()
        
        # 记录重试次数
        if not success:
            self.stats["retry_attempts"] += 1
    
    def get_performance_report(self) -> Dict[str, Any]:
        """获取性能监控报告"""
        if self.stats["total_runs"] == 0:
            return {"status": "no_data", "message": "暂无执行记录"}
        
        success_rate = (self.stats["successful_runs"] / self.stats["total_runs"]) * 100
        avg_execution_time = self.stats["total_execution_time"] / self.stats["total_runs"]
        
        return {
            "status": "success",
            "total_runs": self.stats["total_runs"],
            "successful_runs": self.stats["successful_runs"],
            "failed_runs": self.stats["failed_runs"],
            "filtered_content": self.stats["filtered_content"],
            "retry_attempts": self.stats["retry_attempts"],
            "success_rate": round(success_rate, 2),
            "avg_execution_time": round(avg_execution_time, 2),
            "last_run_time": self.stats["last_run_time"],
            "total_execution_time": round(self.stats["total_execution_time"], 2)
        }
    
    async def log_performance_report(self):
        """记录性能监控报告到日志"""
        report = self.get_performance_report()
        
        if report["status"] == "no_data":
            logger.info("[AutoPublish] 性能监控：暂无执行记录")
            return
        
        logger.info(f"[AutoPublish] 性能监控报告：")
        logger.info(f"  - 总执行次数：{report['total_runs']}")
        logger.info(f"  - 成功次数：{report['successful_runs']}")
        logger.info(f"  - 失败次数：{report['failed_runs']}")
        logger.info(f"  - 内容过滤次数：{report['filtered_content']}")
        logger.info(f"  - 重试次数：{report['retry_attempts']}")
        logger.info(f"  - 成功率：{report['success_rate']}%")
        logger.info(f"  - 平均执行时间：{report['avg_execution_time']}秒")
        logger.info(f"  - 总执行时间：{report['total_execution_time']}秒")
 
    async def terminate(self):
        """停止服务并记录最终性能报告"""
        await self.log_performance_report()
        self.scheduler.remove_all_jobs()
        logger.info("[AutoPublish] 已停止")
