"""Microsoft Store integration (only active in the MSIX/Store build).

- Trial/licence state via Windows.Services.Store
- "Start with Windows" via the package's StartupTask
- How we were launched (startup vs. user) via AppInstance activation args

Everything degrades gracefully: outside the Store package the app is treated as fully licensed.
"""
import asyncio
import os
import time

import core

# Fill in after reserving the name in Partner Center (Product identity → Store ID, e.g. 9NBLGGH4R315).
STORE_PRODUCT_ID = ""
STARTUP_TASK_ID = "PhoneDropStartup"


def _run(coro):
    return asyncio.run(coro)


# ---- licence -----------------------------------------------------------------
class License:
    def __init__(self, state, days_left=None):
        self.state = state          # "full" | "trial" | "expired"
        self.days_left = days_left  # only for "trial"

    @property
    def locked(self):
        return self.state == "expired"

    def __repr__(self):
        return f"License({self.state}, days_left={self.days_left})"


def check_license():
    if os.environ.get("STP_FAKE_LICENSE"):  # for testing the UI: "trial:5" or "expired"
        kind, _, days = os.environ["STP_FAKE_LICENSE"].partition(":")
        return License(kind, int(days) if days else None)
    if not core.PACKAGED:
        return License("full")
    try:
        from winrt.windows.services.store import StoreContext

        async def go():
            return await StoreContext.get_default().get_app_license_async()

        lic = _run(go())
        # A package that wasn't installed from the Store (developer/sideload install) has no SKU.
        if not lic.sku_store_id:
            return License("full")
        if lic.is_active and not lic.is_trial:
            return License("full")
        if lic.is_active and lic.is_trial:
            remaining = lic.trial_time_remaining
            secs = remaining.total_seconds() if hasattr(remaining, "total_seconds") else 0
            return License("trial", max(0, int((secs + 86399) // 86400)))
        return License("expired")
    except Exception:
        # If the Store can't be reached we don't punish the user.
        return License("full")


def open_store_page():
    if STORE_PRODUCT_ID:
        os.startfile(f"ms-windows-store://pdp/?productid={STORE_PRODUCT_ID}")
    else:
        os.startfile("ms-windows-store://search/?query=PhoneDrop")


# ---- startup task ------------------------------------------------------------
def startup_enabled():
    try:
        from winrt.windows.applicationmodel import StartupTask, StartupTaskState

        async def go():
            return (await StartupTask.get_async(STARTUP_TASK_ID)).state

        state = _run(go())
        return state in (StartupTaskState.ENABLED, StartupTaskState.ENABLED_BY_POLICY)
    except Exception:
        return False


def set_startup_enabled(enabled):
    """Returns the new state. Windows may refuse (e.g. user disabled it in Settings)."""
    try:
        from winrt.windows.applicationmodel import StartupTask, StartupTaskState

        async def go():
            task = await StartupTask.get_async(STARTUP_TASK_ID)
            if enabled:
                return await task.request_enable_async()
            task.disable()
            return task.state

        state = _run(go())
        if enabled and state == StartupTaskState.DISABLED_BY_USER:
            os.startfile("ms-settings:startupapps")  # only the user can re-enable it there
        return state in (StartupTaskState.ENABLED, StartupTaskState.ENABLED_BY_POLICY)
    except Exception:
        return False


# ---- activation --------------------------------------------------------------
def launched_at_startup():
    if not core.PACKAGED:
        return False
    try:
        from winrt.windows.applicationmodel import AppInstance
        from winrt.windows.applicationmodel.activation import ActivationKind
        args = AppInstance.get_activated_event_args()
        return args is not None and args.kind == ActivationKind.STARTUP_TASK
    except Exception:
        return False


class LicenseWatcher:
    """Re-checks the licence now and then, so buying unlocks the app without a restart."""

    def __init__(self, store, on_change):
        self.store, self.on_change = store, on_change
        self.license = License("full")
        self.last = 0

    def refresh(self, force=False):
        if not force and time.time() - self.last < (20 if self.license.locked else 600):
            return self.license
        self.last = time.time()
        new = check_license()
        changed = (new.state, new.days_left) != (self.license.state, self.license.days_left)
        self.license = new
        self.store.locked = new.locked
        if changed:
            self.on_change(new)
        return new
