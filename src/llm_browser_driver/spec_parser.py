"""OpenAPI specification parser for spec-driven testing.

Extracts endpoints, request schemas, and generates test goals from
an OpenAPI 3.x YAML specification. Maps API endpoints to frontend
pages via user-provided configuration.

Usage::

    from llm_browser_driver.spec_parser import SpecParser

    parser = SpecParser("openapi.yaml")
    endpoints = parser.get_endpoints()
    goals = parser.generate_goals("http://staging.example.com", mapping)

    # → [
    #     "Test that POST /api/v1/auth/signin creates a signin form..."
    # ]
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class FieldSchema:
    """A single field in a request body schema."""

    name: str
    type: str  # string, integer, boolean, array, object
    required: bool = False
    description: str = ""
    example: Any = None
    enum: list[Any] | None = None
    properties: dict[str, "FieldSchema"] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"FieldSchema({self.name}: {self.type}{'+' if self.required else ''})"


@dataclass
class EndpointSpec:
    """An endpoint extracted from an OpenAPI spec."""

    method: str  # GET, POST, PUT, DELETE, PATCH
    path: str  # /api/v1/jobs
    summary: str = ""
    description: str = ""
    request_body: dict[str, FieldSchema] | None = None
    parameters: list[dict[str, Any]] = field(default_factory=list)
    response_schemas: dict[str, Any] = field(default_factory=dict)

    @property
    def identifier(self) -> str:
        return f"{self.method.upper()} {self.path}"

    def __repr__(self) -> str:
        body = f" body({len(self.request_body or {})})" if self.request_body else ""
        return f"EndpointSpec({self.identifier}{body})"


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class SpecParser:
    """Parse an OpenAPI 3.x specification into structured endpoint data.

    Extracts:
    - All endpoints with their HTTP method and path
    - Request body schemas (fields, types, required)
    - Parameter schemas (query, path, header)
    - Response schemas
    - Summaries and descriptions

    Args:
        spec_path: Path to the OpenAPI YAML file.
        spec_data: Alternatively, pass the parsed spec dict directly.

    Example:
        >>> parser = SpecParser("openapi.yaml")
        >>> for ep in parser.get_endpoints():
        ...     print(ep.identifier)
        POST /api/v1/jobs
        POST /api/v1/auth/signin
        GET /api/v1/jobs
    """

    # Methods that have request bodies (the ones we care about for form testing)
    BODY_METHODS = {"post", "put", "patch"}

    def __init__(
        self,
        spec_path: str | Path | None = None,
        spec_data: dict[str, Any] | None = None,
    ) -> None:
        if spec_data is not None:
            self._spec = spec_data
        elif spec_path is not None:
            self._spec = self._load_yaml(spec_path)
        else:
            raise ValueError("Provide spec_path or spec_data")

    @staticmethod
    def _load_yaml(path: str | Path) -> dict[str, Any]:
        """Load and parse a YAML file."""
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"OpenAPI spec not found: {p}")
        with open(p) as f:
            return yaml.safe_load(f)  # type: ignore

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_endpoints(self, methods: list[str] | None = None) -> list[EndpointSpec]:
        """Extract all endpoints from the spec.

        Args:
            methods: Optional list of HTTP methods to filter by
                     (e.g., ["POST", "PUT"]). Defaults to all.

        Returns:
            List of EndpointSpec objects, ordered by path then method.
        """
        endpoints: list[EndpointSpec] = []
        paths = self._spec.get("paths", {})

        for path, path_item in paths.items():
            for method, operation in path_item.items():
                if method not in self._SPEC_METHODS:
                    continue
                if methods and method.upper() not in methods:
                    continue

                ep = self._parse_endpoint(path, method, operation)
                endpoints.append(ep)

        # Sort by path, then method
        endpoints.sort(key=lambda e: (e.path, e.method))
        return endpoints

    def get_endpoints_by_method(
        self,
        method: str,
        filter_path: str | None = None,
    ) -> list[EndpointSpec]:
        """Get endpoints filtered by HTTP method and optionally path prefix.

        Args:
            method: HTTP method (e.g., "POST").
            filter_path: Optional path prefix filter.

        Returns:
            Filtered list of EndpointSpec.
        """
        endpoints = self.get_endpoints(methods=[method.upper()])
        if filter_path:
            endpoints = [
                ep for ep in endpoints if filter_path in ep.path
            ]
        return endpoints

    def get_body_endpoints(self) -> list[EndpointSpec]:
        """Get all endpoints with request bodies (POST, PUT, PATCH).

        These are the endpoints that typically have form fields to test.
        """
        return [
            ep for ep in self.get_endpoints()
            if ep.method.upper() in self.BODY_METHODS and ep.request_body
        ]

    def generate_goals(
        self,
        base_url: str,
        mapping: dict[str, str] | None = None,
        test_data: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate test goals from the parsed spec.

        Each goal is a dict with:
        - endpoint: EndpointSpec
        - goal: Natural-language test goal
        - page_url: Full URL (base_url + mapped page path)
        - test_data: Pre-filled test data (if provided)

        Args:
            base_url: Base URL of the frontend application.
            mapping: Optional endpoint-to-page mapping dict.
                     Keys are "METHOD /path" or just "/path".
                     Values are frontend page paths.
            test_data: Optional test data dict.
                       Keys are "METHOD /path".
                       Values are field name → value dicts.

        Returns:
            List of test goal dicts.

        Example:
            >>> mapping = {
            ...     "POST /api/v1/auth/signin": "/signin",
            ...     "POST /api/v1/jobs": "/post-a-job",
            ... }
            >>> goals = parser.generate_goals("http://staging", mapping)
            >>> len(goals)
            2
        """
        goals: list[dict[str, Any]] = []

        for ep in self.get_body_endpoints():
            page_path = self._resolve_page_path(ep.identifier, mapping)
            if not page_path:
                # No page mapped — skip
                continue

            goal = self._generate_goal(ep, page_path)
            test_data_entry = {}
            if test_data and ep.identifier in test_data:
                test_data_entry = test_data[ep.identifier]

            goals.append({
                "endpoint": ep,
                "goal": goal,
                "page_url": f"{base_url.rstrip('/')}/{page_path.lstrip('/')}",
                "test_data": test_data_entry,
                "method": ep.method,
                "api_path": ep.path,
            })

        return goals

    # ------------------------------------------------------------------
    # Internal parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_endpoint(
        path: str,
        method: str,
        operation: dict[str, Any],
    ) -> EndpointSpec:
        """Parse a single operation object into an EndpointSpec."""
        summary = operation.get("summary", "")
        description = operation.get("description", "")

        # Parse request body
        request_body: dict[str, FieldSchema] | None = None
        body_def = operation.get("requestBody", {})
        if body_def:
            request_body = SpecParser._parse_request_body(body_def)

        # Parse parameters
        parameters: list[dict[str, Any]] = []
        for param in operation.get("parameters", []):
            parameters.append({
                "name": param.get("name", ""),
                "in": param.get("in", ""),
                "required": param.get("required", False),
                "schema": param.get("schema", {}),
            })

        # Parse response schemas
        response_schemas: dict[str, Any] = {}
        responses = operation.get("responses", {})
        for code, response in responses.items():
            content = response.get("content", {})
            for media_type, media_def in content.items():
                schema = media_def.get("schema", {})
                response_schemas[f"{code}/{media_type}"] = schema

        return EndpointSpec(
            method=method,
            path=path,
            summary=summary,
            description=description,
            request_body=request_body,
            parameters=parameters,
            response_schemas=response_schemas,
        )

    @staticmethod
    def _parse_request_body(
        body_def: dict[str, Any],
    ) -> dict[str, FieldSchema]:
        """Parse a requestBody definition into a dict of FieldSchema."""
        content = body_def.get("content", {})
        json_content = content.get("application/json", {})
        schema = json_content.get("schema", {})

        if not schema:
            return {}

        # Handle allOf (composition)
        if "allOf" in schema:
            # Merge all schemas
            merged: dict[str, Any] = {}
            for part in schema["allOf"]:
                if "$ref" in part:
                    # Resolve $ref
                    ref_path = part["$ref"].split("/")[-1]
                    merged[ref_path] = part
                else:
                    merged.update(part)
            schema = merged

        properties = schema.get("properties", {})
        required_fields = schema.get("required", [])

        fields: dict[str, FieldSchema] = {}
        for name, prop in properties.items():
            fields[name] = SpecParser._parse_property(name, prop, required_fields)

        return fields

    @staticmethod
    def _parse_property(
        name: str,
        prop: dict[str, Any],
        required_fields: list[str],
    ) -> FieldSchema:
        """Parse a single property definition into a FieldSchema."""
        schema = prop if isinstance(prop, dict) else {}
        prop_type = schema.get("type", "string")
        description = schema.get("description", "")
        example = schema.get("example")
        enum = schema.get("enum")
        items = schema.get("items", {})
        properties = schema.get("properties", {})

        # Handle array types
        if prop_type == "array":
            items_schema = items.get("type", "object")
            if items_schema == "object":
                nested = {}
                for sub_name, sub_prop in items.get("properties", {}).items():
                    nested[sub_name] = SpecParser._parse_property(
                        sub_name, sub_prop, []
                    )
                prop_type = "object"

        return FieldSchema(
            name=name,
            type=prop_type,
            required=name in required_fields,
            description=description,
            example=example,
            enum=enum,
            properties=nested if prop_type == "object" else {},
        )

    # ------------------------------------------------------------------
    # Goal generation
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_goal(ep: EndpointSpec, page_path: str) -> str:
        """Generate a natural-language test goal from an endpoint spec.

        The goal is structured to give the LLM clear instructions:
        1. What form/page to find
        2. What fields to expect
        3. What to do with the data
        4. What to verify after submission
        """
        parts: list[str] = []

        # Header
        parts.append(
            f"Test that {ep.method.upper()} {ep.path} "
            f"corresponds to the form on {page_path}."
        )

        # Field descriptions
        if ep.request_body:
            required = [f for f in ep.request_body.values() if f.required]
            optional = [f for f in ep.request_body.values() if not f.required]

            if required:
                fields = ", ".join(
                    f"{f.name}"
                    for f in required
                )
                parts.append(
                    f"The form should include required fields: {fields}."
                )

            if optional:
                fields = ", ".join(f.name for f in optional)
                parts.append(
                    f"Optional fields: {fields}."
                )

            # Submit and verify
            parts.append(
                f"Submit the form with valid test data and verify "
                f"the page responds correctly (redirect, success message, "
                f"or updated state)."
            )

            # Error case
            if required:
                parts.append(
                    "Also test error handling: submit with missing required "
                    f"fields ({required[0].name}...) and verify error messages "
                    f"are displayed."
                )

        # GET endpoints (no form, just verify page loads and data displays)
        if ep.method.upper() == "GET" and not ep.request_body:
            parts.append(
                "Verify the page loads correctly and displays expected content. "
                "Check for common issues: broken images, missing data, "
                "layout problems, console errors."
            )

        return " ".join(parts)

    @staticmethod
    def _resolve_page_path(
        endpoint_id: str,
        mapping: dict[str, str] | None,
    ) -> str | None:
        """Resolve a frontend page path from an endpoint identifier.

        Looks up both exact match ("POST /api/v1/jobs") and path-only
        match ("/api/v1/jobs") in the mapping.
        """
        if not mapping:
            return None

        # Try exact match
        if endpoint_id in mapping:
            return mapping[endpoint_id]

        # Try path-only match
        path_only = endpoint_id.split(" ", 1)[-1]
        if path_only in mapping:
            return mapping[path_only]

        return None

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def get_spec_info(self) -> dict[str, str]:
        """Return basic metadata about the loaded spec."""
        return {
            "title": self._spec.get("info", {}).get("title", "Unknown"),
            "version": self._spec.get("info", {}).get("version", "0.0.0"),
            "description": self._spec.get("info", {}).get("description", ""),
        }

    def get_endpoint_count(self) -> dict[str, int]:
        """Return count of endpoints by HTTP method."""
        counts: dict[str, int] = {}
        for ep in self.get_endpoints():
            counts[ep.method.upper()] = counts.get(ep.method.upper(), 0) + 1
        return counts


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# OpenAPI operation keys that represent endpoints
SpecParser._SPEC_METHODS = {
    "get", "post", "put", "delete", "patch", "head", "options", "trace"
}
