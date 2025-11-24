"""
上网冲浪说说生成模块
基于Tavily API进行实时网络搜索，生成有趣的说说内容
"""

import asyncio
import json
import random
from typing import List, Dict, Any, Optional
from datetime import datetime

import aiohttp
from astrbot.api import logger


class WebSurfingGenerator:
    """上网冲浪说说生成器"""
    
    def __init__(self, context, config):
        """
        初始化上网冲浪生成器
        
        Args:
            context: AstrBot上下文
            config: 插件配置
        """
        self.context = context
        self.config = config
        self.tavily_api_key = config.get("tavily_api_key", "")
        self.session = None
        
        # 搜索主题分类
        self.search_categories = {
            "科技": ["人工智能", "ChatGPT", "AI绘画", "元宇宙", "区块链", "量子计算"],
            "娱乐": ["电影", "音乐", "游戏", "综艺", "明星", "网红"],
            "生活": ["美食", "旅游", "健身", "养生", "宠物", "家居"],
            "社会": ["热点", "时事", "民生", "教育", "职场", "情感"],
            "知识": ["冷知识", "历史", "科学", "文化", "哲学", "心理学"]
        }
        
        # 写作风格
        self.writing_styles = {
            "幽默": "用幽默风趣的语言，加入一些俏皮话和轻松的笑点",
            "深度": "深入分析问题，提供有深度的见解和思考",
            "简洁": "用简洁明了的语言，直击要点",
            "文艺": "用诗意的语言表达，适当使用比喻和意象",
            "实用": "提供实用的信息和建议，帮助读者解决问题"
        }
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建HTTP会话"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def search_with_tavily(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        使用Tavily API进行网络搜索
        
        Args:
            query: 搜索关键词
            max_results: 最大结果数量
            
        Returns:
            搜索结果列表
        """
        if not self.tavily_api_key:
            raise ValueError("未配置Tavily API密钥")
        
        session = await self._get_session()
        
        try:
            # Tavily API请求参数
            payload = {
                "api_key": self.tavily_api_key,
                "query": query,
                "search_depth": "advanced",
                "include_answer": True,
                "include_images": False,
                "max_results": max_results
            }
            
            async with session.post(
                "https://api.tavily.com/search",
                json=payload,
                timeout=30
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # 处理搜索结果
                    results = []
                    for result in data.get("results", []):
                        results.append({
                            "title": result.get("title", ""),
                            "url": result.get("url", ""),
                            "content": result.get("content", ""),
                            "score": result.get("score", 0)
                        })
                    
                    # 如果有答案，也添加到结果中
                    if data.get("answer"):
                        results.insert(0, {
                            "title": "AI总结",
                            "url": "",
                            "content": data["answer"],
                            "score": 1.0
                        })
                    
                    logger.info(f"Tavily搜索成功，获取到 {len(results)} 条结果")
                    return results
                else:
                    error_text = await response.text()
                    logger.error(f"Tavily API请求失败: {response.status} - {error_text}")
                    raise Exception(f"搜索失败: {response.status}")
                    
        except asyncio.TimeoutError:
            logger.error("Tavily搜索超时")
            raise Exception("搜索超时，请稍后重试")
        except Exception as e:
            logger.error(f"Tavily搜索异常: {e}")
            raise
    
    def _generate_search_query(self, category: Optional[str] = None, 
                              custom_topic: Optional[str] = None) -> str:
        """
        生成搜索查询
        
        Args:
            category: 搜索分类
            custom_topic: 自定义主题
            
        Returns:
            搜索查询字符串
        """
        if custom_topic:
            return custom_topic
        
        if category and category in self.search_categories:
            topics = self.search_categories[category]
            return random.choice(topics)
        else:
            # 随机选择一个分类
            all_categories = list(self.search_categories.keys())
            random_category = random.choice(all_categories)
            topics = self.search_categories[random_category]
            return random.choice(topics)
    
    async def generate_surfing_diary(self, 
                                    category: Optional[str] = None,
                                    custom_topic: Optional[str] = None,
                                    writing_style: str = "幽默",
                                    max_length: int = 300,
                                    include_sources: bool = True) -> Dict[str, Any]:
        """
        生成上网冲浪说说
        
        Args:
            category: 搜索分类
            custom_topic: 自定义主题
            writing_style: 写作风格
            max_length: 最大长度
            include_sources: 是否包含信息来源
            
        Returns:
            生成的说说内容及相关信息
        """
        # 生成搜索查询
        search_query = self._generate_search_query(category, custom_topic)
        
        logger.info(f"开始上网冲浪搜索: {search_query}")
        
        try:
            # 进行网络搜索
            search_results = await self.search_with_tavily(search_query)
            
            if not search_results:
                raise Exception("未搜索到相关信息")
            
            # 构建LLM提示词
            system_prompt = self._build_system_prompt(writing_style, max_length)
            user_prompt = self._build_user_prompt(search_query, search_results, include_sources)
            
            # 调用LLM生成说说
            get_using = self.context.get_using_provider()
            if not get_using:
                raise ValueError("未配置 LLM 提供商")
            
            llm_response = await get_using.text_chat(
                system_prompt=system_prompt,
                prompt=user_prompt,
                contexts=[]
            )
            
            diary_content = llm_response.completion_text.strip()
            
            # 内容质量检查
            diary_content = self._validate_content(diary_content, max_length)
            
            # 构建返回结果
            result = {
                "content": diary_content,
                "search_query": search_query,
                "search_results": search_results[:3],  # 只保留前3个结果
                "writing_style": writing_style,
                "category": category if category else "随机",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            logger.info(f"上网冲浪说说生成成功，长度: {len(diary_content)}")
            return result
            
        except Exception as e:
            logger.error(f"生成上网冲浪说说失败: {e}")
            # 返回一个默认的说说内容
            return {
                "content": f"今天上网冲浪发现了关于{search_query}的有趣内容，不过暂时无法获取详细信息。大家有什么新鲜事可以分享吗？😊",
                "search_query": search_query,
                "search_results": [],
                "writing_style": writing_style,
                "category": category if category else "随机",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
    
    def _build_system_prompt(self, writing_style: str, max_length: int) -> str:
        """构建系统提示词"""
        # 使用配置中的自定义提示词，如果没有配置则使用默认提示词
        custom_prompt = self.config.get("surfing_prompt", "")
        
        if custom_prompt:
            # 如果用户配置了自定义提示词，直接使用
            return custom_prompt
        
        # 默认提示词
        style_description = self.writing_styles.get(writing_style, self.writing_styles["幽默"])
        
        return f"""你是一个善于发现网络热点和有趣内容的观察者。请根据提供的网络搜索结果，生成一篇有趣的说说。

写作要求：
1. {style_description}
2. 内容长度不超过{max_length}字
3. 语言生动有趣，吸引读者
4. 可以适当加入表情符号增加趣味性
5. 避免敏感话题和政治内容
6. 保持积极向上的基调
7. 不要添加标签和来源信息


请直接输出说说内容，不需要标题或其他格式。"""
    
    def _build_user_prompt(self, query: str, results: List[Dict], include_sources: bool) -> str:
        """构建用户提示词"""
        prompt = f"搜索主题：{query}\n\n"
        prompt += "以下是网络搜索结果：\n"
        
        for i, result in enumerate(results[:3], 1):
            prompt += f"{i}. {result['title']}: {result['content'][:200]}...\n"
        
        if include_sources:
            prompt += "\n不要在说说中提及信息来源，也不要直接复制原文。"
        
        return prompt
    
    def _validate_content(self, content: str, max_length: int) -> str:
        """验证和清理内容"""
        # 去除多余的空格和换行
        content = ' '.join(content.split())
        
        # 长度检查
        if len(content) > max_length:
            content = content[:max_length-3] + "..."
        
        # 敏感词过滤
        sensitive_words = ["政治", "政府", "领导人", "暴力", "色情", "违法"]
        for word in sensitive_words:
            if word in content:
                content = "内容包含敏感信息，已自动过滤"
                break
        
        return content
    
    async def get_trending_topics(self) -> List[str]:
        """获取热门话题"""
        try:
            # 搜索当前热门话题
            results = await self.search_with_tavily("今日热门话题 热搜", max_results=3)
            
            topics = []
            for result in results:
                # 从标题中提取话题
                title = result.get('title', '')
                if title and len(title) > 5:  # 过滤过短的标题
                    topics.append(title)
            
            return topics[:5]  # 返回最多5个话题
            
        except Exception as e:
            logger.warning(f"获取热门话题失败: {e}")
            # 返回默认话题
            return ["人工智能", "ChatGPT", "AI绘画", "元宇宙", "区块链"]
    
    async def close(self):
        """关闭资源"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    def __del__(self):
        """析构函数"""
        if self.session and not self.session.closed:
            asyncio.create_task(self.close())