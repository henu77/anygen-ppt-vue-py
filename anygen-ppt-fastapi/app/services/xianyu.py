from sqlalchemy.orm import Session
from app.models.xianyu import XianyuAccount, XianyuOrder
from loguru import logger


class XianyuService:
    @staticmethod
    def bind_account(db: Session, account_id: str, cookies: str, unb: str = None) -> XianyuAccount:
        """绑定闲鱼账户"""
        account = db.query(XianyuAccount).filter(XianyuAccount.account_id == account_id).first()
        if account:
            account.cookies = cookies
            account.unb = unb
            account.status = "active"
        else:
            account = XianyuAccount(account_id=account_id, cookies=cookies, unb=unb, status="active")
            db.add(account)

        db.commit()
        logger.info(f"绑定闲鱼账户 {account_id} 成功")
        return account

    @staticmethod
    def unbind_account(db: Session, account_id: str) -> bool:
        """解绑闲鱼账户"""
        account = db.query(XianyuAccount).filter(XianyuAccount.account_id == account_id).first()
        if account:
            db.delete(account)
            db.commit()
            logger.info(f"解绑闲鱼账户 {account_id} 成功")
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
    def update_delivery_template(db: Session, account_id: str, template: str) -> XianyuAccount:
        """更新发货模板"""
        account = db.query(XianyuAccount).filter(XianyuAccount.account_id == account_id).first()
        if account:
            account.delivery_template = template
            db.commit()
            logger.info(f"更新账户 {account_id} 发货模板成功")
        return account

    @staticmethod
    def add_order(db: Session, order_no: str, account_id: str, status: str = None, data: dict = None) -> XianyuOrder:
        """添加订单"""
        order = XianyuOrder(order_no=order_no, account_id=account_id, status=status, data=data)
        db.add(order)
        db.commit()
        logger.info(f"添加订单 {order_no} 成功")
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
            logger.info(f"更新订单 {order_no} 状态为 {status}")
        return order
