STATUSES = ("PENDING", "IN_PROGRESS", "COMPLETED", "BLOCKED")
PRIORITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
EQUIPMENT_TYPES = ("SERVER", "COOLING", "UPS", "NETWORK", "STORAGE", "SENSOR")
TASK_SOURCES = ("DEMO", "USER")


class MaintenanceTask:
    def __init__(
        self,
        task_id,
        title,
        equipment_name,
        equipment_type,
        description,
        priority,
        assigned_technician,
        estimated_minutes,
        status="PENDING",
        block_reason="",
        source="USER",
    ):
        self.task_id = task_id
        self.title = title
        self.equipment_name = equipment_name
        self.equipment_type = equipment_type
        self.description = description
        self.priority = priority
        self.status = status
        self.assigned_technician = assigned_technician
        self.estimated_minutes = estimated_minutes
        self.block_reason = block_reason
        self.source = source

    def to_dict(self):
        return {
            "task_id": self.task_id,
            "title": self.title,
            "equipment_name": self.equipment_name,
            "equipment_type": self.equipment_type,
            "description": self.description,
            "priority": self.priority,
            "status": self.status,
            "assigned_technician": self.assigned_technician,
            "estimated_minutes": self.estimated_minutes,
            "block_reason": self.block_reason,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            task_id=data["task_id"],
            title=data["title"],
            equipment_name=data["equipment_name"],
            equipment_type=data["equipment_type"],
            description=data["description"],
            priority=data["priority"],
            assigned_technician=data["assigned_technician"],
            estimated_minutes=data["estimated_minutes"],
            status=data.get("status", "PENDING"),
            block_reason=data.get("block_reason", ""),
            source=data.get("source", "USER"),
        )

    def __repr__(self):
        return f"MaintenanceTask({self.task_id!r}, {self.title!r}, {self.status})"


class MaintenanceNode:
    def __init__(self, task):
        self.task = task
        self.next = None
        self.prev = None

    def __repr__(self):
        return f"MaintenanceNode({self.task.task_id!r})"
