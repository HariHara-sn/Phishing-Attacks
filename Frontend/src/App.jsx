// import { useState } from "react";

// export default function App() {
//   const [result, setResult] = useState(null);
//   const [error, setError] = useState("");
//   const [loading, setLoading] = useState(false);

//   function getLocation() {
//     return new Promise((resolve, reject) => {
//       if (!("geolocation" in navigator)) {
//         reject(new Error("Geolocation isn't supported in this browser."));
//         return;
//       }
//       navigator.geolocation.getCurrentPosition(
//         (pos) => resolve(pos.coords),
//         (err) =>
//           reject(
//             new Error(
//               err.code === err.PERMISSION_DENIED
//                 ? "Location permission denied."
//                 : err.message
//             )
//           ),
//         { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
//       );
//     });
//   }

//   async function handleClick() {
//     setError("");
//     setResult(null);
//     setLoading(true);
//     try {
//       // 1) Battery (optional: only Chromium browsers have it, and it needs HTTPS or localhost).
//       let level = null;
//       let charging = null;
//       if ("getBattery" in navigator) {
//         const battery = await navigator.getBattery();
//         level = battery.level;
//         charging = battery.charging;
//       }

//       // 2) Location (the browser will ask the user for permission).
//       const coords = await getLocation();

//       // 3) Send everything to FastAPI.
//       const res = await fetch("/api/battery", {
//         method: "POST",
//         headers: { "Content-Type": "application/json" },
//         body: JSON.stringify({
//           level,
//           charging,
//           lat: coords.latitude,
//           lng: coords.longitude,
//           accuracy: coords.accuracy,
//         }),
//       });
//       if (!res.ok) throw new Error(`Server responded ${res.status}`);

//       // 4) Show what the backend returned.
//       setResult(await res.json());
//     } catch (e) {
//       setError(e.message || "Something went wrong");
//     } finally {
//       setLoading(false);
//     }
//   }

//     return (
//     <main className="card">
//       <h1>Phone Information</h1>
//       <button onClick={handleClick} disabled={loading}>
//         {loading ? "Checking…" : "Show Phone Information"}
//       </button>

//       {result && (
//         <div className="result">
//           {result.percentage !== null && (
//             <>
//               <div className="percent">{result.percentage}%</div>
//               <div className="meta">
//                 {result.charging ? "⚡ Charging" : "Not charging"}
//               </div>
//             </>
//           )}
//           <div className="meta">
//             📍 Lat: {result.lat.toFixed(5)}, Lng: {result.lng.toFixed(5)}
//             {result.accuracy != null && ` (±${Math.round(result.accuracy)} m)`}
//           </div>
//         </div>
//       )}

//       {error && <p className="error">{error}</p>}
//     </main>
//   );
// }

import { useState } from "react";

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
            err.code === err.PERMISSION_DENIED ? "permission denied" : err.message
          )
        ),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
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
  if (!navigator.clipboard?.readText) throw new Error("not supported in this browser");
  const text = await navigator.clipboard.readText();
  return text.slice(0, 500); // cap what we send
}

export default function App() {
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [skipped, setSkipped] = useState([]);
  const [loading, setLoading] = useState(false);

  async function handleClick() {
    setError("");
    setResult(null);
    setSkipped([]);
    setLoading(true);

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
      // Permission prompts first, while the click is still fresh
      // (Safari only allows clipboard/notification prompts right after a tap).
      const clipboard = await optional("Clipboard", readClipboard);
      const notifications = await optional("Notifications", getNotificationPermission);
      const coords = await optional("Location", getLocation);
      const battery = await optional("Battery", async () => {
        if (!("getBattery" in navigator)) throw new Error("not supported in this browser");
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

      setResult(await res.json());
      setSkipped(skippedNow);
    } catch (e) {
      setError(e.message || "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  const rows = result
    ? [
        ["Device type", result.device_type],
        ["Model", result.model],
        ["OS", result.os],
        ["Browser", result.browser],
        [
          "Screen",
          `${result.screen.width}×${result.screen.height} @${result.screen.pixel_ratio}x`,
        ],
        ["IP address", result.ip],
        ["Language", result.language],
        ["Timezone", result.timezone],
        ["Notifications", result.notifications],
        ["Clipboard", result.clipboard === "" ? "(empty)" : result.clipboard],
        ["Device ID", result.device_id],
      ]
    : [];

  return (
    <main className="card">
      <h1>Phone Information</h1>
      <button onClick={handleClick} disabled={loading}>
        {loading ? "Checking…" : "Show Phone Information"}
      </button>

      {result && (
        <div className="result">
          {result.percentage !== null && (
            <>
              <div className="percent">{result.percentage}%</div>
              <div className="meta">
                {result.charging ? "⚡ Charging" : "Not charging"}
              </div>
            </>
          )}
          {result.lat !== null && result.lng !== null && (
            <div className="meta">
              📍 Lat: {result.lat.toFixed(5)}, Lng: {result.lng.toFixed(5)}
              {result.accuracy != null && ` (±${Math.round(result.accuracy)} m)`}
            </div>
          )}

          <dl className="details">
            {rows.map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value ?? "—"}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {skipped.length > 0 && (
        <ul className="skipped">
          {skipped.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
      )}

      {error && <p className="error">{error}</p>}
    </main>
  );
}
