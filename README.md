# meal-sync-mcp

Servidor MCP local para macOS con herramientas de `Calendar`, `Reminders` y `Finder`.

## Qué incluye

- `calendar_list_calendars`
- `calendar_list_sources`
- `calendar_create_calendar`
- `calendar_update_calendar`
- `calendar_delete_calendar`
- `calendar_list_events`
- `calendar_create_event`
- `calendar_update_event`
- `calendar_delete_event`
- `finder_list`
- `finder_get_info`
- `finder_reveal`
- `reminders_list_lists`
- `reminders_list_items`
- `reminders_create_item`
- `reminders_complete_item`

## Requisitos

- macOS
- Python 3.14+
- `uv`
- Permisos de Automatización para controlar `Calendar` y `Finder`

## Desarrollo

```bash
uv sync
UV_CACHE_DIR=.uv-cache uv run pytest -q
```

## Ejecutar el servidor

```bash
uv run menu-calendario-mcp
```

Opcionalmente puedes definir un calendario por defecto:

```bash
export MENU_CALENDARIO_DEFAULT_CALENDAR="ibai.ceberio@gmail.com"
uv run menu-calendario-mcp
```

Si no se define `MENU_CALENDARIO_DEFAULT_CALENDAR`, la herramienta `calendar_create_event`
exigirá `calendar_name` explícito.

También puedes definir una lista por defecto de Recordatorios:

```bash
export MENU_CALENDARIO_DEFAULT_REMINDER_LIST="Recordatorios"
uv run menu-calendario-mcp
```

Si no se define `MENU_CALENDARIO_DEFAULT_REMINDER_LIST`, la herramienta
`reminders_create_item` exigirá `list_name` explícito.

## Configuración MCP en Codex

Ejemplo de configuración local:

```toml
[mcp_servers.menu_calendario]
command = "/opt/homebrew/bin/uv"
args = [
  "--directory",
  "/Users/ibai/Proyectos/meal-sync-mcp",
  "run",
  "menu-calendario-mcp",
]

[mcp_servers.menu_calendario.env]
MENU_CALENDARIO_DEFAULT_CALENDAR = "ibai.ceberio@gmail.com"
MENU_CALENDARIO_DEFAULT_REMINDER_LIST = "Recordatorios"
```

## Notas

- `Calendar` modifica y borra eventos solo por `event_id`.
- `Calendar` expone `calendar_list_sources` para descubrir cuentas o destinos disponibles.
- `Calendar` crea calendarios por nombre y, opcionalmente, por `source_id`.
- `Calendar` renombra y borra calendarios por `calendar_id` opaco devuelto por `calendar_list_calendars`.
- `calendar_list_sources` y la creación con `source_id` requieren acceso completo a Calendars para el proceso que ejecuta el servidor.
- La creación con `source_id` depende de lo que permita esa cuenta en macOS; si la cuenta rechaza crear calendarios, el servidor devuelve el error del sistema.
- Si cambia el conjunto u orden de calendarios entre el listado y la mutación, vuelve a listar antes de reintentar.
- `Reminders` completa recordatorios solo por `reminder_id`.
- El listado de recordatorios devuelve solo pendientes por defecto.
- `Finder` solo admite rutas absolutas.
- `finder_reveal` revela en Finder; no abre el archivo con su aplicación por defecto.
