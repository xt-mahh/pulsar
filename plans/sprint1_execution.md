# Pulsar Phase 1 Sprint 1 — execution/ 模块详细计划

> 本文档描述 `execution/` 模块的设计方案，包含 Tool 注册中心、内置工具、微信 MCP Adapter。
> execution 是系统的手，拥有操作一切的能力。

---

## 一、模块定位

**职责**：提供系统执行能力，包括：
- Tool 注册中心（统一管理所有工具）
- 内置工具（HTTP 请求、文件读写、图片处理）
- 平台 MCP Adapter（微信 Adapter v2.0 增强版）
- Adapter 基类规范（为后续多平台扩展做准备）

**设计原则**：
- **注册中心模式** — 所有工具通过装饰器注册，按名称发现和调用
- **平台隔离** — 每个 Adapter 独立，一个平台的故障不影响其他
- **频率控制** — 自动跟踪 API 调用频次，触发限流时排队等待

---

## 二、文件清单

| # | 文件 | 优先级 | 依赖 |
|---|------|--------|------|
| 1 | `execution/__init__.py` | P0 | 无 |
| 2 | `execution/tools/__init__.py` | P0 | 无 |
| 3 | `execution/tools/base.py` | P0 | shared |
| 4 | `execution/tools/registry.py` | P0 | shared |
| 5 | `execution/tools/builtins/__init__.py` | P0 | registry |
| 6 | `execution/tools/builtins/http.py` | P1 | base |
| 7 | `execution/tools/builtins/fileio.py` | P1 | base |
| 8 | `execution/tools/builtins/image.py` | P2 | base |
| 9 | `execution/adapters/__init__.py` | P0 | 无 |
| 10 | `execution/adapters/base.py` | P0 | shared |
| 11 | `execution/adapters/wechat/__init__.py` | P0 | adapter |
| 12 | `execution/adapters/wechat/auth.py` | P0 | shared |
| 13 | `execution/adapters/wechat/models.py` | P0 | shared |
| 14 | `execution/adapters/wechat/tools.py` | P0 | shared |
| 15 | `execution/adapters/wechat/adapter.py` | P0 | 以上全部 |

---

## 三、`execution/tools/base.py` 设计方案

### 3.1 职责

定义工具基类和 `@tool` 装饰器，提供统一的工具定义规范。

### 3.2 工具基类

```python
class BaseTool(ABC):
    """工具基类 — 所有工具必须继承此类"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称（蛇形命名，如 http_request）"""
    
    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述"""
    
    @property
    @abstractmethod
    def input_schema(self) -> dict:
        """JSON Schema 格式的输入参数定义"""
    
    @abstractmethod
    async def execute(self, **kwargs) -> dict:
        """执行工具逻辑"""
    
    def to_definition(self) -> ToolDefinition:
        """转换为 MCP ToolDefinition"""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
            agent="tool.builtins",
        )
```

### 3.3 `@tool` 装饰器

```python
def tool(name: str = None, description: str = None, input_schema: dict = None):
    """工具装饰器 — 将异步函数注册为工具
    
    用法:
        @tool(name="http_request", description="发送 HTTP 请求")
        async def http_request(url: str, method: str = "GET") -> dict:
            ...
    
    自动生成 input_schema:
        - 从函数签名推断参数类型
        - 支持 str/int/float/bool/ Optional / list / dict
        - 有默认值的参数自动标记为 optional
    """
    def decorator(func):
        # 从函数签名生成 input_schema
        sig = inspect.signature(func)
        properties = {}
        required = []
        for param_name, param in sig.parameters.items():
            # 推断类型
            if param.annotation is inspect.Parameter.empty:
                json_type = "string"
            else:
                json_type = _type_to_json_schema(param.annotation)
            
            properties[param_name] = {
                "type": json_type,
                "description": "",  # 可从 docstring 解析
            }
            if param.default is inspect.Parameter.empty:
                required.append(param_name)
        
        schema = {
            "type": "object",
            "properties": properties,
            "required": required,
        }
        
        # 创建工具类
        class DecoratedTool(BaseTool):
            @property
            def name(self): return name or func.__name__
            @property
            def description(self): return description or func.__doc__ or ""
            @property
            def input_schema(self): return input_schema or schema
            async def execute(self, **kwargs): return await func(**kwargs)
        
        return DecoratedTool()
    
    return decorator
```

### 3.4 类型到 JSON Schema 映射

```python
def _type_to_json_schema(annotation) -> str:
    """Python 类型 → JSON Schema 类型映射"""
    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        dict: "object",
        list: "array",
        bytes: "string",  # base64 encoded
    }
    # 处理 Optional[X]
    origin = get_origin(annotation)
    if origin is Union:
        args = get_args(annotation)
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            return type_map.get(non_none[0], "string")
    return type_map.get(annotation, "string")
```

---

## 四、`execution/tools/registry.py` 设计方案

### 4.1 职责

工具注册中心，管理所有工具的注册、发现和调用。

### 4.2 核心接口

```python
class ToolRegistry:
    """工具注册中心 — 单例模式"""
    
    _instance = None
    _tools: dict[str, BaseTool] = {}       # name → tool
    _capability_index: dict[str, set[str]] = {}  # capability → set[name]
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def register(cls, tool: BaseTool) -> None:
        """注册工具
        - 如果同名工具已存在，覆盖并记录警告
        """
    
    @classmethod
    def get(cls, name: str) -> BaseTool:
        """按名称获取工具
        - 未找到时抛出 ToolNotFoundError
        """
    
    @classmethod
    def list_tools(cls) -> list[ToolDefinition]:
        """列出所有已注册工具的定义"""
    
    @classmethod
    async def execute(cls, name: str, **kwargs) -> dict:
        """执行工具
        1. 获取工具
        2. 校验参数（根据 input_schema）
        3. 执行并返回结果
        4. 记录审计日志
        """
    
    @classmethod
    def find_by_capability(cls, capability: str) -> list[BaseTool]:
        """按能力标签查找工具"""
```

### 4.3 自动注册机制

```python
# execution/tools/builtins/__init__.py
from .http import http_request_tool
from .fileio import file_read_tool, file_write_tool
from .image import image_process_tool

# 在包导入时自动注册
def register_all():
    registry = ToolRegistry()
    registry.register(http_request_tool)
    registry.register(file_read_tool)
    registry.register(file_write_tool)
    registry.register(image_process_tool)

register_all()
```

---

## 五、内置工具设计

### 5.1 `http.py` — HTTP 请求工具

```python
@tool(
    name="http_request",
    description="发送 HTTP/HTTPS 请求到指定 URL",
    input_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "请求 URL"},
            "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"], "default": "GET"},
            "headers": {"type": "object", "description": "请求头", "default": {}},
            "params": {"type": "object", "description": "URL 查询参数", "default": {}},
            "body": {"type": "string", "description": "请求体（JSON 字符串）", "default": None},
            "timeout": {"type": "integer", "description": "超时时间（秒）", "default": 30},
        },
        "required": ["url"]
    }
)
async def http_request(url: str, method: str = "GET", headers: dict = None,
                       params: dict = None, body: str = None, timeout: int = 30) -> dict:
    """发送 HTTP 请求"""
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            content=body,
        )
        return {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response.text,
        }
```

### 5.2 `fileio.py` — 文件读写工具

```python
@tool(name="file_read", description="读取文件内容")
async def file_read(path: str, encoding: str = "utf-8") -> dict:
    """读取文件内容"""
    async with aiofiles.open(path, "r", encoding=encoding) as f:
        content = await f.read()
    return {"path": path, "content": content, "size": len(content)}

@tool(name="file_write", description="写入文件内容")
async def file_write(path: str, content: str, encoding: str = "utf-8") -> dict:
    """写入文件内容"""
    # 自动创建目录
    os.makedirs(os.path.dirname(path), exist_ok=True)
    async with aiofiles.open(path, "w", encoding=encoding) as f:
        await f.write(content)
    return {"path": path, "size": len(content)}
```

### 5.3 `image.py` — 图片处理工具

```python
@tool(name="image_process", description="图片基础处理（裁剪、缩放、格式转换）")
async def image_process(path: str, operations: list[dict]) -> dict:
    """图片处理
    operations 示例:
    [
        {"type": "resize", "width": 800, "height": 600},
        {"type": "crop", "x": 0, "y": 0, "width": 400, "height": 300},
        {"type": "convert", "format": "png"}
    ]
    """
    from PIL import Image
    img = Image.open(path)
    for op in operations:
        if op["type"] == "resize":
            img = img.resize((op["width"], op["height"]))
        elif op["type"] == "crop":
            img = img.crop((op["x"], op["y"], op["x"] + op["width"], op["y"] + op["height"]))
        elif op["type"] == "convert":
            img = img.convert("RGB")
            output_path = path.rsplit(".", 1)[0] + f".{op['format']}"
            img.save(output_path)
    return {"path": output_path, "format": img.format, "size": img.size}
```

---

## 六、`execution/adapters/base.py` 设计方案

### 6.1 职责

定义平台 Adapter 基类，所有平台 MCP Adapter 必须实现此接口。

### 6.2 Adapter 基类

```python
class BasePlatformAdapter(ABC):
    """平台适配器基类"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """适配器名称（如 wechat）"""
    
    @property
    @abstractmethod
    def platform(self) -> str:
        """平台名称（如 wechat）"""
    
    @abstractmethod
    async def initialize(self) -> bool:
        """初始化适配器
        - 验证凭据有效性
        - 获取初始 token
        - 返回是否初始化成功
        """
    
    @abstractmethod
    async def get_tools(self) -> list[ToolDefinition]:
        """返回此适配器提供的所有工具定义"""
    
    @abstractmethod
    async def handle_tool_call(self, name: str, args: dict) -> dict:
        """处理 MCP 工具调用
        - name: 工具名
        - args: 参数字典
        - 返回执行结果
        """
    
    async def health_check(self) -> bool:
        """健康检查（默认实现：调用一个轻量 API）"""
        return True
```

---

## 七、微信 MCP Adapter 设计

### 7.1 `auth.py` — Token 管理

```python
class WeChatTokenManager:
    """微信 access_token 管理（带缓存与自动刷新）"""
    
    def __init__(self, app_id: str, app_secret: str, api_base: str = "https://api.weixin.qq.com"):
        self._app_id = app_id
        self._app_secret = app_secret
        self._api_base = api_base
        self._token: Optional[str] = None
        self._expires_at: Optional[datetime] = None
        self._lock = asyncio.Lock()
    
    async def get_token(self) -> str:
        """获取可用 token（优先使用缓存）"""
        if self._token and self._expires_at and datetime.utcnow() < self._expires_at:
            return self._token
        return await self._refresh()
    
    async def get_stable_token(self) -> str:
        """获取稳定版 token（推荐用于定时任务）"""
        return await self._refresh(stable=True)
    
    async def _refresh(self, stable: bool = False) -> str:
        """从微信服务器获取新 token"""
        async with self._lock:
            # 双重检查
            if self._token and self._expires_at and datetime.utcnow() < self._expires_at:
                return self._token
            
            if stable:
                url = f"{self._api_base}/cgi-bin/stable_token"
                body = json.dumps({
                    "grant_type": "client_credential",
                    "appid": self._app_id,
                    "secret": self._app_secret,
                    "force_refresh": False,
                })
            else:
                url = f"{self._api_base}/cgi-bin/token"
                body = None
                params = {
                    "grant_type": "client_credential",
                    "appid": self._app_id,
                    "secret": self._app_secret,
                }
            
            async with httpx.AsyncClient() as client:
                if stable:
                    resp = await client.post(url, content=body)
                else:
                    resp = await client.get(url, params=params)
                data = resp.json()
            
            if "access_token" not in data:
                raise AuthFailedError(f"微信 token 获取失败: {data}")
            
            self._token = data["access_token"]
            expires_in = data.get("expires_in", 7200)
            self._expires_at = datetime.utcnow() + timedelta(seconds=expires_in - 300)  # 提前 5 分钟刷新
            return self._token
```

### 7.2 `models.py` — 微信数据模型

```python
class WeChatArticle(BaseModel):
    """微信图文文章"""
    title: str = Field(..., max_length=32)
    author: str = Field(default="Pulsar", max_length=16)
    digest: str = Field(default="", max_length=128)
    content: str = Field(..., description="HTML 格式正文")
    content_source_url: str = Field(default="", description="原文链接")
    thumb_media_id: str = Field(default="", description="封面图 media_id")
    need_open_comment: int = Field(default=1, ge=0, le=1)
    only_fans_can_comment: int = Field(default=0, ge=0, le=1)

class WeChatDraft(BaseModel):
    """微信草稿"""
    media_id: str
    articles: list[WeChatArticle]
    update_time: datetime

class WeChatPublishResult(BaseModel):
    """发布结果"""
    publish_id: str
    msg_status: int  # 0: 成功, 其他: 失败
    msg_id: Optional[str] = None

class WeChatStats(BaseModel):
    """微信数据统计"""
    date: str
    int_page_read_user: int = 0      # 阅读人数
    int_page_read_count: int = 0     # 阅读次数
    share_user: int = 0              # 分享人数
    share_count: int = 0             # 分享次数
    add_to_fav_user: int = 0         # 收藏人数
    add_to_fav_count: int = 0        # 收藏次数
    new_user: int = 0                # 新增关注
    cancel_user: int = 0             # 取消关注

class WeChatMedia(BaseModel):
    """微信素材"""
    media_id: str
    name: str
    url: str
    update_time: datetime
```

### 7.3 `tools.py` — 工具定义

```python
# 微信 Adapter 工具定义清单（22+ 工具）

WECHAT_TOOLS = {
    # ===== 草稿管理 =====
    "wechat_draft_add": ToolDefinition(
        name="wechat_draft_add",
        description="创建图文草稿",
        input_schema={...},  # 含 title, content, author, digest, thumb_media_id 等
        agent="adapter.wechat",
    ),
    "wechat_draft_update": ToolDefinition(
        name="wechat_draft_update",
        description="更新图文草稿",
        input_schema={...},
        agent="adapter.wechat",
    ),
    "wechat_draft_list": ToolDefinition(
        name="wechat_draft_list",
        description="获取草稿列表",
        input_schema={"offset": 0, "count": 20},
        agent="adapter.wechat",
    ),
    "wechat_draft_delete": ToolDefinition(
        name="wechat_draft_delete",
        description="删除草稿",
        input_schema={"media_id": "..."},
        agent="adapter.wechat",
    ),
    
    # ===== 发布管理 =====
    "wechat_publish_submit": ToolDefinition(
        name="wechat_publish_submit",
        description="提交发布任务",
        input_schema={"media_id": "..."},
        agent="adapter.wechat",
    ),
    "wechat_publish_status": ToolDefinition(
        name="wechat_publish_status",
        description="查询发布状态",
        input_schema={"publish_id": "..."},
        agent="adapter.wechat",
    ),
    "wechat_publish_schedule": ToolDefinition(
        name="wechat_publish_schedule",
        description="定时发布",
        input_schema={"media_id": "...", "publish_time": "..."},
        agent="adapter.wechat",
    ),
    "wechat_publish_cancel": ToolDefinition(
        name="wechat_publish_cancel",
        description="取消发布",
        input_schema={"publish_id": "..."},
        agent="adapter.wechat",
    ),
    
    # ===== 素材管理 =====
    "wechat_media_upload": ToolDefinition(
        name="wechat_media_upload",
        description="上传永久素材",
        input_schema={"file_path": "...", "type": "image/voice/video/thumb"},
        agent="adapter.wechat",
    ),
    "wechat_media_upload_temp": ToolDefinition(
        name="wechat_media_upload_temp",
        description="上传临时素材",
        input_schema={"file_path": "...", "type": "image/voice/video/thumb"},
        agent="adapter.wechat",
    ),
    "wechat_media_list": ToolDefinition(
        name="wechat_media_list",
        description="获取素材列表",
        input_schema={"type": "image/news/video/voice", "offset": 0, "count": 20},
        agent="adapter.wechat",
    ),
    "wechat_media_delete": ToolDefinition(
        name="wechat_media_delete",
        description="删除素材",
        input_schema={"media_id": "..."},
        agent="adapter.wechat",
    ),
    "wechat_upload_image": ToolDefinition(
        name="wechat_upload_image",
        description="上传正文图片（获取微信 CDN URL）",
        input_schema={"file_path": "..."},
        agent="adapter.wechat",
    ),
    
    # ===== 评论管理 =====
    "wechat_comment_list": ToolDefinition(
        name="wechat_comment_list",
        description="获取文章评论列表",
        input_schema={"msg_data_id": "...", "index": 0, "begin": 0, "count": 50},
        agent="adapter.wechat",
    ),
    "wechat_comment_reply": ToolDefinition(
        name="wechat_comment_reply",
        description="回复评论",
        input_schema={"msg_data_id": "...", "user_comment_id": "...", "content": "..."},
        agent="adapter.wechat",
    ),
    "wechat_comment_mark_elect": ToolDefinition(
        name="wechat_comment_mark_elect",
        description="精选评论",
        input_schema={"msg_data_id": "...", "user_comment_id": "..."},
        agent="adapter.wechat",
    ),
    "wechat_comment_delete": ToolDefinition(
        name="wechat_comment_delete",
        description="删除评论",
        input_schema={"msg_data_id": "...", "user_comment_id": "..."},
        agent="adapter.wechat",
    ),
    
    # ===== 数据统计 =====
    "wechat_stats_user_summary": ToolDefinition(
        name="wechat_stats_user_summary",
        description="用户增减数据",
        input_schema={"begin_date": "...", "end_date": "..."},
        agent="adapter.wechat",
    ),
    "wechat_stats_article_summary": ToolDefinition(
        name="wechat_stats_article_summary",
        description="图文阅读数据",
        input_schema={"begin_date": "...", "end_date": "..."},
        agent="adapter.wechat",
    ),
    "wechat_stats_article_total": ToolDefinition(
        name="wechat_stats_article_total",
        description="图文总数据",
        input_schema={"begin_date": "...", "end_date": "..."},
        agent="adapter.wechat",
    ),
    
    # ===== 菜单管理 =====
    "wechat_menu_create": ToolDefinition(
        name="wechat_menu_create",
        description="创建自定义菜单",
        input_schema={"button": [...]},
        agent="adapter.wechat",
    ),
    "wechat_menu_get": ToolDefinition(
        name="wechat_menu_get",
        description="获取菜单配置",
        input_schema={},
        agent="adapter.wechat",
    ),
    "wechat_menu_delete": ToolDefinition(
        name="wechat_menu_delete",
        description="删除菜单",
        input_schema={},
        agent="adapter.wechat",
    ),
}
```

### 7.4 `adapter.py` — 微信 Adapter 主类

```python
class WeChatAdapter(BasePlatformAdapter):
    """微信公众平台 MCP Adapter"""
    
    def __init__(self, config: dict):
        self._config = config
        self._token_manager = WeChatTokenManager(
            app_id=config["app_id"],
            app_secret=config["app_secret"],
            api_base=config.get("api_base", "https://api.weixin.qq.com"),
        )
        self._http = httpx.AsyncClient(timeout=30)
        self._initialized = False
    
    @property
    def name(self) -> str: return "wechat"
    
    @property
    def platform(self) -> str: return "wechat"
    
    async def initialize(self) -> bool:
        """初始化：验证 token 是否可获取"""
        try:
            token = await self._token_manager.get_token()
            self._initialized = bool(token)
            return self._initialized
        except Exception as e:
            logger.error(f"微信 Adapter 初始化失败: {e}")
            return False
    
    async def get_tools(self) -> list[ToolDefinition]:
        return list(WECHAT_TOOLS.values())
    
    async def handle_tool_call(self, name: str, args: dict) -> dict:
        """路由工具调用到具体方法"""
        tool_map = {
            # 草稿管理
            "wechat_draft_add": self._draft_add,
            "wechat_draft_update": self._draft_update,
            "wechat_draft_list": self._draft_list,
            "wechat_draft_delete": self._draft_delete,
            # 发布管理
            "wechat_publish_submit": self._publish_submit,
            "wechat_publish_status": self._publish_status,
            "wechat_publish_schedule": self._publish_schedule,
            "wechat_publish_cancel": self._publish_cancel,
            # 素材管理
            "wechat_media_upload": self._media_upload,
            "wechat_media_upload_temp": self._media_upload_temp,
            "wechat_media_list": self._media_list,
            "wechat_media_delete": self._media_delete,
            "wechat_upload_image": self._upload_image,
            # 评论管理
            "wechat_comment_list": self._comment_list,
            "wechat_comment_reply": self._comment_reply,
            "wechat_comment_mark_elect": self._comment_mark_elect,
            "wechat_comment_delete": self._comment_delete,
            # 数据统计
            "wechat_stats_user_summary": self._stats_user_summary,
            "wechat_stats_article_summary": self._stats_article_summary,
            "wechat_stats_article_total": self._stats_article_total,
            # 菜单管理
            "wechat_menu_create": self._menu_create,
            "wechat_menu_get": self._menu_get,
            "wechat_menu_delete": self._menu_delete,
        }
        
        handler = tool_map.get(name)
        if not handler:
            raise ToolNotFoundError(f"微信工具 '{name}' 不存在")
        
        return await handler(**args)
    
    # ===== 草稿管理实现 =====
    async def _draft_add(self, title: str, content: str, author: str = "Pulsar",
                         digest: str = "", thumb_media_id: str = "",
                         need_open_comment: bool = True) -> dict:
        """创建草稿"""
        token = await self._token_manager.get_token()
        url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}"
        body = {
            "articles": [{
                "title": title[:32],
                "author": author[:16],
                "digest": digest[:128],
                "content": content,
                "thumb_media_id": thumb_media_id,
                "need_open_comment": 1 if need_open_comment else 0,
            }]
        }
        resp = await self._http.post(url, json=body)
        data = resp.json()
        if "media_id" not in data:
            raise ToolCallError(f"创建草稿失败: {data}")
        return {"media_id": data["media_id"]}
    
    async def _draft_list(self, offset: int = 0, count: int = 20) -> dict:
        """获取草稿列表"""
        token = await self._token_manager.get_token()
        url = f"https://api.weixin.qq.com/cgi-bin/draft/batchget?access_token={token}"
        resp = await self._http.post(url, json={"offset": offset, "count": count, "no_content": 0})
        return resp.json()
    
    async def _draft_delete(self, media_id: str) -> dict:
        """删除草稿"""
        token = await self._token_manager.get_token()
        url = f"https://api.weixin.qq.com/cgi-bin/draft/delete?access_token={token}"
        resp = await self._http.post(url, json={"media_id": media_id})
        return resp.json()
    
    async def _draft_update(self, media_id: str, index: int = 0, **article_fields) -> dict:
        """更新草稿"""
        token = await self._token_manager.get_token()
        url = f"https://api.weixin.qq.com/cgi-bin/draft/update?access_token={token}"
        resp = await self._http.post(url, json={
            "media_id": media_id,
            "index": index,
            "articles": article_fields,
        })
        return resp.json()
    
    # ===== 发布管理实现 =====
    async def _publish_submit(self, media_id: str) -> dict:
        """提交发布"""
        token = await self._token_manager.get_token()
        url = f"https://api.weixin.qq.com/cgi-bin/freepublish/submit?access_token={token}"
        resp = await self._http.post(url, json={"media_id": media_id})
        data = resp.json()
        if "publish_id" not in data:
            raise ToolCallError(f"提交发布失败: {data}")
        return {"publish_id": data["publish_id"]}
    
    async def _publish_status(self, publish_id: str) -> dict:
        """查询发布状态"""
        token = await self._token_manager.get_token()
        url = f"https://api.weixin.qq.com/cgi-bin/freepublish/get?access_token={token}"
        resp = await self._http.post(url, json={"publish_id": publish_id})
        return resp.json()
    
    async def _publish_schedule(self, media_id: str, publish_time: int) -> dict:
        """定时发布"""
        token = await self._token_manager.get_token()
        url = f"https://api.weixin.qq.com/cgi-bin/freepublish/submit?access_token={token}"
        resp = await self._http.post(url, json={
            "media_id": media_id,
            "scheduled_time": publish_time,
        })
        return resp.json()
    
    async def _publish_cancel(self, publish_id: str) -> dict:
        """取消发布"""
        token = await self._token_manager.get_token()
        url = f"https://api.weixin.qq.com/cgi-bin/freepublish/delete?access_token={token}"
        resp = await self._http.post(url, json={"publish_id": publish_id})
        return resp.json()
    
    # ===== 素材管理实现 =====
    async def _media_upload(self, file_path: str, type: str) -> dict:
        """上传永久素材"""
        token = await self._token_manager.get_token()
        url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type={type}"
        with open(file_path, "rb") as f:
            files = {"media": (os.path.basename(file_path), f)}
            resp = await self._http.post(url, files=files)
        return resp.json()
    
    async def _media_upload_temp(self, file_path: str, type: str) -> dict:
        """上传临时素材"""
        token = await self._token_manager.get_token()
        url = f"https://api.weixin.qq.com/cgi-bin/media/upload?access_token={token}&type={type}"
        with open(file_path, "rb") as f:
            files = {"media": (os.path.basename(file_path), f)}
            resp = await self._http.post(url, files=files)
        return resp.json()
    
    async def _media_list(self, type: str = "image", offset: int = 0, count: int = 20) -> dict:
        """获取素材列表"""
        token = await self._token_manager.get_token()
        url = f"https://api.weixin.qq.com/cgi-bin/material/batchget_material?access_token={token}"
        resp = await self._http.post(url, json={"type": type, "offset": offset, "count": count})
        return resp.json()
    
    async def _media_delete(self, media_id: str) -> dict:
        """删除素材"""
        token = await self._token_manager.get_token()
        url = f"https://api.weixin.qq.com/cgi-bin/material/del_material?access_token={token}"
        resp = await self._http.post(url, json={"media_id": media_id})
        return resp.json()
    
    async def _upload_image(self, file_path: str) -> dict:
        """上传正文图片"""
        token = await self._token_manager.get_token()
        url = f"https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token={token}"
        with open(file_path, "rb") as f:
            files = {"media": (os.path.basename(file_path), f, "image/png")}
            resp = await self._http.post(url, files=files)
        data = resp.json()
        if "url" not in data:
            raise ToolCallError(f"上传图片失败: {data}")
        return {"url": data["url"]}
    
    # ===== 评论管理实现 =====
    async def _comment_list(self, msg_data_id: str, index: int = 0,
                            begin: int = 0, count: int = 50) -> dict:
        token = await self._token_manager.get_token()
        url = f"https://api.weixin.qq.com/cgi-bin/comment/list?access_token={token}"
        resp = await self._http.post(url, json={
            "msg_data_id": msg_data_id, "index": index,
            "begin": begin, "count": count,
        })
        return resp.json()
    
    async def _comment_reply(self, msg_data_id: str, user_comment_id: str, content: str) -> dict:
        token = await self._token_manager.get_token()
        url = f"https://api.weixin.qq.com/cgi-bin/comment/reply/add?access_token={token}"
        resp = await self._http.post(url, json={
            "msg_data_id": msg_data_id,
            "user_comment_id": user_comment_id,
            "content": content,
        })
        return resp.json()
    
    async def _comment_mark_elect(self, msg_data_id: str, user_comment_id: str) -> dict:
        token = await self._token_manager.get_token()
        url = f"https://api.weixin.qq.com/cgi-bin/comment/markelect?access_token={token}"
        resp = await self._http.post(url, json={
            "msg_data_id": msg_data_id,
            "user_comment_id": user_comment_id,
        })
        return resp.json()
    
    async def _comment_delete(self, msg_data_id: str, user_comment_id: str) -> dict:
        token = await self._token_manager.get_token()
        url = f"https://api.weixin.qq.com/cgi-bin/comment/delete?access_token={token}"
        resp = await self._http.post(url, json={
            "msg_data_id": msg_data_id,
            "user_comment_id": user_comment_id,
        })
        return resp.json()
    
    # ===== 数据统计实现 =====
    async def _stats_user_summary(self, begin_date: str, end_date: str) -> dict:
        token = await self._token_manager.get_token()
        url = f"https://api.weixin.qq.com/datacube/getusersummary?access_token={token}"
        resp = await self._http.post(url, json={
            "begin_date": begin_date, "end_date": end_date,
        })
        return resp.json()
    
    async def _stats_article_summary(self, begin_date: str, end_date: str) -> dict:
        token = await self._token_manager.get_token()
        url = f"https://api.weixin.qq.com/datacube/getarticletotal?access_token={token}"
        resp = await self._http.post(url, json={
            "begin_date": begin_date, "end_date": end_date,
        })
        return resp.json()
    
    async def _stats_article_total(self, begin_date: str, end_date: str) -> dict:
        token = await self._token_manager.get_token()
        url = f"https://api.weixin.qq.com/datacube/getarticletotal?access_token={token}"
        resp = await self._http.post(url, json={
            "begin_date": begin_date, "end_date": end_date,
        })
        return resp.json()
    
    # ===== 菜单管理实现 =====
    async def _menu_create(self, button: list) -> dict:
        token = await self._token_manager.get_token()
        url = f"https://api.weixin.qq.com/cgi-bin/menu/create?access_token={token}"
        resp = await self._http.post(url, json={"button": button})
        return resp.json()
    
    async def _menu_get(self) -> dict:
        token = await self._token_manager.get_token()
        url = f"https://api.weixin.qq.com/cgi-bin/menu/get?access_token={token}"
        resp = await self._http.get(url)
        return resp.json()
    
    async def _menu_delete(self) -> dict:
        token = await self._token_manager.get_token()
        url = f"https://api.weixin.qq.com/cgi-bin/menu/delete?access_token={token}"
        resp = await self._http.get(url)
        return resp.json()
```

---

## 八、频率控制设计

### 8.1 职责

自动跟踪各平台 API 调用频次，触发限流时排队等待或降级。

### 8.2 核心接口

```python
class RateLimiter:
    """API 频率限制器 — 令牌桶算法"""
    
    def __init__(self, max_calls_per_minute: int = 100, max_calls_per_hour: int = 2000):
        self._max_per_minute = max_calls_per_minute
        self._max_per_hour = max_calls_per_hour
        self._minute_tokens = max_calls_per_minute
        self._hour_tokens = max_calls_per_hour
        self._last_minute_refill = time.monotonic()
        self._last_hour_refill = time.monotonic()
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> bool:
        """获取调用许可
        - 有可用 token → 消耗并返回 True
        - 无可用 token → 返回 False（调用方决定等待或降级）
        """
    
    async def acquire_with_wait(self, timeout: float = 30) -> bool:
        """获取调用许可（等待直到有可用 token 或超时）"""
    
    def get_usage(self) -> dict:
        """获取当前使用率"""
```

---

## 九、验收标准

- [ ] `ToolRegistry.register()` 可注册工具，`ToolRegistry.get()` 可按名称获取
- [ ] `@tool` 装饰器可从函数签名自动生成 input_schema
- [ ] 内置工具 `http_request` 可正常发送 HTTP 请求
- [ ] 内置工具 `file_read`/`file_write` 可正常读写文件
- [ ] `WeChatAdapter.initialize()` 可验证微信凭据有效性
- [ ] `WeChatAdapter.handle_tool_call("wechat_draft_add", ...)` 成功创建草稿
- [ ] `WeChatAdapter.handle_tool_call("wechat_publish_submit", ...)` 成功提交发布
- [ ] Token 自动缓存和刷新（首次获取 → 缓存 → 过期自动刷新）
- [ ] `RateLimiter.acquire()` 在超限时返回 False
- [ ] 所有工具调用通过 `ToolRegistry.execute()` 执行

---

## 十、注意事项

1. **微信 API 错误处理**：微信 API 返回的 errcode 需要统一处理，常见错误码（40001=token 过期、45009=频率超限）自动触发 token 刷新或等待
2. **文件上传**：微信素材上传使用 multipart/form-data，注意文件路径存在性检查
3. **正文图片替换**：发布前需要将正文中的本地图片 URL 替换为微信 CDN URL（通过 uploadimg 接口）
4. **频率控制**：微信 API 有严格的频率限制，RateLimiter 必须正确实现
5. **Token 安全**：access_token 不应记录到日志中
6. **幂等设计**：草稿创建和发布提交应支持幂等重试
