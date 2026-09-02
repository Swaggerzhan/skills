#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


HEADER_BEGIN = "@UT-HEADER-BEGIN"
HEADER_END = "@UT-HEADER-END"
RETIRED_CASE_ANCHORS = ("@UT-CASE-BEGIN", "@UT-CASE-END")

TIERS = {"solitary", "sociable", "integration"}
CATEGORIES = {"Positive", "Recovery", "Negative"}
DEPENDENCY_TYPES = {"mock", "inject"}
BRANCH_PREFIXES = {
    "Positive": "BP",
    "Recovery": "BR",
    "Negative": "BN",
}

HEADER_FIELDS = {"Unit", "Tier", "Deps", "Desc", "Args"}
HEAD_FIELDS = {"Detail", "Setup"}
RETIRED_FIELDS = {
    "Case": "the case name comes from the TEST_F/TEST_P below",
    "Status": "the status is derived from the presence of the TEST_F/TEST_P",
}

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
FIELD_RE = re.compile(r"^\s*@([A-Za-z][A-Za-z0-9-]*):\s*(.*)$")
HEAD_FIELD_RE = re.compile(r"^@([A-Za-z][A-Za-z0-9-]*):\s*(.*)$")
BRANCH_RE = re.compile(r"^\s*\*\s+Branch\s+(\S+):\s*(.*)$")
CASE_REF_RE = re.compile(r"^\s*\*\s+Case:\s*(.*?)\s*$")
CATEGORY_BEGIN_RE = re.compile(r"^\s*@Category-BEGIN:\s*(\S+)\s*$")
CATEGORY_END_RE = re.compile(r"^\s*@Category-END:\s*(\S+)\s*$")
DEPENDENCY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.-]*)\(([^()]+)\)$")
TEST_MACRO_RE = re.compile(
    r"\b(TEST_F|TEST_P)\s*\(\s*"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*,\s*"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*\)",
    re.MULTILINE,
)


@dataclass
class Diagnostic:
    line: int
    message: str


@dataclass
class HumanText:
    items: list[str] = field(default_factory=list)

    def append(self, value: str) -> None:
        value = value.strip()
        if not value:
            return
        if value.startswith("- "):
            item = value[2:].strip()
            if item:
                self.items.append(item)
            return
        if self.items:
            self.items[-1] = f"{self.items[-1]} {value}"
        else:
            self.items.append(value)

    def as_text(self) -> str:
        return " ".join(self.items)


@dataclass
class ParsedField:
    name: str
    line: int
    text: HumanText = field(default_factory=HumanText)


@dataclass
class Dependency:
    name: str
    kind: str


@dataclass
class CaseRef:
    name: Optional[str]
    line: int
    category: str
    branch_id: Optional[str]
    detail: HumanText = field(default_factory=HumanText)

    @property
    def placeholder(self) -> bool:
        return self.name is None


@dataclass
class Branch:
    branch_id: str
    line: int
    description: HumanText = field(default_factory=HumanText)
    cases: list[CaseRef] = field(default_factory=list)


@dataclass
class Category:
    name: str
    line: int
    direct_cases: list[CaseRef] = field(default_factory=list)
    branches: list[Branch] = field(default_factory=list)


@dataclass
class Header:
    start_line: int
    end_line: int
    fields: dict[str, ParsedField] = field(default_factory=dict)
    categories: list[Category] = field(default_factory=list)


@dataclass
class CaseHead:
    line: int
    fields: dict[str, ParsedField] = field(default_factory=dict)

    def value(self, name: str) -> Optional[str]:
        parsed = self.fields.get(name)
        if parsed is None:
            return None
        return parsed.text.as_text()


@dataclass
class TestMacro:
    kind: str
    unit: str
    case_name: str
    line: int
    head: Optional[CaseHead] = None


@dataclass
class Document:
    path: Path
    text: str
    lines: list[str]
    header: Optional[Header]
    macros: list[TestMacro]
    diagnostics: list[Diagnostic]
    dependencies: list[Dependency] = field(default_factory=list)

    def add_error(self, line: int, message: str) -> None:
        self.diagnostics.append(Diagnostic(line, message))


def comment_payload(line: str) -> Optional[str]:
    match = re.match(r"^\s*//(.*)$", line)
    if match is None:
        return None
    payload = match.group(1).rstrip()
    if payload.startswith(" "):
        payload = payload[1:]
    return payload


def machine_value(value: str) -> str:
    return re.split(r"\s+//", value, maxsplit=1)[0].strip()


class AnnotationParser:
    def __init__(self, path: Path, text: str):
        self._path = path
        self._text = text
        self._lines = text.splitlines()
        self._diagnostics: list[Diagnostic] = []
        self._head_block_lines: set[int] = set()

    def parse(self) -> Document:
        header_spans = self._find_blocks(HEADER_BEGIN, HEADER_END, "HEADER")

        if len(header_spans) != 1:
            line = header_spans[1][0] if len(header_spans) > 1 else 1
            self._add_error(line, "expected exactly one HEADER block")

        header = self._parse_header(*header_spans[0]) if header_spans else None
        macros = self._parse_test_macros()
        self._parse_heads(header, macros)
        self._check_stray_annotations(header)

        return Document(
            path=self._path,
            text=self._text,
            lines=self._lines,
            header=header,
            macros=macros,
            diagnostics=self._diagnostics,
        )

    def _add_error(self, line: int, message: str) -> None:
        self._diagnostics.append(Diagnostic(line, message))

    def _inside_header(self, header: Optional[Header], line_number: int) -> bool:
        return header is not None and header.start_line <= line_number <= header.end_line

    def _find_blocks(
        self, begin_marker: str, end_marker: str, block_name: str
    ) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        open_line: Optional[int] = None

        for index, line in enumerate(self._lines, start=1):
            payload = comment_payload(line)
            if payload is None:
                continue
            token = payload.strip()

            for marker in (begin_marker, end_marker):
                if marker in token and token != marker:
                    self._add_error(index, f"{marker} must occupy its own comment line")

            if token == begin_marker:
                if open_line is not None:
                    self._add_error(index, f"nested {block_name} block")
                else:
                    open_line = index
                continue

            if token != end_marker:
                continue

            if open_line is None:
                self._add_error(index, f"{block_name} end anchor has no begin anchor")
                continue
            spans.append((open_line, index))
            open_line = None

        if open_line is not None:
            self._add_error(open_line, f"{block_name} block has no end anchor")
        return spans

    def _parse_header(self, start_line: int, end_line: int) -> Header:
        header = Header(start_line, end_line)
        current_category: Optional[Category] = None
        current_branch: Optional[Branch] = None
        continuation: Optional[HumanText] = None

        for line_number in range(start_line + 1, end_line):
            payload = comment_payload(self._lines[line_number - 1])
            if payload is None:
                self._add_error(line_number, "HEADER content must use line comments")
                continuation = None
                continue

            stripped = payload.strip()
            if not stripped:
                continuation = None
                continue

            category_begin = CATEGORY_BEGIN_RE.match(payload)
            if category_begin:
                name = category_begin.group(1)
                if current_category is not None:
                    self._add_error(line_number, "nested category block")
                current_category = Category(name, line_number)
                header.categories.append(current_category)
                current_branch = None
                continuation = None
                continue

            category_end = CATEGORY_END_RE.match(payload)
            if category_end:
                name = category_end.group(1)
                if current_category is None:
                    self._add_error(line_number, "category end anchor has no begin anchor")
                elif current_category.name != name:
                    self._add_error(
                        line_number,
                        f"category end '{name}' does not match '{current_category.name}'",
                    )
                current_category = None
                current_branch = None
                continuation = None
                continue

            branch_match = BRANCH_RE.match(payload)
            if branch_match:
                if current_category is None:
                    self._add_error(line_number, "branch must be inside a category")
                    continuation = None
                    continue
                current_branch = Branch(branch_match.group(1), line_number)
                current_branch.description.append(branch_match.group(2))
                current_category.branches.append(current_branch)
                continuation = current_branch.description
                continue

            case_match = CASE_REF_RE.match(payload)
            if case_match:
                if current_category is None:
                    self._add_error(line_number, "case must be inside a category")
                    continuation = None
                    continue
                raw_name = machine_value(case_match.group(1))
                name = None if raw_name == "(todo)" else raw_name
                case_ref = CaseRef(
                    name=name,
                    line=line_number,
                    category=current_category.name,
                    branch_id=current_branch.branch_id if current_branch else None,
                )
                if current_branch is None:
                    current_category.direct_cases.append(case_ref)
                else:
                    current_branch.cases.append(case_ref)
                continuation = case_ref.detail
                continue

            field_match = FIELD_RE.match(payload)
            if field_match:
                name = field_match.group(1)
                if name not in HEADER_FIELDS:
                    self._add_error(line_number, f"unknown HEADER field '@{name}'")
                    continuation = None
                    continue
                if current_category is not None:
                    self._add_error(line_number, f"@{name} must be outside categories")
                if name in header.fields:
                    self._add_error(line_number, f"duplicate HEADER field '@{name}'")
                    continuation = None
                    continue
                parsed = ParsedField(name, line_number)
                parsed.text.append(field_match.group(2))
                header.fields[name] = parsed
                continuation = parsed.text if name in {"Desc", "Args"} else None
                continue

            if stripped.startswith("@") or stripped.startswith("*"):
                self._add_error(line_number, f"unknown HEADER marker '{stripped}'")
                continuation = None
                continue

            if not payload[:1].isspace():
                self._add_error(line_number, "orphan HEADER continuation line")
                continuation = None
                continue
            if continuation is None:
                self._add_error(line_number, "orphan HEADER continuation line")
                continue
            continuation.append(stripped)

        if current_category is not None:
            self._add_error(current_category.line, "category block has no end anchor")
        return header

    def _parse_test_macros(self) -> list[TestMacro]:
        sanitized = sanitize_cpp(self._text)
        macros: list[TestMacro] = []
        for match in TEST_MACRO_RE.finditer(sanitized):
            macros.append(
                TestMacro(
                    kind=match.group(1),
                    unit=match.group(2),
                    case_name=match.group(3),
                    line=sanitized.count("\n", 0, match.start()) + 1,
                )
            )
        return macros

    def _parse_heads(self, header: Optional[Header], macros: list[TestMacro]) -> None:
        for macro in macros:
            block: list[tuple[int, str]] = []
            line_number = macro.line - 1
            while line_number >= 1:
                if self._inside_header(header, line_number):
                    break
                payload = comment_payload(self._lines[line_number - 1])
                if payload is None:
                    break
                block.append((line_number, payload))
                line_number -= 1
            block.reverse()
            self._head_block_lines.update(line for line, _ in block)
            if block:
                self._parse_head_block(macro, block)

    def _parse_head_block(self, macro: TestMacro, block: list[tuple[int, str]]) -> None:
        head = CaseHead(block[0][0])
        continuation: Optional[HumanText] = None

        for line_number, payload in block:
            stripped = payload.strip()
            if not stripped:
                continuation = None
                continue

            if payload[:1].isspace():
                if continuation is not None:
                    continuation.append(stripped)
                continue

            field_match = HEAD_FIELD_RE.match(payload)
            if field_match is None:
                continuation = None
                continue

            name = field_match.group(1)
            if name in RETIRED_FIELDS:
                self._add_error(
                    line_number, f"'@{name}' is retired: {RETIRED_FIELDS[name]}"
                )
                continuation = None
                continue
            if name not in HEAD_FIELDS:
                self._add_error(line_number, f"unknown case field '@{name}'")
                continuation = None
                continue
            if name in head.fields:
                self._add_error(line_number, f"duplicate case field '@{name}'")
                continuation = None
                continue
            parsed = ParsedField(name, line_number)
            parsed.text.append(field_match.group(2))
            head.fields[name] = parsed
            continuation = parsed.text

        if head.fields:
            macro.head = head

    def _check_stray_annotations(self, header: Optional[Header]) -> None:
        for line_number, line in enumerate(self._lines, start=1):
            if self._inside_header(header, line_number):
                continue
            if line_number in self._head_block_lines:
                continue
            payload = comment_payload(line)
            if payload is None:
                continue
            token = payload.strip()

            for anchor in RETIRED_CASE_ANCHORS:
                if token == anchor:
                    self._add_error(
                        line_number,
                        f"'{anchor}' is retired: case heads are plain '@' comments"
                        " directly above the test macro",
                    )

            field_match = HEAD_FIELD_RE.match(payload)
            if field_match:
                name = field_match.group(1)
                if name in RETIRED_FIELDS:
                    self._add_error(
                        line_number, f"'@{name}' is retired: {RETIRED_FIELDS[name]}"
                    )
                    continue
                if name in HEAD_FIELDS:
                    self._add_error(
                        line_number,
                        f"dangling '@{name}': put it directly above a TEST_F/TEST_P",
                    )
                    continue
                if name in HEADER_FIELDS:
                    self._add_error(
                        line_number, f"'@{name}' belongs inside the HEADER block"
                    )
                    continue

            if CATEGORY_BEGIN_RE.match(payload) or CATEGORY_END_RE.match(payload):
                self._add_error(
                    line_number, "category anchors belong inside the HEADER block"
                )


def sanitize_cpp(text: str) -> str:
    result = list(text)
    index = 0
    length = len(text)

    def blank(start: int, end: int) -> None:
        for offset in range(start, end):
            if result[offset] != "\n":
                result[offset] = " "

    while index < length:
        if text.startswith("//", index):
            end = text.find("\n", index)
            end = length if end == -1 else end
            blank(index, end)
            index = end
            continue

        if text.startswith("/*", index):
            end_marker = text.find("*/", index + 2)
            end = length if end_marker == -1 else end_marker + 2
            blank(index, end)
            index = end
            continue

        raw_match = re.match(r'R"([^\s\\()]*)\(', text[index:])
        if raw_match:
            delimiter = raw_match.group(1)
            terminator = f'){delimiter}"'
            end_marker = text.find(terminator, index + raw_match.end())
            end = length if end_marker == -1 else end_marker + len(terminator)
            blank(index, end)
            index = end
            continue

        if text[index] not in {'"', "'"}:
            index += 1
            continue

        quote = text[index]
        end = index + 1
        while end < length:
            if text[end] == "\\":
                end += 2
                continue
            if text[end] == quote:
                end += 1
                break
            end += 1
        blank(index, min(end, length))
        index = end

    return "".join(result)


def field_value(header: Header, name: str) -> Optional[str]:
    parsed = header.fields.get(name)
    if parsed is None:
        return None
    return parsed.text.as_text()


def parse_dependencies(document: Document, raw_value: str, line: int) -> None:
    value = machine_value(raw_value)
    if not value:
        document.add_error(line, "@Deps must not be empty")
        return

    for raw_dependency in value.split(","):
        token = raw_dependency.strip()
        match = DEPENDENCY_RE.match(token)
        if match is None:
            document.add_error(line, f"invalid dependency '{token}'")
            continue
        name, kind = match.groups()
        if kind not in DEPENDENCY_TYPES:
            document.add_error(line, f"invalid dependency type '{kind}'")
            continue
        document.dependencies.append(Dependency(name, kind))


def validate(document: Document) -> list[Diagnostic]:
    header = document.header
    if header is None:
        return normalized_diagnostics(document.diagnostics)

    for required in ("Unit", "Tier", "Desc"):
        if required not in header.fields:
            document.add_error(header.start_line, f"missing required HEADER field '@{required}'")

    unit = machine_value(field_value(header, "Unit") or "")
    tier = machine_value(field_value(header, "Tier") or "")
    description = field_value(header, "Desc") or ""

    if "Unit" in header.fields:
        if not unit:
            document.add_error(header.fields["Unit"].line, "@Unit must not be empty")
        elif not IDENTIFIER_RE.match(unit):
            document.add_error(header.fields["Unit"].line, f"invalid @Unit '{unit}'")
    if "Tier" in header.fields:
        if not tier:
            document.add_error(header.fields["Tier"].line, "@Tier must not be empty")
        elif tier not in TIERS:
            document.add_error(header.fields["Tier"].line, f"invalid @Tier '{tier}'")
    if "Desc" in header.fields and not description:
        document.add_error(header.fields["Desc"].line, "@Desc must not be empty")
    if not header.categories:
        document.add_error(header.start_line, "HEADER must contain at least one category")

    deps_field = header.fields.get("Deps")
    if deps_field is not None:
        parse_dependencies(document, deps_field.text.as_text(), deps_field.line)

    seen_categories: set[str] = set()
    seen_branches: set[str] = set()
    case_refs: dict[str, CaseRef] = {}

    for category in header.categories:
        if category.name not in CATEGORIES:
            document.add_error(category.line, f"invalid category '{category.name}'")
        if category.name in seen_categories:
            document.add_error(category.line, f"duplicate category '{category.name}'")
        seen_categories.add(category.name)

        refs = list(category.direct_cases)
        expected_prefix = BRANCH_PREFIXES.get(category.name)
        for branch in category.branches:
            if branch.branch_id in seen_branches:
                document.add_error(branch.line, f"duplicate branch id '{branch.branch_id}'")
            seen_branches.add(branch.branch_id)
            if expected_prefix and not re.fullmatch(
                rf"{re.escape(expected_prefix)}[1-9][0-9]*", branch.branch_id
            ):
                document.add_error(
                    branch.line,
                    f"branch '{branch.branch_id}' must use prefix '{expected_prefix}'",
                )
            if not branch.cases:
                document.add_error(branch.line, f"branch '{branch.branch_id}' has no cases")
            if not branch.description.as_text():
                document.add_error(
                    branch.line,
                    f"branch '{branch.branch_id}' must have a description",
                )
            refs.extend(branch.cases)

        if not category.direct_cases and not category.branches:
            document.add_error(category.line, f"category '{category.name}' has no cases")

        for case_ref in refs:
            if case_ref.placeholder:
                continue
            assert case_ref.name is not None
            if not IDENTIFIER_RE.match(case_ref.name):
                document.add_error(case_ref.line, f"invalid case name '{case_ref.name}'")
                continue
            if case_ref.name in case_refs:
                document.add_error(case_ref.line, f"duplicate HEADER case '{case_ref.name}'")
                continue
            case_refs[case_ref.name] = case_ref

    macros_by_name: dict[str, list[TestMacro]] = {}
    for macro in document.macros:
        macros_by_name.setdefault(macro.case_name, []).append(macro)
        if unit and macro.unit != unit:
            document.add_error(
                macro.line,
                f"{macro.kind} unit '{macro.unit}' does not match @Unit '{unit}'",
            )
        if macro.case_name not in case_refs:
            document.add_error(
                macro.line, f"{macro.kind} case '{macro.case_name}' is not registered in HEADER"
            )

    for name, macros in macros_by_name.items():
        if len(macros) > 1:
            document.add_error(macros[1].line, f"multiple test macros implement '{name}'")

    for name, case_ref in case_refs.items():
        if case_ref.detail.items and name in macros_by_name:
            document.add_error(
                case_ref.line,
                f"implemented case '{name}' must not keep detail in the HEADER;"
                " move it above its TEST_F",
            )

    if document.macros and header.end_line > min(macro.line for macro in document.macros):
        document.add_error(header.start_line, "HEADER must appear before all test macros")
    for line_number, line in enumerate(document.lines[header.end_line :], header.end_line + 1):
        if re.match(r"^\s*#\s*include\b", line):
            document.add_error(line_number, "all includes must appear before HEADER")

    return normalized_diagnostics(document.diagnostics)


def normalized_diagnostics(diagnostics: list[Diagnostic]) -> list[Diagnostic]:
    unique = {(item.line, item.message): item for item in diagnostics}
    return sorted(unique.values(), key=lambda item: (item.line, item.message))


def case_status(case_ref: CaseRef, macros_by_name: dict[str, list[TestMacro]]) -> str:
    if case_ref.placeholder:
        return "todo"
    assert case_ref.name is not None
    return "done" if case_ref.name in macros_by_name else "todo"


def branch_status(branch: Branch, macros_by_name: dict[str, list[TestMacro]]) -> str:
    statuses = [case_status(case_ref, macros_by_name) for case_ref in branch.cases]
    if all(status == "done" for status in statuses):
        return "done"
    if all(status == "todo" for status in statuses):
        return "todo"
    return "partial"


def case_ref_json(case_ref: CaseRef, macros_by_name: dict[str, list[TestMacro]]) -> dict[str, Any]:
    return {
        "name": case_ref.name,
        "placeholder": case_ref.placeholder,
        "status": case_status(case_ref, macros_by_name),
    }


def summary_json(document: Document) -> dict[str, Any]:
    assert document.header is not None
    header = document.header
    macros_by_name: dict[str, list[TestMacro]] = {}
    for macro in document.macros:
        macros_by_name.setdefault(macro.case_name, []).append(macro)
    categories: list[dict[str, Any]] = []

    for category in header.categories:
        categories.append(
            {
                "name": category.name,
                "cases": [
                    case_ref_json(case_ref, macros_by_name)
                    for case_ref in category.direct_cases
                ],
                "branches": [
                    {
                        "id": branch.branch_id,
                        "description": branch.description.as_text(),
                        "status": branch_status(branch, macros_by_name),
                        "cases": [
                            case_ref_json(case_ref, macros_by_name)
                            for case_ref in branch.cases
                        ],
                    }
                    for branch in category.branches
                ],
            }
        )

    args_field = header.fields.get("Args")
    return {
        "unit": machine_value(field_value(header, "Unit") or ""),
        "tier": machine_value(field_value(header, "Tier") or ""),
        "dependencies": [
            {"name": dependency.name, "type": dependency.kind}
            for dependency in document.dependencies
        ],
        "description": field_value(header, "Desc") or "",
        "args": args_field.text.items if args_field and args_field.text.items else None,
        "categories": categories,
    }


def find_case(document: Document, case_name: str) -> CaseRef:
    assert document.header is not None
    refs: list[CaseRef] = []
    for category in document.header.categories:
        refs.extend(category.direct_cases)
        for branch in category.branches:
            refs.extend(branch.cases)
    case_ref = next((item for item in refs if item.name == case_name), None)
    if case_ref is None:
        raise ValueError(f"case '{case_name}' was not found")
    return case_ref


def head_items(macro: Optional[TestMacro], field_name: str) -> Optional[list[str]]:
    if macro is None or macro.head is None:
        return None
    parsed = macro.head.fields.get(field_name)
    if parsed is None or not parsed.text.items:
        return None
    return parsed.text.items


def case_json(document: Document, case_name: str) -> dict[str, Any]:
    assert document.header is not None
    case_ref = find_case(document, case_name)
    branch = None
    if case_ref.branch_id is not None:
        for category in document.header.categories:
            for candidate in category.branches:
                if candidate.branch_id == case_ref.branch_id:
                    branch = {
                        "id": candidate.branch_id,
                        "description": candidate.description.as_text(),
                    }
                    break

    macro = next(
        (item for item in document.macros if item.case_name == case_name),
        None,
    )
    if macro is not None:
        detail = head_items(macro, "Detail")
        setup = head_items(macro, "Setup")
    else:
        detail = case_ref.detail.items if case_ref.detail.items else None
        setup = None
    return {
        "name": case_name,
        "category": case_ref.category,
        "branch": branch,
        "status": "done" if macro is not None else "todo",
        "detail": detail,
        "setup": setup,
        "test": (
            {
                "type": macro.kind,
                "unit": macro.unit,
                "case": macro.case_name,
            }
            if macro
            else None
        ),
    }


def print_diagnostics(document: Document, diagnostics: list[Diagnostic]) -> None:
    for diagnostic in diagnostics:
        print(
            f"{document.path}:{diagnostic.line}: {diagnostic.message}",
            file=sys.stderr,
        )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect annotated C++ unit tests.")
    parser.add_argument("--file", required=True, type=Path, help="annotated test file")
    parser.add_argument(
        "--op", required=True, choices=("summary", "case", "verify"), help="operation"
    )
    parser.add_argument("--case_name", help="case name for --op case")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    argument_parser = build_argument_parser()
    args = argument_parser.parse_args(argv)
    if args.op == "case" and not args.case_name:
        argument_parser.error("--case_name is required for --op case")
    if args.op != "case" and args.case_name:
        argument_parser.error("--case_name is only valid for --op case")

    try:
        text = args.file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        print(f"{args.file}: {error}", file=sys.stderr)
        return 2

    document = AnnotationParser(args.file, text).parse()
    diagnostics = validate(document)
    if diagnostics:
        print_diagnostics(document, diagnostics)
        return 1

    if args.op == "verify":
        print("OK")
        return 0

    if args.op == "summary":
        output = summary_json(document)
    else:
        try:
            output = case_json(document, args.case_name)
        except ValueError as error:
            print(f"{args.file}: {error}", file=sys.stderr)
            return 2

    print(json.dumps(output, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
