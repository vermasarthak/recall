"""Tests for package distribution schema access and imports."""

import importlib.resources

import recall


def test_package_version_and_imports():
    assert recall.__version__ == "0.1.0"
    assert recall.Recall is not None


def test_installed_schema_sql_access():
    schema_path = importlib.resources.files("recall.db").joinpath("schema.sql")
    assert schema_path.is_file()
    text = schema_path.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS facts" in text
    assert "CREATE TABLE IF NOT EXISTS entities" in text
