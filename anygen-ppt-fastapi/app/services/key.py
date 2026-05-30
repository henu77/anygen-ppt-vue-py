import secrets
import string
from sqlalchemy.orm import Session
from app.models.key import Key
from loguru import logger


class KeyService:
    @staticmethod
    def generate_key() -> str:
        """生成随机卡密"""
        chars = string.ascii_uppercase + string.digits
        key = "".join(secrets.choice(chars) for _ in range(16))
        # 格式化为 XXXX-XXXX-XXXX-XXXX
        return f"{key[0:4]}-{key[4:8]}-{key[8:12]}-{key[12:16]}"

    @staticmethod
    def create_keys(db: Session, count: int, max_uses: int, is_super: bool = False) -> list[Key]:
        """批量创建卡密"""
        # 批量查询已有卡密，避免逐个查库
        existing_keys = {k.key for k in db.query(Key.key).all()}

        keys = []
        for _ in range(count):
            while True:
                key_str = KeyService.generate_key()
                if key_str not in existing_keys:
                    existing_keys.add(key_str)
                    break

            key = Key(key=key_str, max_uses=max_uses, is_super=is_super, status="active")
            keys.append(key)

        db.add_all(keys)
        db.commit()
        logger.info(f"创建 {count} 个卡密成功")
        return keys

    @staticmethod
    def check_key(db: Session, key_str: str) -> dict:
        """查询卡密信息"""
        key = db.query(Key).filter(Key.key == key_str).first()
        if not key:
            return {"valid": False, "message": "卡密不存在"}

        if key.status != "active":
            return {"valid": False, "message": "卡密已禁用"}

        if key.used_count >= key.max_uses:
            return {"valid": False, "message": "卡密已用尽"}

        return {
            "valid": True,
            "status": key.status,
            "max_uses": key.max_uses,
            "used_count": key.used_count,
            "is_super": int(key.is_super),
        }

    @staticmethod
    def use_key(db: Session, key_str: str) -> bool:
        """使用卡密（增加计数，超级卡密不扣次数）"""
        key = db.query(Key).filter(Key.key == key_str).first()
        if not key:
            return False

        if key.is_super:
            logger.info(f"超级卡密 {key_str} 不扣次数")
            return True

        key.used_count += 1
        if key.used_count >= key.max_uses:
            key.status = "expired"

        db.commit()
        logger.info(f"卡密 {key_str} 使用次数: {key.used_count}")
        return True

    @staticmethod
    def list_keys(db: Session) -> list[Key]:
        """获取卡密列表"""
        return db.query(Key).all()

    @staticmethod
    def update_key_status(db: Session, key_id: int, status: str) -> Key:
        """更新卡密状态"""
        key = db.query(Key).filter(Key.id == key_id).first()
        if key:
            key.status = status
            db.commit()
            logger.info(f"更新卡密 {key_id} 状态为 {status}")
        return key

    @staticmethod
    def delete_key(db: Session, key_id: int) -> bool:
        """删除卡密"""
        key = db.query(Key).filter(Key.id == key_id).first()
        if key:
            # 先将关联任务的 key_id 置空，避免 NOT NULL 约束冲突
            from app.models.task import Task
            db.query(Task).filter(Task.key_id == key_id).update(
                {Task.key_id: None}, synchronize_session="fetch"
            )
            db.flush()
            db.delete(key)
            db.commit()
            logger.info(f"删除卡密 {key_id}")
            return True
        return False

    @staticmethod
    def batch_update_keys(db: Session, action: str, key_ids: list[int], value: int = None) -> int:
        """批量更新卡密"""
        count = 0
        for key_id in key_ids:
            key = db.query(Key).filter(Key.id == key_id).first()
            if not key:
                continue

            if action == "disable":
                key.status = "disabled"
                count += 1
            elif action == "enable":
                key.status = "active"
                count += 1
            elif action == "delete":
                db.delete(key)
                count += 1
            elif action == "reset_count" and value is not None:
                key.used_count = value
                count += 1
            elif action == "set_max_uses" and value is not None:
                key.max_uses = value
                count += 1

        db.commit()
        logger.info(f"批量 {action} 卡密 {count} 个")
        return count
