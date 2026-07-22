"""A tool used to convert users database in other format into PyFSD's format."""

import sys
from argparse import ArgumentParser

from argon2 import PasswordHasher
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from typing_extensions import TypedDict

from pyfsd.db_tables import users_table
from pyfsd.define.check_dict import assert_dict

from .formats import formats

if sys.version_info >= (3, 11):
    from tomllib import load
else:
    from tomli import load  # type: ignore[import-not-found, unused-ignore]


def main() -> None:
    """Main function of the tool."""
    parser = ArgumentParser(
        description="convert users database in other format into PyFSD's format"
    )
    parser.add_argument("filename", help="filename of the original file")
    parser.add_argument(
        "format",
        help="format of the original file",
        choices=["cfcsim", "pyfsd", "fsd"],
    )
    parser.add_argument(
        "-v", "--verbose", help="increase output verbosity", action="store_true"
    )
    parser.add_argument(
        "-c", "--config-path", help="path to the config of PyFSD", default="pyfsd.toml"
    )
    args = parser.parse_args()

    with open(args.config_path, "rb") as config_file:
        config = load(config_file)

    assert_dict(
        config,
        TypedDict(  # type: ignore[operator]
            "BasicConfig",
            {
                "pyfsd": TypedDict(  # type: ignore[operator]
                    "BasicPyFSDConfig",
                    {
                        "database": TypedDict(  # type: ignore[operator]
                            "BasicDatabaseConfig",
                            {"url": str},
                            extra_items=object,
                        ),
                    },
                    extra_items=object,
                )
            },
            extra_items=object,
        ),
    )

    reader = formats[args.format]
    users = reader.read_all(args.filename)
    db_engine = create_engine(config["pyfsd"]["database"]["url"])
    hasher = PasswordHasher()
    import_users = 0

    with db_engine.connect() as conn:
        for user in users:
            if args.verbose:
                print("Converting", *user)
            try:
                conn.execute(
                    users_table.insert().values(
                        user
                        if reader.argon2_hashed
                        else (user[0], hasher.hash(user[1]), user[2])
                    )
                )
            except IntegrityError:
                print("Callsign already exist:", user[0])
            else:
                import_users += 1
        conn.commit()

    print(f"Done. ({import_users})")
