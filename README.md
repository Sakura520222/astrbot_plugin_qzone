<div align="center">

# AstrBot QQ空间插件

[![访问统计](https://visitor-badge.laobi.icu/badge?page_id=Sakura520222.astrbot_plugin_qzone)](https://github.com/Sakura520222/astrbot_plugin_qzone) [![GitHub stars](https://img.shields.io/github/stars/Sakura520222/astrbot_plugin_qzone?style=flat-square&logo=github)](https://github.com/Sakura520222/astrbot_plugin_qzone/stargazers) [![GitHub forks](https://img.shields.io/github/forks/Sakura520222/astrbot_plugin_qzone?style=flat-square&logo=github)](https://github.com/Sakura520222/astrbot_plugin_qzone/network/members)

_✨ 专为AstrBot设计的QQ空间自动化管理插件 ✨_

[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-3.4%2B-orange.svg)](https://github.com/Soulter/AstrBot)
[![GitHub](https://img.shields.io/badge/原作者-Zhalslar-blue)](https://github.com/Zhalslar)
[![版本](https://img.shields.io/badge/版本-v2.1.1-brightgreen.svg)](https://github.com/Sakura520222/astrbot_plugin_qzone)

</div>

## 📖 项目概述

**AstrBot QQ空间插件** 是一个功能强大的QQ空间自动化管理工具，专为AstrBot机器人框架设计。该插件提供了完整的QQ空间操作功能，包括说说发布、点赞评论、校园表白墙管理、AI内容生成等，帮助用户实现QQ空间的智能化管理。

> **⚠️ 重要提示**：V2.0.0+ 版本已进入公测阶段，LLM模块正在开发中，部分功能尚处于测试阶段，请勿用于生产环境。

## ✨ 核心功能

### 🤖 智能内容生成
- **AI写说说**：基于主题智能生成说说内容
- **AI评论**：自动为好友说说生成合适的评论
- **智能配图**：LLM驱动的图片配文功能（开发中）

### 📱 说说管理
- **发布说说**：支持文字+图片的说说发布
- **查看说说**：查看指定用户或好友的说说列表
- **点赞评论**：自动点赞和评论好友说说
- **定时发布**：支持定时自动发布说说和日记

### 💌 校园表白墙
- **投稿系统**：用户可向表白墙投稿
- **审核机制**：管理员审核投稿内容
- **稿件管理**：查看、通过、拒绝稿件功能
- **草稿系统**：AI生成内容可保存为草稿

### 🔧 自动化操作
- **定时任务**：自动发布说说、评论、点赞
- **访客监控**：获取并渲染最近访客列表
- **权限管理**：分级权限控制，确保操作安全

## 🛠️ 环境要求

### 系统要求
- **操作系统**：Windows / Linux / macOS
- **Python版本**：3.10+
- **AstrBot版本**：3.4+

### 依赖包
```txt
pillowmd
json5
Pillow
```

## 📦 安装指南

### 方法一：通过插件市场安装（推荐）
1. 打开AstrBot控制台
2. 进入插件市场
3. 搜索 `astrbot_plugin_qzone`
4. 点击安装并等待完成
5. 重启AstrBot服务

### 方法二：手动安装
```bash
# 切换到AstrBot插件目录
cd /AstrBot/data/plugins

# 克隆插件仓库
git clone https://github.com/Sakura520222/astrbot_plugin_qzone

# 重启AstrBot服务
```

## ⚙️ 配置说明

安装完成后，请前往AstrBot的插件配置面板进行以下配置：

### 基础配置
- **QQ账号设置**：配置用于操作的QQ账号
- **API密钥**：配置必要的API密钥（如需要）
- **权限设置**：配置管理员和用户权限

### 功能配置
- **定时任务设置**：配置自动发布的时间间隔
- **AI模型设置**：配置LLM相关参数
- **表白墙设置**：配置投稿审核规则

## 🚀 使用指南

### 命令速查表

| 命令类别 | 命令 | 参数 | 说明 | 权限要求 |
|---------|------|------|------|----------|
| **说说管理** | 发说说 | 文字 + 图片（可选） | 立即发布一条说说 | 管理员 |
| | 写说说 | 主题（可选）+ 图片（可选） | AI生成内容并发布 | 管理员 |
| | 写稿 | 主题（可选）+ 图片（可选） | AI生成内容保存为草稿 | 所有人 |
| | 查看说说 | @某人（可选）+ 序号/范围（可选） | 查看指定用户的说说 | 所有人 |
| | 点赞说说 | @某人（可选）+ 序号/范围（可选） | 给指定说说点赞 | 所有人 |
| | 评论说说 | @某人（可选）+ 序号/范围（可选） | AI生成评论并发送 | 管理员 |
| **稿件管理** | 投稿 | 文字 + 图片（可选） | 向表白墙投稿 | 所有人 |
| | 通过稿件 | 稿件ID（默认最新） | 审核通过并发布 | 管理员 |
| | 查看稿件 | 稿件ID（可选，默认最新） | 查看稿件详情 | 所有人 |
| | 拒绝稿件 | 稿件ID + 原因（可选） | 拒绝指定稿件 | 管理员 |
| **其他功能** | 查看访客 | 无 | 获取最近访客列表 | 管理员 |

### 使用技巧

#### 特殊用法
1. **@群友替代**：可以使用 `@QQ号` 替代 `@群友`，查看任意用户的说说
2. **范围查询**：序号支持范围查询，如 `查看说说 2~5` 查看第2-5条说说
3. **好友查询**：`查看说说 2` 查看bot好友最近的两条说说
4. **指定用户**：`查看说说@某群友 2` 查看该群友的第2条说说

#### 权限说明
- **管理员权限**：发说说、审核稿件、评论说说等敏感操作
- **用户权限**：投稿、查看说说、点赞等基础操作

## 🎯 功能演示

### 说说发布效果
![说说发布示例](https://github.com/user-attachments/assets/7aa706c2-6c50-4740-b57b-e61b7a232adf)

### 表白墙投稿流程
1. 用户使用 `投稿` 命令提交内容
2. 管理员使用 `查看稿件` 审核内容
3. 管理员使用 `通过稿件` 或 `拒绝稿件` 处理
4. 通过的稿件自动发布到QQ空间

## 🔄 开发进度

### 已完成功能 ✅
- [x] 基础说说发布功能
- [x] 校园表白墙投稿审核系统
- [x] 说说点赞功能（接口成功，实际效果待验证）
- [x] AI评论生成功能
- [x] 定时自动发布说说和日记
- [x] 定时自动评论和点赞好友说说
- [x] LLM驱动的说说内容生成

### 开发中功能 🚧
- [ ] LLM智能配图功能
- [ ] 更丰富的说说主题模板
- [ ] 高级数据分析功能

## 🤝 贡献指南

我们欢迎各种形式的贡献！以下是参与项目的方式：

### 如何贡献
1. **报告问题**：发现bug或有改进建议？请提交Issue
2. **功能建议**：有新的功能想法？欢迎提出建议
3. **代码贡献**：想直接参与开发？请提交Pull Request
4. **文档改进**：发现文档问题？欢迎提交修改

### 贡献流程
1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## ❓ 常见问题解答

### Q: 插件安装后无法正常使用？
A: 请检查以下事项：
- 确认AstrBot版本为3.4+
- 检查Python版本为3.10+
- 验证所有依赖包已正确安装
- 查看插件配置是否正确

### Q: 点赞功能显示成功但实际无效？
A: 这是已知问题，点赞接口返回成功但实际可能不生效，正在调查原因。

### Q: 如何获取技术支持？
A: 可以通过以下方式获取帮助：
- 提交GitHub Issue
- 加入QQ反馈群：460973561
- 查看项目Wiki文档

### Q: 插件支持哪些QQ空间功能？
A: 目前支持说说发布、查看、点赞、评论，以及校园表白墙功能。日记功能正在开发中。

## 📞 技术支持

### 反馈渠道
- **GitHub Issues**：[提交问题报告](https://github.com/Sakura520222/astrbot_plugin_qzone/issues)
- **QQ群**：460973561（请先给项目点⭐️）
- **邮箱**：通过GitHub个人主页联系作者

### 更新日志
详细更新内容请查看 [Releases页面](https://github.com/Sakura520222/astrbot_plugin_qzone/releases)

## 🙏 鸣谢

本项目的发展离不开以下项目和资源的支持：

- **[CampuxBot项目](https://github.com/idoknow/CampuxBot)** - 部分代码参考
- **[QQ空间爬虫之爬取说说](https://kylingit.com/blog/qq-空间爬虫之爬取说说/)** - 技术思路参考
- **[QzoneExporter](https://github.com/wwwpf/QzoneExporter)** - 相关技术参考
- **[QQ空间](https://qzone.qq.com/)** - 界面样式参考
- **所有贡献者和用户** - 感谢你们的支持和建议

## 📄 许可证

本项目采用 **MIT许可证** - 查看 [LICENSE](LICENSE) 文件了解详情。

---

<div align="center">

**如果这个项目对你有帮助，请给个 ⭐️ 支持一下！**

*最后更新：2025.11.22*  
*版本：v2.1.1*

</div>