from sqlalchemy.orm import Session
from app.models.xianyu import XianyuAccount, XianyuOrder
from loguru import logger


class XianyuService:
    @staticmethod
    def bind_account(db: Session, account_id: str, cookies: str, unb: str = None, nickname: str = None) -> XianyuAccount:
        """绑定闲鱼账户"""
        account = db.query(XianyuAccount).filter(XianyuAccount.account_id == account_id).first()
        is_new = account is None
        if account:
            account.cookies = cookies
            account.unb = unb
            account.status = "active"
            if nickname:
                account.nickname = nickname
        else:
            account = XianyuAccount(account_id=account_id, cookies=cookies, unb=unb, nickname=nickname, status="active")
            db.add(account)

        db.commit()
        logger.info(f"[{account.nickname or '-'}] 绑定闲鱼账户: {account_id}")

        # 自动创建 Cookie 续期定时任务
        if is_new:
            try:
                from app.services.scheduled_task import ScheduledTaskService
                from app import scheduler as task_scheduler
                task = ScheduledTaskService.create_task(
                    db,
                    name=f"Cookie续期-{account.nickname or account_id}",
                    task_type="xianyu_cookie_renew",
                    interval_seconds=3600,
                    config={"account_id": account_id},
                )
                task_scheduler.add_job(task.id, task.task_type, task.interval_seconds, task.config)
            except Exception as e:
                logger.warning(f"创建续期任务失败: {e}")

        return account

    @staticmethod
    def unbind_account(db: Session, account_id: str) -> bool:
        """解绑闲鱼账户"""
        account = db.query(XianyuAccount).filter(XianyuAccount.account_id == account_id).first()
        if account:
            nickname = account.nickname
            db.delete(account)
            db.commit()
            logger.info(f"[{nickname or '-'}] 解绑闲鱼账户: {account_id}")

            # 自动删除关联的定时任务
            try:
                from app.services.scheduled_task import ScheduledTaskService
                from app import scheduler as task_scheduler
                task = ScheduledTaskService.get_task_by_type_and_config(db, "xianyu_cookie_renew", account_id)
                if task:
                    task_scheduler.remove_job(task.id)
                    ScheduledTaskService.delete_task(db, task.id)
            except Exception as e:
                logger.warning(f"删除续期任务失败: {e}")

            return True
        return False

    @staticmethod
    def list_accounts(db: Session) -> list[XianyuAccount]:
        """获取闲鱼账户列表"""
        return db.query(XianyuAccount).all()

    @staticmethod
    def get_account(db: Session, account_id: str) -> XianyuAccount:
        """获取闲鱼账户"""
        return db.query(XianyuAccount).filter(XianyuAccount.account_id == account_id).first()

    @staticmethod
    def update_account_status(db: Session, account_id: str, status: str) -> bool:
        """更新闲鱼账户状态"""
        account = db.query(XianyuAccount).filter(XianyuAccount.account_id == account_id).first()
        if not account:
            return False
        account.status = status
        db.commit()
        logger.info(f"[{account.nickname or '-'}] 账户状态更新为 {status}: {account_id}")
        return True

    @staticmethod
    def update_delivery_template(db: Session, account_id: str, template: str) -> XianyuAccount:
        """更新发货模板"""
        account = db.query(XianyuAccount).filter(XianyuAccount.account_id == account_id).first()
        if account:
            account.delivery_template = template
            db.commit()
            logger.info(f"[{account.nickname or '-'}] 更新发货模板: {account_id}")
        return account

    @staticmethod
    def add_order(db: Session, order_no: str, account_id: str, status: str = None, data: dict = None) -> XianyuOrder:
        """添加订单"""
        order = XianyuOrder(order_no=order_no, account_id=account_id, status=status, data=data)
        db.add(order)
        db.commit()
        account = db.query(XianyuAccount).filter(XianyuAccount.account_id == account_id).first()
        acc_name = f"{account.nickname or '-'}" if account else "-"
        logger.info(f"[{acc_name}] 添加订单: {order_no} (账户: {account_id})")
        return order

    @staticmethod
    def list_orders(db: Session, account_id: str = None, status: str = None) -> list[XianyuOrder]:
        """获取订单列表"""
        query = db.query(XianyuOrder)
        if account_id:
            query = query.filter(XianyuOrder.account_id == account_id)
        if status:
            query = query.filter(XianyuOrder.status == status)
        return query.all()

    @staticmethod
    def get_order(db: Session, order_no: str) -> XianyuOrder:
        """获取订单"""
        return db.query(XianyuOrder).filter(XianyuOrder.order_no == order_no).first()

    @staticmethod
    def update_order_status(db: Session, order_no: str, status: str) -> XianyuOrder:
        """更新订单状态"""
        order = db.query(XianyuOrder).filter(XianyuOrder.order_no == order_no).first()
        if order:
            order.status = status
            db.commit()
            account = db.query(XianyuAccount).filter(XianyuAccount.account_id == order.account_id).first()
            acc_name = f"{account.nickname or '-'}" if account else "-"
            logger.info(f"[{acc_name}] 更新订单状态: {order_no} -> {status} (账户: {order.account_id})")
        return order
