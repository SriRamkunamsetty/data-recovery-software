# Third-Party License Inventory

This document provides a comprehensive inventory of all third-party dependencies used in RecoverX, their license classifications, selection rationale, and copyleft compliance terms.

---

## 1. Direct Runtime Dependencies

| Package | Version | License | Primary Supplier | Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **PySide6** | 6.12.0 | LGPLv3 / Commercial | The Qt Company Ltd. | Official Qt for Python bindings powering the desktop GUI (high-DPI, dark/light themes, widgets). Distributed in PyInstaller `onedir` mode to maintain dynamic linking and user replaceability under LGPLv3. |
| **shiboken6** | 6.12.0 | LGPLv3 | The Qt Company Ltd. | CPython / C++ binding generator underpinning PySide6 runtime wrappers. |
| **typing-extensions** | 4.16.0 | PSF-2.0 | Python Software Foundation | Backports of standard typing features for Python 3.12 compatibility. |

### LGPLv3 Compliance Statement (PySide6 / Qt)
- **Dynamic Linking:** In accordance with the GNU Lesser General Public License v3 (LGPLv3), RecoverX is packaged using PyInstaller's `onedir` distribution mode. All Qt runtime shared libraries (`Qt6Core.dll`, `Qt6Gui.dll`, `Qt6Widgets.dll`, etc.) and PySide6 extension modules are kept as separate, dynamically linked binary files in the application directory.
- **Library Modification / Replacement:** Users of RecoverX have the right to modify or replace these Qt shared libraries with their own compatible versions without recompiling the RecoverX source code.
- **Source Code Availability:** RecoverX includes no modifications to the upstream PySide6 or Qt source distributions. Upstream source code can be acquired directly from [The Qt Project](https://code.qt.io/) or [PyPI](https://pypi.org/project/PySide6/).

---

## 2. Packaging and Binary Distribution Tooling

| Package | Version | License | Rationale |
| :--- | :--- | :--- | :--- |
| **pyinstaller** | 6.22.3 | GPL-2.0-or-later WITH PyInstaller-exception-2.0 | Packages the Python interpreter and dependencies into a standalone Windows directory (`onedir`). The PyInstaller license includes an explicit exception allowing distribution of output binaries under terms chosen by the author. |
| **pefile** | 2024.8.26 | MIT | Used by PyInstaller to inspect Windows PE executable headers and resolve DLL dependencies. |
| **pywin32-ctypes** | 0.2.3 | BSD-3-Clause | Clean ctypes-based interface for Windows resource manipulation during packaging. |
| **altgraph** | 0.17.5 | MIT | Graph computation utility used by PyInstaller module analyzer. |

---

## 3. Development, Linting, and Testing Dependencies

These libraries are strictly used during automated test runs, static typing analysis, and code formatting; they are **never** distributed to end users.

| Package | Version | License | Rationale |
| :--- | :--- | :--- | :--- |
| **pytest** | 9.2.0 | MIT | Industry-standard Python test framework for unit and integration testing. |
| **pytest-qt** | 4.5.0 | MIT | Qt testing fixture enabling headless offscreen execution (`QT_QPA_PLATFORM=offscreen`). |
| **hypothesis** | 6.170.12 | MPL-2.0 | Advanced property-based testing framework used to stress-test binary parsers against malformed inputs. |
| **ruff** | 0.17.3 | MIT OR Apache-2.0 | High-performance Python linter and formatter. |
| **mypy** | 2.4.0 | MIT | Strict static type checker ensuring full type safety across domain models and hardware abstractions. |
| **hatchling** | 1.33.0 | MIT | PEP 517 build backend for packaging and local wheel generation. |

---

## 4. RecoverX Application License Status

As specified in [MASTER_PROMPT.md](../MASTER_PROMPT.md) Section 18 and tracked in [docs/DECISIONS.md](DECISIONS.md) (ADR 019):
- The application root repository contains a placeholder `LICENSE` marked **"Owner to decide"**.
- The ultimate open-source (e.g. GPLv3, AGPLv3, Apache-2.0) or commercial/dual license will be formally established by the repository owner prior to public distribution.
- RecoverX contains no bundled third-party recovery binaries or uncredited code copies.
