"""HTML and JSON snippets shared by page renderers."""

from __future__ import annotations

import json


def json_script_payload(payload: object) -> str:
    """Serialize JSON safely for embedding inside a script tag."""
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def render_file_bind_script(bindings: list[tuple[str, str, str]]) -> str:
    """Render JavaScript that mirrors selected file names into status labels."""
    lines = [
        "<script>",
        "  const bindFileState = (inputId, stateId, emptyText) => {",
        "    const input = document.getElementById(inputId);",
        "    const state = document.getElementById(stateId);",
        "    if (!input || !state) return;",
        "",
        "    input.addEventListener(\"change\", () => {",
        "      const file = input.files && input.files[0];",
        "      if (!file) {",
        "        state.textContent = emptyText;",
        "        return;",
        "      }",
        "      state.textContent = `${file.name} • ${(file.size / 1024 / 1024).toFixed(2)} MB`;",
        "    });",
        "  };",
        "",
    ]
    for input_id, state_id, empty_text in bindings:
        lines.append(f'  bindFileState("{input_id}", "{state_id}", "{empty_text}");')
    lines.extend(["</script>"])
    return "\n".join(lines)

