from __future__ import annotations

import html
import json
import urllib.parse
from datetime import date

from .calendar import _vacation_build_calendar
from .config import (
    VACATION_CALENDAR_DEPARTMENT_DELETE_ROUTE,
    VACATION_CALENDAR_DEPARTMENT_SAVE_ROUTE,
    VACATION_CALENDAR_EMPLOYEE_DELETE_ROUTE,
    VACATION_CALENDAR_EMPLOYEE_SAVE_ROUTE,
    VACATION_CALENDAR_LEAVE_DELETE_ROUTE,
    VACATION_CALENDAR_LEAVE_SAVE_ROUTE,
    VACATION_CALENDAR_ROUTE,
    render_layout,
)
from .dates import (
    VACATION_WEEKDAY_LABELS,
    _vacation_date_label,
    _vacation_date_value,
    _vacation_month_bounds,
    _vacation_month_label,
    _vacation_month_value,
    _vacation_next_month,
    _vacation_parse_date,
    _vacation_parse_month,
)
from .repository import (
    _vacation_db_connection,
    _vacation_fetch_department,
    _vacation_fetch_departments,
    _vacation_fetch_employee,
    _vacation_fetch_employees,
    _vacation_fetch_leave,
    _vacation_fetch_leaves_in_range,
)

def _vacation_route(month_value: str, **params: object) -> str:
    query: dict[str, str] = {}
    if month_value:
        query["month"] = month_value
    for key, value in params.items():
        if value is None:
            continue
        clean_value = str(value).strip()
        if clean_value:
            query[key] = clean_value
    suffix = urllib.parse.urlencode(query)
    return f"{VACATION_CALENDAR_ROUTE}?{suffix}" if suffix else VACATION_CALENDAR_ROUTE

def _vacation_render_calendar_cell(cell: dict) -> str:
    classes = ["vacation-day"]
    if not cell["is_current_month"]:
        classes.append("is-other-month")
    if cell["entries"]:
        classes.append("is-busy")
    if any(load["count"] >= load["max_absent"] for load in cell["loads"]):
        classes.append("is-limited")
    if cell["date"] == date.today():
        classes.append("is-today")

    day_value = _vacation_date_value(cell["date"])
    interactive_attrs = (
        f' data-vacation-day="{html.escape(day_value)}" tabindex="0" role="button"'
        if cell["is_current_month"]
        else ""
    )
    day_badge = ""
    entry_html = "".join(
        f'<button class="vacation-entry" type="button" data-vacation-leave-id="{entry["id"]}" '
        f'data-vacation-day="{html.escape(day_value)}">{html.escape(entry["employee_name"])}</button>'
        for entry in cell["entries"][:3]
    )
    if len(cell["entries"]) > 3:
        entry_html += f'<span class="vacation-entry-more">+{len(cell["entries"]) - 3} további</span>'

    load_html = ""

    return f"""
      <div class="{' '.join(classes)}"{interactive_attrs}>
        <div class="vacation-day-head">
          <span class="vacation-day-number">{cell["date"].day}</span>
          {day_badge}
        </div>
        <div class="vacation-day-list">{entry_html}</div>
        {load_html}
      </div>
    """

def _vacation_render_leave_item(leave_entry: dict, month_value: str) -> str:
    start_day = _vacation_parse_date(leave_entry["start_date"])
    end_day = _vacation_parse_date(leave_entry["end_date"])
    if start_day and end_day:
        range_label = _vacation_date_label(start_day) if start_day == end_day else f"{_vacation_date_label(start_day)} - {_vacation_date_label(end_day)}"
    else:
        range_label = f"{leave_entry['start_date']} - {leave_entry['end_date']}"
    department_label = ", ".join(leave_entry["department_names"]) or "Nincs részleg"
    note_html = f"<span>{html.escape(leave_entry['note'])}</span>" if leave_entry["note"] else ""
    return f"""
      <li class="vacation-item">
        <div class="vacation-item-main">
          <strong>{html.escape(leave_entry["employee_name"])}</strong>
          <span>{html.escape(range_label)} · {html.escape(department_label)}</span>
          {note_html}
        </div>
      </li>
    """

def _vacation_render_employee_item(employee: dict, month_value: str) -> str:
    badges = "".join(
        f'<span class="vacation-mini-badge">{html.escape(name)}</span>'
        for name in employee["department_names"]
    )
    edit_href = _vacation_route(month_value, edit_employee=employee["id"]) + "#employee-form"
    return f"""
      <li class="vacation-item">
        <div class="vacation-item-main">
          <strong>{html.escape(employee["name"])}</strong>
          <span>{len(employee["department_names"])} részleg · {employee["vacation_count"]} rögzített szabadság</span>
          <div class="vacation-mini-badge-row">{badges}</div>
        </div>
        <div class="vacation-item-actions">
          <a class="knowledge-action" href="{edit_href}">Szerkesztés</a>
          <form method="post" action="{VACATION_CALENDAR_EMPLOYEE_DELETE_ROUTE}">
            <input type="hidden" name="employee_id" value="{employee["id"]}" />
            <input type="hidden" name="return_month" value="{html.escape(month_value)}" />
            <button class="knowledge-action is-danger" type="submit">Törlés</button>
          </form>
        </div>
      </li>
    """

def _vacation_render_department_item(department: dict, month_value: str) -> str:
    edit_href = _vacation_route(month_value, edit_department=department["id"]) + "#department-form"
    return f"""
      <li class="vacation-item">
        <div class="vacation-item-main">
          <strong>{html.escape(department["name"])}</strong>
          <span>{department["employee_count"]} kolléga · max. {department["max_absent"]} fő lehet egyszerre szabadságon</span>
        </div>
        <div class="vacation-item-actions">
          <a class="knowledge-action" href="{edit_href}">Szerkesztés</a>
          <form method="post" action="{VACATION_CALENDAR_DEPARTMENT_DELETE_ROUTE}">
            <input type="hidden" name="department_id" value="{department["id"]}" />
            <input type="hidden" name="return_month" value="{html.escape(month_value)}" />
            <button class="knowledge-action is-danger" type="submit">Törlés</button>
          </form>
        </div>
      </li>
    """

def render_vacation_calendar(
    *,
    month_value: str = "",
    message: str = "",
    success: bool = False,
    edit_department_id: int | None = None,
    edit_employee_id: int | None = None,
    edit_leave_id: int | None = None,
    department_draft: dict | None = None,
    employee_draft: dict | None = None,
    leave_draft: dict | None = None,
) -> bytes:
    notice_html = ""
    if message:
        notice_class = "notice-banner success" if success else "notice-banner"
        notice_html = f'<div class="{notice_class}">{html.escape(message)}</div>'

    month_start = _vacation_parse_month(month_value)
    month_value = _vacation_month_value(month_start)
    month_end = _vacation_month_bounds(month_start)[1]

    with _vacation_db_connection() as connection:
        departments = _vacation_fetch_departments(connection)
        employees = _vacation_fetch_employees(connection)
        leaves = _vacation_fetch_leaves_in_range(connection, month_start, month_end)
        edit_department = _vacation_fetch_department(connection, edit_department_id) if edit_department_id else None
        edit_employee = _vacation_fetch_employee(connection, edit_employee_id) if edit_employee_id else None
        edit_leave = _vacation_fetch_leave(connection, edit_leave_id) if edit_leave_id else None

    weeks, limit_day_count = _vacation_build_calendar(month_start, leaves)
    month_label = _vacation_month_label(month_start)
    prev_month_href = _vacation_route(_vacation_month_value(_vacation_next_month(month_start, -1)))
    next_month_href = _vacation_route(_vacation_month_value(_vacation_next_month(month_start, 1)))
    cancel_href = _vacation_route(month_value)
    current_view_url = _vacation_route(
        month_value,
        edit_department=edit_department_id,
        edit_employee=edit_employee_id,
    )

    department_state = {
        "id": str((department_draft or {}).get("id", edit_department["id"] if edit_department else "")),
        "name": str((department_draft or {}).get("name", edit_department["name"] if edit_department else "")),
        "max_absent": str((department_draft or {}).get("max_absent", edit_department["max_absent"] if edit_department else 1)),
    }
    employee_state = {
        "id": str((employee_draft or {}).get("id", edit_employee["id"] if edit_employee else "")),
        "name": str((employee_draft or {}).get("name", edit_employee["name"] if edit_employee else "")),
        "department_ids": [
            int(value)
            for value in (employee_draft or {}).get("department_ids", edit_employee["department_ids"] if edit_employee else [])
        ],
    }
    leave_state = {
        "id": str((leave_draft or {}).get("id", edit_leave["id"] if edit_leave else "")),
        "employee_id": str((leave_draft or {}).get("employee_id", edit_leave["employee_id"] if edit_leave else "")),
        "start_date": str((leave_draft or {}).get("start_date", edit_leave["start_date"] if edit_leave else _vacation_date_value(date.today()))),
        "end_date": str((leave_draft or {}).get("end_date", edit_leave["end_date"] if edit_leave else _vacation_date_value(date.today()))),
        "note": str((leave_draft or {}).get("note", edit_leave["note"] if edit_leave else "")),
    }
    leave_modal_should_open = edit_leave is not None or leave_draft is not None
    leave_modal_date = leave_state["start_date"] or _vacation_date_value(date.today())
    leave_modal_leave_id = leave_state["id"]

    weekday_html = "".join(f'<div class="vacation-weekday">{label}</div>' for label in VACATION_WEEKDAY_LABELS)
    calendar_html = weekday_html + "".join(_vacation_render_calendar_cell(cell) for week in weeks for cell in week)

    employee_list_html = "".join(_vacation_render_employee_item(item, month_value) for item in employees)
    employee_list_html = f'<ul class="vacation-list">{employee_list_html}</ul>' if employee_list_html else '<div class="vacation-empty">Először hozz létre legalább egy részleget, utána add fel a kollégákat.</div>'

    department_list_html = "".join(_vacation_render_department_item(item, month_value) for item in departments)
    department_list_html = f'<ul class="vacation-list">{department_list_html}</ul>' if department_list_html else '<div class="vacation-empty">Még nincs részleg felvéve.</div>'

    department_checks_html = "".join(
        f"""
        <label class="vacation-check">
          <input type="checkbox" name="department_ids" value="{department["id"]}"{" checked" if department["id"] in employee_state["department_ids"] else ""} />
          <span>{html.escape(department["name"])} · max. {department["max_absent"]} fő</span>
        </label>
        """
        for department in departments
    )
    if not department_checks_html:
        department_checks_html = '<div class="vacation-empty">Előbb hozz létre legalább egy részleget.</div>'

    employee_options_html = '<option value="">Válassz kollégát</option>' + "".join(
        f'<option value="{employee["id"]}"{" selected" if str(employee["id"]) == leave_state["employee_id"] else ""}>{html.escape(employee["name"])}</option>'
        for employee in employees
    )
    leave_payload_json = json.dumps(
        [
            {
                "id": item["id"],
                "employeeId": item["employee_id"],
                "employeeName": item["employee_name"],
                "startDate": item["start_date"],
                "endDate": item["end_date"],
                "note": item["note"],
                "departmentNames": item["department_names"],
            }
            for item in leaves
        ],
        ensure_ascii=False,
    ).replace("</", "<\\/")
    employee_cancel_html = f'<a class="vacation-inline-link" href="{cancel_href}#employee-form">Mégse</a>' if employee_state["id"] else ""
    department_cancel_html = f'<a class="vacation-inline-link" href="{cancel_href}#department-form">Mégse</a>' if department_state["id"] else ""
    leave_modal_html = f"""
        <div class="vacation-modal-backdrop" data-vacation-modal aria-hidden="true" hidden>
          <article class="vacation-modal-card" role="dialog" aria-modal="true" aria-labelledby="vacation-modal-title">
            <button class="vacation-modal-close" type="button" data-vacation-close aria-label="Bezárás">×</button>
            <div class="vacation-modal-head">
              <h3 id="vacation-modal-title" data-vacation-modal-title>Új szabadság</h3>
              <p data-vacation-modal-subtitle>Válaszd ki a kollégát és a dátumot.</p>
            </div>

            <div class="vacation-modal-day-panel">
              <div class="vacation-modal-day-summary">
                <strong data-vacation-modal-day-label></strong>
                <span data-vacation-modal-day-meta></span>
              </div>
              <div class="vacation-modal-day-list" data-vacation-day-list></div>
            </div>

            <form class="vacation-form-grid is-split vacation-modal-form" method="post" action="{VACATION_CALENDAR_LEAVE_SAVE_ROUTE}">
              <input type="hidden" name="leave_id" value="{html.escape(leave_state['id'])}" data-vacation-leave-id-field />
              <input type="hidden" name="return_month" value="{html.escape(month_value)}" />
              <div class="vacation-field">
                <label for="modal-leave-employee">Kolléga</label>
                <select id="modal-leave-employee" name="employee_id"{" disabled" if not employees else ""} required>{employee_options_html}</select>
              </div>
              <div class="vacation-field">
                <label for="modal-leave-start">Kezdete</label>
                <input id="modal-leave-start" type="date" name="start_date" value="{html.escape(leave_state['start_date'])}" required />
              </div>
              <div class="vacation-field">
                <label for="modal-leave-end">Vége</label>
                <input id="modal-leave-end" type="date" name="end_date" value="{html.escape(leave_state['end_date'])}" required />
              </div>
              <div class="vacation-field is-full">
                <label for="modal-leave-note">Megjegyzés</label>
                <textarea id="modal-leave-note" name="note" placeholder="Opcionális">{html.escape(leave_state['note'])}</textarea>
              </div>
              <div class="vacation-form-actions is-full vacation-modal-actions">
                <button class="button button-secondary" type="submit" data-vacation-save{" disabled" if not employees else ""}>{'Mentés' if leave_state['id'] else 'Felvétel'}</button>
                <button class="knowledge-action" type="button" data-vacation-new{" hidden" if not employees else ""}>Új szabadság</button>
              </div>
            </form>

            <form class="vacation-modal-delete" method="post" action="{VACATION_CALENDAR_LEAVE_DELETE_ROUTE}" data-vacation-delete-form{" hidden" if not leave_state['id'] else ""}>
              <input type="hidden" name="leave_id" value="{html.escape(leave_state['id'])}" data-vacation-delete-id />
              <input type="hidden" name="return_month" value="{html.escape(month_value)}" />
              <button class="knowledge-action is-danger" type="submit">Szabadság törlése</button>
            </form>
          </article>
        </div>
    """

    employee_panel_html = f"""
      <article class="stack-card vacation-list-card" id="employee-form">
        <div class="vacation-list-head">
          <div>
            <h3>Kollégák</h3>
            <p>Felvétel, szerkesztés, törlés.</p>
          </div>
        </div>
        {employee_list_html}
        <div class="vacation-card-divider"></div>
        <div>
          <h3>{'Kolléga szerkesztése' if employee_state['id'] else 'Új kolléga'}</h3>
          <p>{'Név és részlegek módosítása.' if employee_state['id'] else 'Név és részlegek megadása.'}</p>
        </div>
        <form class="vacation-form-grid" method="post" action="{VACATION_CALENDAR_EMPLOYEE_SAVE_ROUTE}">
          <input type="hidden" name="employee_id" value="{html.escape(employee_state['id'])}" />
          <input type="hidden" name="return_month" value="{html.escape(month_value)}" />
          <div class="vacation-field">
            <label for="employee-name">Név</label>
            <input id="employee-name" type="text" name="name" value="{html.escape(employee_state['name'])}" placeholder="Kiss Péter" required />
          </div>
          <div class="vacation-field">
            <strong>Részlegek</strong>
            <div class="vacation-checkbox-grid">{department_checks_html}</div>
            <span class="vacation-field-hint">Minden kijelölt részleg limitjét figyeli.</span>
          </div>
          <div class="vacation-form-actions">
            <button class="button button-secondary" type="submit">{'Mentés' if employee_state['id'] else 'Felvétel'}</button>
            {employee_cancel_html}
          </div>
        </form>
      </article>
    """
    department_panel_html = f"""
      <article class="stack-card vacation-list-card" id="department-form">
        <div class="vacation-list-head">
          <div>
            <h3>Részlegek</h3>
            <p>Felvétel, szerkesztés, törlés.</p>
          </div>
        </div>
        {department_list_html}
        <div class="vacation-card-divider"></div>
        <div>
          <h3>{'Részleg szerkesztése' if department_state['id'] else 'Új részleg'}</h3>
          <p>Írd be, egyszerre hány fő lehet távol.</p>
        </div>
        <form class="vacation-form-grid" method="post" action="{VACATION_CALENDAR_DEPARTMENT_SAVE_ROUTE}">
          <input type="hidden" name="department_id" value="{html.escape(department_state['id'])}" />
          <input type="hidden" name="return_month" value="{html.escape(month_value)}" />
          <div class="vacation-field">
            <label for="department-name">Részleg neve</label>
            <input id="department-name" type="text" name="name" value="{html.escape(department_state['name'])}" placeholder="Beszerzés" required />
          </div>
          <div class="vacation-field">
            <label for="department-max-absent">Max. szabadságon egyszerre</label>
            <input id="department-max-absent" type="number" min="0" name="max_absent" value="{html.escape(department_state['max_absent'])}" required />
          </div>
          <div class="vacation-form-actions">
            <button class="button button-secondary" type="submit">{'Mentés' if department_state['id'] else 'Felvétel'}</button>
            {department_cancel_html}
          </div>
        </form>
      </article>
    """

    content_html = f"""
      <div
        class="vacation-shell"
        data-current-url="{html.escape(current_view_url)}"
        data-leave-modal-open="{'true' if leave_modal_should_open else 'false'}"
        data-leave-modal-date="{html.escape(leave_modal_date)}"
        data-leave-modal-id="{html.escape(leave_modal_leave_id)}"
      >
        <div class="vacation-calendar-stage" data-vacation-calendar-stage>
          <article class="stack-card vacation-calendar-card">
            <div class="vacation-toolbar">
              <div class="vacation-month-nav">
                <a class="knowledge-action" href="{prev_month_href}">Előző</a>
                <div class="vacation-month-title">{html.escape(month_label)}</div>
                <a class="knowledge-action" href="{next_month_href}">Következő</a>
              </div>

              <form class="vacation-month-form" method="get" action="{VACATION_CALENDAR_ROUTE}">
                <input type="month" name="month" value="{html.escape(month_value)}" />
                <button class="knowledge-action" type="submit">Ugrás</button>
              </form>
            </div>

            <div class="vacation-calendar-wrap">
              <div class="vacation-calendar-grid">{calendar_html}</div>
            </div>
          </article>
          {leave_modal_html}
        </div>

        <div class="vacation-section-grid">
          {employee_panel_html}
          {department_panel_html}
        </div>

        <script type="application/json" data-vacation-leaves>{leave_payload_json}</script>
      </div>
    """

    combined_content_html = content_html
    extra_script = f"""
<script>
(() => {{
  if (window.__vacationCalendarAsyncBound) return;
  window.__vacationCalendarAsyncBound = true;

  const ROOT_ID = "vacation-module-root";
  const ROUTE_PREFIX = "{VACATION_CALENDAR_ROUTE}";
  let requestToken = 0;
  const longDateFormatter = new Intl.DateTimeFormat("hu-HU", {{
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "long",
  }});
  const shortDateFormatter = new Intl.DateTimeFormat("hu-HU", {{
    month: "short",
    day: "numeric",
  }});

  const getRoot = () => document.getElementById(ROOT_ID);
  const getShell = () => getRoot()?.querySelector(".vacation-shell") || null;
  const getStage = () => getRoot()?.querySelector("[data-vacation-calendar-stage]") || null;
  const getModal = () => getRoot()?.querySelector("[data-vacation-modal]") || null;
  const shouldHandleUrl = (url) => url.origin === window.location.origin && url.pathname.startsWith(ROUTE_PREFIX);
  const escapeHtml = (value) =>
    String(value ? "").replace(/[&<>"']/g, (char) => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }})[char] || char);
  const parseVacationDate = (value) => new Date(`${{value}}T12:00:00`);
  const formatLongDate = (value) => {{
    if (!value) return "";
    const parsed = parseVacationDate(value);
    return Number.isNaN(parsed.getTime()) ? value : longDateFormatter.format(parsed);
  }};
  const formatShortDate = (value) => {{
    if (!value) return "";
    const parsed = parseVacationDate(value);
    return Number.isNaN(parsed.getTime()) ? value : shortDateFormatter.format(parsed);
  }};
  const formatLeaveRange = (startDate, endDate) => {{
    if (!startDate || !endDate) return "";
    return startDate === endDate ? formatLongDate(startDate) : `${{formatShortDate(startDate)}} - ${{formatShortDate(endDate)}}`;
  }};
  const readVacationLeaves = () => {{
    const node = getRoot()?.querySelector("[data-vacation-leaves]");
    if (!node) return [];
    try {{
      const parsed = JSON.parse(node.textContent || "[]");
      return Array.isArray(parsed) ? parsed : [];
    }} catch (_error) {{
      return [];
    }}
  }};
  const getDayLeaves = (dayValue) =>
    readVacationLeaves()
      .filter((item) => item.startDate <= dayValue && item.endDate >= dayValue)
      .sort((left, right) => left.employeeName.localeCompare(right.employeeName, "hu"));
  const hasVacationEmployees = () => {{
    const select = getModal()?.querySelector('select[name="employee_id"]');
    if (!(select instanceof HTMLSelectElement)) return false;
    return Array.from(select.options).some((option) => option.value);
  }};
  const closeVacationModal = () => {{
    const modal = getModal();
    if (!modal) return;
    modal.setAttribute("aria-hidden", "true");
    modal.classList.remove("is-open");
    modal.hidden = true;
  }};
  const revealVacationStage = () => {{
    const stage = getStage();
    if (!stage) return;
    stage.scrollIntoView({{ behavior: "smooth", block: "start" }});
  }};
  const renderVacationDayEntries = (modal, dayValue, activeLeaveId) => {{
    const list = modal.querySelector("[data-vacation-day-list]");
    const dayLabel = modal.querySelector("[data-vacation-modal-day-label]");
    const dayMeta = modal.querySelector("[data-vacation-modal-day-meta]");
    if (!(list instanceof HTMLElement) || !(dayLabel instanceof HTMLElement) || !(dayMeta instanceof HTMLElement)) {{
      return;
    }}

    const entries = getDayLeaves(dayValue);
    dayLabel.textContent = formatLongDate(dayValue) || dayValue;
    dayMeta.textContent = entries.length
      ? `${{entries.length}} rögzített szabadság ezen a napon.`
      : "Erre a napra még nincs szabadság felvéve.";

    if (!entries.length) {{
      list.innerHTML = '<div class="vacation-empty">Erre a napra még nincs szabadság.</div>';
      return;
    }}

    list.innerHTML = entries
      .map((entry) => {{
        const departmentLabel = Array.isArray(entry.departmentNames) && entry.departmentNames.length
          ? entry.departmentNames.join(", ")
          : "Nincs részleg";
        const noteHtml = entry.note ? `<small>${{escapeHtml(entry.note)}}</small>` : "";
        return `
          <button
            class="vacation-modal-day-entry${{String(entry.id) === String(activeLeaveId) ? " is-active" : ""}}"
            type="button"
            data-vacation-leave-id="${{entry.id}}"
            data-vacation-day="${{dayValue}}"
          >
            <strong>${{escapeHtml(entry.employeeName)}}</strong>
            <span>${{escapeHtml(formatLeaveRange(entry.startDate, entry.endDate))}} · ${{escapeHtml(departmentLabel)}}</span>
            ${{noteHtml}}
          </button>
        `;
      }})
      .join("");
  }};
  const populateVacationModal = (options = {{}}) => {{
    const modal = getModal();
    if (!modal) return;

    const shell = getShell();
    const leaves = readVacationLeaves();
    const selectedLeave = options.leaveId ? leaves.find((item) => String(item.id) === String(options.leaveId)) || null : null;
    const dayValue = options.dayValue || selectedLeave?.startDate || shell?.dataset.leaveModalDate || "";
    const saveForm = modal.querySelector(".vacation-modal-form");
    const deleteForm = modal.querySelector("[data-vacation-delete-form]");
    const title = modal.querySelector("[data-vacation-modal-title]");
    const subtitle = modal.querySelector("[data-vacation-modal-subtitle]");
    const leaveIdField = modal.querySelector("[data-vacation-leave-id-field]");
    const deleteIdField = modal.querySelector("[data-vacation-delete-id]");
    const saveButton = modal.querySelector("[data-vacation-save]");
    const newButton = modal.querySelector("[data-vacation-new]");
    if (!(saveForm instanceof HTMLFormElement) || !(title instanceof HTMLElement) || !(subtitle instanceof HTMLElement)) {{
      return;
    }}

    modal.dataset.dayValue = dayValue;
    renderVacationDayEntries(modal, dayValue, selectedLeave?.id ? "");

    const employeeField = saveForm.querySelector('select[name="employee_id"]');
    const startField = saveForm.querySelector('input[name="start_date"]');
    const endField = saveForm.querySelector('input[name="end_date"]');
    const noteField = saveForm.querySelector('textarea[name="note"]');
    if (leaveIdField instanceof HTMLInputElement) {{
      leaveIdField.value = selectedLeave ? String(selectedLeave.id) : "";
    }}
    if (deleteIdField instanceof HTMLInputElement) {{
      deleteIdField.value = selectedLeave ? String(selectedLeave.id) : "";
    }}
    if (employeeField instanceof HTMLSelectElement) {{
      employeeField.value = selectedLeave ? String(selectedLeave.employeeId) : "";
    }}
    if (startField instanceof HTMLInputElement) {{
      startField.value = selectedLeave ? selectedLeave.startDate : dayValue;
    }}
    if (endField instanceof HTMLInputElement) {{
      endField.value = selectedLeave ? selectedLeave.endDate : dayValue;
    }}
    if (noteField instanceof HTMLTextAreaElement) {{
      noteField.value = selectedLeave?.note || "";
    }}

    const canSave = hasVacationEmployees();
    if (saveButton instanceof HTMLButtonElement) {{
      saveButton.disabled = !canSave;
      saveButton.textContent = selectedLeave ? "Mentés" : "Felvétel";
    }}
    if (employeeField instanceof HTMLSelectElement) {{
      employeeField.disabled = !canSave;
    }}

    if (selectedLeave) {{
      title.textContent = "Szabadság szerkesztése";
      subtitle.textContent = `${{selectedLeave.employeeName}} szabadsága. Módosíthatod vagy törölheted is.`;
      if (deleteForm instanceof HTMLFormElement) {{
        deleteForm.hidden = false;
      }}
      if (newButton instanceof HTMLButtonElement) {{
        newButton.hidden = !canSave;
      }}
    }} else {{
      title.textContent = "Új szabadság";
      subtitle.textContent = canSave
        ? "Kattints egy napra, és innen rögtön felveheted a szabadságot."
        : "Előbb vegyél fel legalább egy kollégát, utána rögzíthető szabadság.";
      if (deleteForm instanceof HTMLFormElement) {{
        deleteForm.hidden = true;
      }}
      if (newButton instanceof HTMLButtonElement) {{
        newButton.hidden = true;
      }}
    }}

    modal.setAttribute("aria-hidden", "false");
    modal.classList.add("is-open");
    modal.hidden = false;
    revealVacationStage();
  }};
  const syncVacationModalFromRoot = () => {{
    const shell = getShell();
    if (!shell) return;
    if (shell.dataset.leaveModalOpen === "true") {{
      populateVacationModal({{
        dayValue: shell.dataset.leaveModalDate || "",
        leaveId: shell.dataset.leaveModalId || "",
      }});
      return;
    }}
    closeVacationModal();
  }};

  const serializeForm = (form, submitter) => {{
    const formData = new FormData(form);
    if (submitter?.name) {{
      formData.append(submitter.name, submitter.value);
    }}
    const body = new URLSearchParams();
    for (const [key, value] of formData.entries()) {{
      body.append(key, String(value));
    }}
    return body;
  }};

  const updateHistory = (mode, nextRoot, fallbackUrl) => {{
    if (mode === "none") return;
    const nextUrl = nextRoot.querySelector(".vacation-shell")?.dataset.currentUrl || fallbackUrl;
    if (!nextUrl) return;
    if (mode === "replace") {{
      window.history.replaceState({{ vacationCalendar: true }}, "", nextUrl);
      return;
    }}
    window.history.pushState({{ vacationCalendar: true }}, "", nextUrl);
  }};

  const swapRoot = (htmlText, fallbackUrl, historyMode, hash) => {{
    const parser = new DOMParser();
    const documentNode = parser.parseFromString(htmlText, "text/html");
    const nextRoot = documentNode.getElementById(ROOT_ID);
    const currentRoot = getRoot();
    if (!nextRoot || !currentRoot) {{
      throw new Error("A szabadságnaptár nézet nem frissíthető részlegesen.");
    }}
    currentRoot.replaceWith(nextRoot);
    if (documentNode.title) {{
      document.title = documentNode.title;
    }}
    updateHistory(historyMode, nextRoot, fallbackUrl);
    syncVacationModalFromRoot();
    if (hash) {{
      window.requestAnimationFrame(() => {{
        const target = document.querySelector(hash);
        if (target) {{
          target.scrollIntoView({{ behavior: "smooth", block: "start" }});
        }}
      }});
    }}
  }};

  const fetchAndSwap = async (url, options = {{}}, historyMode = "push", hash = "") => {{
    const root = getRoot();
    if (!root) return;

    const requestId = ++requestToken;
    root.classList.add("is-loading");
    root.setAttribute("aria-busy", "true");

    try {{
      const response = await fetch(url, {{
        ...options,
        headers: {{
          Accept: "text/html",
          ...(options.headers || {{}}),
        }},
      }});
      const htmlText = await response.text();
      if (requestId !== requestToken) return;
      swapRoot(htmlText, typeof url === "string" ? url : url.toString(), historyMode, hash);
    }} catch (_error) {{
      window.location.assign(typeof url === "string" ? url : url.toString());
    }} finally {{
      const nextRoot = getRoot();
      if (nextRoot) {{
        nextRoot.classList.remove("is-loading");
        nextRoot.removeAttribute("aria-busy");
      }}
    }}
  }};

  document.addEventListener("click", (event) => {{
    const root = getRoot();
    const target = event.target instanceof Element ? event.target : null;
    if (!root || !target || !root.contains(target)) {{
      return;
    }}

    if (target === getModal()) {{
      event.preventDefault();
      closeVacationModal();
      return;
    }}

    const closeButton = target.closest("[data-vacation-close]");
    if (closeButton) {{
      event.preventDefault();
      closeVacationModal();
      return;
    }}

    const newButton = target.closest("[data-vacation-new]");
    if (newButton) {{
      event.preventDefault();
      populateVacationModal({{ dayValue: getModal()?.dataset.dayValue || getShell()?.dataset.leaveModalDate || "" }});
      return;
    }}

    const leaveButton = target.closest("[data-vacation-leave-id]");
    if (leaveButton) {{
      event.preventDefault();
      populateVacationModal({{
        leaveId: leaveButton.getAttribute("data-vacation-leave-id") || "",
        dayValue:
          leaveButton.getAttribute("data-vacation-day") ||
          leaveButton.closest("[data-vacation-day]")?.getAttribute("data-vacation-day") ||
          "",
      }});
      return;
    }}

    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {{
      return;
    }}

    const dayCell = target.closest("[data-vacation-day]");
    if (dayCell) {{
      event.preventDefault();
      populateVacationModal({{ dayValue: dayCell.getAttribute("data-vacation-day") || "" }});
      return;
    }}

    const link = target.closest("a");
    if (!link || !root.contains(link)) {{
      return;
    }}
    if (link.target && link.target !== "_self") {{
      return;
    }}
    const url = new URL(link.href, window.location.href);
    if (!shouldHandleUrl(url)) {{
      return;
    }}
    event.preventDefault();
    const requestUrl = new URL(url.toString());
    requestUrl.hash = "";
    fetchAndSwap(requestUrl.toString(), {{ method: "GET" }}, "push", url.hash);
  }});

  document.addEventListener("keydown", (event) => {{
    const modal = getModal();
    if (event.key === "Escape" && modal?.classList.contains("is-open")) {{
      event.preventDefault();
      closeVacationModal();
      return;
    }}

    const target = event.target instanceof Element ? event.target : null;
    const dayCell = target?.closest("[data-vacation-day]");
    if (!dayCell || !getRoot()?.contains(dayCell)) {{
      return;
    }}
    if (event.key === "Enter" || event.key === " ") {{
      event.preventDefault();
      populateVacationModal({{ dayValue: dayCell.getAttribute("data-vacation-day") || "" }});
    }}
  }});

  document.addEventListener("submit", (event) => {{
    const root = getRoot();
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !root || !root.contains(form)) {{
      return;
    }}
    const actionUrl = new URL(form.action || window.location.href, window.location.href);
    if (!shouldHandleUrl(actionUrl)) {{
      return;
    }}

    event.preventDefault();
    const method = (form.method || "get").toUpperCase();
    const body = serializeForm(form, event.submitter);

    if (method === "GET") {{
      actionUrl.search = body.toString();
      fetchAndSwap(actionUrl.toString(), {{ method: "GET" }}, "push", actionUrl.hash);
      return;
    }}

    fetchAndSwap(actionUrl.toString(), {{ method: "POST", body }}, "replace");
  }});

  window.addEventListener("popstate", () => {{
    const root = getRoot();
    const currentUrl = new URL(window.location.href);
    if (!root || !shouldHandleUrl(currentUrl)) {{
      return;
    }}
    fetchAndSwap(currentUrl.toString(), {{ method: "GET" }}, "none", currentUrl.hash);
  }});

  syncVacationModalFromRoot();
}})();
</script>"""

    return render_layout(
        heading="Szabadságnaptár",
        lead="Részlegenként követhető szabadságkezelés egy helyen.",
        intro_label="Calendar",
        content_html=combined_content_html,
        side_html="",
        notice_html=notice_html,
        extra_script=extra_script,
        single_column=True,
        module_root_id="vacation-module-root",
    )

