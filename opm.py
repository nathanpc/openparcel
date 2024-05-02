#!/usr/bin/env python3

import inspect
import os
import sys
from typing import TextIO

import scripts


class HelpCommand(scripts.Command):
    """Manager usage command."""
    name = 'help'
    description = 'Prints this exact message'

    def __init__(self, parent: str = None):
        super().__init__(parent)


class Manager:
    description: str = 'The openparcel manager script'

    def __init__(self):
        self.commands: list[scripts.Command] = []

        # Populate our available commands.
        self.populate_commands()
        self.commands.append(HelpCommand())

    def populate_commands(self):
        """Populates the list of commands we have available."""
        # Load the command modules.
        self._load_modules()

        # Go through the modules looking for the commands.
        for filename, file_obj in inspect.getmembers(sys.modules['scripts']):
            if inspect.ismodule(file_obj):
                # Go through the members of the modules.
                for class_name, mod_obj in inspect.getmembers(file_obj):
                    # Check if it's actually a command class.
                    if (inspect.isclass(mod_obj) and class_name != 'Command' and
                            issubclass(mod_obj, scripts.Command)):
                        self.commands.append(mod_obj())

    def usage(self, out: TextIO = sys.stdout):
        """Prints a message on how to use this command."""

        # Get the actions padding.
        padding = 0
        for cmd in self.commands:
            if len(cmd.usage_short()) > padding:
                padding = len(cmd.usage_short())

        # Print out the usage message.
        print(f'usage: {sys.argv[0]} command [action] [options]', file=out)
        print(file=out)
        print('Available commands:', file=out)
        for cmd in self.commands:
            print(cmd.usage_long(padding), file=out)

    @staticmethod
    def _load_modules():
        """Loads all the scripts modules."""
        for module in os.listdir(os.path.dirname(__file__) + '/scripts'):
            if module == '__init__.py' or module[-3:] != '.py':
                continue
            __import__(f'scripts.{module[:-3]}', locals(), globals())


if __name__ == '__main__':
    manager = Manager()
    manager.usage()
