#!/bin/zsh

set -euo pipefail

if [[ $# -lt 3 ]]; then
  cat <<'EOF'
Uso:
  ./create_calendar_event.sh "Titulo" "2026-03-22 10:00" "2026-03-22 11:00" [calendario] [ubicacion] [notas]

Ejemplo:
  ./create_calendar_event.sh "Llamada con cliente" "2026-03-22 10:00" "2026-03-22 11:00" "ibai.ceberio@gmail.com" "Google Meet" "Revisar propuesta"
EOF
  exit 1
fi

title="$1"
start_date="$2"
end_date="$3"
calendar_name="${4:-ibai.ceberio@gmail.com}"
location_text="${5:-}"
notes_text="${6:-}"

parse_datetime() {
  local input="$1"
  if [[ ! "$input" =~ ^([0-9]{4})-([0-9]{2})-([0-9]{2})\ ([0-9]{2}):([0-9]{2})$ ]]; then
    echo "Formato de fecha inválido: $input. Usa YYYY-MM-DD HH:MM" >&2
    exit 1
  fi

  echo "${match[1]} ${match[2]} ${match[3]} ${match[4]} ${match[5]}"
}

start_parts=(${(s: :)$(parse_datetime "$start_date")})
end_parts=(${(s: :)$(parse_datetime "$end_date")})

start_year="${start_parts[1]}"
start_month="${start_parts[2]}"
start_day="${start_parts[3]}"
start_hour="${start_parts[4]}"
start_minute="${start_parts[5]}"

end_year="${end_parts[1]}"
end_month="${end_parts[2]}"
end_day="${end_parts[3]}"
end_hour="${end_parts[4]}"
end_minute="${end_parts[5]}"

osascript <<OSA
on run
  set eventTitle to "$title"
  set calendarName to "$calendar_name"
  set locationText to "$location_text"
  set notesText to "$notes_text"

  tell application "Calendar"
    if not (exists calendar calendarName) then
      error "No existe el calendario: " & calendarName
    end if

    set startDate to current date
    set year of startDate to $start_year
    set month of startDate to $start_month
    set day of startDate to $start_day
    set time of startDate to ($start_hour * hours) + ($start_minute * minutes)

    set endDate to current date
    set year of endDate to $end_year
    set month of endDate to $end_month
    set day of endDate to $end_day
    set time of endDate to ($end_hour * hours) + ($end_minute * minutes)

    tell calendar calendarName
      set newEvent to make new event with properties {summary:eventTitle, start date:startDate, end date:endDate}

      if locationText is not "" then
        set location of newEvent to locationText
      end if

      if notesText is not "" then
        set description of newEvent to notesText
      end if
    end tell
  end tell
end run
OSA

echo "Evento creado en '$calendar_name': $title ($start_date -> $end_date)"
