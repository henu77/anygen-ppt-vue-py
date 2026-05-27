from sqlalchemy.orm import Session
from app.models.settings import Settings
from loguru import logger
import json


class SettingsService:
    @staticmethod
    def get_setting(db: Session, key: str) -> Settings:
        """获取单个设置"""
        return db.query(Settings).filter(Settings.key == key).first()

    @staticmethod
    def get_all_settings(db: Session) -> dict:
        """获取所有设置"""
        settings = db.query(Settings).all()
        result = {}
        for setting in settings:
            if setting.type == "json":
                try:
                    result[setting.key] = json.loads(setting.value)
                except:
                    result[setting.key] = setting.value
            elif setting.type == "number":
                try:
                    result[setting.key] = int(setting.value)
                except:
                    result[setting.key] = setting.value
            elif setting.type == "boolean":
                result[setting.key] = setting.value.lower() == "true"
            else:
                result[setting.key] = setting.value

        return result

    @staticmethod
    def update_setting(db: Session, key: str, value: str, type: str = "string") -> Settings:
        """更新设置"""
        setting = db.query(Settings).filter(Settings.key == key).first()
        if setting:
            setting.value = value
            setting.type = type
        else:
            setting = Settings(key=key, value=value, type=type)
            db.add(setting)

        db.commit()
        logger.info(f"更新设置 {key} = {value}")
        return setting

    @staticmethod
    def update_multiple_settings(db: Session, settings_dict: dict) -> int:
        """批量更新设置"""
        count = 0
        for key, value in settings_dict.items():
            if isinstance(value, bool):
                type_str = "boolean"
                value_str = "true" if value else "false"
            elif isinstance(value, int):
                type_str = "number"
                value_str = str(value)
            elif isinstance(value, dict):
                type_str = "json"
                value_str = json.dumps(value)
            else:
                type_str = "string"
                value_str = str(value)

            SettingsService.update_setting(db, key, value_str, type_str)
            count += 1

        return count
