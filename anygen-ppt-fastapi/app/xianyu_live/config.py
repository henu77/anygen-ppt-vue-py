"""xianyu_live 模块运行配置"""

# WebSocket 地址
WS_URL = "wss://wss-goofish.dingtalk.com/"

# 心跳
HEARTBEAT_INTERVAL = 15      # 心跳间隔（秒）
HEARTBEAT_TIMEOUT = 30       # 心跳超时（秒）

# 重连
MAX_NETWORK_FAILURES = 20    # 最大网络重连次数
MAX_AUTH_FAILURES = 5        # 最大认证失败次数

# 消息发送
SEND_MSG_MAX_RETRY = 5       # 消息发送最大重试次数
SEND_MSG_RETRY_DELAY = 2     # 消息发送重试间隔（秒）

# Token 刷新
IM_TOKEN_REFRESH_INTERVAL = 72000  # IM Token 刷新间隔（秒，20 小时）
IM_TOKEN_RETRY_INTERVAL = 300      # Token 获取失败重试间隔（秒）

# IM 注册
APP_KEY = "444e9908a51d1cb236a27862abc769c9"

# 并发控制
MAX_CONCURRENT_DELIVERIES = 10     # 全局最大并发发货数
MESSAGE_SEMAPHORE_LIMIT = 100      # 消息处理并发限制

# 消息去重
MESSAGE_DEDUP_EXPIRY = 3600        # 消息去重过期时间（秒）
MESSAGE_DEDUP_MAX_SIZE = 10000     # 最大去重记录数

# 付款触发关键词
PAYMENT_KEYWORDS = [
    "[我已付款，等待你发货]",
    "[已付款，待发货]",
    "我已付款，等待你发货",
    "[记得及时发货]",
    "[买家已付款]",
]

# 仅记录但不触发发货的关键词（拍下待付款）
PENDING_PAYMENT_KEYWORDS = [
    "[我已拍下，待付款]",
]

# 需要拉取订单详情的消息
FETCH_DETAIL_MESSAGES = [
    "[我已拍下，待付款]",
    "[我已付款，等待你发货]",
    "[买家已付款]",
    "[付款完成]",
    "[已付款，待发货]",
]

# 订单状态
ORDER_STATUS_WAIT_SELLER_SEND = "WAIT_SELLER_SEND_GOODS"
ORDER_STATUS_WAIT_BUYER_PAY = "WAIT_BUYER_PAY"
ORDER_STATUS_TRADE_CLOSED = "TRADE_CLOSED"
ORDER_STATUS_WAIT_BUYER_CONFIRM = "WAIT_BUYER_CONFIRM_GOODS"
ORDER_STATUS_TRADE_FINISHED = "TRADE_FINISHED"
