#!/usr/bin/env python3
import atexit
import sys
from typing import TextIO, Callable


class Argument:
    """Command argument abstraction."""

    def __init__(self, name: str, required: bool = False):
        self.name = name
        self.required = required

    def usage_str(self) -> str:
        """How this argument should be represented in the usage message."""
        if not self.required:
            return f'[{self.name}]'

        return self.name


class Action:
    """Command action abstraction."""

    def __init__(self, name: str, description: str,
                 arguments: list[Argument] = None, callback: callable = None):
        self.name: str = name
        self.description: str = description
        self.arguments: list[Argument] = arguments
        self.callback: Callable[[Argument], None] = callback

    def usage_short(self) -> str:
        """How this action should be summarized in the usage message."""
        usage = f'{self.name} '

        # Is the usage just the action name?
        if self.arguments is None:
            return usage

        # Build up the arguments list.
        for arg in self.arguments:
            usage += f'{arg.usage_str()} '

        return usage

    def usage_long(self, padding: int = 0) -> str:
        """How this argument should be represented in the usage message."""
        return f'\t{self.usage_short().ljust(padding)} -  {self.description}.'


class Command:
    """Common command-line utility script interface."""
    name: str

    def __init__(self, parent: str = None):
        self.parent: str = parent
        self.actions: list[Action] = []

        # Add default actions.
        self.add_action('help', 'This current output', fn=self._show_help())

    def run(self):
        """Runs the command."""
        self.usage()

    def add_action(self, name: str, description: str,
                   args: list[Argument] = None, fn: callable = None):
        """Add an action to the command."""
        self.actions.append(Action(name, description, args, fn))

    def usage(self, out: TextIO = sys.stdout):
        """Prints a message on how to use this command."""
        # Define the correct usage name pattern.
        command = sys.argv[0]
        if self.parent is not None:
            command = f'{self.parent} {command}'

        # Get the actions padding.
        padding = 0
        for action in self.actions:
            if len(action.usage_short()) > padding:
                padding = len(action.usage_short())

        # Print out the usage message.
        print(f'usage: {command} action [options]', file=out)
        print(file=out)
        print('Available actions:', file=out)
        for action in self.actions:
            print(action.usage_long(padding), file=out)

    def enable_exit_handler(self):
        """This command uses an exit handler."""
        atexit.register(self._exit_handler)

    def _exit_handler(self):
        """Performs a couple of important tasks before exiting the program."""
        raise NotImplementedError

    def _show_help(self):
        """Prints the usage message."""
        self.usage()
