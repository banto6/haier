import logging
from collections.abc import Callable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.haier.const import CONFIG_ENTRY_VERSION

_LOGGER = logging.getLogger(__name__)

Migration = Callable[[dict[str, Any]], dict[str, Any]]


class ConfigEntryMigrator:
    """按版本顺序迁移配置条目。"""

    def __init__(
        self,
        target_version: int,
        migrations: dict[int, Migration],
    ) -> None:
        self._target_version = target_version
        self._migrations = migrations

    def migrate(self, hass: HomeAssistant, entry: ConfigEntry) -> bool:
        """将配置条目逐版本迁移到目标版本。"""
        if entry.version > self._target_version:
            _LOGGER.error(
                "配置版本 %s 高于当前支持的版本 %s",
                entry.version,
                self._target_version,
            )
            return False

        version = entry.version
        data = dict(entry.data)

        while version < self._target_version:
            migration = self._migrations.get(version)
            if migration is None:
                _LOGGER.error("缺少从配置版本 %s 开始的迁移方法", version)
                return False

            data = migration(data)
            version += 1

        if version != entry.version:
            hass.config_entries.async_update_entry(
                entry,
                data=data,
                version=version,
            )

        return True


def _migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """迁移版本 1 到版本 2。"""
    return data


def _migrate_v2_to_v3(data: dict[str, Any]) -> dict[str, Any]:
    """将偏好设置从账户配置迁移到独立配置。"""
    account = dict(data.get('account', {}))
    preferences = dict(data.get('preferences', {}))

    preferences.setdefault(
        'default_load_all_entity',
        account.pop('default_load_all_entity', True)
    )
    preferences.setdefault(
        'ignore_device_offline',
        account.pop('ignore_device_offline', False)
    )

    return {
        **data,
        'account': account,
        'preferences': preferences,
    }


CONFIG_ENTRY_MIGRATOR = ConfigEntryMigrator(
    target_version=CONFIG_ENTRY_VERSION,
    migrations={
        1: _migrate_v1_to_v2,
        2: _migrate_v2_to_v3,
    },
)
