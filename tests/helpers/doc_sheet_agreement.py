"""Doc<->sheet agreement, both directions (gts-9o61).

The oracle is the independent Python parse of the document
(``tests.helpers.doc_inspect.floating_actions``, gts-e5cl), never a golden
blessed off the system under test.  The assertion runs in both directions —
every parsed action has exactly one sheet row, and every sheet row for the doc
has a counterpart in the parse — because 2026-08-29 failed in the second
direction: 20 actions the scanner never saw became 20 rows marked *Deleted*,
which no ``input == expected`` corpus check can see.

``compare_doc_sheet`` is pure (records in, problems out) so the failure modes
can be reproduced offline; ``assert_doc_sheet_agreement`` is the live wrapper.
"""
import json

from tests.helpers.doc_inspect import _EMAIL_RE, floating_actions, load_doc

_DELETED = 'deleted'
_SHEET_DEFAULT_STATUS = 'Open'


def _sheet_custom_fields(raw) -> dict[str, str]:
    """Sheet cell -> {name: text}.  ADR-0027 rule 15 values are {text, runs};
    a bare string is tolerated so a pre-rule-15 cell reads without exploding."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {'<unparseable custom_fields cell>': str(raw)}
    if not isinstance(parsed, dict):
        return {'<unparseable custom_fields cell>': str(raw)}
    out = {}
    for name, value in parsed.items():
        if isinstance(value, dict):
            out[name] = value.get('text', '')
        else:
            out[name] = '' if value is None else str(value)
    return out


def _row_field(row, name, default=None):
    value = getattr(row, name, default)
    return default if value is None else value


def compare_doc_sheet(doc_actions, sheet_rows, *, allow_pending: bool = False) -> list[str]:
    """Return every doc<->sheet disagreement as a human-readable line.

    An empty list means agreement.  All disagreements are reported, not just
    the first, so one run names the whole gap instead of one row of it.
    """
    problems: list[str] = []

    for a in doc_actions:
        if a.error:
            problems.append(
                f'doc paragraph {a.body_index}: {a.error} — {a.raw_text[:80]!r}'
            )
        elif a.token is None and a.pending and not allow_pending:
            problems.append(
                f'doc paragraph {a.body_index}: pending (unassigned) trigger with no '
                f'token — {a.raw_text[:80]!r}'
            )

    by_token: dict[str, list] = {}
    for a in doc_actions:
        if a.token:
            by_token.setdefault(a.token, []).append(a)

    rows_by_token: dict[str, list] = {}
    for row in sheet_rows:
        token = _row_field(row, 'action_id', '') or ''
        rows_by_token.setdefault(token, []).append(row)

    for token in sorted(set(by_token) | set(rows_by_token), key=_token_sort_key):
        actions = by_token.get(token, [])
        rows = rows_by_token.get(token, [])

        if actions and not rows:
            problems.append(f'{token}: present in the doc, no sheet row')
            continue
        if rows and not actions:
            states = ', '.join(sorted({(_row_field(r, "sync_status", "") or "-") for r in rows}))
            problems.append(
                f'{token}: sheet row (sync_status={states}) has no doc counterpart'
            )
            continue

        if len(rows) > 1:
            problems.append(f'{token}: {len(rows)} sheet rows for one action')
            continue

        row = rows[0]
        if (_row_field(row, 'sync_status', '') or '').strip().lower() == _DELETED:
            problems.append(
                f'{token}: sheet row marked Deleted while the action is still in the doc'
            )
            continue

        if len({(a.action_text, a.assignee_email, a.status) for a in actions}) > 1:
            problems.append(
                f'{token}: {len(actions)} doc occurrences disagree with each other'
            )
            continue

        problems.extend(_compare_fields(token, actions[0], row))

    return problems


def _compare_fields(token: str, action, row) -> list[str]:
    problems = []

    doc_email = action.assignee_email or ''
    sheet_email = _row_field(row, 'assignee', '') or ''
    if doc_email != sheet_email:
        problems.append(
            f'{token}: assignee_email doc={doc_email!r} sheet={sheet_email!r}'
        )

    # A PERSON chip exports to .docx with the email as its display text when the
    # account name does not resolve, so an email-shaped chip label carries no
    # display-name claim to compare against the sheet's resolved name.
    sheet_name = _row_field(row, 'assignee_name', '') or ''
    doc_name_is_a_claim = bool(action.assignee_name) and not _EMAIL_RE.fullmatch(
        action.assignee_name
    )
    if doc_name_is_a_claim and action.assignee_name != sheet_name:
        problems.append(
            f'{token}: assignee_name doc={action.assignee_name!r} sheet={sheet_name!r}'
        )

    sheet_text = _row_field(row, 'action', '') or ''
    if action.action_text != sheet_text:
        problems.append(
            f'{token}: action_text doc={action.action_text!r} sheet={sheet_text!r}'
        )

    # The doc carrying no (Status) token is agreement with the sheet's default;
    # the oracle reports absence rather than inventing the default itself.
    doc_status = action.status if action.status is not None else _SHEET_DEFAULT_STATUS
    sheet_status = _row_field(row, 'status', '') or _SHEET_DEFAULT_STATUS
    if doc_status != sheet_status:
        problems.append(
            f'{token}: status doc={doc_status!r} sheet={sheet_status!r}'
        )

    doc_fields = action.custom_fields
    sheet_fields = _sheet_custom_fields(_row_field(row, 'custom_fields', ''))
    if doc_fields != sheet_fields:
        problems.append(
            f'{token}: custom_fields doc={doc_fields!r} sheet={sheet_fields!r}'
        )

    return problems


def _token_sort_key(token: str):
    prefix, _, number = token.partition('-')
    try:
        return (prefix, int(number))
    except ValueError:
        return (prefix, 0)


def assert_doc_sheet_agreement(session, doc_id: str | None = None, *,
                               allow_pending: bool = False) -> None:
    """Assert the live doc and the live ActionSheet agree, both directions.

    Read-only: a .docx export and a .xlsx export, no GAS route, no mutation.
    """
    from scn.surfaces import SheetReader
    from tests.helpers.download import download_docx, download_xlsx

    doc_id = doc_id or session.doc_id
    doc_actions = floating_actions(load_doc(download_docx(doc_id)))
    sheet_rows = SheetReader().read(download_xlsx(session.sheet_id), doc_id)

    problems = compare_doc_sheet(doc_actions, sheet_rows, allow_pending=allow_pending)
    if problems:
        raise AssertionError(
            f'doc<->sheet disagreement for {doc_id} '
            f'({len(doc_actions)} doc actions, {len(sheet_rows)} sheet rows):\n  '
            + '\n  '.join(problems)
        )
