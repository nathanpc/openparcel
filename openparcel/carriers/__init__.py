#!/usr/bin/env python3

from typing import Union

from openparcel.carriers.base import BaseCarrier


def _load_modules():
    """Loads all the modules in the current package."""
    import os
    import sys

    for module in os.listdir(os.path.dirname(__file__)):
        if module == '__init__.py' or module[-3:] != '.py':
            continue
        __import__(f'{sys.modules[__name__].__name__}.{module[:-3]}',
                   locals(), globals())
    del module


def get_carriers() -> list[BaseCarrier.__class__]:
    """Gets a list of all available carrier classes."""
    # Import everything that is required for us to get the list of carriers.
    import sys
    import inspect

    # Cache the carrier list.
    if not hasattr(get_carriers, 'carrier_list'):
        get_carriers.carrier_list = []
    else:
        return get_carriers.carrier_list

    # Go through the modules looking for the carriers.
    for filename, file_obj in inspect.getmembers(sys.modules[__name__]):
        if inspect.ismodule(file_obj):
            # Go through the members of the modules.
            for class_name, mod_obj in inspect.getmembers(file_obj):
                # Check if it's actually a carrier class.
                if (inspect.isclass(mod_obj) and
                        class_name.startswith('Carrier')):
                    get_carriers.carrier_list.append(mod_obj)

    return get_carriers.carrier_list


def get_carrier_names() -> list[str]:
    """Gets a list of all available carrier names."""
    # Cache the carrier name list.
    if not hasattr(get_carrier_names, 'names'):
        get_carrier_names.names = []
    else:
        return get_carrier_names.names

    # Populate the carrier names list.
    for carrier in get_carriers():
        get_carrier_names.names.append(carrier.name)

    return get_carrier_names.names


def get_carrier_from_name(name: str) -> Union[BaseCarrier, None]:
    """Gets a carrier object based on its full name."""
    for carrier in get_carriers():
        if carrier.name == name:
            return carrier

    return None


# Load all the carrier modules.
_load_modules()
