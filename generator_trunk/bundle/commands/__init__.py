"""One module per `bundle` subcommand.

Each exposes ``cmd_<verb>(args)`` (the implementation) and ``_main_<verb>(argv)``
(its argparse front end, dispatched from :func:`bundle.cli.main`).
"""
