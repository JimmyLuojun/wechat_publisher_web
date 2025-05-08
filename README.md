# 微信公众号文章发布助手 (WeChat Publisher Web)

## 项目描述

这里写一段（1-2段）关于您项目的简洁描述。它解决了什么问题？主要目标是什么？
*例如：“微信公众号文章发布助手 (WeChat Publisher Web) 是一个基于 Django 的 Web 应用，旨在简化创建和发布文章到微信公众号的流程。它允许用户上传 Markdown 文件，管理相关图片，预览内容，并将文章直接发布到微信公众号的草稿箱。”*

## 目录 (可选，但对于较长的 README 很用)

* [主要功能](#主要功能)
* [技术栈](#技术栈)
* [环境要求](#环境要求)
* [安装步骤](#安装步骤)
* [配置说明](#配置说明)
* [运行应用](#运行应用)
* [使用指南](#使用指南)
* [API 接口](#api接口)
* [常见问题](#常见问题)
* [如何贡献](#如何贡献)
* [许可证](#许可证)

## 主要功能

列出您应用的核心功能点。
* 上传 Markdown 格式的文章。
* 上传并关联封面图片。
* 上传并管理 Markdown 中引用的内容图片。
* 自动图片处理（例如，根据微信限制调整图片大小）。
* 从 Markdown frontmatter 中提取元数据。
* 生成 HTML 预览。
* 缓存已上传至微信的图片（封面图和内容图）以便复用。
* 将文章作为草稿发布到微信公众号。
*针对特定微信 API 错误的重试机制（例如，封面图上传失败）。

## 技术栈

列出项目使用的主要技术和库。
* **后端:** Python, Django, Django REST Framework
* **前端:** HTML, CSS, JavaScript (原生 JS)
* **关键 Python 库:**
    * `PyYAML` (用于读取 Markdown frontmatter)
    * `Pillow` (用于图片处理)
    * `requests` (用于与微信 API 交互，可能在 `publishing_engine` 中)
    * *(列出其他重要的库)*
* **数据库:** SQLite (开发环境), *(如果生产环境使用 PostgreSQL, MySQL 等，请注明)*
* **依赖管理:** Poetry (根据您的虚拟环境路径推断)
* **外部服务:** 微信公众平台 API

## 环境要求

用户在安装和运行您的项目前，需要准备哪些软件环境？
* Git
* Python (指明版本, 例如 3.12)
* Poetry (或者 pip，如果您也提供了 `requirements.txt`)
* 拥有 API 权限的微信公众号。

## 安装步骤

分步说明如何在本地安装和运行项目。

1.  **克隆代码库:**
    ```bash
    git clone <您的代码库URL>
    cd wechat_publisher_web
    ```
2.  **设置 Python 虚拟环境并安装依赖:**
    *如果使用 Poetry:*
    ```bash
    poetry install
    poetry shell # 激活虚拟环境
    ```
    *如果使用 pip 和 `requirements.txt` (如果需要，可以用 `poetry export -f requirements.txt --output requirements.txt` 生成):*
    ```bash
    python -m venv venv
    source venv/bin/activate  # Windows 系统: venv\Scripts\activate
    pip install -r requirements.txt
    ```
3.  **数据库设置:**
    ```bash
    python manage.py migrate
    ```
4.  **创建超级管理员 (用于访问 Django Admin 后台):**
    ```bash
    python manage.py createsuperuser
    ```
5.  **(如果适用) `publishing_engine` 设置:**
    * 如果 `publishing_engine` 是一个子模块或有独立的安装步骤，请在此处详细说明。

## 配置说明

解释所有必要的配置。

1.  **环境变量:**
    * 说明如何设置必要的环境变量 (例如 `WECHAT_APP_ID`, `WECHAT_SECRET`, `WECHAT_BASE_URL`, `MEDIA_ROOT`, `PREVIEW_CSS_FILE_PATH`, `DATABASE_URL` 如果不是 SQLite 等)。
    * 提及是否使用 `.env` 文件，并提供一个 `.env.example` 模板文件。
    * `.env.example` 示例:
        ```
        DJANGO_SECRET_KEY='your_secret_key_here'
        DEBUG=True
        WECHAT_APP_ID='your_wechat_app_id'
        WECHAT_SECRET='your_wechat_secret'
        WECHAT_BASE_URL='[https://api.wechat.com](https://api.wechat.com)' # 或实际地址
        # 预览页面自定义 CSS 文件路径 (相对于项目根目录或绝对路径)
        PREVIEW_CSS_FILE_PATH='publisher/static/publisher/css/preview_style.css'
        # ... 其他设置 ...
        ```
2.  **微信公众平台设置:**
    * 确保已启用 API 权限。
    * **IP 白名单:** 提醒用户将其服务器的公网 IP 地址添加到微信公众平台的 IP 白名单中 (基本配置 -> IP白名单)。这是您最近遇到的问题！
    * 回调 URL 配置 (如果您的应用使用任何微信回调)。

## 运行应用

1.  **启动开发服务器:**
    ```bash
    python manage.py runserver
    ```
2.  **访问应用:**
    打开浏览器并访问 `http://127.0.0.1:8000/` (或您的主应用入口 URL)。

## 使用指南

解释如何使用应用的核心功能。

1.  **导航**至上传表单 (`/publisher/upload/`)。
2.  **上传文件:**
    * 选择您的 **Markdown 文件 (.md)**。
    * 选择一个 **封面图片 (JPG, PNG)**。
    * (可选) 选择您 Markdown 中引用的 **内容图片**。
3.  **Markdown Frontmatter 要求:**
    * 解释 Markdown 文件 YAML frontmatter 中的必填和可选字段。这非常重要！
    * 示例:
        ```yaml
        ---
        title: "必填: 您的文章标题"
        author: "必填: 作者名称"
        digest: "可选: 文章摘要，用于微信文章列表 (建议最多120字符)"
        cover_image_path: "必填: 主封面图片的路径，系统将按此引用或作为占位符名称 (例如: cover.jpg 或 /server/path/to/cover.jpg - 请明确其用途和格式！)"
        # 添加您的 metadata_reader.py 期望或处理的任何其他字段
        ---
        ```
4.  **处理与预览:** 点击 "处理与预览" 按钮。
5.  **检查预览:** 如果成功，将出现一个预览链接。检查内容。
6.  **确认并发布:** 如果预览无误，点击 "确认并发布到微信草稿箱"。
7.  **在微信后台完成:** 文章将作为草稿发布。您需要前往微信公众平台后台进行最终编辑和定时/直接发布。

## API 接口 (可选)

如果您的 API 接口也希望被其他服务调用或用于高级集成，请简要描述它们 (主要面向开发者)。

* **`POST /publisher/api/process/`**
    * **描述:** 上传 Markdown、封面图片和内容图片，以启动处理流程并生成预览。
    * **请求:** `multipart/form-data` 类型，包含字段 `markdown_file`, `cover_image`, `content_images` (可多选)。
    * **响应:** 成功时返回包含 `task_id` 和 `preview_url` 的 JSON。
* **`POST /publisher/api/confirm/`**
    * **描述:** 确认已处理的任务，并将其作为草稿发布到微信。
    * **请求:** JSON 类型，包含 `{"task_id": "your_task_id"}`。
    * **响应:** 成功时返回包含 `status`, `message`, 和 `wechat_media_id` 的 JSON。

## 常见问题 (可选)

列出常见问题及其解决方案。
* **API 调用返回 404 错误:** 确保 `app.js` 中的 URL 与 Django `urls.py` 配置匹配。检查路径末尾是否有斜杠。
* **微信 API 错误: "invalid ip ... not in whitelist"**: 将服务器 IP 添加到微信公众号的 IP 白名单中。
* **YAML 解析错误 / 元数据验证错误**: 检查 Markdown frontmatter 是否符合正确的 YAML 语法，并包含所有必填字段 (例如 `title`, `cover_image_path`)。确保包含特殊字符的字符串值已用引号括起来。
* **图片处理失败**: 确保 Pillow 已正确安装。检查图片文件格式和大小限制。
* **静态文件 (CSS/JS) 未加载/更新**: 清除浏览器缓存 (强制刷新)，并确保 Django 静态文件配置正确 (`STATIC_URL`, `STATICFILES_DIRS`)。

## 如何贡献 (如果您接受他人贡献)

为项目贡献代码的指南。
* 代码规范。
* 如何提交 Pull Request。
* 如何报告 Bug 或建议功能。

## 许可证

指明您项目的许可证 (例如 MIT, Apache 2.0, GPL)。
*例如：“本项目采用 MIT 许可证 - 详情请参阅 LICENSE.md 文件。”*
(然后您需要创建一个包含实际许可证文本的 `LICENSE.md` 文件)。

---

**编写优秀 README 的技巧:**

* **清晰简洁:** 直奔主题。
* **使用 Markdown:** 使用标题、列表、代码块等 Markdown 格式使 README 更易于阅读。
* **保持更新:** 随着项目的发展，及时更新 README 以反映设置、功能或用法的更改。
* **面向新用户:** 从一个从未见过您项目的用户的角度来编写。
* **添加截图或 GIF (可选):** 可视化内容可以非常有效地展示您的应用。

从最重要的部分开始 (项目描述、安装、配置、运行、使用指南)，然后根据需要填写其他部分。祝您顺利！