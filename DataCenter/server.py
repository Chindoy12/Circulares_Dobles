import json
import logging
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from maintenance_service import MaintenanceError, MaintenanceService
from models import PRIORITIES, STATUSES

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "src")
DEFAULT_DATA_FILE = os.path.join(PROJECT_ROOT, "data", "maintenance_state.json")
HOST = "127.0.0.1"
MAX_BODY_BYTES = 16 * 1024
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
}

logger = logging.getLogger("maintenance_server")


class JsonStateStore:
    def __init__(self, file_path):
        self.file_path = file_path
        self.lock = threading.Lock()

    def load(self):
        if not os.path.exists(self.file_path):
            return {"tasks": [], "current_task_id": None}
        with open(self.file_path, "r", encoding="utf-8") as state_file:
            return json.load(state_file)

    def save(self, snapshot):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        temporary_path = self.file_path + ".tmp"
        with open(temporary_path, "w", encoding="utf-8") as state_file:
            json.dump(snapshot, state_file, ensure_ascii=False, indent=2)
        os.replace(temporary_path, self.file_path)


state_store = JsonStateStore(os.environ.get("MAINTENANCE_DATA_FILE", DEFAULT_DATA_FILE))


class ApiError(Exception):
    def __init__(self, status_code, code, message, field=None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.field = field


def run_operation(operation, mutates):
    with state_store.lock:
        service = MaintenanceService.from_snapshot(state_store.load())
        result = operation(service)
        if mutates:
            state_store.save(service.to_snapshot())
        return result, service


def build_state(service):
    current = service.get_current_task()
    return {
        "tasks": [task.to_dict() for task in service.get_all_tasks()],
        "current_task_id": None if current is None else current.task_id,
        "links": service.get_link_map(),
        "summary": service.get_maintenance_summary(),
    }


def read_filter(query, name, allowed):
    value = query.get(name, [""])[0].upper()
    if value in ("", "ALL"):
        return None
    if value not in allowed:
        raise ApiError(400, "INVALID_FILTER", f"Filtro {name} inválido.", name)
    return value


def get_state(body, query):
    return run_operation(lambda service: None, False)


def list_tasks(body, query):
    status = read_filter(query, "status", STATUSES)
    priority = read_filter(query, "priority", PRIORITIES)
    return run_operation(lambda service: [task.to_dict() for task in service.get_all_tasks(status, priority)], False)


def get_current(body, query):
    return run_operation(lambda service: service.get_current_task().to_dict() if service.get_current_task() else None, False)


def get_summary(body, query):
    return run_operation(lambda service: service.get_maintenance_summary(), False)


def get_integrity(body, query):
    return run_operation(lambda service: service.validate_integrity(), False)


def create_task(body, query):
    payload = body.get("task", body)
    position = body.get("position", "end")
    after_task_id = body.get("after_task_id")
    return run_operation(lambda service: service.create_task(payload, position, after_task_id).to_dict(), True)


def load_demo(body, query):
    return run_operation(lambda service: [task.task_id for task in service.load_demo_tasks()], True)


def move_next(body, query):
    return run_operation(lambda service: service.move_to_next_task().to_dict(), True)


def move_previous(body, query):
    return run_operation(lambda service: service.move_to_previous_task().to_dict(), True)


def get_task(body, query, task_id):
    return run_operation(lambda service: service.get_task(task_id).to_dict(), False)


def update_task(body, query, task_id):
    return run_operation(lambda service: service.update_task(task_id, body).to_dict(), True)


def delete_task(body, query, task_id):
    return run_operation(lambda service: service.delete_task(task_id).to_dict(), True)


def select_task(body, query, task_id):
    return run_operation(lambda service: service.select_task(task_id).to_dict(), True)


def start_task(body, query, task_id):
    return run_operation(lambda service: service.start_task(task_id).to_dict(), True)


def complete_task(body, query, task_id):
    return run_operation(lambda service: service.complete_task(task_id).to_dict(), True)


def block_task(body, query, task_id):
    return run_operation(lambda service: service.block_task(task_id, body.get("reason")).to_dict(), True)


def unblock_task(body, query, task_id):
    return run_operation(lambda service: service.unblock_task(task_id).to_dict(), True)


TASK_ID = r"(?P<task_id>[A-Za-z0-9-]{1,20})"
ROUTES = [
    ("GET", r"/api/state", get_state, 200),
    ("GET", r"/api/tasks", list_tasks, 200),
    ("POST", r"/api/tasks", create_task, 201),
    ("GET", r"/api/tasks/current", get_current, 200),
    ("GET", r"/api/summary", get_summary, 200),
    ("GET", r"/api/integrity", get_integrity, 200),
    ("POST", r"/api/demo", load_demo, 200),
    ("POST", r"/api/navigation/next", move_next, 200),
    ("POST", r"/api/navigation/previous", move_previous, 200),
    ("GET", rf"/api/tasks/{TASK_ID}", get_task, 200),
    ("PUT", rf"/api/tasks/{TASK_ID}", update_task, 200),
    ("DELETE", rf"/api/tasks/{TASK_ID}", delete_task, 200),
    ("POST", rf"/api/tasks/{TASK_ID}/select", select_task, 200),
    ("POST", rf"/api/tasks/{TASK_ID}/start", start_task, 200),
    ("POST", rf"/api/tasks/{TASK_ID}/complete", complete_task, 200),
    ("POST", rf"/api/tasks/{TASK_ID}/block", block_task, 200),
    ("POST", rf"/api/tasks/{TASK_ID}/unblock", unblock_task, 200),
]
COMPILED_ROUTES = [(method, re.compile(f"^{pattern}/?$"), action, status) for method, pattern, action, status in ROUTES]


def parse_body(raw_body):
    if not raw_body:
        return {}
    try:
        body = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ApiError(400, "INVALID_JSON", "El cuerpo de la solicitud no es JSON válido.")
    if not isinstance(body, dict):
        raise ApiError(400, "INVALID_JSON", "El cuerpo de la solicitud debe ser un objeto JSON.")
    return body


def dispatch(method, raw_path, raw_body):
    parsed = urlparse(raw_path)
    query = parse_qs(parsed.query)
    path_matched = False
    for route_method, pattern, action, success_status in COMPILED_ROUTES:
        match = pattern.match(parsed.path)
        if not match:
            continue
        path_matched = True
        if route_method != method:
            continue
        body = parse_body(raw_body) if method in ("POST", "PUT") else {}
        result, service = action(body, query, **match.groupdict())
        return success_status, {"ok": True, "data": result, "state": build_state(service)}
    if path_matched:
        raise ApiError(405, "METHOD_NOT_ALLOWED", "Método HTTP no permitido para esta ruta.")
    raise ApiError(404, "ROUTE_NOT_FOUND", "La ruta solicitada no existe.")


def error_payload(code, message, field=None):
    return {"ok": False, "error": {"code": code, "message": message, "field": field}}


def handle_request(method, raw_path, raw_body):
    try:
        return dispatch(method, raw_path, raw_body)
    except ApiError as error:
        return error.status_code, error_payload(error.code, error.message, error.field)
    except MaintenanceError as error:
        return error.status_code, error_payload(type(error).__name__, error.message, error.field)
    except Exception:
        logger.exception("Unexpected API failure")
        return 500, error_payload("INTERNAL_ERROR", "Ocurrió un error interno. Intenta de nuevo.")


class MaintenanceRequestHandler(BaseHTTPRequestHandler):
    def send_body(self, status_code, content_type, body):
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_api(self, method):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            status_code, payload = 413, error_payload("PAYLOAD_TOO_LARGE", "La solicitud es demasiado grande.")
        else:
            raw_body = self.rfile.read(length) if length else b""
            status_code, payload = handle_request(method, self.path, raw_body)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_body(status_code, "application/json; charset=utf-8", body)

    def do_GET(self):
        entry = STATIC_FILES.get(urlparse(self.path).path)
        if entry is None:
            self.handle_api("GET")
            return
        file_name, content_type = entry
        with open(os.path.join(FRONTEND_DIR, file_name), "rb") as static_file:
            self.send_body(200, content_type, static_file.read())

    def do_POST(self):
        self.handle_api("POST")

    def do_PUT(self):
        self.handle_api("PUT")

    def do_DELETE(self):
        self.handle_api("DELETE")

    def log_message(self, format, *args):
        logger.info("%s - %s", self.address_string(), format % args)


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((HOST, port), MaintenanceRequestHandler)
    print(f"Data Center Maintenance Rotation en http://{HOST}:{port}")
    print(f"Datos guardados en: {state_store.file_path}")
    print("Presiona Ctrl+C para detener el servidor.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
