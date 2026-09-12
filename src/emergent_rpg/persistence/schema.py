from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import MetaData, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.reflection import Inspector

CURRENT_SCHEMA_VERSION = 1
SCHEMA_METADATA_TABLE = "schema_metadata"


class StoreSchemaError(RuntimeError):
    """Raised when a persisted SQLite schema cannot be opened safely."""


def _expected_application_columns(metadata: MetaData) -> dict[str, set[str]]:
    return {
        table.name: {column.name for column in table.columns}
        for table in metadata.sorted_tables
    }


def _actual_columns(inspector: Inspector, table_name: str) -> set[str]:
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def _validate_application_shape(
    inspector: Inspector,
    tables: set[str],
    expected: Mapping[str, set[str]],
    *,
    allow_schema_metadata: bool,
) -> None:
    permitted_tables = set(expected)
    if allow_schema_metadata:
        permitted_tables.add(SCHEMA_METADATA_TABLE)
    if tables != permitted_tables:
        missing = sorted(permitted_tables - tables)
        extra = sorted(tables - permitted_tables)
        raise StoreSchemaError(
            f"database table set does not match schema v{CURRENT_SCHEMA_VERSION}: "
            f"missing={missing}, extra={extra}"
        )

    for table_name, expected_columns in expected.items():
        actual_columns = _actual_columns(inspector, table_name)
        if actual_columns != expected_columns:
            raise StoreSchemaError(
                f"database table {table_name} does not match schema v{CURRENT_SCHEMA_VERSION}: "
                f"expected columns={sorted(expected_columns)}, "
                f"actual columns={sorted(actual_columns)}"
            )


def _read_schema_version(engine: Engine, inspector: Inspector) -> int:
    metadata_columns = _actual_columns(inspector, SCHEMA_METADATA_TABLE)
    if metadata_columns != {"id", "schema_version"}:
        raise StoreSchemaError(
            "schema_metadata has an unsupported shape; expected id and schema_version"
        )
    with engine.connect() as connection:
        rows = list(
            connection.execute(
                text("SELECT id, schema_version FROM schema_metadata ORDER BY id")
            ).mappings()
        )
    if len(rows) != 1 or rows[0]["id"] != 1:
        raise StoreSchemaError("schema_metadata must contain exactly one row with id=1")
    version = rows[0]["schema_version"]
    if not isinstance(version, int):
        raise StoreSchemaError("schema_metadata schema_version must be an integer")
    return version


def _create_version_metadata(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE schema_metadata ("
                "id INTEGER PRIMARY KEY, "
                "schema_version INTEGER NOT NULL"
                ")"
            )
        )
        connection.execute(
            text("INSERT INTO schema_metadata (id, schema_version) VALUES (1, :version)"),
            {"version": CURRENT_SCHEMA_VERSION},
        )


def ensure_schema_compatible(engine: Engine, metadata: MetaData) -> int:
    """Create, adopt, or reject a database schema before normal store access."""
    expected = _expected_application_columns(metadata)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if not tables:
        with engine.begin() as connection:
            metadata.create_all(bind=connection)
            connection.execute(
                text(
                    "CREATE TABLE schema_metadata ("
                    "id INTEGER PRIMARY KEY, "
                    "schema_version INTEGER NOT NULL"
                    ")"
                )
            )
            connection.execute(
                text("INSERT INTO schema_metadata (id, schema_version) VALUES (1, :version)"),
                {"version": CURRENT_SCHEMA_VERSION},
            )
        return CURRENT_SCHEMA_VERSION

    if SCHEMA_METADATA_TABLE not in tables:
        _validate_application_shape(
            inspector,
            tables,
            expected,
            allow_schema_metadata=False,
        )
        _create_version_metadata(engine)
        return CURRENT_SCHEMA_VERSION

    version = _read_schema_version(engine, inspector)
    if version > CURRENT_SCHEMA_VERSION:
        raise StoreSchemaError(
            f"database schema version {version} is newer than supported "
            f"version {CURRENT_SCHEMA_VERSION}"
        )
    if version < CURRENT_SCHEMA_VERSION:
        raise StoreSchemaError(
            f"database schema version {version} requires a migration to "
            f"version {CURRENT_SCHEMA_VERSION}"
        )
    _validate_application_shape(
        inspector,
        tables,
        expected,
        allow_schema_metadata=True,
    )
    return version
