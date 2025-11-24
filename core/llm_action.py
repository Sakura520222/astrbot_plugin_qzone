import asyncio
import base64
import io
import random
from typing import Any

from aiocqhttp import CQHttp
from PIL import Image

from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.star.context import Context

from .post import Post
from .web_surfing import WebSurfingGenerator


class LLMAction:
    def __init__(self, context: Context, config: AstrBotConfig, client: CQHttp):
        self.context = context
        self.config = config
        self.client = client
        
        # 初始化上网冲浪生成器
        self.web_surfing = WebSurfingGenerator(context, config)

    def _build_context(
        self, round_messages: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        """
        把所有回合里的纯文本消息打包成 openai-style 的 user 上下文。
        """
        contexts: list[dict[str, str]] = []
        for msg in round_messages:
            # 提取并拼接所有 text 片段
            text_segments = [
                seg["data"]["text"] for seg in msg["message"] if seg["type"] == "text"
            ]

            text = f"{msg['sender']['nickname']}: {''.join(text_segments).strip()}"
            # 仅当真正说了话才保留
            if text:
                contexts.append({"role": "user", "content": text})
        return contexts

    async def _get_msg_contexts(self, group_id: str) -> list[dict]:
        """获取群聊历史消息"""
        message_seq = 0
        contexts: list[dict] = []
        while len(contexts) < self.config["diary_max_msg"]:
            payloads = {
                "group_id": group_id,
                "message_seq": message_seq,
                "count": 200,
                "reverseOrder": True,
            }
            result: dict = await self.client.api.call_action(
                "get_group_msg_history", **payloads
            )
            round_messages = result["messages"]
            if not round_messages:
                break
            message_seq = round_messages[0]["message_id"]

            contexts.extend(self._build_context(round_messages))
        return contexts

    async def generate_diary(self, group_id: str = "", topic: str | None = None, 
                           style: str = "default", max_length: int = 500, 
                           multi_group: bool = False, max_groups: int = 3) -> str:
        """根据聊天记录生成说说
        
        Args:
            group_id: 群组ID，为空则随机选择
            topic: 指定主题
            style: 写作风格（default/poetic/humorous/philosophical/casual）
            max_length: 最大长度限制
            multi_group: 是否从多个群聊获取消息
            max_groups: 最多获取的群聊数量
        """
        get_using = self.context.get_using_provider()
        if not get_using:
            raise ValueError("未配置 LLM 提供商")
        contexts = []

        if group_id:
            contexts = await self._get_msg_contexts(group_id)
        else:
            if multi_group:
                # 多群聊消息融合模式
                contexts = await self._get_multi_group_contexts(max_groups)
            else:
                # 单群聊模式（保持原有逻辑）
                group_list = await self.client.get_group_list()
                group_ids = [group["group_id"] for group in group_list]
                random_group_id = str(random.choice(group_ids))  # 随机获取一个群组
                contexts = await self._get_msg_contexts(random_group_id)

        # 构建风格化的系统提示词
        style_prompts = {
            "default": self.config["diary_prompt"],
            "poetic": "请用诗意的语言表达，可以适当使用比喻和意象，让文字富有韵律感",
            "humorous": "请用幽默风趣的语言表达，可以加入一些俏皮话和轻松的笑点",
            "philosophical": "请用哲理性的语言表达，可以探讨一些人生哲理和深度思考",
            "casual": "请用轻松随意的语言表达，就像和朋友聊天一样自然"
        }
        
        base_prompt = style_prompts.get(style, self.config["diary_prompt"])
        
        # 根据模式调整提示词
        if multi_group:
            base_prompt = "请综合多个群聊的聊天记录，提炼出有趣的话题和观点，生成一篇说说。" + base_prompt
        
        system_prompt = (
            f"# 写作主题：{topic}\n\n" + base_prompt
            if topic
            else base_prompt
        )
        
        # 添加长度限制
        system_prompt += f"\n\n# 要求：内容长度不超过{max_length}字"

        logger.debug(f"风格：{style}, 主题：{topic}, 多群聊：{multi_group}, 系统提示词：{system_prompt}")

        try:
            # 构建用户提示词，将聊天记录作为用户输入
            if multi_group:
                user_prompt = "请综合以下多个群聊的聊天记录，生成一篇说说：\n" + "\n".join([ctx["content"] for ctx in contexts])
            else:
                user_prompt = "请根据以下聊天记录生成一篇说说：\n" + "\n".join([ctx["content"] for ctx in contexts])
            
            llm_response = await get_using.text_chat(
                system_prompt=system_prompt,
                prompt=user_prompt,
                contexts=contexts,
            )
            diary = llm_response.completion_text
            
            # 内容过滤和长度检查
            diary = self._filter_content(diary)
            if len(diary) > max_length:
                diary = diary[:max_length-3] + "..."
            
            logger.info(f"LLM 生成的说说（风格：{style}，多群聊：{multi_group}，长度：{len(diary)}）：{diary}")
            return diary

        except Exception as e:
            raise ValueError(f"LLM 调用失败：{e}")
    
    async def _get_multi_group_contexts(self, max_groups: int = 3) -> list[dict]:
        """从多个群聊获取消息上下文"""
        group_list = await self.client.get_group_list()
        
        # 随机选择多个群聊
        selected_groups = random.sample(group_list, min(max_groups, len(group_list)))
        
        all_contexts = []
        
        for group in selected_groups:
            try:
                group_id = str(group["group_id"])
                group_name = group["group_name"]
                logger.info(f"正在获取群聊 {group_name}({group_id}) 的消息")
                
                # 获取该群聊的消息
                group_contexts = await self._get_msg_contexts(group_id)
                
                # 为每个群聊的消息添加群聊标识
                for ctx in group_contexts:
                    ctx["content"] = f"【{group_name}】{ctx['content']}"
                
                all_contexts.extend(group_contexts)
                
                logger.info(f"群聊 {group_name} 获取到 {len(group_contexts)} 条消息")
                
            except Exception as e:
                logger.error(f"获取群聊 {group['group_name']} 消息失败：{e}")
                continue
        
        # 随机打乱消息顺序，避免群聊顺序影响
        random.shuffle(all_contexts)
        
        # 限制总消息数量，避免上下文过长
        max_total_messages = self.config["diary_max_msg"] * 2  # 允许比单群聊多一倍的消息
        if len(all_contexts) > max_total_messages:
            all_contexts = all_contexts[:max_total_messages]
        
        logger.info(f"多群聊模式：从 {len(selected_groups)} 个群聊获取了 {len(all_contexts)} 条消息")
        return all_contexts
    
    def _filter_content(self, content: str) -> str:
        """内容过滤和审核，避免生成不当内容"""
        # 敏感词过滤列表（更全面的敏感词库）
        sensitive_categories = {
            "政治敏感": ["政治", "政府", "领导人", "国家", "政策", "体制", "民主"],
            "暴力违法": ["暴力", "违法", "犯罪", "毒品", "赌博", "诈骗", "杀人"],
            "色情低俗": ["色情", "淫秽", "低俗", "性爱", "淫乱", "猥亵"]
        }
        
        # 检查敏感词
        for category, words in sensitive_categories.items():
            for word in words:
                if word in content:
                    logger.warning(f"检测到敏感内容：{category} - {word}")
                    return "内容包含敏感信息，已自动过滤"
        
        # 内容质量检查
        if self._is_low_quality(content):
            logger.warning("内容质量过低，已过滤")
            return "内容质量不符合要求，已自动过滤"
        
        # 长度检查
        if len(content.strip()) < 10:
            logger.warning("内容过短，已过滤")
            return "内容过短，已自动过滤"
        
        return content
    
    def _is_low_quality(self, content: str) -> bool:
        """判断内容质量是否过低"""
        # 检查重复字符
        if self._has_repeated_chars(content, threshold=5):
            return True
        
        # 检查无意义内容
        meaningless_patterns = [
            "啊啊啊啊", "哈哈哈", "。。。", "？？？", "！！！",
            "test", "测试", "hello", "你好", "123", "abc"
        ]
        
        for pattern in meaningless_patterns:
            if pattern in content:
                return True
        
        # 检查标点符号比例
        punctuation_count = sum(1 for char in content if char in "，。！？；：、")
        if len(content) > 0 and punctuation_count / len(content) > 0.5:
            return True
        
        return False
    
    def _has_repeated_chars(self, content: str, threshold: int = 5) -> bool:
        """检查是否有重复字符超过阈值"""
        if not content:
            return False
        
        max_repeat = 1
        current_repeat = 1
        
        for i in range(1, len(content)):
            if content[i] == content[i-1]:
                current_repeat += 1
                max_repeat = max(max_repeat, current_repeat)
            else:
                current_repeat = 1
        
        return max_repeat >= threshold
    
    async def generate_image(self, text: str, style: str = "default") -> list[str]:
        """根据文本内容生成图片
        
        Args:
            text: 文本内容
            style: 图片风格（default/artistic/minimalist/vibrant）
            
        Returns:
            图片URL或base64编码的图片列表
        """
        get_using = self.context.get_using_provider()
        if not get_using:
            raise ValueError("未配置 LLM 提供商")
        
        # 检查是否支持图片生成
        if not hasattr(get_using, 'image_generate'):
            logger.warning("当前LLM提供商不支持图片生成功能")
            return []
        
        try:
            # 构建图片生成提示词
            style_prompts = {
                "default": "生成一张与文本内容相关的精美图片",
                "artistic": "生成一张具有艺术感的图片，体现文本的意境",
                "minimalist": "生成一张简约风格的图片，突出文本的核心",
                "vibrant": "生成一张色彩鲜艳、充满活力的图片"
            }
            
            image_prompt = f"{style_prompts.get(style, style_prompts['default'])}。文本内容：{text}"
            
            # 调用图片生成API
            image_response = await get_using.image_generate(
                prompt=image_prompt,
                size="1024x1024",
                quality="standard",
                n=1
            )
            
            # 处理返回的图片数据
            image_urls = []
            for image_data in image_response.images:
                if hasattr(image_data, 'url'):
                    image_urls.append(image_data.url)
                elif hasattr(image_data, 'b64_json'):
                    # 如果是base64编码的图片，可以保存为文件或直接使用
                    image_data = base64.b64decode(image_data.b64_json)
                    image = Image.open(io.BytesIO(image_data))
                    
                    # 保存图片到临时文件
                    temp_path = f"/tmp/qzone_image_{random.randint(1000, 9999)}.png"
                    image.save(temp_path)
                    image_urls.append(temp_path)
            
            logger.info(f"成功生成 {len(image_urls)} 张图片")
            return image_urls
            
        except Exception as e:
            logger.error(f"图片生成失败：{e}")
            return []
    
    async def generate_diary_with_images(self, group_id: str = "", topic: str | None = None, 
                                       style: str = "default", max_length: int = 500,
                                       multi_group: bool = False, max_groups: int = 3,
                                       generate_images: bool = True) -> tuple[str, list[str]]:
        """生成说说并配图
        
        Returns:
            (说说内容, 图片列表)
        """
        # 先生成文本内容
        text = await self.generate_diary(
            group_id=group_id,
            topic=topic,
            style=style,
            max_length=max_length,
            multi_group=multi_group,
            max_groups=max_groups
        )
        
        # 检查内容是否被过滤
        if "内容包含敏感信息" in text or "内容质量不符合要求" in text or "内容过短" in text:
            return text, []
        
        # 生成图片
        images = []
        if generate_images:
            try:
                images = await self.generate_image(text, style)
                logger.info(f"成功为说说生成 {len(images)} 张配图")
            except Exception as e:
                logger.warning(f"图片生成失败，继续发布纯文本说说：{e}")
        
        return text, images
 
    async def analyze_sentiment_and_topic(self, text: str, event=None) -> tuple[str, str]:
        """分析文本的情感和话题
        
        Returns:
            (情感分类, 话题分类)
        """
        try:
            # 构建情感和话题分析提示词
            prompt = """请分析以下文本的情感和话题，按以下格式返回：
情感分类：[积极/消极/中性/混合]
话题分类：[生活/工作/学习/情感/娱乐/科技/其他]

文本内容：{text}""".format(text=text)
            
            # 使用AstrBot v4.5.7+的新LLM调用方式
            if event and hasattr(event, 'unified_msg_origin'):
                # 如果有事件对象，使用会话相关的LLM调用
                umo = event.unified_msg_origin
                provider_id = await self.context.get_current_chat_provider_id(umo=umo)
                llm_resp = await self.context.llm_generate(
                    chat_provider_id=provider_id,
                    prompt=prompt,
                )
                result = llm_resp.completion_text
            else:
                # 如果没有事件对象，使用默认的LLM调用
                get_using = self.context.get_using_provider()
                if not get_using:
                    return "中性", "其他"
                
                context = [
                    {"role": "system", "content": "你是一个专业的情感分析和话题分类助手"},
                    {"role": "user", "content": prompt}
                ]
                
                # 兼容旧版本调用方式
                if hasattr(get_using, 'chat_complete'):
                    response = await get_using.chat_complete(context)
                elif hasattr(get_using, 'chat'):
                    response = await get_using.chat(context)
                elif hasattr(get_using, 'complete'):
                    response = await get_using.complete(context)
                else:
                    logger.warning("未找到合适的LLM调用方法，使用默认分析结果")
                    return "中性", "其他"
                
                result = response.choices[0].message.content
            
            # 解析结果
            sentiment = "中性"
            topic = "其他"
            
            for line in result.split('\n'):
                if line.startswith("情感分类："):
                    sentiment = line.replace("情感分类：", "").strip()
                elif line.startswith("话题分类："):
                    topic = line.replace("话题分类：", "").strip()
            
            # 验证情感分类
            valid_sentiments = ["积极", "消极", "中性", "混合"]
            if sentiment not in valid_sentiments:
                sentiment = "中性"
            
            # 验证话题分类
            valid_topics = ["生活", "工作", "学习", "情感", "娱乐", "科技", "其他"]
            if topic not in valid_topics:
                topic = "其他"
            
            logger.info(f"情感分析结果：情感={sentiment}，话题={topic}")
            return sentiment, topic
            
        except Exception as e:
            logger.warning(f"情感分析失败：{e}")
            return "中性", "其他"
    
    async def generate_diary_with_analysis(self, group_id: str = "", topic: str | None = None, 
                                         style: str = "default", max_length: int = 500,
                                         multi_group: bool = False, max_groups: int = 3,
                                         generate_images: bool = True) -> tuple[str, list[str], str, str]:
        """生成说说并进行分析
        
        Returns:
            (说说内容, 图片列表, 情感分类, 话题分类)
        """
        # 生成说说内容和图片
        text, images = await self.generate_diary_with_images(
            group_id=group_id,
            topic=topic,
            style=style,
            max_length=max_length,
            multi_group=multi_group,
            max_groups=max_groups,
            generate_images=generate_images
        )
        
        # 检查内容是否被过滤
        if "内容包含敏感信息" in text or "内容质量不符合要求" in text or "内容过短" in text:
            return text, [], "中性", "其他"
        
        # 进行情感和话题分析
        sentiment, topic_analysis = await self.analyze_sentiment_and_topic(text, event=None)
        
        return text, images, sentiment, topic_analysis
 
    async def generate_comment(self, post: Post, event=None) -> str:
        """根据帖子内容生成评论"""
        # 构建提示词
        prompt = self.config.get("comment_prompt", "请根据帖子内容生成一条精辟简短的评论, 评论要抓住主题")
        
        # 构建完整的提示词
        full_prompt = f"{prompt}\n帖子内容：{post.text}"
        
        # 使用AstrBot v4.5.7+的新LLM调用方式
        try:
            if event and hasattr(event, 'unified_msg_origin'):
                # 如果有事件对象，使用会话相关的LLM调用
                umo = event.unified_msg_origin
                provider_id = await self.context.get_current_chat_provider_id(umo=umo)
                llm_resp = await self.context.llm_generate(
                    chat_provider_id=provider_id,
                    prompt=full_prompt,
                )
                return llm_resp.completion_text
            else:
                # 如果没有事件对象，使用默认的LLM调用
                get_using = self.context.get_using_provider()
                if not get_using:
                    raise ValueError("未配置 LLM 提供商")
                
                # 构建上下文
                context = [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"帖子内容：{post.text}"}
                ]
                
                # 兼容旧版本调用方式
                if hasattr(get_using, 'chat_complete'):
                    response = await get_using.chat_complete(context)
                    return response.choices[0].message.content
                elif hasattr(get_using, 'chat'):
                    response = await get_using.chat(context)
                    return response.choices[0].message.content
                elif hasattr(get_using, 'complete'):
                    response = await get_using.complete(context)
                    return response.choices[0].message.content
                else:
                    logger.warning("未找到合适的LLM调用方法，使用默认评论")
                    return "👍 这条说说很有意思！"
        except Exception as e:
            logger.error(f"LLM调用失败：{e}")
            # 返回一个安全的默认评论
            return "👍 这条说说很有意思！"
    
    async def generate_surfing_diary(self, 
                                    category: str = "随机",
                                    custom_topic: str = "",
                                    writing_style: str = "幽默",
                                    max_length: int = 300,
                                    include_sources: bool = True) -> dict:
        """
        生成上网冲浪说说
        
        Args:
            category: 搜索分类（科技/娱乐/生活/社会/知识/随机）
            custom_topic: 自定义搜索主题
            writing_style: 写作风格（幽默/深度/简洁/文艺/实用）
            max_length: 最大长度
            include_sources: 是否包含信息来源
            
        Returns:
            生成的说说内容及相关信息
        """
        try:
            result = await self.web_surfing.generate_surfing_diary(
                category=category if category != "随机" else None,
                custom_topic=custom_topic if custom_topic else None,
                writing_style=writing_style,
                max_length=max_length,
                include_sources=include_sources
            )
            
            logger.info(f"上网冲浪说说生成成功，分类：{category}，风格：{writing_style}")
            return result
            
        except Exception as e:
            logger.error(f"生成上网冲浪说说失败：{e}")
            # 返回错误信息
            return {
                "content": f"上网冲浪失败：{str(e)}，请检查网络连接或Tavily API配置。",
                "search_query": custom_topic if custom_topic else category,
                "search_results": [],
                "writing_style": writing_style,
                "category": category,
                "timestamp": "",
                "error": str(e)
            }
    
    async def get_trending_topics(self) -> list:
        """获取热门话题"""
        try:
            topics = await self.web_surfing.get_trending_topics()
            logger.info(f"获取到 {len(topics)} 个热门话题")
            return topics
        except Exception as e:
            logger.error(f"获取热门话题失败：{e}")
            return []
    
    async def generate_surfing_diary_with_images(self,
                                                 category: str = "随机",
                                                 custom_topic: str = "",
                                                 writing_style: str = "幽默",
                                                 max_length: int = 300,
                                                 include_sources: bool = True) -> tuple:
        """
        生成上网冲浪说说并配图
        
        Returns:
            (说说内容, 图片列表, 搜索信息)
        """
        try:
            # 先生成说说内容
            surfing_result = await self.generate_surfing_diary(
                category=category,
                custom_topic=custom_topic,
                writing_style=writing_style,
                max_length=max_length,
                include_sources=include_sources
            )
            
            # 检查是否生成成功
            if surfing_result.get("error"):
                return surfing_result["content"], [], surfing_result
            
            # 生成图片
            images = []
            try:
                images = await self.generate_image(surfing_result["content"], "default")
                logger.info(f"成功为上网冲浪说说生成 {len(images)} 张配图")
            except Exception as e:
                logger.warning(f"图片生成失败，继续发布纯文本说说：{e}")
            
            return surfing_result["content"], images, surfing_result
            
        except Exception as e:
            logger.error(f"生成上网冲浪说说配图失败：{e}")
            return f"生成说说失败：{str(e)}", [], {}
    
    async def close(self):
        """关闭资源"""
        try:
            await self.web_surfing.close()
        except Exception as e:
            logger.warning(f"关闭上网冲浪生成器失败：{e}")
