"""Tests for the OpenAPI spec parser.

Covers:
- Loading YAML specs
- Extracting endpoints by method
- Parsing request bodies (fields, types, required, enums, arrays)
- Generating test goals with field descriptions
- Page path resolution (exact and path-only mapping)
- Endpoint counts and spec metadata
"""

from __future__ import annotations

import pytest
import yaml

from llm_browser_driver.spec_parser import SpecParser


# ---------------------------------------------------------------------------
# Sample OpenAPI specs
# ---------------------------------------------------------------------------

MINIMAL_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Test API", "version": "1.0.0"},
    "paths": {
        "/api/v1/jobs": {
            "post": {
                "summary": "Create a job",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string", "description": "Job title"},
                                    "location": {"type": "string"},
                                },
                                "required": ["title"],
                            }
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    }
                },
            },
            "get": {
                "summary": "List jobs",
                "responses": {"200": {"description": "OK"}},
            },
        },
        "/api/v1/auth/signin": {
            "post": {
                "summary": "Sign in",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "email": {"type": "string", "format": "email"},
                                    "password": {"type": "string"},
                                },
                                "required": ["email", "password"],
                            }
                        }
                    }
                },
                "responses": {"200": {"description": "OK"}},
            }
        },
    },
}


FULL_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Full API", "version": "2.0.0", "description": "A full-featured API"},
    "paths": {
        "/api/v1/users": {
            "post": {
                "summary": "Create user",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "username": {"type": "string", "description": "User name"},
                                    "email": {"type": "string", "format": "email", "description": "Email address"},
                                    "role": {
                                        "type": "string",
                                        "enum": ["admin", "user", "moderator"],
                                    },
                                    "age": {"type": "integer"},
                                    "active": {"type": "boolean"},
                                    "tags": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "address": {
                                        "type": "object",
                                        "properties": {
                                            "street": {"type": "string"},
                                            "city": {"type": "string"},
                                        },
                                    },
                                },
                                "required": ["username", "email"],
                            }
                        }
                    }
                },
                "parameters": [
                    {"name": "X-Request-ID", "in": "header", "required": True},
                ],
                "responses": {
                    "201": {
                        "description": "Created",
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    }
                },
            },
            "get": {
                "summary": "List users",
                "parameters": [
                    {"name": "page", "in": "query", "schema": {"type": "integer"}},
                ],
                "responses": {"200": {"description": "OK"}},
            },
        },
        "/api/v1/auth/signup": {
            "post": {
                "summary": "Register",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "username": {"type": "string"},
                                    "email": {"type": "string", "format": "email"},
                                    "password": {"type": "string"},
                                },
                                "required": ["username", "email", "password"],
                            }
                        }
                    }
                },
                "responses": {"201": {"description": "Created"}},
            }
        },
    },
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_parser():
    return SpecParser(spec_data=MINIMAL_SPEC)


@pytest.fixture
def full_parser():
    return SpecParser(spec_data=FULL_SPEC)


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------


class TestSpecLoading:
    def test_load_from_dict(self):
        parser = SpecParser(spec_data=MINIMAL_SPEC)
        assert parser is not None

    def test_load_from_file(self, tmp_path):
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(MINIMAL_SPEC))
        parser = SpecParser(spec_path=str(spec_file))
        assert parser is not None

    def test_load_nonexistent_file(self):
        with pytest.raises(FileNotFoundError):
            SpecParser(spec_path="/nonexistent/spec.yaml")

    def test_no_spec_provided(self):
        with pytest.raises(ValueError, match="Provide spec_path or spec_data"):
            SpecParser()


# ---------------------------------------------------------------------------
# Endpoint extraction
# ---------------------------------------------------------------------------


class TestGetEndpoints:
    def test_returns_all_endpoints(self, minimal_parser):
        endpoints = minimal_parser.get_endpoints()
        assert len(endpoints) == 3  # POST /jobs, POST /signin, GET /jobs

    def test_filters_by_method(self, minimal_parser):
        posts = minimal_parser.get_endpoints(methods=["POST"])
        assert len(posts) == 2
        assert all(ep.method == "post" for ep in posts)

    def test_returns_empty_for_no_matches(self, minimal_parser):
        endpoints = minimal_parser.get_endpoints(methods=["DELETE"])
        assert len(endpoints) == 0

    def test_sorted_by_path(self, full_parser):
        endpoints = full_parser.get_endpoints()
        # Should be sorted: /api/v1/auth/signup, /api/v1/jobs (get), /api/v1/jobs (post), /api/v1/users (get)
        paths = [(ep.path, ep.method) for ep in endpoints]
        assert paths == sorted(paths)

    def test_body_endpoints_only(self, minimal_parser):
        body_eps = minimal_parser.get_body_endpoints()
        assert len(body_eps) == 2
        assert all(ep.method.upper() in ("POST", "PUT", "PATCH") for ep in body_eps)

    def test_get_body_endpoints_excludes_get(self, minimal_parser):
        body_eps = minimal_parser.get_body_endpoints()
        for ep in body_eps:
            assert ep.method != "get"


class TestGetEndpointsByMethod:
    def test_post_only(self, minimal_parser):
        posts = minimal_parser.get_endpoints_by_method("POST")
        assert len(posts) == 2

    def test_post_with_path_filter(self, minimal_parser):
        posts = minimal_parser.get_endpoints_by_method("POST", filter_path="/jobs")
        assert len(posts) == 1
        assert posts[0].path == "/api/v1/jobs"

    def test_auth_only(self, minimal_parser):
        posts = minimal_parser.get_endpoints_by_method("POST", filter_path="/auth")
        assert len(posts) == 1
        assert posts[0].path == "/api/v1/auth/signin"


# ---------------------------------------------------------------------------
# Request body parsing
# ---------------------------------------------------------------------------


class TestRequestBodyParsing:
    def test_required_fields(self, full_parser):
        endpoints = full_parser.get_body_endpoints()
        user_ep = next(ep for ep in endpoints if ep.path == "/api/v1/users")

        assert user_ep.request_body is not None
        assert user_ep.request_body["username"].required is True
        assert user_ep.request_body["email"].required is True
        assert user_ep.request_body["role"].required is False

    def test_field_types(self, full_parser):
        endpoints = full_parser.get_body_endpoints()
        user_ep = next(ep for ep in endpoints if ep.path == "/api/v1/users")

        assert user_ep.request_body["username"].type == "string"
        assert user_ep.request_body["age"].type == "integer"
        assert user_ep.request_body["active"].type == "boolean"

    def test_enum_fields(self, full_parser):
        endpoints = full_parser.get_body_endpoints()
        user_ep = next(ep for ep in endpoints if ep.path == "/api/v1/users")

        assert user_ep.request_body["role"].enum == ["admin", "user", "moderator"]

    def test_array_fields(self, full_parser):
        endpoints = full_parser.get_body_endpoints()
        user_ep = next(ep for ep in endpoints if ep.path == "/api/v1/users")

        assert user_ep.request_body["tags"].type == "array"

    def test_object_fields(self, full_parser):
        endpoints = full_parser.get_body_endpoints()
        user_ep = next(ep for ep in endpoints if ep.path == "/api/v1/users")

        assert user_ep.request_body["address"].type == "object"
        assert "street" in user_ep.request_body["address"].properties
        assert "city" in user_ep.request_body["address"].properties

    def test_field_descriptions(self, full_parser):
        endpoints = full_parser.get_body_endpoints()
        user_ep = next(ep for ep in endpoints if ep.path == "/api/v1/users")

        assert user_ep.request_body["username"].description == "User name"
        assert user_ep.request_body["email"].description == "Email address"

    def test_parameters_parsed(self, full_parser):
        endpoints = full_parser.get_body_endpoints()
        user_ep = next(ep for ep in endpoints if ep.path == "/api/v1/users")

        assert len(user_ep.parameters) == 1
        assert user_ep.parameters[0]["name"] == "X-Request-ID"
        assert user_ep.parameters[0]["in"] == "header"
        assert user_ep.parameters[0]["required"] is True

    def test_response_schemas_parsed(self, full_parser):
        endpoints = full_parser.get_body_endpoints()
        user_ep = next(ep for ep in endpoints if ep.path == "/api/v1/users")

        assert "201/application/json" in user_ep.response_schemas


# ---------------------------------------------------------------------------
# Spec metadata
# ---------------------------------------------------------------------------


class TestSpecInfo:
    def test_basic_info(self):
        parser = SpecParser(spec_data=MINIMAL_SPEC)
        info = parser.get_spec_info()
        assert info["title"] == "Test API"
        assert info["version"] == "1.0.0"
        assert info["description"] == ""

    def test_full_info(self):
        parser = SpecParser(spec_data=FULL_SPEC)
        info = parser.get_spec_info()
        assert info["title"] == "Full API"
        assert info["version"] == "2.0.0"
        assert info["description"] == "A full-featured API"

    def test_endpoint_counts(self):
        parser = SpecParser(spec_data=MINIMAL_SPEC)
        counts = parser.get_endpoint_count()
        assert counts == {"post": 2, "get": 1}

    def test_endpoint_counts_empty(self):
        parser = SpecParser(spec_data={"paths": {}})
        counts = parser.get_endpoint_count()
        assert counts == {}


# ---------------------------------------------------------------------------
# Test goal generation
# ---------------------------------------------------------------------------


class TestGenerateGoals:
    def test_generates_goals_for_body_endpoints(self, minimal_parser):
        mapping = {
            "POST /api/v1/jobs": "/post-a-job",
            "POST /api/v1/auth/signin": "/signin",
        }
        goals = minimal_parser.generate_goals("http://staging", mapping)
        assert len(goals) == 2

    def test_goal_contains_endpoint_info(self, minimal_parser):
        mapping = {
            "POST /api/v1/jobs": "/post-a-job",
        }
        goals = minimal_parser.generate_goals("http://staging", mapping)
        assert len(goals) == 1

        goal = goals[0]["goal"]
        assert "POST /api/v1/jobs" in goal
        assert "/post-a-job" in goal

    def test_goal_mentions_required_fields(self, minimal_parser):
        mapping = {
            "POST /api/v1/auth/signin": "/signin",
        }
        goals = minimal_parser.generate_goals("http://staging", mapping)
        assert len(goals) == 1

        goal = goals[0]["goal"]
        assert "email" in goal
        assert "password" in goal

    def test_goal_mentions_submit_action(self, minimal_parser):
        mapping = {
            "POST /api/v1/jobs": "/post-a-job",
        }
        goals = minimal_parser.generate_goals("http://staging", mapping)
        assert "Submit" in goals[0]["goal"] or "submit" in goals[0]["goal"]

    def test_no_goals_without_mapping(self, minimal_parser):
        goals = minimal_parser.generate_goals("http://staging")
        assert len(goals) == 0

    def test_skips_endpoints_without_page_mapping(self, minimal_parser):
        mapping = {
            "POST /api/v1/jobs": "/post-a-job",
            # Note: /signin is NOT mapped
        }
        goals = minimal_parser.generate_goals("http://staging", mapping)
        assert len(goals) == 1
        assert "signin" not in goals[0]["page_url"]

    def test_path_only_mapping(self, minimal_parser):
        """Mapping by path alone (without METHOD) should work."""
        mapping = {
            "/api/v1/jobs": "/post-a-job",
        }
        goals = minimal_parser.generate_goals("http://staging", mapping)
        assert len(goals) == 1

    def test_full_endpoint_mapping(self, minimal_parser):
        """Mapping by METHOD /path should work."""
        mapping = {
            "POST /api/v1/jobs": "/post-a-job",
        }
        goals = minimal_parser.generate_goals("http://staging", mapping)
        assert len(goals) == 1

    def test_page_url_construction(self, minimal_parser):
        mapping = {
            "POST /api/v1/jobs": "/post-a-job",
        }
        goals = minimal_parser.generate_goals("http://staging.example.com", mapping)
        assert goals[0]["page_url"] == "http://staging.example.com/post-a-job"

    def test_test_data_included(self, minimal_parser):
        mapping = {
            "POST /api/v1/jobs": "/post-a-job",
        }
        test_data = {
            "POST /api/v1/jobs": {"title": "Test Job", "location": "Remote"},
        }
        goals = minimal_parser.generate_goals(
            "http://staging", mapping, test_data=test_data
        )
        assert goals[0]["test_data"] == {"title": "Test Job", "location": "Remote"}

    def test_error_case_mentioned_for_required_fields(self, minimal_parser):
        mapping = {
            "POST /api/v1/auth/signin": "/signin",
        }
        goals = minimal_parser.generate_goals("http://staging", mapping)
        goal = goals[0]["goal"]
        assert "error" in goal.lower() or "missing" in goal.lower()


# ---------------------------------------------------------------------------
# EndpointSpec repr
# ---------------------------------------------------------------------------


class TestEndpointSpecRepr:
    def test_repr_with_body(self, minimal_parser):
        endpoints = minimal_parser.get_body_endpoints()
        ep = next(ep for ep in endpoints if ep.path == "/api/v1/jobs")
        assert "POST" in repr(ep)
        assert "/api/v1/jobs" in repr(ep)
        assert "body(2)" in repr(ep) or "body(1)" in repr(ep)

    def test_repr_without_body(self, minimal_parser):
        endpoints = minimal_parser.get_endpoints(methods=["GET"])
        ep = endpoints[0]
        assert "GET" in repr(ep)
        assert "body(0)" not in repr(ep)


# ---------------------------------------------------------------------------
# Identifier property
# ---------------------------------------------------------------------------


class TestEndpointIdentifier:
    def test_identifier_format(self):
        parser = SpecParser(spec_data=MINIMAL_SPEC)
        endpoints = parser.get_endpoints()
        for ep in endpoints:
            assert ep.identifier == f"{ep.method.upper()} {ep.path}"
