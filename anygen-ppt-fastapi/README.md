# Anygen PPT FastAPI 后端

现代化的 PPT 导出和闲鱼管理系统后端，基于 FastAPI + SQLite。

## 🚀 快速开始

### 1. 安装依赖

```bash
cd anygen-ppt-fastapi
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，修改必要的配置
```

### 3. 启动服务

```bash
# 开发模式
python main.py

# 或使用 uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 4. 访问应用

- **前端**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs
- **Redoc**: http://localhost:8000/redoc

## 📁 项目结构

```
anygen-ppt-fastapi/
├── main.py                      # 应用入口
├── config.py                    # 配置管理
├── requirements.txt             # 依赖列表
├── .env.example                 # 环境变量示例
├── manager.py                   # 闲鱼登录管理器（原有）
│
├── app/
│   ├── models/                  # ORM 数据模型
│   │   ├── base.py             # 基础模型
│   │   ├── task.py             # 任务模型
│   │   ├── key.py              # 卡密模型
│   │   ├── settings.py         # 设置模型
│   │   └── xianyu.py           # 闲鱼模型
│   │
│   ├── schemas/                 # 请求/响应 Schema
│   │   ├── auth.py             # 认证 Schema
│   │   ├── task.py             # 任务 Schema
│   │   ├── key.py              # 卡密 Schema
│   │   ├── xianyu.py           # 闲鱼 Schema
│   │   └── settings.py         # 设置 Schema
│   │
│   ├── services/                # 业务逻辑层
│   │   ├── auth.py             # 认证服务
│   │   ├── task.py             # 任务服务
│   │   ├── key.py              # 卡密服务
│   │   ├── settings.py         # 设置服务
│   │   ├── xianyu.py           # 闲鱼服务
│   │   └── export.py           # 导出服务
│   │
│   ├── routes/                  # 路由层
│   │   ├── auth.py             # 认证路由
│   │   ├── export.py           # 导出路由
│   │   ├── tasks.py            # 任务路由
│   │   ├── query.py            # 查询路由
│   │   ├── keys.py             # 卡密管理路由
│   │   ├── xianyu.py           # 闲鱼路由
│   │   └── settings.py         # 设置路由
│   │
│   ├── database/                # 数据库层
│   │   ├── db.py               # 数据库连接
│   │   └── init_db.py          # 数据库初始化
│   │
│   ├── utils/                   # 工具函数
│   │   ├── jwt.py              # JWT 工具
│   │   ├── validators.py       # 验证工具
│   │   ├── sse.py              # SSE 工具
│   │   └── logger.py           # 日志工具
│   │
│   └── external/                # 外部服务
│       └── xianyu_client.py    # 闲鱼客户端（httpx）
│
├── static/                      # 前端静态文件（Vue 打包后）
│   ├── index.html
│   ├── assets/
│   │   ├── *.js
│   │   ├── *.css
│   │   └── ...
│   └── ...
│
├── data/                        # 数据目录
│   └── app.db                  # SQLite 数据库
│
└── logs/                        # 日志目录
    └── app.log
```

## 🔌 API 接口

### 认证接口

- `POST /api/auth` - 登录
- `GET /api/auth` - 验证 token

### 导出接口

- `POST /api/export` - 提交导出任务
- `GET /api/download/{task_id}` - 下载 PPT 文件
- `GET /api/tasks/{task_id}/stream` - SSE 实时更新

### 任务接口

- `GET /api/tasks` - 获取任务列表
- `GET /api/tasks/{task_id}` - 获取任务详情
- `POST /api/retry/{task_id}` - 重试任务（需认证）
- `POST /api/cleanup` - 清理过期任务（需认证）

### 查询接口

- `GET /api/query?key=xxx` - 查询卡密信息

### 卡密管理接口（需认证）

- `GET /api/keys` - 获取卡密列表
- `POST /api/keys` - 创建卡密
- `PATCH /api/keys/{id}` - 更新卡密状态
- `DELETE /api/keys/{id}` - 删除卡密
- `POST /api/keys/batch` - 批量操作卡密

### 系统设置接口（需认证）

- `GET /api/settings` - 获取设置
- `PUT /api/settings` - 更新设置

### 闲鱼接口

- `POST /api/xianyu/login` - 生成二维码
- `POST /api/xianyu/login/check` - 检查登录状态
- `POST /api/xianyu/login/verify` - 验证 cookies
- `GET /api/xianyu-multi` - 获取账户列表（需认证）
- `POST /api/xianyu-multi/bind` - 绑定账户（需认证）
- `POST /api/xianyu-multi/unbind` - 解绑账户（需认证）
- `POST /api/xianyu-multi/template` - 更新模板（需认证）
- `GET /api/xianyu-multi/orders` - 获取订单（需认证）
- `POST /api/xianyu/orders/{order_no}/confirm-delivery` - 确认发货（需认证）

## 🔐 认证

使用 JWT Token 进行认证。登录后获取 token，在后续请求的 Authorization 头中使用：

```
Authorization: Bearer <token>
```

## 💾 数据库

使用 SQLite 数据库，自动初始化。数据库文件位于 `data/app.db`。

### 表结构

- **tasks** - 导出任务表
- **keys** - 卡密表
- **settings** - 系统设置表
- **xianyu_accounts** - 闲鱼账户表
- **xianyu_orders** - 闲鱼订单表

## 🔧 配置

编辑 `.env` 文件配置以下参数：

```env
# FastAPI 配置
DEBUG=True
HOST=0.0.0.0
PORT=8000

# 数据库配置
DATABASE_URL=sqlite:///./data/app.db

# JWT 配置
SECRET_KEY=your-secret-key-change-this-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# 管理员密码
ADMIN_PASSWORD=admin123

# 日志配置
LOG_LEVEL=INFO
LOG_FILE=logs/app.log

# 闲鱼配置
XIANYU_PROXY=
XIANYU_TIMEOUT=60
```

## 📦 前端集成

### 构建前端

```bash
cd anygen-ppt-vue
npm run build
```

### 复制到后端

```bash
cp -r anygen-ppt-vue/dist/* anygen-ppt-fastapi/static/
```

### 启动后端

```bash
cd anygen-ppt-fastapi
python main.py
```

访问 http://localhost:8000 既可以访问前端，也可以调用 API。

## 🧪 测试

### 使用 curl 测试

```bash
# 登录
curl -X POST http://localhost:8000/api/auth \
  -H "Content-Type: application/json" \
  -d '{"password":"admin123"}'

# 创建卡密
curl -X POST http://localhost:8000/api/keys \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"count":10,"max_uses":5,"is_super":false}'

# 提交导出任务
curl -X POST http://localhost:8000/api/export \
  -H "Content-Type: application/json" \
  -d '{
    "key":"XXXX-XXXX-XXXX-XXXX",
    "url":"https://example.com/file.pptx",
    "email":"user@example.com"
  }'
```

### 使用 API 文档测试

访问 http://localhost:8000/docs 使用 Swagger UI 进行交互式测试。

## 🚀 部署

### 生产环境

```bash
# 安装依赖
pip install -r requirements.txt

# 修改 .env 配置
# - 设置 DEBUG=False
# - 修改 SECRET_KEY
# - 修改 ADMIN_PASSWORD

# 启动服务（使用 Gunicorn）
gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Docker 部署

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 📝 日志

日志文件位于 `logs/app.log`，同时输出到控制台。

## 🔗 相关项目

- [anygen-ppt-vue](../anygen-ppt-vue) - Vue 3 前端项目
- [manager.py](./manager.py) - 闲鱼登录管理器

## 📄 许可证

MIT

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📞 联系方式

如有问题，请提交 Issue 或联系开发者。
