"""Presentation pages package."""

from recoverx.presentation.pages.dashboard_page import DashboardPage
from recoverx.presentation.pages.device_page import DeviceSelectionPage
from recoverx.presentation.pages.report_page import RecoveryReportPage
from recoverx.presentation.pages.results_page import RecoveryResultsPage
from recoverx.presentation.pages.scan_config_page import ScanConfigurationPage
from recoverx.presentation.pages.scan_progress_page import ScanProgressPage
from recoverx.presentation.pages.settings_page import SettingsPage

__all__ = [
    "DashboardPage",
    "DeviceSelectionPage",
    "RecoveryReportPage",
    "RecoveryResultsPage",
    "ScanConfigurationPage",
    "ScanProgressPage",
    "SettingsPage",
]
