# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2019-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""This module is a collection of miscellaneous functions that interact with project paths."""

import os
import sys
from pathlib import Path
from pepclibs.helperlibs.Exceptions import ErrorNotFound

def get_project_data_envvar(prjname):
    """
    Return the name of the environment variable that points to the data location of project
    'prjname'.
    """

    name = prjname.replace("-", "_").upper()
    return f"{name}_DATA_PATH"

def get_project_helpers_envvar(prjname):
    """
    Return the name of the environment variable that points to the helper programs location of
    project 'prjname'.
    """

    name = prjname.replace("-", "_").upper()
    return f"{name}_HELPERSPATH"

def find_project_data(prjname, subpath, what=None):
    """
    Search for project 'prjname' data. The data are searched for in the 'subpath' sub-path of
    the following directories (and in the following order).
      * in the directory the of the running program.
      * in the directory specified by the '<prjname>_DATA_PATH' environment variable.
      * in '$HOME/.local/share/<prjname>/', if it exists.
      * in '/usr/local/share/<prjname>/', if it exists.
      * in '/usr/share/<prjname>/', if it exists.

    The 'what' argument is a human-readable description of 'subpath' (or what is searched for),
    which will be used in the error message if an error occurs.
    """

    searched = []
    paths = []

    paths.append(Path(sys.argv[0]).parent)

    path = os.environ.get(get_project_data_envvar(prjname))
    if path:
        paths.append(Path(path))

    for path in paths:
        path /= subpath
        if path.exists():
            return path
        searched.append(path)

    path = Path.home() / Path(f".local/share/{prjname}/{subpath}")
    if path.exists():
        return path

    searched.append(path)

    for path in (Path(f"/usr/local/share/{prjname}"), Path(f"/usr/share/{prjname}")):
        path /= subpath
        if path.exists():
            return path
        searched.append(path)

    if not what:
        what = f"'{subpath}'"
    searched = [str(s) for s in searched]
    dirs = " * " + "\n * ".join(searched)

    raise ErrorNotFound(f"cannot find {what}, searched in the following locations:\n{dirs}")

def get_project_data_search_descr(prjname, subpath):
    """
    This method returns a human-readable string describing the locations the 'find_project_data()'
    function looks for the data at.
    """

    envvar = get_project_data_envvar(prjname)
    paths = (f"{Path(sys.argv[0]).parent}/{subpath}",
             f"${envvar}/{subpath}",
             f"$HOME/.local/share/{prjname}/{subpath}",
             f"/usr/local/share/{prjname}/{subpath}",
             f"/usr/share/{prjname}/{subpath}")

    return ", ".join(paths)

def find_project_helper(prjname, helper):
    """
    Search for a helper program 'helper' belonging to the 'prjname' project. The helper program is
    searched for in the following locations (and in the following order).
      * in the paths defined by the 'PATH' environment variable.
      * in the directory the of the running program.
      * in the directory specified by the '<prjname>_HELPERSPATH' environment variable.
      * in '$HOME/.local/bin/', if it exists.
      * in '/usr/local/bin/', if it exists.
      * in '/usr/bin', if it exists.
    """

    from pepclibs.helperlibs import LocalProcessManager # pylint: disable=import-outside-toplevel

    with LocalProcessManager.LocalProcessManager() as lpman:
        exe_path = lpman.which(helper, must_find=False)
        if exe_path:
            return exe_path

    searched = ["$PATH"]
    paths = [Path(sys.argv[0]).parent]

    path = os.environ.get(get_project_helpers_envvar(prjname))
    if path:
        paths.append(Path(path))

    paths.append(Path.home() / Path(".local/bin"))
    paths.append(Path("/usr/local/bin"))
    paths.append(Path("/usr/bin"))

    for path in paths:
        exe_path = path / helper
        if exe_path.exists():
            return exe_path
        searched.append(str(path))

    dirs = " * " + "\n * ".join(searched)
    raise ErrorNotFound(f"cannot find the '{helper}' program, searched in the following "
                        f"locations:\n{dirs}")