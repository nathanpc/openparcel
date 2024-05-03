#!/usr/bin/env python3

from scripts import Command, Manager


class HelpCommand(Command):
    """Manager usage command."""
    name = 'help'
    description = 'Prints this exact message'

    def __init__(self, parent: Manager = None):
        super().__init__(parent)

    def run(self):
        self.parent.usage()


if __name__ == '__main__':
    manager = Manager()
    manager.append_command(HelpCommand(manager))
    manager.run()
