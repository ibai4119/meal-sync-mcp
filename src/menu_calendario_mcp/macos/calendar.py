"""Calendar.app service integration built on top of JXA."""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import ConflictError, NotFoundError, ValidationError
from ..models import CalendarEvent, CalendarInfo
from ..utils import validate_time_range
from .applescript import AppleScriptRunner, jxa_program


def _clean_text(value: object) -> str | None:
    """Normalize free-form text inputs, collapsing empty strings to `None`."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(slots=True)
class CalendarService:
    """High-level Calendar.app operations exposed through MCP tools."""

    runner: AppleScriptRunner
    default_calendar_name: str | None = None

    def list_calendars(self) -> list[CalendarInfo]:
        """Return the calendars visible to the current macOS user."""

        payload = {"default_calendar_name": self.default_calendar_name}
        script = jxa_program(
            """
  const calendar = Application('Calendar');
  calendar.includeStandardAdditions = true;
  const result = calendar.calendars().map(c => ({
    name: c.name(),
    color: c.color ? String(c.color()) : null,
    is_default: payload.default_calendar_name ? payload.default_calendar_name === c.name() : false,
  }));
  return toJson(result);
""",
            payload,
        )
        rows = self.runner.run_json(script)
        return [CalendarInfo(**row) for row in rows]

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
