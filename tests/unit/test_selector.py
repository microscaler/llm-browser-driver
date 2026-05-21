"""Tests for selector.py — anti-fragile element matching.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Browser, Page

from llm_browser_driver.selector import (
    click_by_id,
    click_by_button_text,
    click_by_link,
    find_field,
    find_select_field,
    click_select_option,
)


# ---------------------------------------------------------------------------
# click_by_id tests
# ---------------------------------------------------------------------------

class TestClickById:
    def test_click_by_id_success(self, browser_page: Page):
        """Should click element by id and return success message."""
        browser_page.goto("data:text/html,<button id='my-button'>Click Me</button>")
        success, msg = click_by_id(browser_page, "my-button")
        assert success is True
        assert "Clicked by id" in msg

    def test_click_by_id_spaces_converted(self, browser_page: Page):
        """Spaces in element text should be converted to hyphens for id lookup."""
        browser_page.goto("data:text/html,<button id='submit-btn'>Submit</button>")
        success, msg = click_by_id(browser_page, "submit-btn")
        assert success is True
        assert "submit-btn" in msg

    def test_click_by_id_not_found(self, browser_page: Page):
        """Should return failure when id doesn't exist."""
        browser_page.goto("data:text/html,<button id='other'>Other</button>")
        success, msg = click_by_id(browser_page, "nonexistent")
        assert success is False
        assert msg == ""


# ---------------------------------------------------------------------------
# click_by_button_text tests
# ---------------------------------------------------------------------------

class TestClickByButtonText:
    def test_click_by_exact_text(self, browser_page: Page):
        """Should click button with matching text."""
        browser_page.goto("data:text/html,<button>Sign In</button>")
        success, msg = click_by_button_text(browser_page, "Sign In")
        assert success is True

    def test_click_by_partial_text(self, browser_page: Page):
        """Should click button with partial text match."""
        browser_page.goto("data:text/html,<button>Sign In Now</button>")
        success, msg = click_by_button_text(browser_page, "Sign In")
        assert success is True

    def test_click_by_button_text_not_found(self, browser_page: Page):
        """Should return failure when no button matches."""
        browser_page.goto("data:text/html,<button>Sign In</button>")
        success, msg = click_by_button_text(browser_page, "Delete Account")
        assert success is False


# ---------------------------------------------------------------------------
# click_by_link tests
# ---------------------------------------------------------------------------

class TestClickByLink:
    def test_click_by_link_text(self, browser_page: Page):
        """Should click link by visible text."""
        browser_page.goto("data:text/html,<a href='/signup'>Create Account</a>")
        success, msg = click_by_link(browser_page, "Create Account")
        assert success is True
        assert "Clicked link" in msg

    def test_click_by_link_href(self, browser_page: Page):
        """Should click link by href match."""
        browser_page.goto("data:text/html,<a href='/signin' class='nav-link'>Login</a>")
        success, msg = click_by_link(browser_page, "/signin")
        assert success is True

    def test_click_by_link_not_found(self, browser_page: Page):
        """Should return failure when link doesn't exist."""
        browser_page.goto("data:text/html,<a href='/signup'>Sign Up</a>")
        success, msg = click_by_link(browser_page, "/nonexistent")
        assert success is False


# ---------------------------------------------------------------------------
# find_field tests
# ---------------------------------------------------------------------------

class TestFindField:
    def test_find_by_name(self, browser_page: Page):
        """Should find input by name attribute."""
        browser_page.goto("data:text/html,<input type='email' name='email'>")
        success, display = find_field(browser_page, "email")
        assert success is True
        assert display == "email"

    def test_find_by_placeholder(self, browser_page: Page):
        """Should find input by placeholder text."""
        browser_page.goto("data:text/html,<input type='text' placeholder='Enter your email'>")
        success, display = find_field(browser_page, "Enter your email")
        assert success is True

    def test_find_by_id(self, browser_page: Page):
        """Should find input by id attribute."""
        browser_page.goto("data:text/html,<input type='password' id='user-password'>")
        success, display = find_field(browser_page, "user-password")
        assert success is True
        assert display == "user-password"

    def test_find_by_aria_label(self, browser_page: Page):
        """Should find input by aria-label."""
        browser_page.goto("data:text/html,<input type='text' aria-label='First Name'>")
        success, display = find_field(browser_page, "First Name")
        assert success is True
        assert display == "First Name"

    def test_find_by_label_text(self, browser_page: Page):
        """Should find input by associated <label[for] text."""
        browser_page.goto(
            "data:text/html,"
            '<label for="fname">First Name</label>'
            '<input type="text" id="fname">'
        )
        success, display = find_field(browser_page, "First Name")
        assert success is True

    def test_find_by_label_for_data(self, browser_page: Page):
        """Should find input by <label[data-for] text."""
        browser_page.goto(
            "data:text/html,"
            '<label data-for="fname">First Name</label>'
            '<input type="text" id="fname">'
        )
        success, display = find_field(browser_page, "First Name")
        assert success is True

    def test_find_field_not_found(self, browser_page: Page):
        """Should return failure when no field matches."""
        browser_page.goto("data:text/html,<input name='email'>")
        success, display = find_field(browser_page, "username")
        assert success is False

    def test_find_textarea_by_name(self, browser_page: Page):
        """Should find textarea by name."""
        browser_page.goto("data:text/html,<textarea name='bio'></textarea>")
        success, display = find_field(browser_page, "bio")
        assert success is True


# ---------------------------------------------------------------------------
# find_select_field tests
# ---------------------------------------------------------------------------

class TestFindSelectField:
    def test_find_select_by_name(self, browser_page: Page):
        """Should find select by name attribute."""
        browser_page.goto("data:text/html,<select name='country'><option>US</option></select>")
        success, name = find_select_field(browser_page, "country")
        assert success is True
        assert name == "country"

    def test_find_select_not_found(self, browser_page: Page):
        """Should return failure when select doesn't exist."""
        browser_page.goto("data:text/html,<select name='country'></select>")
        success, name = find_select_field(browser_page, "language")
        assert success is False


# ---------------------------------------------------------------------------
# click_select_option tests
# ---------------------------------------------------------------------------

class TestClickSelectOption:
    def test_click_select_option(self, browser_page: Page):
        """Should find select and click matching option."""
        browser_page.goto(
            "data:text/html,"
            "<select name='country'>"
            "  <option value='US'>United States</option>"
            "  <option value='CA'>Canada</option>"
            "</select>"
        )
        success, msg = click_select_option(browser_page, "country", "Canada")
        assert success is True
        assert "Canada" in msg

    def test_click_select_option_not_found(self, browser_page: Page):
        """Should return failure when option not found."""
        browser_page.goto(
            "data:text/html,"
            "<select name='country'>"
            "  <option value='US'>United States</option>"
            "</select>"
        )
        success, msg = click_select_option(browser_page, "country", "France")
        assert success is False
        assert "not found" in msg.lower()

    def test_click_select_not_found(self, browser_page: Page):
        """Should return failure when select doesn't exist."""
        browser_page.goto("data:text/html,<p>No select here</p>")
        success, msg = click_select_option(browser_page, "country", "US")
        assert success is False
        assert "Could not find" in msg
