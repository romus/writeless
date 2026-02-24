#!/usr/bin/env python3
"""Write Less entrypoint."""

from writeless.log import setup as setup_logging

setup_logging()

from writeless.menubar_app import WriteLessApp


if __name__ == "__main__":
    WriteLessApp().run()

