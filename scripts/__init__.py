#!/usr/bin/env python3
import atexit
import sys
from typing import TextIO, TypeVar, Any

# Typing hints.
TCommand = TypeVar('TCommand', bound='Command')


class Argument:
    """Command argument abstraction."""

    def __init__(self, name: str, required: bool = False):
        self.name = name
        self.required = required
        self.value = None
        self.populated = False

    def set_value(self, value):
        """Sets the value passed as the argument."""
        self.value = value
        self.populated = True

    def usage_str(self) -> str:
        """How this argument should be represented in the usage message."""
        if self.required:
            return f'<{self.name}>'

        return f'[{self.name}]'


class Action:
    """Command action abstraction."""
    name: str
    description: str
    arguments: list[Argument] = None
    default: bool = False

    def __init__(self, parent: TCommand = None):
        self.parent = parent

    def perform(self, *args, **kwargs):
        """Performs the action as a proper method."""
        raise NotImplementedError

    def perform_from_cli(self):
        """Performs the action using the supplied command-line arguments."""
        # Check if action requires no arguments at all.
        if self.arguments is None:
            self.perform()
            return

        # Check if we have the required number of arguments.
        num_required = 0
        for arg in self.arguments:
            if arg.required:
                num_required += 1
        if self.argnum() < num_required:
            print('Not enough arguments. This action requires at least '
                  f'{num_required}\n', file=sys.stderr)
            self.parent.usage(out=sys.stderr)
            exit(1)

        # Call the callback function with its arguments.
        self.populate_args()
        args = self._args_list()
        if args is None:
            self.perform()
        self.perform(*args)

    def populate_args(self):
        """Populates the values into the argument objects list."""
        # Do we even have anything to populate?
        if self.argnum() == 0:
            return

        # Go through the arguments that were passed in to us.
        index = 0
        first = len(sys.argv) - self.parent.argnum() + 1
        for arg in self.arguments:
            arg.set_value(self.parse_arg(index, sys.argv[first + index]))
            index += 1

            if first + index == len(sys.argv):
                return

    def parse_arg(self, index: int, value: str) -> Any:
        """Parses the argument at the index and returns the parsed value."""
        return value

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

    def argnum(self) -> int:
        """Gets the number of arguments passed to the action."""
        return self.parent.argnum() - 1

    def _args_list(self) -> list | None:
        """Gets the list of argument values."""
        # No arguments.
        if self.arguments is None:
            return None
        if len(self.arguments) == 0:
            return None

        # Build up the arguments list.
        args = []
        for arg in self.arguments:
            # Stop as soon as a value is not populated.
            if arg.populated is None:
                return args

            # Append the value to the arguments list.
            args.append(arg.value)

        return args


class HelpAction(Action):
    """Default action to display the usage message."""
    name = 'help'
    description = 'This current output'

    def __init__(self):
        super().__init__()

    def perform(self):
        self.parent.usage()


class Command:
    """Common command-line utility script interface."""
    name: str

    def __init_subclass__(cls, **kwargs):
        # Implement a method to have our post init method always called.
        def init_decorator(prev_init):
            def new_init(self, *args, **_kwargs):
                prev_init(self, *args, **_kwargs)
                self._post_init_()
            return new_init

        cls.__init__ = init_decorator(cls.__init__)

    def __init__(self, parent: str = None):
        self.parent: str = parent
        self.actions: list[Action] = []

    def _post_init_(self):
        """Method that should always be called after the initialization of an
        object. Even subclasses."""
        self.add_action(HelpAction())

    def perform_action(self, action_name: str, *args, **kwargs):
        """Performs an action from this command."""
        for action in self.actions:
            if action.name == action_name:
                action.perform(*args, **kwargs)
                return

        raise RuntimeError(f'Requested action {action_name} does not exist.')

    def run(self):
        """Runs the command."""
        # Perform the default action.
        if self.argnum() == 0:
            for action in self.actions:
                if action.default:
                    action.perform_from_cli()
                    return

            # In case we have no default action.
            self.usage(sys.stderr)
            exit(1)

        # Perform the requested action.
        req_action = sys.argv[1].lower()
        for action in self.actions:
            if action.name == req_action:
                action.perform_from_cli()
                return

        # Looks like it was an invalid action.
        print(f'Unknown action {req_action}.\n', file=sys.stderr)
        self.usage(sys.stderr)
        exit(1)

    def add_action(self, action: Action):
        """Add an action to the command."""
        action.parent = self
        self.actions.append(action)

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

    def argnum(self) -> int:
        """Gets the number of arguments passed to the command."""
        if self.parent is not None:
            return len(sys.argv) - 2
        return len(sys.argv) - 1

    def _exit_handler(self):
        """Performs a couple of important tasks before exiting the program."""
        raise NotImplementedError
