import random
from typing import Any

from aiocqhttp import CQHttp

from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.star.context import Context

from .post import Post


class LLMAction:
    def __init__(self, context: Context, config: AstrBotConfig, client: CQHttp):
        self.context = context
        self.config = config
        self.client = client

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

    async def generate_diary(self, group_id: str = "", topic: str | None = None) -> str:
        """根据聊天记录生成日记"""
        get_using = self.context.get_using_provider()
        if not get_using:
            raise ValueError("未配置 LLM 提供商")
        contexts = []

        if group_id:
            contexts = await self._get_msg_contexts(group_id)
        else:
            group_list = await self.client.get_group_list()
            group_ids = [group["group_id"] for group in group_list]
            random_group_id = str(random.choice(group_ids))  # 随机获取一个群组
            contexts = await self._get_msg_contexts(random_group_id)
        # TODO: 更多模式

        system_prompt = (
            f"# 写作主题：{topic}\n\n" + self.config["diary_prompt"]
            if topic
            else self.config["diary_prompt"]
        )

        logger.debug(f"{system_prompt}\n\n{contexts}")

        try:
            # 构建用户提示词，将聊天记录作为用户输入
            user_prompt = "请根据以下聊天记录生成一篇日记：\n" + "\n".join([ctx["content"] for ctx in contexts])
            
            llm_response = await get_using.text_chat(
                system_prompt=system_prompt,
                prompt=user_prompt,
                contexts=contexts,
            )
            diary = llm_response.completion_text
            logger.info(f"LLM 生成的日记：{diary}")
            return diary

        except Exception as e:
            raise ValueError(f"LLM 调用失败：{e}")

    async def generate_comment(self, post: Post) -> str:
        """根据帖子内容生成评论"""
        using_provider = self.context.get_using_provider()
        if not using_provider:
            raise ValueError("未配置 LLM 提供商")
        
        # 检查说说是否只有图片而没有文字内容
        has_text = bool(post.text.strip()) or bool(post.rt_con.strip())
        has_images = bool(post.images)
        
        # 如果只有图片而没有文字内容，则不进行评论
        if not has_text and has_images:
            logger.info("说说只有图片而没有文字内容，跳过评论")
            return ""
        
        try:
            # 构建包含图片描述的提示词
            image_description = ""
            if post.images:
                image_description = f"\n该帖子包含 {len(post.images)} 张图片，请根据文字内容生成评论。"
            
            prompt = f"\n这条帖子的具体内容如下：\n{post.text}\n{post.rt_con}{image_description}"
            logger.debug(prompt)
            
            # 移除不支持的image_urls参数，仅使用文本内容
            llm_response = await using_provider.text_chat(
                system_prompt=self.config["comment_prompt"],
                prompt=prompt,
            )
            comment = llm_response.completion_text.rstrip("。")
            logger.info(f"LLM 生成的评论：{comment}")
            return comment

        except Exception as e:
            raise ValueError(f"LLM 调用失败：{e}")
