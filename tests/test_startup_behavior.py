import ast
import asyncio
import importlib.util
import logging
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]


def _load_gateway_module():
    package_names = (
        "custom_components",
        "custom_components.haier",
        "custom_components.haier.core",
    )
    for package_name in package_names:
        package = types.ModuleType(package_name)
        package.__path__ = []
        sys.modules[package_name] = package

    aiohttp = types.ModuleType("aiohttp")
    aiohttp.WSMsgType = types.SimpleNamespace(TEXT=1, CLOSED=2, CLOSING=3, ERROR=4)
    sys.modules["aiohttp"] = aiohttp

    homeassistant = types.ModuleType("homeassistant")
    homeassistant_core = types.ModuleType("homeassistant.core")
    homeassistant_core.HomeAssistant = object
    homeassistant_helpers = types.ModuleType("homeassistant.helpers")
    homeassistant_aiohttp = types.ModuleType("homeassistant.helpers.aiohttp_client")
    homeassistant_aiohttp.async_get_clientsession = lambda hass: None
    homeassistant_event = types.ModuleType("homeassistant.helpers.event")
    homeassistant_event.async_track_time_interval = lambda *args, **kwargs: None
    sys.modules.update(
        {
            "homeassistant": homeassistant,
            "homeassistant.core": homeassistant_core,
            "homeassistant.helpers": homeassistant_helpers,
            "homeassistant.helpers.aiohttp_client": homeassistant_aiohttp,
            "homeassistant.helpers.event": homeassistant_event,
        }
    )

    client_module = types.ModuleType("custom_components.haier.core.client")
    client_module.HaierClient = object
    device_module = types.ModuleType("custom_components.haier.core.device")
    device_module.HaierDevice = object
    event_module = types.ModuleType("custom_components.haier.core.event")
    event_module.EVENT_DEVICE_CONTROL = "device_control"
    event_module.EVENT_DEVICE_DATA_CHANGED = "device_data_changed"
    event_module.EVENT_GATEWAY_DISCONNECTED = "gateway_disconnected"
    event_module.EVENT_DEVICE_ONLINE_CHANGED = "device_online_changed"
    event_module.listen_event = lambda *args, **kwargs: None
    event_module.fire_event = lambda *args, **kwargs: None
    sys.modules.update(
        {
            "custom_components.haier.core.client": client_module,
            "custom_components.haier.core.device": device_module,
            "custom_components.haier.core.event": event_module,
        }
    )

    module_path = ROOT / "custom_components/haier/core/device_gateway.py"
    spec = importlib.util.spec_from_file_location(
        "custom_components.haier.core.device_gateway", module_path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class StartupSourceTests(unittest.TestCase):
    def test_entity_does_not_force_unique_id_as_entity_id(self):
        source = (ROOT / "custom_components/haier/entity.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        assignments = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.Assign, ast.AnnAssign))
        ]
        self.assertFalse(
            any("self.entity_id" in ast.unparse(node) for node in assignments)
        )

    def test_platforms_are_ready_before_gateway_starts(self):
        source = (ROOT / "custom_components/haier/__init__.py").read_text(
            encoding="utf-8"
        )
        self.assertLess(
            source.index("async_forward_entry_setups"),
            source.index("gateway = HaierDeviceGateway"),
        )


class InitialDeviceStateTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.gateway_module = _load_gateway_module()

    async def test_initial_snapshots_and_offline_state_are_published(self):
        class Device:
            def __init__(self, device_id):
                self.id = device_id

        class Client:
            async def get_devices_online_status(self):
                return {"online": True, "offline": False}

            async def get_device_snapshot_data(self, device_id):
                return {"temperature": 4}

        events = []
        gateway = self.gateway_module.HaierDeviceGateway.__new__(
            self.gateway_module.HaierDeviceGateway
        )
        gateway._hass = object()
        gateway._client = Client()

        with patch.object(
            self.gateway_module,
            "fire_event",
            side_effect=lambda hass, event, data: events.append((event, data)),
        ):
            await gateway._init_devices([Device("online"), Device("offline")])

        self.assertIn(
            (
                self.gateway_module.EVENT_DEVICE_ONLINE_CHANGED,
                {"deviceId": "offline", "online": False},
            ),
            events,
        )
        self.assertIn(
            (
                self.gateway_module.EVENT_DEVICE_DATA_CHANGED,
                {"deviceId": "online", "attributes": {"temperature": 4}},
            ),
            events,
        )
        self.assertFalse(
            any(
                event == self.gateway_module.EVENT_DEVICE_ONLINE_CHANGED
                and data == {"deviceId": "online", "online": True}
                for event, data in events
            )
        )

    async def test_snapshot_failure_is_logged_without_blocking_other_devices(self):
        class Device:
            def __init__(self, device_id):
                self.id = device_id

        class Client:
            async def get_devices_online_status(self):
                return {"broken": True, "healthy": True}

            async def get_device_snapshot_data(self, device_id):
                if device_id == "broken":
                    raise RuntimeError("snapshot failed")
                return {"temperature": 4}

        events = []
        gateway = self.gateway_module.HaierDeviceGateway.__new__(
            self.gateway_module.HaierDeviceGateway
        )
        gateway._hass = object()
        gateway._client = Client()

        with (
            patch.object(
                self.gateway_module,
                "fire_event",
                side_effect=lambda hass, event, data: events.append((event, data)),
            ),
            self.assertLogs(
                self.gateway_module._LOGGER, level=logging.ERROR
            ) as logs,
        ):
            await gateway._init_devices([Device("broken"), Device("healthy")])

        self.assertTrue(
            any("broken" in message for message in logs.output), logs.output
        )
        self.assertIn(
            (
                self.gateway_module.EVENT_DEVICE_DATA_CHANGED,
                {"deviceId": "healthy", "attributes": {"temperature": 4}},
            ),
            events,
        )


if __name__ == "__main__":
    unittest.main()
