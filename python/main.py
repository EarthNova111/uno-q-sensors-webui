import datetime
import threading
from arduino.app_bricks.web_ui import WebUI
from arduino.app_utils import App, Bridge

print("Python ready", flush=True)

web = WebUI()

_lock = threading.Lock()
_state = {
    "temp_c": 73.0,
    "target_temp_c": 88,
    "distance_cm": 11.2,
    "water_pct": 48,
    "mode": "off",          # "off" | "on" | "auto"
    "active": False,        # สถานะปั๊ม / SSR
    "estop": False,         # สถานะหยุดฉุกเฉิน
    "auto_refill": False,   # สถานะเติมน้ำอัตโนมัติ
    "last_update_utc": None,
}


def now_utc_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ฟังก์ชันให้ฝั่ง .ino เรียกผ่าน Bridge.call(...) เพื่อส่งค่าเซ็นเซอร์และสถานะขึ้นมา
def update_pot_telemetry(temp_c, distance_cm, water_pct, mode, active, estop):
    with _lock:
        _state["temp_c"] = float(temp_c)
        _state["distance_cm"] = float(distance_cm)
        _state["water_pct"] = int(water_pct)
        _state["mode"] = str(mode)
        _state["active"] = bool(active)
        _state["estop"] = bool(estop)
        _state["last_update_utc"] = now_utc_iso()
    return True


# ฟังก์ชันให้ฝั่ง .ino ดึงค่า target_temp หรือ mode ล่าสุดจาก Python ได้ด้วย
def get_control_config():
    with _lock:
        return {
            "mode": _state["mode"],
            "target_temp_c": _state["target_temp_c"],
            "estop": _state["estop"],
            "auto_refill": _state["auto_refill"],
        }


Bridge.provide("update_pot_telemetry", update_pot_telemetry)
Bridge.provide("get_control_config", get_control_config)


def api_state(_req=None):
    with _lock:
        payload = {
            "ok": True,
            "connected": True,
            "now_utc": now_utc_iso(),
            "temp_c": _state["temp_c"],
            "target_temp_c": _state["target_temp_c"],
            "distance_cm": _state["distance_cm"],
            "water_pct": _state["water_pct"],
            "mode": _state["mode"],
            "active": _state["active"],
            "estop": _state["estop"],
            "auto_refill": _state["auto_refill"],
            "last_update_utc": _state["last_update_utc"],
        }
    return payload


def api_control(req=None):
    data = {}
    if req is not None and hasattr(req, "get_json"):
        data = req.get_json(silent=True) or {}

    with _lock:
        if "mode" in data:
            m = str(data["mode"]).lower().strip()
            if m in ("on", "off", "auto"):
                if not _state["estop"] or m == "off":
                    _state["mode"] = m
                    if m == "on":
                        _state["active"] = True
                    elif m == "off":
                        _state["active"] = False

        if "target_temp_c" in data:
            t = int(data["target_temp_c"])
            if 60 <= t <= 100:
                _state["target_temp_c"] = t

        if "auto_refill" in data:
            _state["auto_refill"] = bool(data["auto_refill"])

        if "estop" in data:
            est = bool(data["estop"])
            _state["estop"] = est
            if est:
                _state["mode"] = "off"
                _state["active"] = False

        payload = {
            "ok": True,
            "mode": _state["mode"],
            "target_temp_c": _state["target_temp_c"],
            "active": _state["active"],
            "estop": _state["estop"],
            "auto_refill": _state["auto_refill"],
        }

    web.send_message("state_update", payload)
    return payload


web.expose_api("GET", "/api/state", api_state)
web.expose_api("POST", "/api/control", api_control)

web.on_connect(
    lambda sid: web.send_message("hello", {"message": f"Connected to AutoPot WebUI ({sid})"})
)

App.run()
