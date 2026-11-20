"""Answer a model's explicit dictionary lookup from the active document and candidate filters."""
from __future__ import annotations

from typing import Any

from .conditional_reviews import documented_dictionary_group
from .query_grounding import dictionary_options


def dictionary_question_text(question: dict[str, str]) -> str:
    return f"{question['table']}.{question['field']} 字段“{question['category']}”的字典取值需要核实。"


def _valid_reference(question: Any) -> bool:
    return (isinstance(question, dict) and question.keys() == {"table", "field", "category"}
            and all(isinstance(value, str) and value.strip() and len(value) <= 2000 for value in question.values()))


def documented_dictionary_entries(question: dict[str, str], table: str,
                                  fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the complete category on one named physical column, without inferring a scope."""
    if not _valid_reference(question) or question["table"] != table:
        return []
    category = question["category"]
    matches = [field for field in fields if field.get("field_name") == question["field"]]
    if len(matches) != 1:
        return []
    return documented_dictionary_group(matches[0], category, dictionary_options)


def dictionary_filter_answers(question: dict[str, str], table: str, fields: list[dict[str, Any]],
                              filters: list[dict[str, Any]]) -> bool:
    """Check whether the confirmed base-column predicate uses exactly the documented codes."""
    entries = documented_dictionary_entries(question, table, fields)
    if not entries or not isinstance(filters, list) or any(not isinstance(item, dict) for item in filters):
        return False
    matches = [item for item in filters if item.get("table", "base") == "base" and item.get("field") == question["field"]]
    if len(matches) != 1 or matches[0].get("confirmed") is not True:
        return False
    item = matches[0]
    if item.get("op") == "eq":
        values = [item.get("value")]
    elif item.get("op") == "in" and isinstance(item.get("value"), list):
        values = item["value"]
    else:
        return False
    if any(type(value) not in (str, int, float) for value in values):
        return False
    return len(values) == len(entries) and set(values) == {entry["value"] for entry in entries}


def apply_dictionary_filter_answers(definition: dict[str, Any], questions: list[dict[str, str]], table: str,
                                    fields: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Drop only a resolved, canonical dictionary review without an existing human explanation."""
    notes = definition.get("uncertainties") or []
    answers = definition.get("uncertainty_resolutions") or []
    if (not notes or not isinstance(questions, list)
            or any(not isinstance(items, list) or any(not isinstance(value, str) for value in items)
                   for items in (notes, answers))):
        return []
    pending, resolved = [], set()
    for question in questions[:100]:
        if not _valid_reference(question):
            continue
        text = dictionary_question_text(question)
        if text not in notes or text in resolved or question in pending:
            continue
        if dictionary_filter_answers(question, table, fields, definition.get("filters") or []):
            resolved.add(text)
        else:
            pending.append(question)
    if resolved:
        retained_notes, retained_answers = [], []
        for index, note in enumerate(notes):
            answer = answers[index] if index < len(answers) else ""
            if note in resolved and not answer.strip():
                continue
            retained_notes.append(note)
            retained_answers.append(answer)
        if len(retained_notes) != len(notes):
            definition["uncertainties"] = retained_notes
            definition["uncertainty_resolutions"] = retained_answers
    return pending
