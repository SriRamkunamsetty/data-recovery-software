"""Windows storage infrastructure module: audited ctypes Win32 bindings and readers."""

from recoverx.infrastructure.storage.win32.discovery import (
    DiscoveredWindowsDevice,
    WindowsDeviceEnumerator,
)
from recoverx.infrastructure.storage.win32.helper.client import (
    NamedPipeClient,
    WindowsElevatedDeviceReader,
    launch_elevated_helper,
)
from recoverx.infrastructure.storage.win32.reader import WindowsRawDeviceReader
from recoverx.infrastructure.storage.win32.resolver import WindowsVolumeIdentityResolver

__all__ = [
    "DiscoveredWindowsDevice",
    "NamedPipeClient",
    "WindowsDeviceEnumerator",
    "WindowsElevatedDeviceReader",
    "WindowsRawDeviceReader",
    "WindowsVolumeIdentityResolver",
    "launch_elevated_helper",
]
