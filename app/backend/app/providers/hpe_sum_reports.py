"""Bounded parser for the observed SUM 12.7 repository XML report.

Repository inventory is not target applicability, signature authentication, or
proof of completion. No automatic conversion to an executable Assessment exists.
"""

import hashlib
import re
from dataclasses import dataclass
from xml.etree import ElementTree as ET

LIMIT = 8 * 1024 * 1024
COMPONENT_FIELDS = frozenset(
    {
        "reboot_required",
        "status",
        "location",
        "description",
        "reboot_details",
        "filename",
        "type",
        "version",
        "name",
        "altname",
        "typeofcomponent",
    }
)


class SumReportError(ValueError):
    pass


@dataclass(frozen=True)
class RepositoryComponent:
    filename: str
    name: str
    version: str
    kind: str
    status: str
    reboot_required: str
    reboot_details: str


@dataclass(frozen=True)
class RepositoryReport:
    sha256: str
    app_version: str
    components: tuple[RepositoryComponent, ...]
    # Inventory alone never establishes these capabilities.
    target_applicability_verified: bool = False
    signature_verified: bool = False
    can_apply: bool = False


def _scalar(node, name, *, required=True):
    matches = node.findall(name)
    if len(matches) != 1:
        if not matches and not required:
            return ""
        raise SumReportError("Missing or repeated report field.")
    element = matches[0]
    if len(element) or element.attrib:
        raise SumReportError("Unexpected structured report field.")
    value = (element.text or "").strip()
    if (required and not value) or len(value) > 16384:
        raise SumReportError("Empty or oversized report field.")
    return value


def parse_repository_report(data: bytes) -> RepositoryReport:
    if not isinstance(data, bytes) or not data or len(data) > LIMIT:
        raise SumReportError("Report is empty or exceeds the size limit.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError:
        raise SumReportError("Report must be UTF-8 XML.") from None
    if "<!doctype" in text.lower() or "<!entity" in text.lower() or "\x00" in text:
        raise SumReportError("XML entities and document declarations are prohibited.")
    try:
        root = ET.fromstring(text)
    except (ET.ParseError, ValueError):
        raise SumReportError("Malformed SUM XML report.") from None
    stack = [(root, 0)]
    count = 0
    while stack:
        node, depth = stack.pop()
        count += 1
        if count > 10000 or depth > 16 or node.attrib:
            raise SumReportError("Report structure exceeds the supported bounds.")
        stack.extend((child, depth + 1) for child in node)
    if root.tag != "report" or any(
        n.tag
        not in {
            "inventoryreport",
            "report_type",
            "report_date",
            "bundles",
            "app_version",
            "language",
        }
        for n in root
    ):
        raise SumReportError("Unsupported SUM report structure.")
    if (
        _scalar(root, "report_type") != "0"
        or _scalar(root, "app_version") != "SUM 12.7.0"
        or _scalar(root, "language") != "en"
    ):
        raise SumReportError("Unsupported SUM report type, version or language.")
    _scalar(root, "report_date")
    inventories = root.findall("inventoryreport")
    if len(inventories) != 1 or len(root.findall("bundles")) > 1:
        raise SumReportError("Ambiguous SUM report sections.")
    nodes = list(inventories[0])
    if len(nodes) > 256 or any(n.tag != "component" for n in nodes):
        raise SumReportError("Unsupported component inventory.")
    components = []
    seen = set()
    for node in nodes:
        if any(child.tag not in COMPONENT_FIELDS for child in node):
            raise SumReportError("Unknown component report field.")
        for field in COMPONENT_FIELDS:
            _scalar(
                node,
                field,
                required=field not in {"altname", "description", "location", "reboot_details"},
            )
        filename = _scalar(node, "filename")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,254}", filename) or ".." in filename:
            raise SumReportError("Invalid package filename in report.")
        if filename.casefold() in seen:
            raise SumReportError("Repeated component filename in report.")
        seen.add(filename.casefold())
        kind = _scalar(node, "type")
        if kind != _scalar(node, "typeofcomponent"):
            raise SumReportError("Inconsistent component type.")
        components.append(
            RepositoryComponent(
                filename=filename,
                name=_scalar(node, "name"),
                version=_scalar(node, "version"),
                kind=kind,
                status=_scalar(node, "status"),
                reboot_required=_scalar(node, "reboot_required"),
                reboot_details=_scalar(node, "reboot_details", required=False),
            )
        )
    return RepositoryReport(hashlib.sha256(data).hexdigest(), "SUM 12.7.0", tuple(components))
