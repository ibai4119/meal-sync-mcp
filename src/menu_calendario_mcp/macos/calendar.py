"""Calendar.app service integration built on top of JXA."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

from ..errors import ConflictError, NotFoundError, ValidationError
from ..models import CalendarEvent, CalendarInfo, CalendarSourceInfo
from ..utils import validate_time_range
from .applescript import AppleScriptRunner, jxa_program
from .eventkit import EventKitCalendarManager


def _clean_text(value: object) -> str | None:
    """Normalize free-form text inputs, collapsing empty strings to `None`."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _encode_calendar_id(*, index: int, name: str, color: str | None) -> str:
    payload = {"index": index, "name": name, "color": color}
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_calendar_id(calendar_id: str) -> dict[str, Any]:
    clean_calendar_id = _clean_text(calendar_id)
    if not clean_calendar_id:
        raise ValidationError("'calendar_id' is required")
    try:
        raw = base64.urlsafe_b64decode(clean_calendar_id.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("'calendar_id' is invalid") from exc
    if not isinstance(payload, dict):
        raise ValidationError("'calendar_id' is invalid")
    if not isinstance(payload.get("index"), int):
        raise ValidationError("'calendar_id' is invalid")
    if not isinstance(payload.get("name"), str):
        raise ValidationError("'calendar_id' is invalid")
    if payload.get("color") is not None and not isinstance(payload.get("color"), str):
        raise ValidationError("'calendar_id' is invalid")
    return payload


def _calendar_signature(row: dict[str, object]) -> tuple[object, object]:
    return (row.get("name"), row.get("color"))


def _find_inserted_calendar_index(
    before_rows: list[dict[str, object]], after_rows: list[dict[str, object]]
) -> int:
    """Locate the single inserted calendar between two ordered calendar listings."""

    before_signatures = [_calendar_signature(row) for row in before_rows]
    after_signatures = [_calendar_signature(row) for row in after_rows]
    for index in range(len(after_signatures)):
        candidate = after_signatures[:index] + after_signatures[index + 1 :]
        if candidate == before_signatures:
            return index
    raise ConflictError("Calendar creation did not produce an identifiable new calendar.")


@dataclass(slots=True)
class CalendarService:
    """High-level Calendar.app operations exposed through MCP tools."""

    runner: AppleScriptRunner
    default_calendar_name: str | None = None
    eventkit: EventKitCalendarManager | None = None

    def _list_calendar_rows(self) -> list[dict[str, object]]:
        """Return raw calendar rows in Calendar.app order."""

        script = jxa_program(
            """
  const calendar = Application('Calendar');
  calendar.includeStandardAdditions = true;
  const result = calendar.calendars().map(c => ({
    name: c.name(),
    color: c.color ? String(c.color()) : null,
  }));
  return toJson(result);
"""
        )
        rows = self.runner.run_json(script)
        if not isinstance(rows, list):
            raise ValidationError("Calendar listing returned an invalid payload.")
        return rows

    def _calendar_info_from_row(self, row: dict[str, object], *, index: int) -> CalendarInfo:
        """Build a `CalendarInfo` instance with an opaque calendar identifier."""

        name = row["name"]
        color = row.get("color")
        if not isinstance(name, str):
            raise ValidationError("Calendar listing returned an invalid name.")
        if color is not None and not isinstance(color, str):
            raise ValidationError("Calendar listing returned an invalid color.")
        return CalendarInfo(
            calendar_id=_encode_calendar_id(index=index, name=name, color=color),
            name=name,
            color=color,
            is_default=bool(self.default_calendar_name and self.default_calendar_name == name),
        )

    def list_sources(self) -> list[CalendarSourceInfo]:
        """Return EventKit calendar sources available for source-aware calendar creation."""

        manager = self.eventkit or EventKitCalendarManager()
        return manager.list_sources()

    def list_calendars(self) -> list[CalendarInfo]:
        """Return the calendars visible to the current macOS user."""

        rows = self._list_calendar_rows()
        return [self._calendar_info_from_row(row, index=index) for index, row in enumerate(rows)]

    def create_calendar(self, *, name: str, source_id: str | None = None) -> CalendarInfo:
        """Create a new calendar with the given name."""

        clean_name = _clean_text(name)
        if not clean_name:
            raise ValidationError("'name' is required")

        before_rows = self._list_calendar_rows()
        clean_source_id = _clean_text(source_id)
        if clean_source_id:
            manager = self.eventkit or EventKitCalendarManager()
            manager.create_calendar(name=clean_name, source_id=clean_source_id)
        else:
            payload = {"name": clean_name}
            script = jxa_program(
                """
  const app = Application('Calendar');
  app.includeStandardAdditions = true;
  const calendar = app.Calendar({name: payload.name});
  app.calendars.push(calendar);
  return toJson({
    name: calendar.name(),
    color: calendar.color ? String(calendar.color()) : null,
  });
""",
                payload,
            )
            row = self.runner.run_json(script)
            if not isinstance(row, dict):
                raise ValidationError("Calendar creation returned an invalid payload.")
        after_rows = self._list_calendar_rows()
        if len(after_rows) != len(before_rows) + 1:
            raise ConflictError("Calendar creation did not produce a single new calendar.")
        index = _find_inserted_calendar_index(before_rows, after_rows)
        candidate = after_rows[index]
        return self._calendar_info_from_row(candidate, index=index)

    def update_calendar(self, *, calendar_id: str, new_name: str | None = None) -> CalendarInfo:
        """Update mutable fields on an existing calendar identified by `calendar_id`."""

        calendar_ref = _decode_calendar_id(calendar_id)
        clean_new_name = _clean_text(new_name)
        if clean_new_name is None:
            raise ValidationError("At least one field must be provided to update a calendar.")

        payload = {
            "calendar_index": calendar_ref["index"],
            "expected_name": calendar_ref["name"],
            "expected_color": calendar_ref["color"],
            "new_name": clean_new_name,
        }
        script = jxa_program(
            """
  const app = Application('Calendar');
  app.includeStandardAdditions = true;
  const calendars = app.calendars();
  if (payload.calendar_index < 0 || payload.calendar_index >= calendars.length) {
    throw new Error('Calendar not found for the provided calendar_id');
  }
  const calendar = calendars[payload.calendar_index];
  const currentName = calendar.name();
  const currentColor = calendar.color ? String(calendar.color()) : null;
  if (currentName !== payload.expected_name || currentColor !== payload.expected_color) {
    throw new Error('Calendar no longer matches the provided calendar_id. Refresh the calendar list and try again.');
  }
  if (payload.new_name !== null) {
    calendar.name = payload.new_name;
  }
  return toJson({
    name: calendar.name(),
    color: calendar.color ? String(calendar.color()) : null,
  });
""",
            payload,
        )
        row = self.runner.run_json(script)
        if not isinstance(row, dict):
            raise ValidationError("Calendar update returned an invalid payload.")
        refreshed_rows = self._list_calendar_rows()
        target_index = calendar_ref["index"]
        if target_index >= len(refreshed_rows):
            raise NotFoundError("Updated calendar not found after mutation.")
        return self._calendar_info_from_row(refreshed_rows[target_index], index=target_index)

    def delete_calendar(self, *, calendar_id: str) -> dict[str, object]:
        """Delete a calendar by its opaque `calendar_id`."""

        calendar_ref = _decode_calendar_id(calendar_id)

        payload = {
            "calendar_index": calendar_ref["index"],
            "expected_name": calendar_ref["name"],
            "expected_color": calendar_ref["color"],
        }
        script = jxa_program(
            """
  const app = Application('Calendar');
  app.includeStandardAdditions = true;
  const calendars = app.calendars();
  if (payload.calendar_index < 0 || payload.calendar_index >= calendars.length) {
    throw new Error('Calendar not found for the provided calendar_id');
  }
  const calendar = calendars[payload.calendar_index];
  const currentName = calendar.name();
  const currentColor = calendar.color ? String(calendar.color()) : null;
  if (currentName !== payload.expected_name || currentColor !== payload.expected_color) {
    throw new Error('Calendar no longer matches the provided calendar_id. Refresh the calendar list and try again.');
  }
  const temporaryName = `__codex_delete__${ObjC.unwrap($.NSUUID.UUID.UUIDString)}`;
  calendar.name = temporaryName;
  app.calendars.byName(temporaryName).delete();
  return toJson({deleted: true, calendar_id: payload.calendar_index});
""",
            payload,
        )
        row = self.runner.run_json(script)
        if not row.get("deleted"):
            raise NotFoundError("Calendar not found for the provided calendar_id")
        return row

    def list_events(
        self,
        *,
        start_iso: str,
        end_iso: str,
        calendar_name: str | None = None,
        query: str | None = None,
    ) -> list[CalendarEvent]:
        """Return events that overlap the requested time range."""

        start, end = validate_time_range(start_iso, end_iso)
        payload = {
            "calendar_name": calendar_name,
            "query": query or "",
            "start_iso": start.isoformat(),
            "end_iso": end.isoformat(),
        }
        script = jxa_program(
            """
  const app = Application('Calendar');
  app.includeStandardAdditions = true;
  const startDate = new Date(payload.start_iso);
  const endDate = new Date(payload.end_iso);
  const query = String(payload.query || '').toLowerCase();
  const calendars = payload.calendar_name
    ? app.calendars.whose({name: payload.calendar_name})()
    : app.calendars();

  if (payload.calendar_name && calendars.length === 0) {
    throw new Error(`Calendar not found: ${payload.calendar_name}`);
  }

  const events = [];
  calendars.forEach(cal => {
    cal.events().forEach(event => {
      const eventStart = event.startDate();
      const eventEnd = event.endDate();
      if (!(eventStart < endDate && eventEnd > startDate)) {
        return;
      }
      const title = event.summary() || '';
      const notes = event.description() || '';
      const haystack = `${title}\n${notes}`.toLowerCase();
      if (!query || haystack.includes(query)) {
        events.push({
          event_id: event.id(),
          calendar_name: cal.name(),
          title,
          start_iso: isoString(event.startDate()),
          end_iso: isoString(event.endDate()),
          all_day: Boolean(event.alldayEvent()),
          location: event.location() || null,
          notes: notes || null,
        });
      }
    });
  });
  return toJson(events);
""",
            payload,
        )
        rows = self.runner.run_json(script)
        return [CalendarEvent(**row) for row in rows]

    def create_event(
        self,
        *,
        title: str,
        start_iso: str,
        end_iso: str,
        calendar_name: str | None = None,
        all_day: bool = False,
        location: str | None = None,
        notes: str | None = None,
    ) -> CalendarEvent:
        """Create a new event in the selected or default calendar."""

        start, end = validate_time_range(start_iso, end_iso)
        title = _clean_text(title)
        if not title:
            raise ValidationError("'title' is required")
        chosen_calendar = calendar_name or self.default_calendar_name
        if not chosen_calendar:
            raise ValidationError(
                "'calendar_name' is required because no default calendar is configured."
            )

        payload = {
            "calendar_name": chosen_calendar,
            "title": title,
            "start_iso": start.isoformat(),
            "end_iso": end.isoformat(),
            "all_day": all_day,
            "location": location or "",
            "notes": notes or "",
        }
        script = jxa_program(
            """
  const app = Application('Calendar');
  app.includeStandardAdditions = true;
  const calendars = app.calendars.whose({name: payload.calendar_name})();
  if (calendars.length === 0) {
    throw new Error(`Calendar not found: ${payload.calendar_name}`);
  }
  const cal = calendars[0];
  const event = app.Event({
    summary: payload.title,
    startDate: new Date(payload.start_iso),
    endDate: new Date(payload.end_iso),
    alldayEvent: Boolean(payload.all_day),
  });
  cal.events.push(event);
  if (payload.location) {
    event.location = payload.location;
  }
  if (payload.notes) {
    event.description = payload.notes;
  }
  return toJson({
    event_id: event.id(),
    calendar_name: cal.name(),
    title: event.summary(),
    start_iso: isoString(event.startDate()),
    end_iso: isoString(event.endDate()),
    all_day: Boolean(event.alldayEvent()),
    location: event.location() || null,
    notes: event.description() || null,
  });
""",
            payload,
        )
        row = self.runner.run_json(script)
        return CalendarEvent(**row)

    def update_event(
        self,
        *,
        event_id: str,
        title: str | None = None,
        start_iso: str | None = None,
        end_iso: str | None = None,
        all_day: bool | None = None,
        location: str | None = None,
        notes: str | None = None,
    ) -> CalendarEvent:
        """Update mutable fields on an existing event identified by `event_id`."""

        if not any(v is not None for v in [title, start_iso, end_iso, all_day, location, notes]):
            raise ValidationError("At least one field must be provided to update an event.")
        start_dt = end_dt = None
        if start_iso is not None and end_iso is not None:
            start_dt, end_dt = validate_time_range(start_iso, end_iso)
        elif start_iso is not None or end_iso is not None:
            raise ConflictError("'start_iso' and 'end_iso' must be provided together when updating dates.")

        payload = {
            "event_id": event_id,
            "title": title,
            "start_iso": start_dt.isoformat() if start_dt else None,
            "end_iso": end_dt.isoformat() if end_dt else None,
            "all_day": all_day,
            "location": location,
            "notes": notes,
        }
        script = jxa_program(
            """
  const app = Application('Calendar');
  const calendars = app.calendars();
  let matched = null;
  let matchedCalendar = null;

  calendars.forEach(cal => {
    if (matched) return;
    const results = cal.events.whose({id: payload.event_id})();
    if (results.length > 0) {
      matched = results[0];
      matchedCalendar = cal;
    }
  });

  if (!matched) {
    throw new Error(`Event not found: ${payload.event_id}`);
  }

  if (payload.title !== null) matched.summary = payload.title;
  if (payload.start_iso !== null) matched.startDate = new Date(payload.start_iso);
  if (payload.end_iso !== null) matched.endDate = new Date(payload.end_iso);
  if (payload.all_day !== null) matched.alldayEvent = Boolean(payload.all_day);
  if (payload.location !== null) matched.location = payload.location;
  if (payload.notes !== null) matched.description = payload.notes;

  return toJson({
    event_id: matched.id(),
    calendar_name: matchedCalendar.name(),
    title: matched.summary(),
    start_iso: isoString(matched.startDate()),
    end_iso: isoString(matched.endDate()),
    all_day: Boolean(matched.alldayEvent()),
    location: matched.location() || null,
    notes: matched.description() || null,
  });
""",
            payload,
        )
        row = self.runner.run_json(script)
        return CalendarEvent(**row)

    def delete_event(self, *, event_id: str) -> dict[str, object]:
        """Delete an event by its Calendar identifier."""

        payload = {"event_id": event_id}
        script = jxa_program(
            """
  const app = Application('Calendar');
  const calendars = app.calendars();
  let matched = null;

  calendars.forEach(cal => {
    if (matched) return;
    const results = cal.events.whose({id: payload.event_id})();
    if (results.length > 0) {
      matched = results[0];
    }
  });
  if (!matched) {
    throw new Error(`Event not found: ${payload.event_id}`);
  }
  matched.delete();
  return toJson({deleted: true, event_id: payload.event_id});
""",
            payload,
        )
        row = self.runner.run_json(script)
        if not row.get("deleted"):
            raise NotFoundError(f"Event not found: {event_id}")
        return row
