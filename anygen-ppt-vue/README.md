# Vue 3 + FastAPI PPT Export Admin

基于 Vue 3 + Vite 开发的 PPT 导出服务前端，与 FastAPI 后端分离部署。

## 快速开始

### 安装依赖

\`\`\`bash
npm install
\`\`\`

### 开发模式

\`\`\`bash
npm run dev
\`\`\`

访问 http://localhost:5173

### 构建生产版本

\`\`\`bash
npm run build
\`\`\`

生产文件输出到 `dist/` 目录

## 项目结构

```
src/
├── views/              页面组件
├── components/         可复用组件
├── stores/            Pinia 状态管理
├── services/          API 服务
├── router/            路由配置
├── types/             TypeScript 类型定义
├── App.vue            根组件
├── main.ts            入口文件
└── style.css          全局样式
```

## 主要功能

- ✅ PPT 导出表单
- ✅ 管理员认证登录
- ✅ 仪表盘统计
- ✅ 任务管理
- ✅ 卡密查询
- ✅ 响应式设计

## 技术栈

- Vue 3 - 前端框架
- Vite - 构建工具
- Vue Router - 路由管理
- Pinia - 状态管理
- Axios - HTTP 客户端
- TypeScript - 类型安全
- Tailwind CSS - 样式框架

## 与后端通信

默认 API 地址：

- 开发模式：http://localhost:8000（通过 Vite 代理）
- 生产模式：/ 同域名下的 /api 路由

## 环境变量

创建 `.env.local` 文件：

\`\`\`
VITE_API_URL=http://localhost:8000
\`\`\`

## 部署到 FastAPI

1. 构建前端：\`npm run build\`
2. 复制 dist 文件夹到 FastAPI 项目
3. FastAPI 配置提供静态文件

详见后端项目文档
