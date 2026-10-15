import re

from maintenance_list import CircularDoublyLinkedList
from models import EQUIPMENT_TYPES, PRIORITIES, MaintenanceTask

TASK_ID_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9-]{0,19}$")
MAX_ESTIMATED_MINUTES = 1440
TEXT_LIMITS = {
    "title": (3, 80),
    "equipment_name": (2, 60),
    "description": (5, 300),
    "assigned_technician": (3, 60),
}
EDITABLE_FIELDS = ("title", "equipment_name", "equipment_type", "description", "priority", "assigned_technician", "estimated_minutes")
INSERT_POSITIONS = ("end", "start", "after")

DEMO_TASKS = [
    {
        "task_id": "DEMO-001",
        "title": "Inspect Application Server Rack A",
        "equipment_name": "Rack A - Application Servers",
        "equipment_type": "SERVER",
        "description": "Revisar ventiladores, LEDs de estado, cableado y temperatura de los servidores del rack A.",
        "priority": "HIGH",
        "assigned_technician": "Laura Gómez",
        "estimated_minutes": 45,
    },
    {
        "task_id": "DEMO-002",
        "title": "Check Cooling Unit 01",
        "equipment_name": "CRAC Unit 01",
        "equipment_type": "COOLING",
        "description": "Verificar temperatura de suministro, filtros, drenaje de condensado y alarmas del equipo de refrigeración.",
        "priority": "CRITICAL",
        "assigned_technician": "Andrés Rojas",
        "estimated_minutes": 60,
    },
    {
        "task_id": "DEMO-003",
        "title": "Test UPS Backup System",
        "equipment_name": "UPS Bank 2",
        "equipment_type": "UPS",
        "description": "Ejecutar prueba de autonomía controlada y revisar el estado de las baterías del UPS.",
        "priority": "CRITICAL",
        "assigned_technician": "Camila Torres",
        "estimated_minutes": 90,
    },
    {
        "task_id": "DEMO-004",
        "title": "Inspect Core Network Switch",
        "equipment_name": "Core Switch SW-01",
        "equipment_type": "NETWORK",
        "description": "Revisar puertos, registros de errores, redundancia de fuentes y uso de CPU del switch principal.",
        "priority": "HIGH",
        "assigned_technician": "Julián Pérez",
        "estimated_minutes": 40,
    },
    {
        "task_id": "DEMO-005",
        "title": "Verify Environmental Sensors",
        "equipment_name": "Sensor Grid Zone B",
        "equipment_type": "SENSOR",
        "description": "Comparar lecturas de temperatura y humedad con un instrumento de referencia y revisar alertas.",
        "priority": "MEDIUM",
        "assigned_technician": "Laura Gómez",
        "estimated_minutes": 30,
    },
    {
        "task_id": "DEMO-006",
        "title": "Review Backup Storage Unit",
        "equipment_name": "Storage Array ST-03",
        "equipment_type": "STORAGE",
        "description": "Revisar estado de discos, alertas RAID y ejecución del último respaldo programado.",
        "priority": "LOW",
        "assigned_technician": "Andrés Rojas",
        "estimated_minutes": 35,
    },
]


class MaintenanceError(Exception):
    status_code = 400

    def __init__(self, message, field=None):
        super().__init__(message)
        self.message = message
        self.field = field


class ValidationError(MaintenanceError):
    status_code = 400


class TaskNotFoundError(MaintenanceError):
    status_code = 404


class DuplicateTaskError(MaintenanceError):
    status_code = 409


class InvalidTransitionError(MaintenanceError):
    status_code = 409


class MaintenanceService:
    def __init__(self, task_list=None):
        self.task_list = task_list if task_list is not None else CircularDoublyLinkedList()

    @classmethod
    def from_snapshot(cls, snapshot):
        service = cls()
        for task_data in (snapshot or {}).get("tasks", []):
            service.task_list.append(MaintenanceTask.from_dict(task_data))
        current_task_id = (snapshot or {}).get("current_task_id")
        if current_task_id:
            service.task_list.select(current_task_id)
        return service

    def to_snapshot(self):
        current = self.task_list.get_current_task()
        return {
            "tasks": [task.to_dict() for task in self.task_list.get_all_tasks()],
            "current_task_id": None if current is None else current.task_id,
        }

    def create_task(self, data, position="end", after_task_id=None, source="USER"):
        if not isinstance(data, dict):
            raise ValidationError("El cuerpo de la solicitud debe ser un objeto JSON.")
        if position not in INSERT_POSITIONS:
            raise ValidationError("La posición de inserción debe ser end, start o after.", "position")
        task_id = self._clean_task_id(data.get("task_id"))
        if self.task_list.find(task_id) is not None:
            raise DuplicateTaskError(f"Ya existe una tarea con el identificador {task_id}.", "task_id")
        fields = self._validate_fields(data, required=True)
        task = MaintenanceTask(task_id=task_id, source=source, **fields)

        if position == "start":
            self.task_list.prepend(task)
        elif position == "after":
            if not after_task_id:
                raise ValidationError("Indica la tarea de referencia para insertar después.", "after_task_id")
            if self.task_list.insert_after(after_task_id, task) is None:
                raise TaskNotFoundError(f"No existe la tarea de referencia {after_task_id}.", "after_task_id")
        else:
            self.task_list.append(task)
        return task

    def get_task(self, task_id):
        node = self.task_list.find(task_id)
        if node is None:
            raise TaskNotFoundError(f"No existe la tarea {task_id}.")
        return node.task

    def get_all_tasks(self, status=None, priority=None):
        return [
            task
            for task in self.task_list.get_all_tasks()
            if (status is None or task.status == status) and (priority is None or task.priority == priority)
        ]

    def update_task(self, task_id, data):
        task = self.get_task(task_id)
        if not isinstance(data, dict):
            raise ValidationError("El cuerpo de la solicitud debe ser un objeto JSON.")
        if "task_id" in data and data["task_id"] != task_id:
            raise ValidationError("El identificador de una tarea no se puede modificar.", "task_id")
        if "status" in data and data["status"] != task.status:
            raise ValidationError("El estado se cambia con las acciones iniciar, completar, bloquear o desbloquear.", "status")
        fields = self._validate_fields(data, required=False)
        if not fields:
            raise ValidationError("No se enviaron campos para actualizar.")
        for name, value in fields.items():
            setattr(task, name, value)
        return task

    def delete_task(self, task_id):
        task = self.task_list.remove(task_id)
        if task is None:
            raise TaskNotFoundError(f"No existe la tarea {task_id}.")
        return task

    def select_task(self, task_id):
        if self.task_list.select(task_id) is None:
            raise TaskNotFoundError(f"No existe la tarea {task_id}.")
        return self.task_list.get_current_task()

    def move_to_next_task(self):
        task = self.task_list.next_task()
        if task is None:
            raise TaskNotFoundError("La ronda de mantenimiento está vacía.")
        return task

    def move_to_previous_task(self):
        task = self.task_list.previous_task()
        if task is None:
            raise TaskNotFoundError("La ronda de mantenimiento está vacía.")
        return task

    def get_current_task(self):
        return self.task_list.get_current_task()

    def start_task(self, task_id):
        task = self.get_task(task_id)
        if task.status == "BLOCKED":
            raise InvalidTransitionError("La tarea está bloqueada. Resuelve el bloqueo antes de iniciarla.")
        if task.status != "PENDING":
            raise InvalidTransitionError("Solo se pueden iniciar tareas pendientes.")
        task.status = "IN_PROGRESS"
        return task

    def complete_task(self, task_id):
        task = self.get_task(task_id)
        if task.status == "BLOCKED":
            raise InvalidTransitionError("No se puede completar una tarea bloqueada sin resolver el bloqueo.")
        if task.status != "IN_PROGRESS":
            raise InvalidTransitionError("Solo se pueden completar tareas en ejecución.")
        task.status = "COMPLETED"
        return task

    def block_task(self, task_id, reason):
        task = self.get_task(task_id)
        reason = reason.strip() if isinstance(reason, str) else ""
        if len(reason) < 5 or len(reason) > 200:
            raise ValidationError("El motivo del bloqueo debe tener entre 5 y 200 caracteres.", "reason")
        if task.status not in ("PENDING", "IN_PROGRESS"):
            raise InvalidTransitionError("Solo se pueden bloquear tareas pendientes o en ejecución.")
        task.status = "BLOCKED"
        task.block_reason = reason
        return task

    def unblock_task(self, task_id):
        task = self.get_task(task_id)
        if task.status != "BLOCKED":
            raise InvalidTransitionError("La tarea no está bloqueada.")
        task.status = "PENDING"
        task.block_reason = ""
        return task

    def load_demo_tasks(self):
        added = []
        for task_data in DEMO_TASKS:
            if self.task_list.find(task_data["task_id"]) is None:
                added.append(self.create_task(task_data, source="DEMO"))
        return added

    def get_maintenance_summary(self):
        tasks = self.task_list.get_all_tasks()
        summary = {
            "total": len(tasks),
            "pending": 0,
            "in_progress": 0,
            "completed": 0,
            "blocked": 0,
            "high_priority": 0,
            "estimated_minutes": 0,
            "demo_tasks": 0,
            "user_tasks": 0,
        }
        for task in tasks:
            summary[task.status.lower()] += 1
            summary["estimated_minutes"] += task.estimated_minutes
            if task.priority in ("HIGH", "CRITICAL"):
                summary["high_priority"] += 1
            summary["demo_tasks" if task.source == "DEMO" else "user_tasks"] += 1
        return summary

    def validate_integrity(self):
        return self.task_list.validate_integrity()

    def get_link_map(self):
        return self.task_list.get_link_map()

    def _clean_task_id(self, raw_task_id):
        if raw_task_id is None or (isinstance(raw_task_id, str) and not raw_task_id.strip()):
            return self._generate_task_id()
        if not isinstance(raw_task_id, str):
            raise ValidationError("El identificador debe ser texto.", "task_id")
        task_id = raw_task_id.strip().upper()
        if not TASK_ID_PATTERN.match(task_id):
            raise ValidationError("El identificador debe tener 1 a 20 caracteres: letras, números o guiones.", "task_id")
        return task_id

    def _generate_task_id(self):
        number = self.task_list.size + 1
        while self.task_list.find(f"MT-{number:03d}") is not None:
            number += 1
        return f"MT-{number:03d}"

    def _validate_fields(self, data, required):
        fields = {}
        for name in EDITABLE_FIELDS:
            if name not in data:
                if required:
                    raise ValidationError(f"El campo {name} es obligatorio.", name)
                continue
            fields[name] = self._validate_field(name, data[name])
        return fields

    def _validate_field(self, name, value):
        if name == "estimated_minutes":
            if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                raise ValidationError("La duración estimada debe ser un número entero.", name)
            try:
                minutes = int(value)
            except ValueError:
                raise ValidationError("La duración estimada debe ser un número entero.", name)
            if isinstance(value, float) and value != minutes:
                raise ValidationError("La duración estimada debe ser un número entero.", name)
            if minutes <= 0 or minutes > MAX_ESTIMATED_MINUTES:
                raise ValidationError(f"La duración debe ser positiva y no superar {MAX_ESTIMATED_MINUTES} minutos.", name)
            return minutes
        if not isinstance(value, str):
            raise ValidationError(f"El campo {name} debe ser texto.", name)
        value = value.strip()
        if name == "priority":
            if value.upper() not in PRIORITIES:
                raise ValidationError("Prioridad inválida. Usa LOW, MEDIUM, HIGH o CRITICAL.", name)
            return value.upper()
        if name == "equipment_type":
            if value.upper() not in EQUIPMENT_TYPES:
                raise ValidationError("Tipo de equipo inválido.", name)
            return value.upper()
        minimum, maximum = TEXT_LIMITS[name]
        if not minimum <= len(value) <= maximum:
            raise ValidationError(f"El campo {name} debe tener entre {minimum} y {maximum} caracteres.", name)
        return value
