anygen-ppt-vue/
├── 📄 index.html                    入口 HTML
├── 📄 package.json                  NPM 配置
├── 📄 vite.config.ts                Vite 配置（含代理）
├── 📄 tsconfig.json                 TypeScript 配置
├── 📄 tsconfig.node.json            Node TypeScript 配置
├── 📄 tailwind.config.js            Tailwind 配置
├── 📄 postcss.config.js             PostCSS 配置
├── 📄 .gitignore                    Git 忽略文件
├── 📄 .env.example                  环境变量示例
│
├── 📖 README.md                     项目说明
├── 📖 QUICK_START.md                快速开始指南 ⭐
├── 📖 PROGRESS.md                   完成进度
├── 📖 COMPLETION_REPORT.md          完成报告 ⭐
├── 📖 DIRECTORY_TREE.md             本文件
│
├── 📁 public/                       静态资源
│   └── (预留)
│
├── 📁 src/                          源代码目录
│   ├── 📄 main.ts                   入口文件
│   ├── 📄 App.vue                   根组件
│   ├── 📄 style.css                 全局样式
│   │
│   ├── 📁 views/                    页面组件 ⭐
│   │   ├── HomePage.vue             首页 - PPT 导出表单
│   │   │   ├── ✅ 表单验证
│   │   │   ├── ✅ SSE 实时更新
│   │   │   ├── ✅ 本地存储
│   │   │   ├── ✅ 错误处理
│   │   │   └── ✅ 教程模态框
│   │   │
│   │   ├── LoginPage.vue            登录页
│   │   │   ├── ✅ 密码验证
│   │   │   ├── ✅ Token 管理
│   │   │   └── ✅ 错误提示
│   │   │
│   │   ├── QueryPage.vue            卡密查询页
│   │   │   ├── ✅ 卡密查询
│   │   │   ├── ✅ 使用统计
│   │   │   └── ✅ 状态显示
│   │   │
│   │   ├── AdminLayout.vue          后台布局框架
│   │   │   ├── ✅ 侧边栏导航
│   │   │   ├── ✅ 移动菜单
│   │   │   ├── ✅ 路由守卫
│   │   │   └── ✅ 退出登录
│   │   │
│   │   ├── AdminDashboard.vue       仪表盘
│   │   │   ├── ✅ 统计卡片
│   │   │   ├── ✅ 最近任务
│   │   │   ├── ✅ 表格/卡片双视图
│   │   │   └── ✅ 响应式设计
│   │   │
│   │   ├── AdminKeys.vue            密钥管理页面（预留）
│   │   ├── AdminTasks.vue           任务管理页面（预留）
│   │   └── AdminSettings.vue        系统设置页面（预留）
│   │
│   ├── 📁 components/               可复用组件 ⭐
│   │   ├── StatCard.vue             统计卡片
│   │   │   └── 支持 4 种颜色
│   │   └── StatusBadge.vue          状态徽章
│   │       └── 支持 4 种状态
│   │
│   ├── 📁 services/                 API 服务 ⭐
│   │   └── api.ts                   所有 API 调用
│   │       ├── authAPI              认证 API
│   │       ├── exportAPI            导出 API
│   │       ├── tasksAPI             任务 API
│   │       ├── queryAPI             查询 API
│   │       └── 请求拦截器           JWT 自动附加
│   │
│   ├── 📁 stores/                   Pinia 状态管理 ⭐
│   │   └── auth.ts                  认证 store
│   │       ├── 登录 (login)
│   │       ├── 登出 (logout)
│   │       └── 验证 (verifyAuth)
│   │
│   ├── 📁 router/                   路由配置 ⭐
│   │   └── index.ts                 路由定义 + 守卫
│   │       ├── / (首页)
│   │       ├── /query (查询页)
│   │       ├── /login (登录页)
│   │       └── /admin (后台)
│   │           ├── /admin (仪表盘)
│   │           ├── /admin/keys
│   │           ├── /admin/tasks
│   │           └── /admin/settings
│   │
│   └── 📁 types/                    TypeScript 类型 ⭐
│       └── index.ts                 接口定义
│           ├── Task
│           ├── TaskStats
│           ├── ExportResponse
│           ├── Key
│           └── AuthResponse
│
└── 📁 dist/ (构建后)               生产构建输出
    ├── index.html
    ├── assets/
    │   ├── index.*.js
    │   ├── vendor.*.js
    │   └── *.css
    └── ...


📊 统计信息
═══════════════════════════════════════════
✅ 总文件数: 30+ 个
✅ 页面组件: 8 个
✅ 可复用组件: 2 个
✅ API 服务: 1 个（包含 5 个模块）
✅ 状态管理: 1 个
✅ 路由配置: 1 个
✅ TypeScript 类型: 1 个
✅ 配置文件: 7 个
✅ 文档: 5 个
═══════════════════════════════════════════

🚀 快速命令
═══════════════════════════════════════════
npm install         # 安装依赖
npm run dev         # 开发服务器 (http://localhost:5173)
npm run build       # 生产构建
npm run preview     # 预览生产版本
═══════════════════════════════════════════

📋 核心特性
═══════════════════════════════════════════
✅ Vue 3 Composition API
✅ TypeScript 完整支持
✅ Vite 快速构建
✅ Vue Router 路由守卫
✅ Pinia 状态管理
✅ Axios HTTP 客户端
✅ Tailwind CSS 响应式
✅ SSE 实时更新
✅ JWT 认证体系
✅ 完全响应式设计
═══════════════════════════════════════════

📚 文档导航
═══════════════════════════════════════════
QUICK_START.md ................. 快速开始 ⭐⭐⭐
COMPLETION_REPORT.md ........... 完成报告 ⭐⭐⭐
README.md ....................... 项目说明
PROGRESS.md ..................... 完成进度
═══════════════════════════════════════════
