# 前端集成和部署指南

## 📋 集成步骤

### 第 1 步: 构建 Vue 前端

在 `anygen-ppt-vue` 目录中：

```bash
cd anygen-ppt-vue

# 安装依赖（如果还没有）
npm install

# 构建生产版本
npm run build
```

构建完成后，会在 `dist/` 目录生成静态文件。

### 第 2 步: 复制前端文件到后端

将 Vue 构建的文件复制到 FastAPI 的静态目录：

```bash
# 从项目根目录执行
cp -r anygen-ppt-vue/dist/* anygen-ppt-fastapi/static/

# 或者在 Windows 上
xcopy anygen-ppt-vue\dist\* anygen-ppt-fastapi\static\ /E /Y
```

### 第 3 步: 启动 FastAPI 后端

```bash
cd anygen-ppt-fastapi

# 安装依赖（如果还没有）
pip install -r requirements.txt

# 启动服务
python main.py
```

### 第 4 步: 访问应用

打开浏览器访问：

```
http://localhost:8000
```

---

## 🏗️ 部署架构

### 单一服务部署

```
┌─────────────────────────────────────┐
│     FastAPI 应用 (main.py)          │
├─────────────────────────────────────┤
│  ┌───────────────────────────────┐  │
│  │  前端静态文件 (static/)       │  │
│  │  - index.html                 │  │
│  │  - assets/                    │  │
│  │  - ...                        │  │
│  └───────────────────────────────┘  │
│                                     │
│  ┌───────────────────────────────┐  │
│  │  API 路由 (/api/*)            │  │
│  │  - /api/auth                  │  │
│  │  - /api/export                │  │
│  │  - /api/tasks                 │  │
│  │  - ...                        │  │
│  └───────────────────────────────┘  │
│                                     │
│  ┌───────────────────────────────┐  │
│  │  SQLite 数据库 (data/app.db)  │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
         监听: 0.0.0.0:8000
```

### 优势

- ✅ **简化部署** - 单一服务，无需配置反向代理
- ✅ **降低成本** - 减少服务器资源占用
- ✅ **易于维护** - 统一的日志和监控
- ✅ **快速启动** - 一条命令启动整个应用

---

## 🚀 部署方式

### 方式 1: 本地开发

```bash
# 启动后端
cd anygen-ppt-fastapi
python main.py

# 访问
http://localhost:8000
```

### 方式 2: 生产部署（Linux/Mac）

```bash
# 安装依赖
pip install -r requirements.txt
pip install gunicorn

# 启动服务（4 个 worker）
gunicorn main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --access-logfile - \
  --error-logfile -
```

### 方式 3: Docker 部署

#### 创建 Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动应用
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### 构建和运行

```bash
# 构建镜像
docker build -t anygen-ppt-api:latest .

# 运行容器
docker run -d \
  --name anygen-ppt-api \
  -p 8000:8000 \
  -e ADMIN_PASSWORD=your-password \
  -e SECRET_KEY=your-secret-key \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  anygen-ppt-api:latest

# 查看日志
docker logs -f anygen-ppt-api

# 停止容器
docker stop anygen-ppt-api
```

#### Docker Compose

```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DEBUG=False
      - ADMIN_PASSWORD=admin123
      - SECRET_KEY=your-secret-key-here
      - LOG_LEVEL=INFO
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    restart: unless-stopped
```

运行：

```bash
docker-compose up -d
```

### 方式 4: Nginx 反向代理

#### Nginx 配置

```nginx
upstream fastapi_app {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name example.com;

    # 前端静态文件
    location / {
        proxy_pass http://fastapi_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # API 路由
    location /api/ {
        proxy_pass http://fastapi_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # SSE 流式响应
        proxy_buffering off;
        proxy_cache off;
    }

    # 健康检查
    location /health {
        proxy_pass http://fastapi_app;
        access_log off;
    }
}
```

---

## 📦 文件结构

部署后的目录结构：

```
anygen-ppt-fastapi/
├── main.py                      # 应用入口
├── config.py                    # 配置
├── requirements.txt             # 依赖
├── .env                         # 环境变量（生产）
│
├── app/                         # 应用代码
│   ├── models/
│   ├── schemas/
│   ├── services/
│   ├── routes/
│   ├── database/
│   ├── utils/
│   └── external/
│
├── static/                      # 前端静态文件 ⭐
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

---

## 🔧 配置管理

### 环境变量

编辑 `.env` 文件：

```env
# 应用配置
DEBUG=False
HOST=0.0.0.0
PORT=8000

# 数据库
DATABASE_URL=sqlite:///./data/app.db

# JWT
SECRET_KEY=your-very-long-secret-key-change-this
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# 管理员
ADMIN_PASSWORD=your-secure-password

# 日志
LOG_LEVEL=INFO
LOG_FILE=logs/app.log

# 闲鱼
XIANYU_PROXY=
XIANYU_TIMEOUT=60
```

### 生产环境建议

```env
DEBUG=False
LOG_LEVEL=WARNING
ACCESS_TOKEN_EXPIRE_MINUTES=480
SECRET_KEY=<生成一个强密钥>
ADMIN_PASSWORD=<设置一个强密码>
```

生成强密钥：

```python
import secrets
print(secrets.token_urlsafe(32))
```

---

## 📊 性能优化

### 1. 使用 Gunicorn + Uvicorn

```bash
gunicorn main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --worker-connections 1000 \
  --max-requests 1000 \
  --max-requests-jitter 100
```

### 2. 启用 Gzip 压缩

在 Nginx 中：

```nginx
gzip on;
gzip_types text/plain text/css application/json application/javascript;
gzip_min_length 1000;
```

### 3. 缓存策略

```nginx
# 缓存静态文件
location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
    expires 30d;
    add_header Cache-Control "public, immutable";
}

# 不缓存 HTML
location ~* \.html$ {
    expires -1;
    add_header Cache-Control "no-cache, no-store, must-revalidate";
}
```

### 4. 数据库优化

```python
# 添加索引
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_keys_key ON keys(key);
CREATE INDEX idx_tasks_created_at ON tasks(created_at);
```

---

## 🔐 安全建议

### 1. HTTPS

使用 Let's Encrypt 配置 HTTPS：

```bash
# 使用 Certbot
certbot certonly --standalone -d example.com
```

Nginx 配置：

```nginx
server {
    listen 443 ssl http2;
    ssl_certificate /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;
    
    # SSL 安全配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
}
```

### 2. 防火墙

```bash
# 仅允许必要的端口
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### 3. 定期备份

```bash
# 备份数据库
cp data/app.db data/app.db.backup.$(date +%Y%m%d)

# 或使用 cron
0 2 * * * cp /app/data/app.db /backup/app.db.$(date +\%Y\%m\%d)
```

---

## 📈 监控和日志

### 1. 日志查看

```bash
# 实时查看日志
tail -f logs/app.log

# 查看最后 100 行
tail -100 logs/app.log

# 搜索错误
grep ERROR logs/app.log
```

### 2. 性能监控

```bash
# 查看进程
ps aux | grep uvicorn

# 查看端口占用
netstat -tlnp | grep 8000

# 查看资源使用
top
```

### 3. 应用监控

访问健康检查端点：

```bash
curl http://localhost:8000/health
# 响应: {"status":"ok"}
```

---

## 🚨 故障排查

### 问题 1: 前端加载失败

**症状**: 访问 http://localhost:8000 显示 404

**解决**:
```bash
# 检查静态文件是否存在
ls -la static/

# 重新复制文件
cp -r anygen-ppt-vue/dist/* static/
```

### 问题 2: API 连接失败

**症状**: 前端无法调用 API

**解决**:
```bash
# 检查 CORS 配置
# 确保 main.py 中有 CORS 中间件

# 检查 API 是否运行
curl http://localhost:8000/health
```

### 问题 3: 数据库错误

**症状**: "database is locked" 错误

**解决**:
```bash
# 删除数据库文件
rm data/app.db

# 重启应用（自动重新初始化）
python main.py
```

### 问题 4: 内存占用过高

**症状**: 应用占用大量内存

**解决**:
```bash
# 检查日志文件大小
du -sh logs/

# 清理旧日志
rm logs/app.log.*

# 重启应用
```

---

## 📋 检查清单

部署前检查：

- [ ] 构建了 Vue 前端 (`npm run build`)
- [ ] 复制了静态文件到 `static/` 目录
- [ ] 创建了 `.env` 文件并配置了参数
- [ ] 安装了 Python 依赖 (`pip install -r requirements.txt`)
- [ ] 测试了 API 端点 (http://localhost:8000/docs)
- [ ] 验证了前端可以加载 (http://localhost:8000)
- [ ] 检查了日志没有错误 (`logs/app.log`)
- [ ] 备份了重要数据

---

## 🎯 部署命令速查

### 开发环境

```bash
cd anygen-ppt-fastapi
python main.py
```

### 生产环境（Linux）

```bash
cd anygen-ppt-fastapi
gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Docker

```bash
docker build -t anygen-ppt-api .
docker run -p 8000:8000 anygen-ppt-api
```

### Docker Compose

```bash
docker-compose up -d
```

---

## 📞 获取帮助

- 查看 API 文档: http://localhost:8000/docs
- 查看日志: `logs/app.log`
- 查看项目文档: `README.md`, `DEVELOPMENT_REPORT.md`

---

**部署完成后，应用将在 http://localhost:8000 运行！** 🎉
