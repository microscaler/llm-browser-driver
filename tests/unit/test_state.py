"""Tests for state.py — page state extraction.
"""

from __future__ import annotations

from playwright.sync_api import Page

from llm_browser_driver.state import (
    build_page_summary,
    extract_inputs,
    extract_textareas,
    extract_buttons,
    extract_links,
    extract_selects,
    extract_form_fields,
    extract_disabled_elements,
    extract_html_snippet,
    extract_accessibility_tree,
    get_page_state,
)


# ---------------------------------------------------------------------------
# extract_* tests
# ---------------------------------------------------------------------------

class TestExtractInputs:
    def test_extract_single_input(self, browser_page: Page):
        browser_page.goto("data:text/html,<input type='text' name='email' placeholder='Enter email'>")
        inputs = extract_inputs(browser_page)
        assert len(inputs) == 1
        assert inputs[0]["name"] == "email"
        assert inputs[0]["type"] == "text"
        assert inputs[0]["placeholder"] == "Enter email"

    def test_extract_multiple_inputs(self, browser_page: Page):
        browser_page.goto(
            "data:text/html,"
            "<input type='email' name='email'>"
            "<input type='password' name='password'>"
        )
        inputs = extract_inputs(browser_page)
        assert len(inputs) == 2
        names = [i["name"] for i in inputs]
        assert "email" in names
        assert "password" in names

    def test_excludes_hidden_inputs(self, browser_page: Page):
        browser_page.goto(
            "data:text/html,"
            "<input type='hidden' name='csrf'>"
            "<input type='text' name='visible'>"
        )
        inputs = extract_inputs(browser_page)
        assert len(inputs) == 1
        assert inputs[0]["name"] == "visible"

    def test_excludes_submit_buttons(self, browser_page: Page):
        browser_page.goto(
            "data:text/html,"
            "<input type='submit' name='submit'>"
            "<input type='text' name='data'>"
        )
        inputs = extract_inputs(browser_page)
        assert len(inputs) == 1
        assert inputs[0]["name"] == "data"

    def test_disabled_input_flag(self, browser_page: Page):
        browser_page.goto("data:text/html,<input type='text' name='email' disabled>")
        inputs = extract_inputs(browser_page)
        assert inputs[0]["disabled"] is True

    def test_readonly_input_flag(self, browser_page: Page):
        browser_page.goto("data:text/html,<input type='text' name='slug' readonly value='fixed'>")
        inputs = extract_inputs(browser_page)
        assert inputs[0]["readonly"] is True


class TestExtractTextareas:
    def test_extract_textarea(self, browser_page: Page):
        browser_page.goto("data:text/html,<textarea name='bio' rows='3'></textarea>")
        textareas = extract_textareas(browser_page)
        assert len(textareas) == 1
        assert textareas[0]["name"] == "bio"
        assert textareas[0]["rows"] == "3"

    def test_empty_textarea_value(self, browser_page: Page):
        browser_page.goto("data:text/html,<textarea name='bio'></textarea>")
        textareas = extract_textareas(browser_page)
        assert textareas[0]["value"] == ""


class TestExtractButtons:
    def test_extract_button(self, browser_page: Page):
        browser_page.goto("data:text/html,<button>Sign In</button>")
        buttons = extract_buttons(browser_page)
        assert len(buttons) == 1
        assert buttons[0]["text"] == "Sign In"

    def test_button_with_aria_label(self, browser_page: Page):
        browser_page.goto("data:text/html,<button aria-label='Submit form'>Submit</button>")
        buttons = extract_buttons(browser_page)
        assert buttons[0]["aria_label"] == "Submit form"

    def test_disabled_button_flag(self, browser_page: Page):
        browser_page.goto("data:text/html,<button disabled>Sign In</button>")
        buttons = extract_buttons(browser_page)
        assert buttons[0]["disabled"] is True


class TestExtractLinks:
    def test_extract_link(self, browser_page: Page):
        browser_page.goto("data:text/html,<a href='/signup'>Create Account</a>")
        links = extract_links(browser_page)
        assert len(links) == 1
        assert links[0]["text"] == "Create Account"
        assert links[0]["href"] == "/signup"

    def test_link_with_aria_label(self, browser_page: Page):
        browser_page.goto("data:text/html,<a href='/login' aria-label='Go to login'>Login</a>")
        links = extract_links(browser_page)
        assert links[0]["aria_label"] == "Go to login"

    def test_excludes_buttons_with_link_role(self, browser_page: Page):
        """Buttons with role=button should not be extracted as links."""
        browser_page.goto("data:text/html,<button role='button' href='/test'>Test</button>")
        links = extract_links(browser_page)
        assert len(links) == 0


class TestExtractSelects:
    def test_extract_select_with_options(self, browser_page: Page):
        browser_page.goto(
            "data:text/html,"
            "<select name='country'>"
            "  <option value='US'>United States</option>"
            "  <option value='CA'>Canada</option>"
            "</select>"
        )
        selects = extract_selects(browser_page)
        assert len(selects) == 1
        assert selects[0]["name"] == "country"
        assert len(selects[0]["options"]) == 2
        assert selects[0]["options"][0]["text"] == "United States"
        assert selects[0]["options"][0]["value"] == "US"

    def test_select_disabled_flag(self, browser_page: Page):
        browser_page.goto("data:text/html,<select name='country' disabled></select>")
        selects = extract_selects(browser_page)
        assert selects[0]["disabled"] is True


class TestExtractFormFields:
    def test_extract_label_for(self, browser_page: Page):
        browser_page.goto(
            "data:text/html,"
            '<label for="email">Email address</label>'
            '<input id="email">'
        )
        fields = extract_form_fields(browser_page)
        assert len(fields) == 1
        assert fields[0]["text"] == "Email address"
        assert fields[0]["for"] == "email"

    def test_extract_label_data_for(self, browser_page: Page):
        browser_page.goto(
            "data:text/html,"
            '<label data-for="name">Full Name</label>'
        )
        fields = extract_form_fields(browser_page)
        assert len(fields) == 1
        assert fields[0]["data_for"] == "name"


class TestExtractDisabledElements:
    def test_extract_disabled_button(self, browser_page: Page):
        browser_page.goto("data:text/html,<button disabled>Submit</button>")
        disabled = extract_disabled_elements(browser_page)
        assert len(disabled) == 1
        assert disabled[0]["tag"] == "button"

    def test_extract_disabled_input(self, browser_page: Page):
        browser_page.goto("data:text/html,<input disabled type='text' name='email'>")
        disabled = extract_disabled_elements(browser_page)
        assert len(disabled) == 1
        assert disabled[0]["tag"] == "input"
        assert disabled[0]["name"] == "email"


class TestExtractHtmlSnippet:
    def test_extract_top_html(self, browser_page: Page):
        browser_page.goto("data:text/html,<html><body><h1>Test</h1><p>Content</p></body></html>")
        html = extract_html_snippet(browser_page, max_bytes=2048)
        assert "Test" in html
        assert "Content" in html

    def test_max_bytes_limit(self, browser_page: Page):
        browser_page.goto("data:text/html,<html><body>" + "<p>x</p>" * 100 + "</body></html>")
        html = extract_html_snippet(browser_page, max_bytes=50)
        assert len(html) <= 50

    def test_empty_page(self, browser_page: Page):
        browser_page.goto("data:text/html,")
        html = extract_html_snippet(browser_page)
        assert html == ""


class TestExtractAccessibilityTree:
    def test_native_accessibility_tree(self, browser_page: Page):
        browser_page.goto("data:text/html,<h1>Hello</h1><button>Click</button>")
        tree = extract_accessibility_tree(browser_page)
        # Playwright's native accessibility.snapshot() should work
        assert "children" in tree or "error" not in tree

    def test_fallback_accessibility_tree(self, browser_page: Page):
        """Fallback TreeWalker should produce children."""
        browser_page.goto(
            "data:text/html,"
            '<div aria-label="Test div">Content</div>'
            '<input aria-label="Test input">'
        )
        tree = extract_accessibility_tree(browser_page)
        # The fallback should produce nodes
        children = tree.get("children", [])
        # At least the div with aria-label should be found
        names = [n.get("name", "") for n in children]
        assert "Test div" in names or "Test input" in names


# ---------------------------------------------------------------------------
# build_page_summary tests
# ---------------------------------------------------------------------------

class TestBuildPageSummary:
    def test_includes_page_info(self, sample_page_state: dict):
        summary = build_page_summary(sample_page_state)
        assert "Test Page" in summary
        assert "localhost:7174" in summary

    def test_includes_element_counts(self, sample_page_state: dict):
        summary = build_page_summary(sample_page_state)
        assert "ELEMENT COUNTS" in summary
        assert "Inputs: 3" in summary  # count from forms dict
        assert "Buttons: 2" in summary

    def test_includes_input_details(self, sample_page_state: dict):
        summary = build_page_summary(sample_page_state)
        assert "INPUTS" in summary
        assert "name=email" in summary
        assert "placeholder=Email" in summary

    def test_includes_button_details(self, sample_page_state: dict):
        summary = build_page_summary(sample_page_state)
        assert "BUTTONS" in summary
        assert "text='Sign In'" in summary

    def test_includes_link_details(self, sample_page_state: dict):
        summary = build_page_summary(sample_page_state)
        assert "LINKS" in summary
        assert "href=/signup" in summary

    def test_includes_select_options(self, sample_page_state: dict):
        summary = build_page_summary(sample_page_state)
        assert "SELECTS" in summary
        assert "United States" in summary

    def test_includes_form_labels(self, sample_page_state: dict):
        summary = build_page_summary(sample_page_state)
        assert "FORM LABELS" in summary
        assert "Email address" in summary

    def test_includes_console_errors(self, sample_page_state: dict):
        summary = build_page_summary(sample_page_state)
        assert "CONSOLE" in summary
        assert "Deprecated API called" in summary

    def test_includes_accessibility_tree(self, sample_page_state: dict):
        summary = build_page_summary(sample_page_state)
        assert "ACCESSIBILITY TREE" in summary
        assert "role=heading" in summary


# ---------------------------------------------------------------------------
# get_page_state tests
# ---------------------------------------------------------------------------

class TestGetPageState:
    def test_returns_complete_state(self, browser_page: Page):
        browser_page.goto("data:text/html,<h1>Test</h1><button>Click</button>")
        state = get_page_state(browser_page)

        assert state["title"] == "Test"
        assert "data:text/html" in state["url"]
        assert "forms" in state
        assert "details" in state
        assert "html_snippet" in state
        assert "accessibility_tree" in state
        assert "console" in state
        assert "viewport" in state

    def test_counts_inputs(self, browser_page: Page):
        browser_page.goto(
            "data:text/html,"
            "<input type='text' name='email'>"
            "<input type='email' name='confirm'>"
        )
        state = get_page_state(browser_page)
        assert state["forms"]["input_count"] == 2

    def test_counts_buttons(self, browser_page: Page):
        browser_page.goto(
            "data:text/html,"
            "<button>One</button>"
            "<button>Two</button>"
            "<button>Three</button>"
        )
        state = get_page_state(browser_page)
        assert state["forms"]["button_count"] == 3

    def test_empty_page(self, browser_page: Page):
        browser_page.goto("data:text/html,<h1>Hello</h1>")
        state = get_page_state(browser_page)
        assert state["forms"]["input_count"] == 0
        assert state["forms"]["button_count"] == 0
