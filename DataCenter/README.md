# Data Center Maintenance Rotation

**Caso de estudio:** Rotación de tareas de mantenimiento en un centro de datos
**Asignatura:** Estructuras de Datos — Taller de Listas Circulares Dobles
**Tecnologías:** Python 3 (sin librerías externas), HTML5, CSS3 y JavaScript nativo
**Ejecución:** servidor local (`localhost`)

---

## 1. Descripción del problema

Una empresa administra un centro de datos con servidores, equipos de refrigeración, sistemas UPS, switches de red, unidades de almacenamiento y sensores ambientales. Estos equipos requieren inspecciones periódicas, y el personal técnico las organiza en una **ronda de trabajo**: al terminar la última tarea se vuelve a la primera, y en cualquier momento se puede regresar a la tarea anterior para revisarla de nuevo.

El sistema permite registrar, consultar, insertar, eliminar y recorrer tareas en ambos sentidos, cambiar su estado, validar la integridad de los enlaces y visualizar la estructura.

## 2. Objetivos

**Objetivo general.** Implementar manualmente una lista circular doble en Python y aplicarla a la gestión de una ronda de mantenimiento, con una interfaz web que permita comprobar su comportamiento mediante operaciones reales.

**Objetivos específicos.**

1. Modelar las tareas (`MaintenanceTask`) y los nodos (`MaintenanceNode`) del caso de estudio.
2. Implementar las operaciones de inserción, búsqueda, eliminación y navegación bidireccional en `CircularDoublyLinkedList`.
3. Garantizar las invariantes de la estructura mediante `validate_integrity()` y pruebas con `unittest`.
4. Separar las reglas de negocio (validaciones y estados) en `MaintenanceService`.
5. Exponer las operaciones mediante una API HTTP en Python y consumirlas desde un frontend en español.

## 3. ¿Por qué una lista circular doble?

Una ronda de mantenimiento es, por naturaleza, **cíclica** y **bidireccional**:

- Al terminar la última inspección se continúa con la primera → el último nodo apunta al primero (`tail.next = head`).
- El técnico puede necesitar volver a la tarea anterior → cada nodo conserva el enlace `prev`, y desde la primera se retrocede a la última (`head.prev = tail`).
- Insertar una tarea urgente después de la actual o retirar una tarea solo requiere reajustar los enlaces de los nodos vecinos, sin desplazar los demás elementos.

No es la única estructura posible: también podría resolverse con un arreglo y aritmética modular (`(i + 1) % n`). La lista circular doble resulta **apropiada para este taller** porque representa de forma directa y explícita el recorrido circular en ambos sentidos, y permite estudiar el manejo de enlaces.

## 4. Clases

| Clase | Archivo | Atributos | Responsabilidad |
|---|---|---|---|
| `MaintenanceTask` | `models.py` | `task_id`, `title`, `equipment_name`, `equipment_type`, `description`, `priority`, `status`, `assigned_technician`, `estimated_minutes`, `block_reason`, `source` | Representa una tarea de mantenimiento (objeto de dominio). |
| `MaintenanceNode` | `models.py` | `task`, `next`, `prev` | Nodo de la lista. Guarda **una referencia** a la tarea (no copia sus datos) y los dos enlaces. |
| `CircularDoublyLinkedList` | `maintenance_list.py` | `head`, `current`, `size` | Implementación manual de la estructura: inserción, búsqueda, eliminación, navegación y validación. |
| `MaintenanceService` | `maintenance_service.py` | `task_list` | Reglas de negocio: validación de datos, identificadores únicos, transiciones de estado, resumen. No manipula `next`/`prev`. |
| `JsonStateStore` | `server.py` | `file_path`, `lock` | Guarda y carga la ronda en un archivo JSON local. |

Atributos adicionales de `MaintenanceTask`: `block_reason` (motivo de bloqueo, necesario para la regla "no completar sin resolver el bloqueo") y `source` (`DEMO` o `USER`, para distinguir datos de demostración de los registrados por el usuario).

Valores permitidos:

- **Estados:** `PENDING`, `IN_PROGRESS`, `COMPLETED`, `BLOCKED`.
- **Prioridades:** `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.
- **Tipos de equipo:** `SERVER`, `COOLING`, `UPS`, `NETWORK`, `STORAGE`, `SENSOR`.

## 5. Métodos de `CircularDoublyLinkedList`

| Método | Función | Complejidad |
|---|---|---|
| `is_empty()` | Indica si `head` es `None`. | O(1) |
| `append(task)` | Inserta al final (entre `tail` y `head`). Si la lista está vacía, el nodo se enlaza consigo mismo. | O(1) |
| `prepend(task)` | Inserta al inicio: hace un `append` y mueve `head` al nuevo nodo (en una lista circular, "antes de head" y "después de tail" son la misma posición). | O(1) |
| `insert_after(task_id, task)` | Inserta un nodo nuevo después del nodo con ese identificador. | O(n) por la búsqueda |
| `find(task_id)` | Recorre como máximo `size` nodos y devuelve el nodo o `None`. | O(n) |
| `remove(task_id)` | Desenlaza el nodo; actualiza `head` y `current` si apuntaban a él. | O(n) por la búsqueda |
| `select(task_id)` | Cambia `current` al nodo indicado. | O(n) |
| `next_task()` | `current = current.next`. | O(1) |
| `previous_task()` | `current = current.prev`. | O(1) |
| `get_current_task()` | Devuelve la tarea de `current`. | O(1) |
| `get_all_tasks()` | Recorre desde `head` exactamente `size` veces. | O(n) |
| `get_link_map()` | Describe cada nodo con sus vecinos `prev`/`next` para la visualización. | O(n) |
| `validate_integrity()` | Verifica todas las invariantes (ver sección 7). | O(n) |

Métodos de `MaintenanceService`: `create_task`, `get_task`, `get_all_tasks`, `update_task`, `delete_task`, `select_task`, `move_to_next_task`, `move_to_previous_task`, `get_current_task`, `start_task`, `complete_task`, `block_task`, `unblock_task`, `load_demo_tasks`, `get_maintenance_summary`, `validate_integrity`, `to_snapshot`, `from_snapshot`.

## 6. Enlaces `next` y `prev` y comportamiento circular

```
          ┌──────────────────── prev ─────────────────────┐
          ▼                                               │
      ┌───────┐  next   ┌───────┐  next   ┌───────┐       │
 ┌───▶│  A    │ ──────▶ │  B    │ ──────▶ │  C    │ ──────┘ next (tail → head)
 │    │ head  │ ◀────── │       │ ◀────── │ tail  │
 │    └───────┘  prev   └───────┘  prev   └───────┘
 └───────────────────── prev (head → tail) ───┘
```

- `node.next` apunta al siguiente nodo; `node.prev` al anterior.
- No existe ningún `None` dentro de una lista no vacía: `tail.next is head` y `head.prev is tail`.
- No se necesita un atributo `tail`: siempre es `head.prev`.
- Con un solo nodo: `node.next is node` y `node.prev is node`.

### Ejemplo de recorrido en ambos sentidos

Ronda `A → B → C`, `current = A`:

| Operación | `current` resultante |
|---|---|
| `next_task()` | B |
| `next_task()` | C |
| `next_task()` | **A** (desde la última regresa a la primera) |
| `previous_task()` | **C** (desde la primera llega a la última) |
| `previous_task()` | B |

### Ejemplo de inserción: `insert_after("A", X)` en `A ⇄ B`

```python
new_node.prev = reference          # X.prev = A
new_node.next = reference.next     # X.next = B
reference.next.prev = new_node     # B.prev = X
reference.next = new_node          # A.next = X
```

Resultado: `A ⇄ X ⇄ B`, y `B.next` sigue apuntando a `A` (circularidad intacta). El orden de las asignaciones importa: si se hiciera primero `A.next = X`, se perdería la referencia a `B`.

### Ejemplo de eliminación: `remove("X")` en `A ⇄ X ⇄ B`

```python
node.prev.next = node.next   # A.next = B
node.next.prev = node.prev   # B.prev = A
```

Casos especiales:

- Si `X` era `head`, el nuevo `head` es `X.next`.
- Si `X` era `current`, el nuevo `current` es `X.next` (la siguiente tarea de la ronda).
- Si `X` era el único nodo, la lista queda vacía: `head = current = None`, `size = 0`.
- Si el identificador no existe, la lista no cambia y se devuelve `None`.
- El nodo eliminado queda desenlazado (`next = prev = None`).

## 7. Invariantes verificadas por `validate_integrity()`

1. Lista vacía coherente: `head = None`, `current = None`, `size = 0`.
2. Para cada nodo: `node.next.prev is node` y `node.prev.next is node`.
3. El recorrido con `next` regresa a `head` después de exactamente `size` pasos.
4. El recorrido con `prev` regresa a `head` después de exactamente `size` pasos.
5. `tail.next is head` y `head.prev is tail`.
6. `size` coincide con el número real de nodos.
7. `current` pertenece a la lista.
8. No hay identificadores duplicados.

Los recorridos tienen un límite de `size + 1` pasos, de modo que una lista con enlaces dañados **no produce un ciclo infinito**: la validación termina y reporta la falla (esto también está probado).

## 8. Ventajas y desventajas

**Ventajas**

- Recorrido bidireccional: se avanza con `next` y se retrocede con `prev`.
- Recorrido continuo sin casos especiales en los extremos: no hay `None` al final.
- Inserción y eliminación en O(1) una vez localizado el nodo (por ejemplo, junto a `current`), sin desplazar elementos.
- Acceso inmediato al último nodo mediante `head.prev`.

**Desventajas**

- Mayor complejidad de implementación: cada inserción o eliminación debe actualizar cuatro referencias y considerar casos especiales (lista vacía, un solo nodo, `head`, `current`).
- Uso adicional de memoria: cada nodo guarda dos referencias (`next` y `prev`).
- Exige cuidado al manipular enlaces: un error puede dejar la lista inconsistente o provocar ciclos infinitos en los recorridos.
- La búsqueda por identificador sigue siendo O(n): la estructura no acelera las búsquedas, no ofrece persistencia ni seguridad por sí misma.

## 9. Reglas de negocio (`MaintenanceService`)

| Acción | Estado de origen | Estado resultante |
|---|---|---|
| Iniciar | `PENDING` | `IN_PROGRESS` |
| Completar | `IN_PROGRESS` | `COMPLETED` |
| Bloquear (con motivo de 5 a 200 caracteres) | `PENDING` o `IN_PROGRESS` | `BLOCKED` |
| Resolver bloqueo | `BLOCKED` | `PENDING` |

- No se puede completar ni iniciar una tarea bloqueada sin resolver el bloqueo.
- Los identificadores son únicos (se comparan en mayúsculas). Si no se envía uno, se genera `MT-001`, `MT-002`, etc.
- La duración debe ser un entero entre 1 y 1440 minutos.
- El estado no se cambia desde "Editar": solo mediante las acciones anteriores.

## 10. Persistencia

La ronda se guarda en `data/maintenance_state.json` (se crea automáticamente). En cada solicitud el servidor:

1. Lee el archivo y **reconstruye la lista circular doble** con `append` en el mismo orden, y restaura `current` con `select`.
2. Ejecuta la operación sobre la lista enlazada en memoria.
3. Guarda el resultado de forma atómica (archivo temporal + `os.replace`).

Todo el ciclo leer–operar–guardar se ejecuta dentro de un `threading.Lock`, por lo que dos solicitudes simultáneas no producen actualizaciones contradictorias. El JSON es solo el formato de almacenamiento; la organización y navegación de las tareas dependen siempre de los nodos enlazados.

Para reiniciar la ronda, detén el servidor y borra la carpeta `data/`.

## 11. Datos de demostración

El botón **Cargar demo** agrega seis tareas (`DEMO-001` a `DEMO-006`): *Inspect Application Server Rack A*, *Check Cooling Unit 01*, *Test UPS Backup System*, *Inspect Core Network Switch*, *Verify Environmental Sensors* y *Review Backup Storage Unit*. Solo se agregan las que no existen, así que pulsarlo varias veces no las duplica. Aparecen con la etiqueta **Demo**; las tareas creadas por el usuario aparecen como **Usuario**. Son datos ilustrativos, no registros reales de una empresa.

## 12. API HTTP

Todas las respuestas son JSON con la forma `{"ok": true, "data": ..., "state": {...}}` o `{"ok": false, "error": {"code", "message", "field"}}`.

| Método | Ruta | Operación |
|---|---|---|
| GET | `/api/state` | Estado completo (tareas, enlaces, resumen) |
| GET | `/api/tasks?status=&priority=` | Listar tareas (con filtros opcionales) |
| POST | `/api/tasks` | Crear: `{"task": {...}, "position": "end" \| "start" \| "after", "after_task_id": "..."}` |
| GET | `/api/tasks/current` | Tarea actual |
| GET | `/api/tasks/{id}` | Consultar una tarea |
| PUT | `/api/tasks/{id}` | Actualizar campos editables |
| DELETE | `/api/tasks/{id}` | Eliminar |
| POST | `/api/tasks/{id}/select` | Seleccionar como `current` |
| POST | `/api/tasks/{id}/start` · `/complete` · `/block` · `/unblock` | Cambiar estado (`block` recibe `{"reason": "..."}`) |
| POST | `/api/navigation/next` · `/api/navigation/previous` | Avanzar / retroceder |
| GET | `/api/summary` | Resumen de mantenimiento |
| GET | `/api/integrity` | Ejecutar `validate_integrity()` |
| POST | `/api/demo` | Cargar datos de demostración |

Códigos usados: `200`, `201` (creación), `400` (datos inválidos), `404` (tarea o ruta inexistente), `405` (método no permitido), `409` (identificador duplicado o transición de estado inválida), `413` (cuerpo demasiado grande) y `500` (error interno, sin exponer trazas).

## 13. Interfaz

- **Indicadores:** total, pendientes, en ejecución, completadas, bloqueadas y prioridad alta/crítica (calculados por el backend).
- **Lista circular doble:** cada `MaintenanceNode` es una tarjeta con su ID, título, etiquetas `HEAD`/`TAIL` y los IDs de sus vecinos (`← prev`, `next →`). Las flechas azules continuas representan `next`; las grises punteadas, `prev`. El cierre `tail → head` está rotulado. El nodo actual se resalta. Hay vista **circular** y **lineal** (la lineal se usa automáticamente en pantallas pequeñas). Clic en un nodo = seleccionarlo como `current`. Las flechas ← → del teclado también navegan.
- **Tarea actual:** datos completos, `current.prev` y `current.next`, y acciones Retroceder, Avanzar, Iniciar, Completar, Bloquear / Resolver bloqueo y Editar. Los botones se desactivan cuando la transición no es válida (el backend también lo valida).
- **Verificación de integridad:** ejecuta `validate_integrity()` en el servidor y muestra cada comprobación, los nodos visitados en ambos sentidos y la hora. Si la ronda cambia después, se avisa que el resultado ya no es actual.
- **Administración:** tabla en el orden real de la ronda, filtros por estado y prioridad, detalle, selección, edición y eliminación con confirmación.

## 14. Estructura de carpetas

```text
data-center-maintenance/
├── src/
│   ├── index.html          # Estructura de la interfaz
│   ├── styles.css          # Estilos (tema oscuro azul/gris/negro)
│   └── app.js              # Interacción y llamadas a la API
├── tests/
│   └── test_maintenance.py # Pruebas con unittest
├── models.py               # MaintenanceTask y MaintenanceNode
├── maintenance_list.py     # CircularDoublyLinkedList
├── maintenance_service.py  # MaintenanceService y datos de demostración
├── server.py               # Servidor HTTP local: API + archivos del frontend
├── .gitignore
└── README.md
```

Cambios respecto a la estructura de referencia del enunciado: como el proyecto se ejecuta solo en `localhost`, se eliminaron `vercel.json` y la carpeta `api/`, y la API quedó en `server.py`, que además sirve el frontend. No hay `requirements.txt` porque solo se usa la biblioteca estándar de Python (`http.server`, `json`, `threading`, `unittest`). Se agregó `tests/` para las pruebas.

## 15. Ejecución

Requisito: Python 3.10 o superior (probado con Python 3.13). No se instala ninguna dependencia.

```bash
cd data-center-maintenance
python server.py
```

Abre **http://127.0.0.1:8000** en el navegador. Para usar otro puerto: `PORT=8080 python server.py` (en Windows PowerShell: `$env:PORT=8080; python server.py`). Detén el servidor con `Ctrl + C`.

> El frontend debe abrirse a través del servidor (no con doble clic sobre `index.html`), porque necesita la API.

## 16. Pruebas

```bash
cd data-center-maintenance
python -m unittest discover -s tests -v
```

41 pruebas cubren: lista vacía, primer nodo, inserción al inicio, al final y después de un nodo, navegación en ambos sentidos con circularidad, eliminación del primero, del último, del actual y del único nodo, búsqueda inexistente, operaciones sucesivas, detección de enlaces rotos y de `size` incorrecto, terminación del recorrido con un ciclo dañado, validaciones del servicio, transiciones de estado, carga de demostración sin duplicados, reconstrucción desde JSON y la API (códigos de estado, filtros, persistencia y ocultamiento de errores internos). Las pruebas comprueban referencias reales entre nodos con `assertIs`.

## 17. Limitaciones conocidas

- La persistencia es un archivo JSON local: adecuada para un solo equipo, no para varios servidores.
- No hay autenticación de usuarios.
- En cada solicitud la lista se reconstruye desde el archivo (O(n)); con pocas decenas de tareas es imperceptible.
- La vista circular está pensada para rondas pequeñas o medianas; con muchas tareas la vista lineal es más legible.
- Las fuentes tipográficas se cargan desde Google Fonts; sin internet se usan las fuentes del sistema y la aplicación funciona igual.
