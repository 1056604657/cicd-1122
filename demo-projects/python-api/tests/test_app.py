from python_api.app import greet


def test_greet_with_name():
    assert greet("GitLab") == "Hello, GitLab"


def test_greet_with_blank_name():
    assert greet("   ") == "Hello, world"
