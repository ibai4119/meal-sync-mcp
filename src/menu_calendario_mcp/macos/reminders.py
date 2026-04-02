"""Reminders.app service integration built on top of JXA."""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import ConflictError, NotFoundError, ValidationError
from ..models import ReminderItem, ReminderListInfo
from ..utils import parse_iso_datetime
from .applescript import AppleScriptRunner, jxa_program


def _clean_text(value: object) -> str | None:
    """Normalize free-form text inputs, collapsing empty strings to `None`."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(slots=True)
class RemindersService:
    """High-level Reminders.app operations exposed through MCP tools."""

    runner: AppleScriptRunner
    default_list_name: str | None = None

    def list_lists(self) -> list[ReminderListInfo]:
        """Return reminder lists visible to the current macOS user."""

        payload = {"default_list_name": self.default_list_name}
        script = jxa_program(
            """
  const app = Application('Reminders');
  app.includeStandardAdditions = true;
  const result = app.lists().map(list => ({
    name: list.name(),
    is_default: payload.default_list_name ? list.name() === payload.default_list_name : false,
  }));
  return toJson(result);
""",
            payload,
        )
        rows = self.runner.run_json(script)
        return [ReminderListInfo(**row) for row in rows]

    def list_items(
        self,
        *,
        list_name: str | None = None,
        include_completed: bool = False,
        query: str | None = None,
    ) -> list[ReminderItem]:
        """Return reminder items filtered by list, completion state, and query."""

        payload = {
            "list_name": list_name,
            "include_completed": include_completed,
            "query": query or "",
        }
        script = jxa_program(
            """
  const app = Application('Reminders');
  app.includeStandardAdditions = true;
  const query = String(payload.query || '').toLowerCase();
  const lists = payload.list_name
    ? app.lists.whose({name: payload.list_name})()
    : app.lists();

  if (payload.list_name && lists.length === 0) {
    throw new Error(`Reminder list not found: ${payload.list_name}`);
  }

  const result = [];
  lists.forEach(list => {
    list.reminders().forEach(reminder => {
      const completed = Boolean(reminder.completed());
      if (!payload.include_completed && completed) {
        return;
      }
      const title = reminder.name() || '';
      const notes = reminder.body ? (reminder.body() || '') : '';
      const haystack = `${title}\n${notes}`.toLowerCase();
      if (!query || haystack.includes(query)) {
        result.push({
          reminder_id: reminder.id(),
          list_name: list.name(),
          title,
          is_completed: completed,
          due_iso: reminder.dueDate() ? isoString(reminder.dueDate()) : null,
          notes: notes || null,
        });
      }
    });
  });
  return toJson(result);
""",
            payload,
        )
        rows = self.runner.run_json(script)
        return [ReminderItem(**row) for row in rows]

    def create_item(
        self,
        *,
        title: str,
        list_name: str | None = None,
        due_iso: str | None = None,
        notes: str | None = None,
    ) -> ReminderItem:
        """Create a reminder in the selected or default list."""

        clean_title = _clean_text(title)
        if not clean_title:
            raise ValidationError("'title' is required")
        chosen_list = list_name or self.default_list_name
        if not chosen_list:
            raise ValidationError(
                "'list_name' is required because no default reminder list is configured."
            )
        due_dt = None
        if due_iso is not None:
            due_dt = parse_iso_datetime(due_iso, field_name="due_iso")

        payload = {
            "list_name": chosen_list,
            "title": clean_title,
            "due_iso": due_dt.isoformat() if due_dt else None,
            "notes": notes or "",
        }
        script = jxa_program(
            """
  const app = Application('Reminders');
  app.includeStandardAdditions = true;
  const lists = app.lists.whose({name: payload.list_name})();
  if (lists.length === 0) {
    throw new Error(`Reminder list not found: ${payload.list_name}`);
  }
  const list = lists[0];
  const reminder = app.Reminder({name: payload.title});
  list.reminders.push(reminder);
  if (payload.due_iso !== null) {
    reminder.dueDate = new Date(payload.due_iso);
  }
  if (payload.notes) {
    reminder.body = payload.notes;
  }
  return toJson({
    reminder_id: reminder.id(),
    list_name: list.name(),
    title: reminder.name(),
    is_completed: Boolean(reminder.completed()),
    due_iso: reminder.dueDate() ? isoString(reminder.dueDate()) : null,
    notes: reminder.body ? (reminder.body() || null) : null,
  });
""",
            payload,
        )
        row = self.runner.run_json(script)
        return ReminderItem(**row)

    def complete_item(self, *, reminder_id: str) -> ReminderItem:
        """Mark a reminder as completed and return its resulting state."""

        if not _clean_text(reminder_id):
            raise ValidationError("'reminder_id' is required")
        payload = {"reminder_id": reminder_id}
        script = jxa_program(
            """
  const app = Application('Reminders');
  app.includeStandardAdditions = true;
  let matched = null;
  let matchedList = null;

  app.lists().forEach(list => {
    if (matched) return;
    const results = list.reminders.whose({id: payload.reminder_id})();
    if (results.length > 0) {
      matched = results[0];
      matchedList = list;
    }
  });

  if (!matched) {
    throw new Error(`Reminder not found: ${payload.reminder_id}`);
  }

  if (Boolean(matched.completed())) {
    return toJson({
      reminder_id: matched.id(),
      list_name: matchedList.name(),
      title: matched.name(),
      is_completed: true,
      due_iso: matched.dueDate() ? isoString(matched.dueDate()) : null,
      notes: matched.body ? (matched.body() || null) : null,
    });
  }

  matched.completed = true;
  return toJson({
    reminder_id: matched.id(),
    list_name: matchedList.name(),
    title: matched.name(),
    is_completed: true,
    due_iso: matched.dueDate() ? isoString(matched.dueDate()) : null,
    notes: matched.body ? (matched.body() || null) : null,
  });
""",
            payload,
        )
        row = self.runner.run_json(script)
        if not row.get("is_completed"):
            raise ConflictError(f"Could not complete reminder: {reminder_id}")
        return ReminderItem(**row)
