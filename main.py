# main.py

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import pillowmd

from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core import AstrBotConfig
from astrbot.core.config.default import VERSION
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
    AiocqhttpAdapter,
)
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.version_comparator import VersionComparator

from .core.auto_comment import AutoComment
from .core.auto_publish import AutoPublish
from .core.campus_wall import CampusWall
from .core.llm_action import LLMAction
from .core.post import Post, PostDB
from .core.qzone_api import Qzone
from .core.surfing_manager import SurfingManager
from .core.utils import get_ats, get_image_urls, get_nickname


@register("astrbot_plugin_qzone", "Zhalslar", "...", "...")
class QzonePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.config = config

        # 检查版本
        if not VersionComparator.compare_version(VERSION, "4.1.0") >= 0:
            raise Exception("AstrBot 版本过低, 请升级至 4.1.0 或更高版本")

        # pillowmd样式目录
        default_style_dir = (
            Path(get_astrbot_data_path()) / "plugins/astrbot_plugin_qzone/default_style"
        )
        self.pillowmd_style_dir = config.get("pillowmd_style_dir") or default_style_dir

        # 数据库文件
        self.db_path = StarTools.get_data_dir("astrbot_plugin_qzone") / "posts_v2.db"
        # 缓存
        self.cache = StarTools.get_data_dir("astrbot_plugin_qzone") / "cache"
        self.cache.mkdir(parents=True, exist_ok=True)
        # 数据库管理器
        self.db = PostDB(self.db_path)
        
        # 上网冲浪功能管理器
        data_dir = StarTools.get_data_dir("astrbot_plugin_qzone")
        self.surfing_manager = SurfingManager(str(data_dir))

    async def initialize(self):
        """加载、重载插件时触发"""
        # 初始化数据库
        await self.db.initialize()
        # 实例化pillowmd样式
        try:
            self.style = pillowmd.LoadMarkdownStyles(self.pillowmd_style_dir)
        except Exception as e:
            logger.error(f"无法加载pillowmd样式：{e}")

        asyncio.create_task(self.initialize_qzone(False))

    @filter.on_platform_loaded()
    async def on_platform_loaded(self):
        """平台加载完成时"""
        asyncio.create_task(self.initialize_qzone(True))

    async def initialize_qzone(self, wait_ws_connected: bool = False):
        """初始化QQ空间、自动评论模块、自动发说说模块"""
        client = None
        for inst in self.context.platform_manager.platform_insts:
            if isinstance(inst, AiocqhttpAdapter):
                if client := inst.get_client():
                    break
        if not client:
            return
        # 等待 ws 连接完成
        if wait_ws_connected:
            ws_connected = asyncio.Event()

            @client.on_websocket_connection
            def _(_):  # 连接成功时触发
                ws_connected.set()

            try:
                await asyncio.wait_for(ws_connected.wait(), timeout=10)
            except asyncio.TimeoutError:
                logger.warning("等待 aiocqhttp WebSocket 连接超时")

        # 加载QQ空间模块
        self.qzone = Qzone(client)

        # llm内容生成器
        self.llm = LLMAction(self.context, self.config, client)

        # 加载自动评论模块
        if self.config.get("comment_cron"):
            self.auto_comment = AutoComment(
                self.context, self.config, self.qzone, self.llm
            )
            logger.info("自动发说说模块加载完毕！")

        # 加载自动发说说模块
        if self.config.get("comment_cron"):
            self.auto_publish = AutoPublish(
                self.context, self.config, self.qzone, self.llm
            )
            logger.info("自动发说说模块加载完毕！")

        # 加载表白墙模块
        if self.config.get("campus_wall_switch"):
            self.campus_wall = CampusWall(
                self.context,
                self.config,
                self.qzone,
                self.db,
                self.style,
            )
            logger.info("表白墙模块加载完毕！")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("查看访客")
    async def visitor(self, event: AiocqhttpMessageEvent):
        """查看访客"""
        succ, data = await self.qzone.get_visitor()
        if not succ:
            yield event.plain_result(data)
            logger.error(f"查看访客失败：{data}")
            return
        if not data:
            yield event.plain_result("无访客记录")
            return
        img = await self.style.AioRender(text=data, useImageUrl=True, autoPage=True)
        img_path = img.Save(self.cache)
        yield event.image_result(str(img_path))

    async def _get_posts(self, event: AiocqhttpMessageEvent, no_self: bool = False) -> list[Post]:
        """获取说说，返回稿件列表"""
        # 解析目标用户
        at_ids = get_ats(event)
        target_id = at_ids[0] if at_ids else None
        posts: list[Post] = []

        # 解析范围参数
        end_parm = event.message_str.split(" ")[-1]
        if "~" in end_parm:
            start_index, end_index = map(int, end_parm.split("~"))
            index = start_index
            num = end_index - start_index + 1
        elif end_parm.isdigit():
            index = int(end_parm)
            num = 1
        else:
            index = 1
            num = 1

        if target_id:
            # 获取说说, pos为开始位置， num为获取数量
            succ, data = await self.qzone.get_feeds(target_id=target_id, pos=index, num=num)
        else:
            # 获取最新说说, page为查询第几页
            succ, data = await self.qzone.get_recent_feeds(page=index)

        # 处理错误
        if not succ:
            await event.send(event.plain_result(str(data)))
            logger.error(f"获取说说失败：{data}")
            event.stop_event()
            raise StopIteration
        if not data:
            await event.send(event.plain_result("获取不到说说"))
            event.stop_event()
            raise StopIteration

        posts = data # type: ignore

        # 过滤自己的说说
        if no_self:
            posts = [post for post in posts if post.uin != self.qzone.ctx.uin]

        # 存到数据库
        for post in posts:
            await post.save(self.db)

        return posts

    @filter.command("查看说说")
    async def view_qzone(self, event: AiocqhttpMessageEvent):
        """查看说说 <@群友> <序号>"""
        posts: list[Post] = await self._get_posts(event)
        for post in posts:
            img_path = await post.to_image(self.style)
            yield event.image_result(img_path)

    @filter.command("点赞说说")
    async def like(self, event: AiocqhttpMessageEvent):
        """点赞说说 <@群友> <序号>"""
        posts = await self._get_posts(event)
        results = []
        
        for i, post in enumerate(posts, 1):
            succ, data = await self.qzone.like(fid=post.tid, target_id=str(post.uin))
            if not succ:
                results.append(f"{i}. 点赞{post.name}的说说失败: {data}")
                logger.error(f"点赞失败: {data}")
                continue
            results.append(f"{i}. 已给{post.name}的说说点赞: {post.text[:10]}")
        
        # 将所有结果合并为一条消息发送
        if results:
            yield event.plain_result("\n".join(results))

    # @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("评论说说")
    async def comment(self, event: AiocqhttpMessageEvent):
        """评论说说 <@群友> <序号>"""
        posts = await self._get_posts(event, no_self=True)
        results = []
        
        for i, post in enumerate(posts, 1):
            content = await self.llm.generate_comment(post, event)
            succ, data = await self.qzone.comment(
                fid=post.tid,
                target_id=str(post.uin),
                content=content,
            )
            if not succ:
                results.append(f"{i}. 评论{post.name}的说说失败: {data}")
                logger.error(f"评论失败: {data}")
                continue

            # 同步评论到数据库
            bot_id = event.get_self_id()
            bot_name = await get_nickname(event, bot_id)
            comment = {
                "content": content,
                "qq_account": bot_id,
                "nickname": bot_name,
                "comment_tid": post.tid,
                "created_time": post.create_time,
            }
            # 更新数据
            post.comments.append(comment)
            await post.save(self.db)
            results.append(f"{i}. 已给{post.name}的说说评论: {content[:20]}...")
        
        # 将所有结果合并为一条消息发送
        if results:
            yield event.plain_result("\n".join(results))

    @filter.command("删除说说") # 接口测试中
    async def delete_qzone(self, event: AiocqhttpMessageEvent):
        """删除说说 <序号>"""
        posts = await self._get_posts(event)
        results = []
        
        for i, post in enumerate(posts, 1):
            succ, data = await self.qzone.delete(post.tid)
            if succ:
                results.append(f"{i}. 已删除{post.name}的说说: {post.text[:10]}")
            else:
                results.append(f"{i}. 删除{post.name}的说说失败: {data['message']}")
        
        # 将所有结果合并为一条消息发送
        if results:
            yield event.plain_result("\n".join(results))

    async def _publish(
        self,
        event: AiocqhttpMessageEvent,
        text: str,
        images: list[str],
        publish: bool = True,
    ):
        """发说说封装"""
        self_id = event.get_self_id()
        post = Post(
            uin=int(self_id),
            name=await get_nickname(event, self_id),
            gin=int(event.get_group_id() or 0),
            text=text,
            images=images,
            status="pending",
        )
        if publish:
            succ, data = await self.qzone.publish(post)
            if not succ:
                await event.send(event.plain_result(str(data)))
                logger.error(f"发布说说失败：{str(data)}")
                event.stop_event()
                raise StopIteration
            post.tid = data.get("tid", "")
            post.status = "approved"
            if now:= data.get("now", ""):
                post.create_time = now

        await post.save(self.db)
        img_path = await post.to_image(self.style)
        await event.send(event.image_result(img_path))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("发说说")
    async def publish_handle(self, event: AiocqhttpMessageEvent):
        """发说说 <内容> <图片>, 由用户指定内容"""
        text = event.message_str.removeprefix("发说说").strip()
        images = await get_image_urls(event)
        await self._publish(event, text, images)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("写说说")
    async def keep_diary(self, event: AiocqhttpMessageEvent, topic: str | None = None):
        """写说说 <主题> <图片>, 由AI生成内容后直接发布"""
        text = await self.llm.generate_diary(group_id=event.get_group_id(), topic=topic)
        images = await get_image_urls(event)
        await self._publish(event, text, images)

    @filter.command("写稿", alias={"写草稿"})
    async def write_draft(self, event: AiocqhttpMessageEvent, topic: str | None = None):
        """写稿 <主题> <图片>, 由AI写完后用‘通过稿件 ID’命令发布"""
        text = await self.llm.generate_diary(group_id=event.get_group_id(), topic=topic)
        images = await get_image_urls(event)
        await self._publish(event, text, images, publish=False)

    @filter.command("投稿")
    async def contribute(self, event: AiocqhttpMessageEvent):
        """投稿 <内容> <图片>"""
        await self.campus_wall.contribute(event)

    @filter.permission_type(filter.PermissionType.MEMBER)
    @filter.command("查看稿件")
    async def view_post(self, event: AiocqhttpMessageEvent, input: str | int):
        "查看稿件 <稿件ID>, 默认最新稿件"
        await self.campus_wall.view(event, input)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("通过稿件")
    async def approve_post(self, event: AiocqhttpMessageEvent, input: str | int):
        """通过稿件 <稿件ID>"""
        await self.campus_wall.approve(event, input)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("拒绝稿件")
    async def reject_post(self, event: AiocqhttpMessageEvent, input: str | int):
        """拒绝稿件 <稿件ID> <原因>"""
        await self.campus_wall.reject(event, input)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("删除稿件")
    async def delete_post(self, event: AiocqhttpMessageEvent, input: str | int):
        """删除稿件 <稿件ID>"""
        await self.campus_wall.delete(event, input)

    # 上网冲浪指令组
    @filter.command_group("冲浪")
    def surfing(self):
        """上网冲浪相关功能"""
        pass

    @surfing.command("写说说")
    async def surfing_diary(self, event: AiocqhttpMessageEvent, 
                           category: str = "随机",
                           custom_topic: str = "",
                           writing_style: str = "幽默"):
        """
        上网冲浪写说说 <分类> <自定义主题> <写作风格>
        
        分类选项：科技/娱乐/生活/社会/知识/随机
        写作风格：幽默/深度/简洁/文艺/实用
        """
        try:
            # 检查用户权限
            user_id = event.get_sender_id()
            has_permission, error_msg = self.surfing_manager.check_permission(user_id, self.config)
            if not has_permission:
                yield event.plain_result(error_msg)
                return
            
            # 检查剩余使用次数
            remaining = self.surfing_manager.get_remaining_usage(user_id, self.config)
            if remaining == 0:
                yield event.plain_result(f"❌ 今日使用次数已达上限，请明天再试")
                return
            
            # 生成上网冲浪说说
            result = await self.llm.generate_surfing_diary(
                category=category,
                custom_topic=custom_topic,
                writing_style=writing_style
            )
            
            if result.get("error"):
                yield event.plain_result(f"上网冲浪失败：{result['error']}")
                return
            
            # 获取图片
            images = await get_image_urls(event)
            
            # 发布说说
            await self._publish(event, result["content"], images)
            
            # 记录使用次数
            self.surfing_manager.record_usage(user_id)
            
            # 获取更新后的剩余次数
            new_remaining = self.surfing_manager.get_remaining_usage(user_id, self.config)
            
            # 发送成功信息
            yield event.plain_result(
                f"✅ 上网冲浪说说发布成功！\n"
                f"📝 主题：{result.get('search_query', '随机')}\n"
                f"🎨 风格：{writing_style}\n"
                f"🔍 搜索了 {len(result.get('search_results', []))} 条信息\n"
                f"📊 今日剩余次数：{new_remaining if new_remaining >= 0 else '无限制'}"
            )
            
        except Exception as e:
            logger.error(f"上网冲浪写说说失败：{e}")
            yield event.plain_result(f"上网冲浪写说说失败：{str(e)}")

    @surfing.command("写说说配图")
    async def surfing_diary_with_images(self, event: AiocqhttpMessageEvent,
                                       category: str = "随机",
                                       custom_topic: str = "",
                                       writing_style: str = "幽默"):
        """
        上网冲浪写说说并配图 <分类> <自定义主题> <写作风格>
        
        分类选项：科技/娱乐/生活/社会/知识/随机
        写作风格：幽默/深度/简洁/文艺/实用
        """
        try:
            # 检查用户权限
            user_id = event.get_sender_id()
            has_permission, error_msg = self.surfing_manager.check_permission(user_id, self.config)
            if not has_permission:
                yield event.plain_result(error_msg)
                return
            
            # 检查剩余使用次数
            remaining = self.surfing_manager.get_remaining_usage(user_id, self.config)
            if remaining == 0:
                yield event.plain_result(f"❌ 今日使用次数已达上限，请明天再试")
                return
            
            # 生成上网冲浪说说并配图
            content, images, result = await self.llm.generate_surfing_diary_with_images(
                category=category,
                custom_topic=custom_topic,
                writing_style=writing_style
            )
            
            if result.get("error"):
                yield event.plain_result(f"上网冲浪失败：{result['error']}")
                return
            
            # 发布说说
            await self._publish(event, content, images)
            
            # 记录使用次数
            self.surfing_manager.record_usage(user_id)
            
            # 获取更新后的剩余次数
            new_remaining = self.surfing_manager.get_remaining_usage(user_id, self.config)
            
            # 发送成功信息
            yield event.plain_result(
                f"✅ 上网冲浪说说配图发布成功！\n"
                f"📝 主题：{result.get('search_query', '随机')}\n"
                f"🎨 风格：{writing_style}\n"
                f"🖼️ 配图：{len(images)} 张\n"
                f"🔍 搜索了 {len(result.get('search_results', []))} 条信息\n"
                f"📊 今日剩余次数：{new_remaining if new_remaining >= 0 else '无限制'}"
            )
            
        except Exception as e:
            logger.error(f"上网冲浪写说说配图失败：{e}")
            yield event.plain_result(f"上网冲浪写说说配图失败：{str(e)}")

    @surfing.command("热门话题")
    async def trending_topics(self, event: AiocqhttpMessageEvent):
        """获取当前热门话题"""
        try:
            topics = await self.llm.get_trending_topics()
            
            if not topics:
                yield event.plain_result("暂时没有获取到热门话题，请稍后再试")
                return
            
            # 格式化热门话题列表
            topic_list = "\n".join([f"• {topic}" for topic in topics[:10]])  # 显示前10个
            
            yield event.plain_result(
                f"🔥 当前热门话题：\n{topic_list}\n\n"
                f"💡 使用命令：/冲浪 写说说 <分类> <话题> <风格> 来生成说说"
            )
            
        except Exception as e:
            logger.error(f"获取热门话题失败：{e}")
            yield event.plain_result(f"获取热门话题失败：{str(e)}")

    @surfing.command("帮助")
    async def surfing_help(self, event: AiocqhttpMessageEvent):
        """上网冲浪功能帮助"""
        # 获取当前配置信息
        access_mode = self.config.get("surfing_access_mode", "所有人")
        daily_limit = self.config.get("surfing_daily_limit", 3)
        
        # 获取用户使用情况
        user_id = event.get_sender_id()
        stats = self.surfing_manager.get_usage_statistics(user_id)
        remaining = self.surfing_manager.get_remaining_usage(user_id, self.config)
        
        help_text = f"""
🌊 上网冲浪功能帮助

📊 当前状态：
• 访问模式：{access_mode}
• 每日限制：{daily_limit if daily_limit > 0 else '无限制'}次
• 您今日已使用：{stats['today_usage']}次
• 剩余次数：{remaining if remaining >= 0 else '无限制'}次

📚 可用命令：
• /冲浪 写说说 <分类> <主题> <风格> - 生成并发布上网冲浪说说
• /冲浪 写说说配图 <分类> <主题> <风格> - 生成带配图的说说
• /冲浪 热门话题 - 获取当前热门话题
• /冲浪 我的统计 - 查看个人使用统计
• /冲浪 帮助 - 显示此帮助信息

🎯 分类选项：
• 科技 - 科技新闻、AI发展、编程等
• 娱乐 - 影视、音乐、游戏、明星等
• 生活 - 日常、美食、旅游、健康等
• 社会 - 时事、政策、社会热点等
• 知识 - 科普、历史、文化、学习等
• 随机 - 随机选择分类

✍️ 写作风格：
• 幽默 - 轻松幽默的风格
• 深度 - 深度分析的观点
• 简洁 - 简洁明了的表达
• 文艺 - 文艺优美的语言
• 实用 - 实用贴士和建议

💡 示例：
• /冲浪 写说说 科技 AI发展 幽默
• /冲浪 写说说配图 生活 美食 实用
• /冲浪 写说说 随机 今日热点 简洁
        """
        yield event.plain_result(help_text)
    
    @surfing.command("我的统计")
    async def my_stats(self, event: AiocqhttpMessageEvent):
        """查看个人上网冲浪使用统计"""
        user_id = event.get_sender_id()
        stats = self.surfing_manager.get_usage_statistics(user_id)
        remaining = self.surfing_manager.get_remaining_usage(user_id, self.config)
        
        # 格式化最近7天的使用情况
        recent_days = ""
        for date, count in stats["recent_days"].items():
            if count > 0:
                recent_days += f"• {date}: {count}次\n"
        
        if not recent_days:
            recent_days = "• 最近7天无使用记录\n"
        
        stats_text = f"""
📊 您的上网冲浪使用统计

📈 总体统计：
• 总使用次数：{stats['total_usage']}次
• 今日使用次数：{stats['today_usage']}次
• 剩余使用次数：{remaining if remaining >= 0 else '无限制'}次

📅 最近7天使用情况：
{recent_days}
💡 提示：使用 /冲浪 写说说 命令开始冲浪吧！
        """
        yield event.plain_result(stats_text)
    
    @filter.permission_type(filter.PermissionType.ADMIN)
    @surfing.command("重置次数")
    async def reset_usage(self, event: AiocqhttpMessageEvent, target_user: str = ""):
        """重置用户使用次数 <@用户>"""
        if target_user:
            # 重置指定用户
            user_id = target_user
            if user_id.startswith("@"):
                user_id = user_id[1:]
            
            if not user_id.isdigit():
                yield event.plain_result("❌ 请输入正确的QQ号")
                return
            
            self.surfing_manager.reset_user_usage(user_id)
            yield event.plain_result(f"✅ 已重置用户 {user_id} 的使用次数")
        else:
            # 重置所有用户
            all_usage = self.surfing_manager.get_all_users_usage()
            user_count = len(all_usage)
            
            # 重置所有用户
            for user_id in list(all_usage.keys()):
                self.surfing_manager.reset_user_usage(user_id)
            
            yield event.plain_result(f"✅ 已重置所有 {user_count} 个用户的使用次数")
    
    @filter.permission_type(filter.PermissionType.ADMIN)
    @surfing.command("查看统计")
    async def view_stats(self, event: AiocqhttpMessageEvent):
        """查看所有用户的上网冲浪使用统计"""
        all_usage = self.surfing_manager.get_all_users_usage()
        
        if not all_usage:
            yield event.plain_result("📊 暂无用户使用记录")
            return
        
        # 按总使用次数排序
        sorted_users = sorted(all_usage.items(), key=lambda x: sum(x[1].values()), reverse=True)
        
        stats_text = "📊 所有用户上网冲浪使用统计\n\n"
        
        for i, (user_id, usage_data) in enumerate(sorted_users[:10], 1):  # 显示前10名
            total_usage = sum(usage_data.values())
            today_usage = usage_data.get(self.surfing_manager._get_today_date(), 0)
            
            stats_text += f"{i}. 用户 {user_id}:\n"
            stats_text += f"   • 总使用次数: {total_usage}次\n"
            stats_text += f"   • 今日使用次数: {today_usage}次\n"
            
            # 显示最近3天的使用情况
            recent_days = []
            for j in range(3):
                date = (datetime.now() - timedelta(days=j)).strftime("%Y-%m-%d")
                if date in usage_data:
                    recent_days.append(f"{date}: {usage_data[date]}次")
            
            if recent_days:
                stats_text += f"   • 最近使用: {', '.join(recent_days)}\n"
            
            stats_text += "\n"
        
        if len(sorted_users) > 10:
            stats_text += f"... 还有 {len(sorted_users) - 10} 个用户\n"
        
        stats_text += "\n💡 使用 /冲浪 重置次数 <@用户> 来重置指定用户的使用次数"
        
        yield event.plain_result(stats_text)

    async def terminate(self):
        """插件卸载时"""
        if hasattr(self, "qzone"):
            await self.qzone.terminate()
        if hasattr(self, "auto_comment"):
            await self.auto_comment.terminate()
        if hasattr(self, "auto_publish"):
            await self.auto_publish.terminate()
        if hasattr(self, "llm"):
            await self.llm.close()
