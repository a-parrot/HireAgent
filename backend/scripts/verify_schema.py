"""Read-only structure verification for databases initialized using sql/01-schema.sql."""

import argparse
import asyncio

from sqlalchemy import Boolean, inspect
from sqlalchemy.dialects.mysql import TINYINT

from app.clients.mysql_client import MySQLClient
from app.core.config import Settings
from app.models.mysql.entities import Base


def verify(connection):
    inspector = inspect(connection)
    differences = []
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            differences.append(table.name + ": table missing")
            continue
        columns = {c["name"]: c for c in inspector.get_columns(table.name)}
        if set(columns) != set(table.columns.keys()):
            differences.append(table.name + ": columns differ")
            continue
        for column in table.columns:
            reflected = columns[column.name]
            if reflected["nullable"] != column.nullable:
                differences.append(
                    table.name + "." + column.name + ": nullability differs"
                )
            # Compare dialect affinity and length; separate client defaults from server defaults.
            expected = column.type.dialect_impl(connection.dialect)
            actual = reflected["type"]
            # MySQL reflects BOOLEAN (an alias) as TINYINT(1).
            boolean_alias = (
                isinstance(expected, Boolean)
                and isinstance(actual, TINYINT)
                and actual.display_width == 1
            )
            if not boolean_alias and (
                actual._type_affinity is not expected._type_affinity
                or getattr(actual, "length", None) != getattr(expected, "length", None)
            ):
                differences.append(table.name + "." + column.name + ": type differs")
        if inspector.get_pk_constraint(table.name)["constrained_columns"] != [
            c.name for c in table.primary_key.columns
        ]:
            differences.append(table.name + ": primary key differs")
        unique = {
            tuple(c["column_names"])
            for c in inspector.get_unique_constraints(table.name)
        }
        from sqlalchemy import UniqueConstraint

        for constraint in table.constraints:
            if (
                isinstance(constraint, UniqueConstraint)
                and tuple(c.name for c in constraint.columns) not in unique
            ):
                differences.append(table.name + ": unique constraint missing")
        actual_fks = {
            (
                tuple(f["constrained_columns"]),
                f["referred_table"],
                tuple(f["referred_columns"]),
            )
            for f in inspector.get_foreign_keys(table.name)
        }
        for fk in table.foreign_key_constraints:
            expected = (
                tuple(e.parent.name for e in fk.elements),
                fk.referred_table.name,
                tuple(e.column.name for e in fk.elements),
            )
            if expected not in actual_fks:
                differences.append(table.name + ": foreign key missing")
    return differences


async def main():
    db = MySQLClient(Settings())
    try:
        async with db.engine.connect() as connection:
            differences = await connection.run_sync(verify)
        if differences:
            raise SystemExit("\n".join(differences))
        print(
            "Columns, types, primary keys, unique keys and foreign keys match baseline."
        )
        print(
            "Also review CHECK constraints/defaults against sql/01-schema.sql before manually stamping revision 008."
        )
    finally:
        await db.close()


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    asyncio.run(main())
