import json
import pathlib
import subprocess

import pytest


_REPO_ROOT = pathlib.Path(__file__).parent.parent


def _parse_paragraph(text: str):
    script = f"""
const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync('src/FloatingActionParser.js', 'utf8');
const logs = [];
const context = {{
  DocumentApp: {{ ElementType: {{ PERSON: 'PERSON' }} }},
  GasLogger: {{ log: (tag, data) => logs.push({{ tag, data }}) }},
}};
vm.createContext(context);
vm.runInContext(source, context);

const para = {{
  getText: () => {json.dumps(text)},
  getNumChildren: () => 0,
  getChild: () => {{ throw new Error('unexpected child access'); }},
}};
const doc = {{
  getId: () => 'doc-123',
  getBody: () => ({{ getParagraphs: () => [para] }}),
}};

try {{
  const result = context.FloatingActionParser.parse(doc);
  process.stdout.write(JSON.stringify({{ ok: true, result, logs }}));
}} catch (err) {{
  process.stdout.write(JSON.stringify({{
    ok: false,
    message: err.message,
    kind: err.syncErrorKind || '',
    data: err.syncErrorData || null,
    logs,
  }}));
}}
"""
    result = subprocess.run(
        ["node", "-"],
        input=script,
        text=True,
        capture_output=True,
        cwd=str(_REPO_ROOT),
        check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    ("paragraph", "expected_email", "expected_action"),
    [
        ("AI-2 @stu@asyn.com | this is another action", "stu@asyn.com", "this is another action"),
        pytest.param(
            "AI-2 | @stu@asyn.com | this is another action",
            "stu@asyn.com",
            "this is another action",
            marks=pytest.mark.xfail(reason="pipe-delimited assignee not yet supported — GTaskSheet-tis"),
        ),
    ],
)
def test_floating_action_parser_accepts_valid_bare_email_forms(paragraph, expected_email, expected_action):
    parsed = _parse_paragraph(paragraph)

    assert parsed["ok"] is True, parsed
    assert len(parsed["result"]) == 1
    action = parsed["result"][0]
    assert action["assigneeEmail"] == expected_email
    assert action["action"] == expected_action


@pytest.mark.parametrize(
    ("paragraph", "expected_id", "expected_email"),
    [
        ("AI-# @stu@asyn.com | some action", None, "stu@asyn.com"),
        pytest.param(
            "AI-# | @stu@asyn.com | some action",
            None,
            "stu@asyn.com",
            marks=pytest.mark.xfail(reason="pipe-delimited assignee not yet supported — GTaskSheet-tis"),
        ),
    ],
)
def test_floating_action_parser_ai_hash_triggers_auto_assign(paragraph, expected_id, expected_email):
    parsed = _parse_paragraph(paragraph)

    assert parsed["ok"] is True, parsed
    assert len(parsed["result"]) == 1
    action = parsed["result"][0]
    assert action["id"] is None
    assert action["assigneeEmail"] == expected_email


@pytest.mark.parametrize(
    ("paragraph", "expected_email"),
    [
        ("AI-2 stu@asyn.com | some action", "stu@asyn.com"),
        ("AI-2 @stu@asyn.com | some action", "stu@asyn.com"),
    ],
)
def test_floating_action_parser_bare_email_with_and_without_at_prefix(paragraph, expected_email):
    parsed = _parse_paragraph(paragraph)

    assert parsed["ok"] is True, parsed
    assert len(parsed["result"]) == 1
    action = parsed["result"][0]
    assert action["assigneeEmail"] == expected_email
    assert action["assigneeName"] == ""


@pytest.mark.parametrize(
  "paragraph",
  [
    "AI-2 | not-an-email | this is another action",
    "AI-3 | stu@asyn.com | and a third action is here",
  ],
)
def test_floating_action_parser_skips_invalid_assignee_token(paragraph):
  parsed = _parse_paragraph(paragraph)

  assert parsed["ok"] is True, parsed
  assert parsed["result"] == []
  assert parsed["logs"] == [
    {
      "tag": "sync.skip",
      "data": {
        "reason": "invalid-email-token",
        "docId": "doc-123",
        "paragraph": paragraph,
      },
    }
  ]