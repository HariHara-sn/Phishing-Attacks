# Device Info: Phishing-Awareness Demonstration

This project is a React and FastAPI demonstration for **security awareness
and authorized testing**. It illustrates why people should be cautious about
following unfamiliar links and granting browser permissions.

> **This is not a phishing kit.** The app does not ask for usernames or
> passwords. It displays what it collects after a user clicks the button and
> the browser permits the requested data access. Use it only with informed
> consent on devices and networks you own or are authorized to test.

## How the demo works

1. The user opens the React page and clicks **Show Phone Information**.
2. The browser attempts to read available information. Location and
   notification access are governed by browser permissions; clipboard access
   may also be restricted by the browser. Unsupported or denied optional
   information is skipped.
3. The frontend sends the collected report to FastAPI at `POST /api/battery`.
   During development, Vite proxies `/api` requests to `http://127.0.0.1:8000`.
4. The page displays the response. The backend retains the latest report in
   memory and logs a privacy-filtered summary as structured JSON. When the
   local observability stack is running, the same summary is sent to Loki.

The report can include:

- Approximate device category, browser, operating system, screen dimensions,
  and a random browser-install ID (not a hardware identifier).
- Battery status when supported by the browser.
- Location when available and permitted.
- Browser language, timezone, and notification permission status.
- Up to 500 characters of clipboard text when clipboard access succeeds.
- Client IP address as inferred by the backend.

Some fields may be unavailable, inaccurate, or omitted depending on the
browser, device, permissions, and proxy configuration. A forwarded IP header
may be supplied by the client or an intermediary and should not be treated as
verified identity.

## Privacy and safe-use requirements

- Clipboard contents may include passwords, tokens, messages, or other private
  data. The frontend can send up to 500 characters, and the API response
  contains the received value. The application excludes clipboard contents,
  location, IP address, and device ID from its terminal and Loki log summaries.
  **Do not use real clipboard contents or personal data during demonstrations.**
  Use synthetic test data.
- Location, device details, and IP address are sensitive. Obtain explicit,
  informed consent before testing, and explain what is collected, why, and
  where it is sent.
- Do not disguise the link, impersonate a trusted service, distribute it to
  unsuspecting people, or use this demo to collect data without authorization.
- A public tunnel makes the app reachable by others. Keep tunnels private when
  possible, do not expose real data, and stop the forwards when testing ends.
- The backend currently allows requests from any origin and keeps the latest
  report in process memory. These are development choices, not production
  safeguards. Do not deploy this configuration as a public service.
- To perform a safer demonstration, use a dedicated test device/account,
  dummy clipboard text, a private tunnel, and a session with participants who
  have been told the purpose and scope.

## Phishing awareness

Phishing commonly uses messages or web pages that imitate trusted people or
services to pressure someone into clicking a link, sharing credentials, or
granting access. Warning signs can include unexpected requests, mismatched
domains, urgency or threats, requests for secrets, and permission prompts
that do not match the task.

Before opening a link or granting a permission:

- Verify the sender and domain using a known, separate channel.
- Do not enter passwords or one-time codes after following an unexpected link.
- Deny permissions that are not needed, and review or revoke site permissions
  after a demonstration.
- Report suspicious messages through your organization’s approved process.

## Requirements

- Python 3.10 or newer
- Node.js and npm
- A modern browser; battery status and clipboard features vary by browser
- HTTPS or `localhost` for browser features that require a secure context

## Run locally on Windows

### Backend

```powershell
cd D:\CyberProj\deviceInfo\Backend
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API documentation: <http://127.0.0.1:8000/docs>

### Frontend

In a second terminal:

```powershell
cd D:\CyberProj\deviceInfo\Frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

## VS Code Dev Tunnels

Forward port `5173` for the frontend and `8000` for the backend. Configure
visibility according to the audience and keep both forwards private unless
public access is necessary and authorized. The frontend Vite configuration
allows `*.devtunnels.ms` hostnames and proxies `/api` requests to the local
backend on port `8000`. Ensure both local servers are running while using the
tunnel; a stopped local server will cause the corresponding tunnel to fail.

## Local logs with Loki and Grafana

Docker Desktop with Docker Compose is required. Start the local observability
services from the project root:

```powershell
cd D:\CyberProj\deviceInfo
docker compose up -d
```

Install the backend dependency (or reinstall all backend requirements):

```powershell
cd D:\CyberProj\deviceInfo\Backend
python -m pip install -r requirements.txt
```

Start or restart FastAPI after Loki is running. Application summary logs are
printed as readable JSON in the backend terminal and sent to Loki as compact
JSON. Loki and Grafana ports are bound to localhost only.

1. Open <http://localhost:3000> and sign in (the initial Grafana credentials
   are `admin` / `admin`; Grafana will prompt you to change the password).
2. Add a **Loki** data source with URL `http://loki:3100`, then select **Save &
   test**. This hostname works from Grafana's Docker container.
3. In **Explore**, select the Loki data source and run:

```logql
{app="battery-api"}
{app="battery-api", env="dev"} | json
{app="battery-api"} | json | event="device_info_received"
{app="battery-api"} | json | report_percentage < 20
{app="battery-api"} | json | report_charging="false"
{app="battery-api"} | json | report_device_type="phone"
```

The log report intentionally includes only battery percentage/status, broad
device type, OS, browser, and receipt time. Clipboard text, exact location,
client IP, and device ID are excluded from logs. The API response still contains
the report fields described above. Stop the local stack when finished:

```powershell
cd D:\CyberProj\deviceInfo
docker compose down
```

## API endpoints

- `POST /api/battery` — accepts the device report and returns the latest report.
- `GET /api/battery` — returns the latest in-memory report, or `404` before
  the first report is received.
- `GET /docs` — interactive FastAPI documentation.

## Project layout

```text
Backend/
  main.py             FastAPI endpoint, validation, and structured logging
  requirements.txt    Python dependencies
Frontend/
  src/App.jsx         Permission-aware browser collection and display
  src/main.jsx        React entry point
  vite.config.js      Vite server and API proxy configuration
  package.json        Frontend scripts and dependencies
```


opencode -s ses_e8d52fe0bffejZfQ1kroqyw2Eb