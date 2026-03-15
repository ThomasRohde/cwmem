"""Evaluate cwmem SKILL.md: token count (minimize) with functional completeness guard."""
import sys
import re
from pathlib import Path

SKILL = Path("skills/cwmem/SKILL.md")

# Required functional markers — if any are missing, the skill is broken.
# Each tuple is (check_name, regex_pattern) tested case-insensitively.
REQUIRED = [
    # Step 0: command resolution
    ("resolve_uv_run", r"uv run cwmem"),
    ("resolve_uvx", r"uvx cwmem"),
    ("resolve_path", r"PATH|on PATH|which cwmem"),
    ("resolve_pyproject", r"pyproject\.toml"),
    # Step 1: init check + setup questions
    ("check_status", r"status"),
    ("init_command", r"init"),
    ("ask_questions", r"\?"),  # at least one question mark (setup questions)
    # Write operations
    ("cmd_add", r"add\b.*--title|--title.*add\b"),
    ("cmd_type_flag", r"--type"),
    ("cmd_event_add", r"event-add"),
    ("cmd_entity_add", r"entity-add"),
    ("cmd_link", r"\blink\b.*source|link\b.*mem-|link\b.*ent-"),
    # Read operations
    ("cmd_search", r"\bsearch\b"),
    ("cmd_list", r"\blist\b"),
    # Sync
    ("sync_export", r"sync export"),
    # Proactive recording
    ("proactive", r"proactiv|offer to record|record.*decision"),
    # Safety
    ("dry_run", r"--dry-run"),
    # Reference to commands.md
    ("ref_commands", r"commands\.md|references/"),
    # YAML frontmatter with name and description
    ("frontmatter_name", r"^name:\s*cwmem"),
    ("frontmatter_desc", r"^description:"),
]

def count_tokens_approx(text: str) -> int:
    """Approximate token count: split on whitespace and punctuation boundaries.

    Rough heuristic: 1 token ≈ 0.75 words for English + code mixed content.
    We use a more accurate split: words + standalone punctuation/symbols.
    """
    # Split into word-like tokens (letters/digits) and punctuation tokens
    tokens = re.findall(r"[a-zA-Z0-9_]+|[^\s]", text)
    return len(tokens)

def main():
    if not SKILL.exists():
        print("SKILL.md not found", file=sys.stderr)
        sys.exit(1)

    text = SKILL.read_text(encoding="utf-8")

    # Strip YAML frontmatter for body checks, but check frontmatter separately
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            body_only = parts[2]
        else:
            frontmatter = ""
            body_only = text
    else:
        frontmatter = ""
        body_only = text

    full_text = text  # check against full text including frontmatter

    # Check all required markers
    missing = []
    for name, pattern in REQUIRED:
        if name.startswith("frontmatter_"):
            search_text = frontmatter
        else:
            search_text = full_text
        if not re.search(pattern, search_text, re.IGNORECASE | re.MULTILINE):
            missing.append(name)

    if missing:
        print(f"FAILED: missing required markers: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    token_count = count_tokens_approx(text)
    print(token_count)

if __name__ == "__main__":
    main()
