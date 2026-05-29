"""闲鱼 Cookie 续期定时任务入口

降级链路：API 三步续期（含重试）→ 浏览器续期 → 标记失败
连续失败 >= 3 次 → 自动禁用任务 + 标记账户 need_relogin
"""
from loguru import logger

# 内存中的连续失败计数 {account_id: count}
_failure_counts: dict[str, int] = {}
MAX_CONSECUTIVE_FAILURES = 3


async def run(config: dict) -> dict:
    """定时任务入口"""
    from app.database.db import SessionLocal
    from app.services.xianyu import XianyuService
    from app.services.cookie_renew import renew
    from app.services.scheduled_task import ScheduledTaskService
    from app import scheduler as task_scheduler

    account_id = config.get("account_id")
    if not account_id:
        return {"status": "failed", "message": "config 中缺少 account_id"}

    db = SessionLocal()
    try:
        account = XianyuService.get_account(db, account_id)
        if not account:
            return {"status": "failed", "message": f"账户不存在: {account_id}"}
        if not account.cookies:
            return {"status": "failed", "message": f"账户无 Cookie: [{account.nickname or '-'}] {account_id}"}

        nickname = account.nickname or "-"
        result = await renew(account.cookies, account_id)

        if result["success"]:
            # 续期成功：更新 Cookie，重置失败计数
            account.cookies = result["new_cookies"]
            db.commit()
            _failure_counts.pop(account_id, None)
            logger.info(f"[{nickname}] Cookie 续期成功: {account_id}")
            return {"status": "success", "message": f"[{nickname}] {result['message']}"}
        else:
            # 续期失败：累加失败计数
            count = _failure_counts.get(account_id, 0) + 1
            _failure_counts[account_id] = count
            logger.warning(f"[{nickname}] Cookie 续期失败 ({count}/{MAX_CONSECUTIVE_FAILURES}): {account_id} - {result['message']}")

            if count >= MAX_CONSECUTIVE_FAILURES:
                # 连续失败 >= 3 次：禁用任务 + 标记账户 need_relogin
                logger.error(f"[{nickname}] 连续失败 {count} 次，禁用续期任务: {account_id}")
                XianyuService.update_account_status(db, account_id, "need_relogin")
                # 找到并禁用对应的定时任务
                task = ScheduledTaskService.get_task_by_type_and_config(db, "xianyu_cookie_renew", account_id)
                if task:
                    ScheduledTaskService.update_task(db, task.id, enabled=False)
                    task_scheduler.pause_job(task.id)
                _failure_counts.pop(account_id, None)

                # 发送邮件通知
                try:
                    from app.utils.email import send_email
                    from app.models.base import now_cn
                    send_email(
                        subject=f"[闲鱼保活] 账户 {nickname} Cookie续期失败，需要重新扫码",
                        body=f"""
                        <h3>闲鱼 Cookie 续期失败通知</h3>
                        <p><b>账户：</b>{nickname} ({account_id})</p>
                        <p><b>状态：</b>连续失败 {count} 次，已自动禁用续期任务</p>
                        <p><b>最后失败原因：</b>{result['message']}</p>
                        <p><b>时间：</b>{now_cn().strftime('%Y-%m-%d %H:%M:%S')}</p>
                        <hr>
                        <p>请登录管理后台重新扫码绑定该账户。</p>
                        """,
                    )
                except Exception as e:
                    logger.warning(f"发送邮件通知失败: {e}")

                return {"status": "failed", "message": f"[{nickname}] 连续失败{count}次，已禁用任务，请重新扫码登录"}

            return {"status": "failed", "message": f"[{nickname}] {result['message']} (连续失败{count}次)"}
    finally:
        db.close()
