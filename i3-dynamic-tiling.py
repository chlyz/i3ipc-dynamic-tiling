#!/usr/bin/env python3

import i3ipc
from i3ipc import Event
import time
import argparse
import logging
import copy
import os
import signal
import sys

###############################################################################
# Argument parser                                                             #
###############################################################################

parser = argparse.ArgumentParser(description=\
        """A Python IPC implementation of dynamic tiling for the i3 window
        manager, trying to mimic the tiling behavior of the excellent DWM and
        XMONAD window managers, while utilizing the strengths of I3 and SWAY.
        """)

parser.add_argument(
        '--log-level',
        nargs='?',
        default='info',
        help="""The logging level: debug, info [default], warning, error, or
        critical.""")

parser.add_argument(
        '--workspaces-ignore',
        nargs='*',
        default='',
        help="""Workspaces to be handled manually as default i3, that is, not
        handled dynamically.""")

parser.add_argument(
        '--workspaces-only',
        nargs='*',
        default='',
        help="""Workspaces to be handled manually dynamical, that is, all other
        workspaces will be handled manually as the default i3. This will
        override the --workspaces-ignore option.""")

parser.add_argument(
        '--opacity-focused',
        default='1',
        help="""The opacity of the focused window.""")

parser.add_argument(
        '--opacity-inactive',
        default='1',
        help="""The opacity of the inactive windows.""")

parser.add_argument(
        '--tabbed-hide-polybar',
        default='false',
        help="""Hide the polybar when in tabbed mode [false, true].""")

args = parser.parse_args()

# Check the logging level argument.
log_level_numeric = getattr(logging, args.log_level.upper(), None)
if not isinstance(log_level_numeric, int):
    raise ValueError('Invalid log level: {}'.format(args.log_level))

if args.tabbed_hide_polybar.upper() not in ['FALSE', 'TRUE']:
    raise ValueError('Invalid hide polybar tabbed argument: {}'\
            .format(args.tabbed_hide_polybar))

# Check the workspace ignore argument.
for w in args.workspaces_ignore:
    if w not in map(str, range(1, 10)):
        raise ValueError('Invalid ignore workspace: {}'.format(args.workspaces_ignore))

# Check the workspace only argument.
for w in args.workspaces_only:
    if w not in map(str, range(1, 10)):
        raise ValueError('Invalid only workspace: {}'.format(args.workspaces_only))

###############################################################################
# Logging                                                                     #
###############################################################################

# Create the logger.
logging.basicConfig(
        format='%(asctime)s %(levelname)s: %(message)s',
        level=log_level_numeric)

###############################################################################
# Global variables                                                            #
###############################################################################

I3DT_VARIANT          = None
I3DT_OPACITY_ACTIVE   = float(args.opacity_focused)
I3DT_OPACITY_INACTIVE = float(args.opacity_inactive)
I3DT_LAYOUT           = dict()
I3DT_GLBL_MARK        = 'I3DT_GLBL_{}'
I3DT_MAIN_MARK        = 'I3DT_MAIN_{}'
I3DT_SCND_MARK        = 'I3DT_SCND_{}'
I3DT_SCND_TBBD_MARK   = 'I3DT_SCND_{}_TBBD_'
I3DT_WINDOW_PREV      = []
I3DT_WINDOW_CURR      = []
I3DT_HIDE_BAR         = True if args.tabbed_hide_polybar.upper() == 'TRUE' else False

# Workspaces to ignore.
I3DT_WORKSPACE_IGNORE = []
if args.workspaces_only:
    I3DT_WORKSPACE_IGNORE = list(map(str, range(1, 10)))
    for w in args.workspaces_only:
        I3DT_WORKSPACE_IGNORE.remove(w)
elif args.workspaces_ignore:
    I3DT_WORKSPACE_IGNORE = args.workspaces_ignore


###############################################################################
# Helper functions                                                            #
###############################################################################

def execute_commands(commands, preamble='Executing:'):
    if commands:
        if preamble: logging.debug(preamble)
        if isinstance(commands, list):
            parsed_commands = [x for x in commands if x]
            commands = parsed_commands
            reply = i3.command('; '.join(commands))
            for i, c in enumerate(commands):
                logging.debug('+ {} => {}'.format(c, reply[i].ipc_data))
                if not reply[i].success:
                    logging.error(reply[i].error)
        else:
            reply = i3.command(commands)
            logging.debug('+ {} => {}'.format(commands, reply[0].ipc_data))
            if not reply[0].success:
                logging.error(reply[0].error)
    return []

def get_workspace_info(i3, workspace=[]):

    if not workspace:
        tree = i3.get_tree()
        focused = tree.find_focused()
        workspace = focused.workspace()

    # Initialize the dictionary.
    key = workspace.name
    main_mark = I3DT_MAIN_MARK.format(key)
    scnd_mark = I3DT_SCND_MARK.format(key)
    glbl_mark = I3DT_GLBL_MARK.format(key)
    tbbd_mark = I3DT_SCND_TBBD_MARK.format(key)
    info = {
            'mode': 'manual',
            'name': workspace.name,
            'layout': workspace.layout,
            'children': [],
            'tiled': [],
            'floating': [],
            'descendants': [],
            'id': workspace.id,
            'focused': None,
            'fullscreen': False,
            'unmanaged': [],
            'glbl': { 'mark': glbl_mark, 'id': None, 'orientation': 'horizontal', 'layout': 'splith' },
            'main': { 'mark': main_mark, 'fullscreen': 0, 'id': None, 'focus': None, 'layout': 'splitv', 'children': [] },
            'scnd': { 'mark': scnd_mark, 'fullscreen': 0, 'id': None, 'focus': None, 'layout': 'splitv', 'children': [], 'position': 'right' },
            'tbbd': { 'mark': tbbd_mark, 'indices': [], 'children': [] },
            }

    # Collect workspace information.
    if not key in I3DT_WORKSPACE_IGNORE:
        info['mode'] = 'tiled'

    info['descendants'] = workspace.descendants()
    for c in workspace.leaves():
        info['children'].append(c.id)
        if c.floating and c.floating.endswith('on'):
            info['floating'].append(c.id)
        else:
            info['tiled'].append(c.id)

    main_index = None
    scnd_index = None
    for i, c in enumerate(info['descendants']):
        marks = c.marks
        if c.focused:
            info['focused'] = c.id
            info['fullscreen'] = c.fullscreen_mode
        if glbl_mark in marks:
            info['glbl']['id'] = c.id
            info['glbl']['orientation'] = c.orientation
            info['glbl']['layout'] = c.layout
        elif main_mark in marks:
            info['main']['id'] = c.id
            if c.focus:
                info['main']['focus'] = c.focus[0]
            info['main']['fullscreen'] = c.fullscreen_mode
            info['main']['layout'] = c.layout
            info['main']['children'] = list(d.id for d in c.leaves())
            main_index = i
        elif scnd_mark in marks:
            info['scnd']['id'] = c.id
            if c.focus:
                info['scnd']['focus'] = c.focus[0]
            info['scnd']['fullscreen'] = c.fullscreen_mode
            info['scnd']['layout'] = c.layout
            info['scnd']['children'] = list(d.id for d in c.leaves())
            scnd_index = i
        else:
            for m in marks:
                if m.startswith(tbbd_mark):
                    info['mode'] = 'monocle'
                    info['tbbd']['indices'].append(int(m.split('_')[-1]))
                    info['tbbd']['children'].append(c.id)
                    break

    # Find the secondary container position.
    if main_index and scnd_index:
        orientation = 'horizontal'
        if info['glbl']['orientation']:
            orientation = info['glbl']['orientation']
        if orientation == 'horizontal':
            if main_index < scnd_index:
                info['scnd']['position'] = 'right'
            else:
                info['scnd']['position'] = 'left'
        else:
            if main_index < scnd_index:
                info['scnd']['position'] = 'below'
            else:
                info['scnd']['position'] = 'above'

    # Find unmanaged windows.
    info['unmanaged'] = copy.deepcopy(info['tiled'])
    for i in info['main']['children']:
        info['unmanaged'].remove(i)
    for i in info['scnd']['children']:
        info['unmanaged'].remove(i)

    return info

def rename_secondary_container(info):
    command = []
    command.append('[con_id={}] unmark {}'\
            .format(info['scnd']['id'], info['scnd']['mark']))
    command.append('[con_id={}] mark {}'\
            .format(info['scnd']['id'], info['main']['mark']))
    return command

def restore_container_layout(key, info):
    global I3DT_LAYOUT
    command = []
    if info[key]['id']:
        if info['name'] not in I3DT_LAYOUT:
            I3DT_LAYOUT[info['name']] = { 'main': 'splitv', 'scnd': 'splitv' }
        if not key in I3DT_LAYOUT[info['name']]:
            I3DT_LAYOUT[info['name']][key] = 'splitv'
        if info[key]['layout'] != I3DT_LAYOUT[info['name']][key]:
            if I3DT_LAYOUT[info['name']][key] == 'stacked':
                command.append('[con_id={}] layout {}'\
                        .format(info[key]['children'][0], 'stacking'))
            else:
                command.append('[con_id={}] layout {}'\
                        .format(info[key]['children'][0],
                            I3DT_LAYOUT[info['name']][key]))
            if I3DT_VARIANT == 'sway':
                if I3DT_LAYOUT[info['name']][key] in ['splith', 'splitv']:
                    for c in info[key]['children']:
                        if c == info['focused']:
                            command.append('[con_id={}] opacity {}'\
                                    .format(c, I3DT_OPACITY_ACTIVE))
                        else:
                            command.append('[con_id={}] opacity {}'\
                                    .format(c, I3DT_OPACITY_INACTIVE))
                else:
                    for c in info[key]['children']:
                        command.append('[con_id={}] opacity {}'\
                                .format(c, I3DT_OPACITY_ACTIVE))
    return command

def save_container_layout(key, info):
    global I3DT_LAYOUT
    if info['name'] not in I3DT_LAYOUT:
        I3DT_LAYOUT[info['name']] = { 'main': 'splitv', 'scnd': 'splitv' }
    if info[key]['id']:
        I3DT_LAYOUT[info['name']][key] = info[key]['layout']

def find_parent_id(con_id, info):
    parent = None
    containers = (c for c in info['descendants'] if not c.name)
    for c in containers:
        for d in c.descendants():
            if d.id == con_id:
                parent = c.id
                break
    return parent

def create_container(i3, name, con_id=None):
    """Create a split container for the specified container id

    Parameters
    ----------
    i3 : i3ipc.Connection
        An i3ipc connection
    name : str
        The name of the target split container
    con_id : int, optional
        The container id that should be contained (default is the
        focused container id)
    """

    logging.debug('Create container: {}'.format(name))

    # Get workspace information.
    info = get_workspace_info(i3)

    # Exit if container already exists.
    if info[name]['id']: raise ValueError('Container already exist!')

    # Get the window that should be contained and make sure it is
    # focused.
    command = []
    focused = info['focused']
    if not con_id:
        con_id = focused
    else:
        command.append('[con_id={}] focus'.format(con_id))

    # Remove any marks that may exist.
    command.append('[con_id={}] unmark'.format(con_id))

    # Move the window outside any other container.
    other = 'main' if name == 'scnd' else 'scnd'
    if con_id in info[other]['children']:
        if info['glbl']['id']:
            command.append('move to mark {}; splitv'\
                    .format(info['glbl']['mark']))
        else:
            if other == 'main':
                move = 'right'
                if info['layout'] in ['splitv', 'stacked']:
                    move = 'down'

                # Move the to the edge of the container.
                for [ind, cid] in enumerate(info['main']['children']):
                    if info['focused'] == cid: break
                layout = info['main']['layout']
                if (layout in ['splith', 'tabbed'] and move == 'right')\
                        or (layout in ['splitv', 'stacked'] and move == 'down'):
                    for n in range(1, len(info['main']['children']) - ind):
                        command.append('move {}'.format(move))
            else:
                move = 'left'
                if info['layout'] in ['splitv', 'stacked']:
                    move = 'up'

                # Move the to the edge of the container.
                for [ind, cid] in enumerate(info['scnd']['children']):
                    if info['focused'] == cid: break
                layout = info['main']['layout']
                if (layout in ['splith', 'tabbed'] and move == 'left')\
                        or (layout in ['splitv', 'stacked'] and move == 'up'):
                    for n in range(1, num + 1):
                        command.append('move {}'.format(move))

            # Move outside the split container.
            command.append('move {}'.format(move))
            # TODO: Add option to set default split size
            # TODO: Add variables to remember the split size
            if info['layout'] in ['splitv', 'stacked']:
                command.append('splith')
                command.append('resize set height 50 ppt')
            else:
                command.append('splitv')
                command.append('resize set width 50 ppt')
    else:
        command.append('[con_id={}] splitv'.format(con_id))
    command = execute_commands(command, '')

    # Find and mark the newly created split container.
    info = get_workspace_info(i3)
    parent = find_parent_id(con_id, info)
    command.append('[con_id={}] mark {}'\
            .format(parent, info[name]['mark']))

    # Make sure that the newly created container is in the global split
    # container.
    if info['glbl']['id']:
        command.append('[con_id={}] move to mark {}'\
                .format(parent, info['glbl']['mark']))
        if name == 'main' and info['scnd']['id']:
            command.append('[con_id={}] swap container with con_id {}'\
                    .format(parent, info['scnd']['id']))

    command = execute_commands(command, '')

def find_parent_container_key(info, con_id=None):
    key = None
    if not con_id:
        con_id = info['focused']
    if info['main']['id'] and con_id in info['main']['children']:
        key = 'main'
    elif info['scnd']['id'] and con_id in info['scnd']['children']:
        key = 'scnd'
    return key

def find_parent_container(info):
    parent = None
    children = []
    if info['focused'] in info['main']['children']:
        parent = info['main']['id']
        layout = info['main']['layout']
        children = info['main']['children']
    elif info['focused'] in info['scnd']['children']:
        parent = info['scnd']['id']
        layout = info['scnd']['layout']
        children = info['scnd']['children']
    else:
        parent = info['id']
        layout = info['layout']
        children = info['tiled']
    return parent, layout, children

def find_container_index(info, con_ids=None):
    if not con_ids:
        con_ids = info['tiled']
    ind = 0;
    for c in con_ids:
        if c == info['focused']:
            break
        ind += 1
    return ind

def get_movement(layout, direction):
    if direction == 'next':
        if layout in ['splith', 'tabbed']:
            movement = 'right'
        else:
            movement = 'down'
    elif direction == 'prev':
        if layout in ['splith', 'tabbed']:
            movement = 'left'
        else:
            movement = 'up'
    return movement


def i3dt_focus(i3, e):
    action = e.binding.command.split(" ")[-1]
    logging.info('Window::Focus::{}'.format(action.title()))
    info = get_workspace_info(i3)
    key = find_parent_container_key(info)
    is_monocle = i3dt_monocle_enabled(key, info)
    command = []
    if action in ['next', 'prev']:
        children = info['tiled']
        if key and is_monocle:
            children = info[key]['children']
        index = find_container_index(info, children)
        length = len(children)
        if length > 1:
            if action == 'next':
                command.append('[con_id={}] focus'\
                        .format(children[(index + 1) % length]))
            elif action == 'prev':
                command.append('[con_id={}] focus'\
                        .format(children[(index - 1) % length]))
        elif is_monocle:
            command.extend(i3dt_monocle_disable_commands(key, info))
    elif action == 'other':
        if info['scnd']['id']:
            if is_monocle:
                command.extend(i3dt_monocle_disable_commands(key, info))
            other = 'main' if key == 'scnd' else 'scnd'
            command.append('[con_id={}] focus'.format(info[other]['focus']))
        else:
            logging.warning('Window::Focus::Other::No other container')
    elif action == 'toggle':
        if is_monocle and (not key or \
                not I3DT_WINDOW_PREV in info[key]['children']):
            command.extend(i3dt_monocle_disable_commands(key, info))
        if I3DT_WINDOW_PREV:
            command.append('[con_id={}] focus'.format(I3DT_WINDOW_PREV))
        else:
            logging.warning('Window::Focus::Toggle::No previous window')
    execute_commands(command, '')


def i3dt_move(i3, e):
    action = e.binding.command.split(" ")[-1]
    logging.info('Window::Move::{}'.format(action.title()))
    info = get_workspace_info(i3)
    command = []
    if action in ['next', 'prev']:
        # Find the position of the focused window in the list of all windows
        # and only perform the movement if it keeps the window within the
        # container.
        parent, layout, children = find_parent_container(info)
        if children:
            movement = get_movement(layout, action)
            if action == 'next':
                if not info['focused'] == children[-1]:
                    command.append('move {}'.format(movement))
            elif action == 'prev':
                if not info['focused'] == children[0]:
                    command.append('move {}'.format(movement))
    elif action == 'other':
        # Find the parent container of the window and then move the window to
        # the other container. Make sure that the main container does not
        # become empty.
        if info['focused'] in info['main']['children']:
            if len(info['main']['children']) == 1:
                if info['scnd']['id']:
                    command.append('[con_id={}] focus'\
                            .format(info['scnd']['children'][0]))
                    command.append('swap container with con_id {}'\
                            .format(info['focused']))
            elif info['scnd']['id']:
                command.append('[con_id={}] move to mark {}'\
                        .format(info['focused'], info['scnd']['mark']))
                command.append('[con_id={}] focus; focus child'\
                        .format(info['main']['id']))
            else:
                create_container(i3, 'scnd')
        else:
            command.append('[con_id={}] move to mark {}'\
                    .format(info['focused'], info['main']['mark']))
            command.append('[con_id={}] focus; focus child'\
                    .format(info['scnd']['id']))
    elif action == 'swap':
        if info['focused'] in info['main']['children'] and info['scnd']['id']:
            command.append('[con_id={}] focus'.format(info['scnd']['focus']))
        # else:
        #     command.append('[con_id={}] focus'.format(info['main']['focus']))
        command.append('swap container with con_id {}'\
                .format(info['focused']))

    execute_commands(command, '')


def i3dt_tabbed_toggle(i3, e):
    logging.info('Workspace::Tabbed')

    global I3DT_LAYOUT
    info = get_workspace_info(i3)
    if info['mode'] == 'manual': return
    if info['mode'] == 'monocle':
        i3dt_monocle_toggle(i3)
        return
    command = []
    if info['layout'] == 'tabbed' or info['glbl']['layout'] == 'tabbed':
        if I3DT_HIDE_BAR: os.system("polybar-msg cmd show 1>/dev/null")
        if info['scnd']['id']:
            command.append('[con_id={}] layout toggle split'.\
                    format(info['scnd']['id']))
        for k in ['main', 'scnd']:
            command.extend(restore_container_layout(k, info))
        execute_commands(command, '')
    elif info['mode'] == 'tiled':
        if I3DT_HIDE_BAR: os.system("polybar-msg cmd hide 1>/dev/null")
        for k in ['main', 'scnd']:
            save_container_layout(k, info)
            command.append('[con_id={}] layout tabbed'\
                    .format(info[k]['children'][0]))
        if info['scnd']['id']:
            command.append('[con_id={}] layout tabbed'.\
                    format(info['scnd']['id']))
        execute_commands(command, '')

        # Find the newly created split container and mark it.
        if not I3DT_VARIANT == 'sway':
            info = get_workspace_info(i3)
            if not info['glbl']['id']:
                glbl = info['descendants'][0].id
                execute_commands('[con_id={}] mark {}'\
                        .format(glbl, info['glbl']['mark']), '')



def i3dt_monocle_disable_commands(key, info):
    """Generate a list of i3 commands to disable the monocle mode.

    Parameters
    ----------
    key : str
        The name of the split container of the focused window
    info : dict
        The current workspace information dictionary

    Returns
    -------
    list
        List of commands to run
    """
    commands = []
    if not key and info['fullscreen']:
        commands.append('fullscreen disable')
    elif info[key]['id'] and info[key]['fullscreen']:
        commands.extend(restore_container_layout(key, info))
        commands.append('[con_id={}] fullscreen toggle'.format(info[key]['id']))
    return commands



def i3dt_monocle_enable_commands(key, info):
    """Generate a list of i3 commands to enable the monocle mode.

    Parameters
    ----------
    key : str
        The name of the split container of the focused window
    info : dict
        The current workspace information dictionary

    Returns
    -------
    list
        List of commands to run
    """
    commands = []
    if not key and not info['fullscreen']:
        commands.append('fullscreen enable')
    elif key and info[key]['id'] and not info[key]['fullscreen']:
        save_container_layout(key, info)
        if not info[key]['layout'] == 'tabbed'\
                and (len(info[key]['children']) > 1):
            commands.append('layout tabbed')
            if I3DT_VARIANT == 'sway':
                for c in info[key]['children']:
                    commands.append('[con_id={}] opacity {}'\
                            .format(c, I3DT_OPACITY_ACTIVE))
        commands.append('[con_id={}] fullscreen toggle'.format(info[key]['id']))
        if not I3DT_VARIANT == 'sway':
            commands.append('focus child')
    return commands



def i3dt_monocle_toggle_commands(key, info):
    """Generate a list of i3 commands to toggle the monocle mode.

    Parameters
    ----------
    key : str
        The name of the split container of the focused window
    info : dict
        The current workspace information dictionary

    Returns
    -------
    list
        List of commands to run
    """
    commands = []
    if i3dt_monocle_enabled(key, info):
        commands = i3dt_monocle_disable_commands(key, info)
    else:
        commands = i3dt_monocle_enable_commands(key, info)
    return commands



def i3dt_monocle_enabled(key, info):
    """Check if monocle mode is enabled.

    Parameters
    ----------
    key : str
        The name of the split container of the focused window
    info : dict
        The current workspace information dictionary

    Returns
    -------
    bool
        True if monocle mode is enabled, False otherwise.
    """
    enabled = False
    if not key and info['fullscreen']:
        enabled = True
    elif key and info[key]['id'] and info[key]['fullscreen']:
        enabled = True
    return enabled



def i3dt_monocle_toggle(i3):
    """Toggle the monocle mode on or off

    Parameters
    ----------
    i3 : i3ipc.Connection
        An i3ipc connection
    """
    logging.info('Workspace::Monocle')
    info = get_workspace_info(i3)
    key = find_parent_container_key(info)
    commands = i3dt_monocle_toggle_commands(key, info)
    execute_commands(commands, '')



def i3dt_mirror(i3):
    logging.info('Workspace::Mirror')
    info = get_workspace_info(i3)
    if info['scnd']['id'] and info['mode'] == 'tiled':
        execute_commands('[con_id={}] swap container with con_id {}'\
                .format(info['main']['id'], info['scnd']['id']))


def i3dt_reflect(i3):
    logging.info('Workspace::Reflect')
    info = get_workspace_info(i3)
    command = []
    if info['scnd']['id'] and info['mode'] == 'tiled':
        # Toggle split on the second container to create a workspace global
        # split container.
        command.append('[con_id={}] layout toggle split'\
                .format(info['scnd']['id']))
        # Sway does not create a global split container as i3 does.
        if not I3DT_VARIANT == 'sway' and not info['glbl']['id']:
            command = execute_commands(command)
            info = get_workspace_info(i3)
            command.append('[con_id={}] mark {}'\
                    .format(info['descendants'][0].id, info['glbl']['mark']))
        # Update the layout of the containers.
        command = execute_commands(command)
        info = get_workspace_info(i3)
        orientation = 'horizontal'
        if I3DT_VARIANT == 'sway' and info['layout'] == 'splitv':
            orientation = 'vertical'
        else:
            orientation = info['glbl']['orientation']
        for k in ['main', 'scnd']:
            layout = info[k]['layout']
            if (layout == 'splitv' and orientation == 'vertical')\
                    or (layout == 'splith' and orientation == 'horizontal'):
                command.append('[con_id={}] layout toggle split'\
                        .format(info[k]['children'][0]))
        execute_commands(command, '')

def i3dt_kill(i3, e):
    logging.info('Window::Close')
    info = get_workspace_info(i3)
    if info['mode'] == 'manual': return
    # floating = e.container.floating
    # if floating and floating.endswith('on'): return
    command = []
    if info['focused'] in info['main']['children']\
            and (len(info['main']['children']) == 1)\
            and info['scnd']['id']:
        command.append('[con_id={}] swap container with con_id {}'\
                .format(info['focused'], info['scnd']['children'][0]))
    execute_commands(command)


def on_window_close(i3, e):
    logging.info('Window::Close')
    floating = e.container.floating
    if floating and floating.endswith('on'): return
    info = get_workspace_info(i3)
    if info['mode'] == 'manual': return
    command = []
    if not info['main']['id'] and info['scnd']['id']:
        if len(info['scnd']['children']) == 1:
            command.extend(rename_secondary_container(info))
        else:
            con_id = info['scnd']['children'][0]
            create_container(i3, 'main', con_id)
            command.append('[con_id={}] focus'.format(con_id))
    execute_commands(command)


def on_workspace_focus(i3, e):
    global I3DT_LAYOUT
    logging.info('Workspace::Focus::{}'.format(e.current.name))
    info = get_workspace_info(i3, e.current)
    command = []
    if not info['mode'] == 'manual':
        if info['glbl']['layout'] == 'tabbed' or info['mode'] == 'monocle':
            if I3DT_HIDE_BAR: os.system("polybar-msg cmd hide 1>/dev/null")
        else:
            if I3DT_HIDE_BAR: os.system("polybar-msg cmd show 1>/dev/null")
        if info['name'] not in I3DT_LAYOUT:
            I3DT_LAYOUT[info['name']] = { 'main': 'splitv', 'scnd': 'splitv' }
        if info['unmanaged']:
            if info['main']['id']:
                if not info['scnd']['id']:
                    create_container(i3, 'scnd', info['unmanaged'][0])
            elif len(info['unmanaged']) > 1:
                unmanaged = info['unmanaged']
                create_container(i3, 'main', unmanaged[0])
                create_container(i3, 'scnd', unmanaged[1])
            info = get_workspace_info(i3)
            for i in info['unmanaged']:
                command.append('[con_id={}] move to mark {}'\
                        .format(i, info['scnd']['mark']))
    else:
        if I3DT_HIDE_BAR: os.system("polybar-msg cmd show 1>/dev/null")
    execute_commands(command)


def on_window_new(i3, e):

    logging.info('Window::New')
    info = get_workspace_info(i3)

    if info['mode'] == 'manual' \
            or (e.container.name and e.container.name.startswith('polybar')) \
            or (e.container.floating and e.container.floating.endswith('on')) \
            or len(info['tiled']) < 2:
        # or not e.container.name \
        return

    command = []
    if not info['main']['id']:
        create_container(i3, 'main', info['tiled'][0])
        create_container(i3, 'scnd', info['tiled'][1])
    elif not info['scnd']['id']:
        if info['mode'] == 'monocle':
            index = 0
            if info['tbbd']['indices']:
                index = max(info['tbbd']['indices']) + 1
            execute_commands('mark {}'\
                    .format(info['tbbd']['mark'] + str(index)))
        else:
            create_container(i3, 'scnd')
    else:
        if info['focused'] in info['main']['children']:
            commands = []
            commands.append('[con_id={}] move to mark {}'\
                    .format(info['focused'], info['scnd']['mark']))
            commands.append('[con_id={}] focus'\
                    .format(info['focused']))
            execute_commands(commands, '')


def on_window_focus(i3, e):
    global I3DT_WINDOW_PREV
    global I3DT_WINDOW_CURR

    logging.info('Window::Focus')
    I3DT_WINDOW_PREV = I3DT_WINDOW_CURR
    I3DT_WINDOW_CURR = e.container.id
    command = []
    if I3DT_VARIANT == 'sway' and I3DT_WINDOW_PREV:
        info = get_workspace_info(i3)
        prev_key = find_parent_container_key(info, I3DT_WINDOW_PREV)
        if prev_key:
            logging.info('Window::Opacity')
            curr_key = find_parent_container_key(info)
            if not curr_key == prev_key\
                    or info[curr_key]['layout'] in ['splith', 'splitv']:
                command.append('[con_id={}] opacity {}'\
                        .format(I3DT_WINDOW_PREV, I3DT_OPACITY_INACTIVE))
        command.append('[con_id={}] opacity {}'\
                .format(I3DT_WINDOW_CURR, I3DT_OPACITY_ACTIVE))
        execute_commands(command, '')


def on_window_floating(i3, e):
    logging.info('Window::Floating')
    info = get_workspace_info(i3)
    if info['mode'] == 'manual': return
    command = []
    if e.container.floating == 'user_off':
        if info['scnd']['id']:
            command.append('move to mark {}'\
                    .format(info['scnd']['mark']))
        elif info['main']['id']:
            create_container(i3, 'scnd')
        else:
            if len(info['unmanaged']) > 1:
                unmanaged = info['unmanaged']
                create_container(i3, 'main', unmanaged[0])
                create_container(i3, 'scnd', unmanaged[1])
                info = get_workspace_info(i3)
                for c in info['unmanaged']:
                    command.append('[con_id={}] move to mark {}'\
                            .format(c, info['scnd']['id']))
    elif not info['main']['id'] and info['scnd']['id']:
        if len(info['scnd']['children']) == 1:
            command.extend(rename_secondary_container(info))
        else:
            create_container(i3, 'main', info['scnd']['children'][0])
    execute_commands(command)


def on_window_move(i3, e):
    logging.info('Window:move')
    info = get_workspace_info(i3)
    if info['mode'] == 'manual': return
    command = []
    if not info['main']['id'] and info['scnd']['id']:
        if len(info['scnd']['children']) == 1:
            command.extend(rename_secondary_container(info))
        else:
            create_container(i3, 'main', info['scnd']['children'][0])
    execute_commands(command)


def i3dt_layout(i3, e):
    logging.info('Container::Layout')
    if not I3DT_VARIANT == 'sway':
        execute_commands(['layout toggle tabbed split'], '')
        return
    info = get_workspace_info(i3)
    key = find_parent_container_key(info)
    if key:
        command = []
        opacity = I3DT_OPACITY_ACTIVE
        if info[key]['layout'] in ['splith', 'splitv']:
            opacity = I3DT_OPACITY_INACTIVE
        for c in info[key]['children']:
            if not c == info['focused']:
                command.append('[con_id={}] opacity {}'.format(c, opacity))
        command.append('[con_id={}] opacity {}'\
                .format(info['focused'], I3DT_OPACITY_ACTIVE))
        execute_commands(command, '')



def on_binding(i3, e):
    if e.binding.command.startswith('nop'):
        if e.binding.command.startswith('nop i3dt_focus'):
            i3dt_focus(i3, e)
        elif e.binding.command.startswith('nop i3dt_move'):
            i3dt_move(i3, e)
        elif e.binding.command == 'nop i3dt_reflect':
            i3dt_reflect(i3)
        elif e.binding.command == 'nop i3dt_mirror':
            i3dt_mirror(i3)
        elif e.binding.command == 'nop i3dt_monocle_toggle':
            i3dt_monocle_toggle(i3)
        elif e.binding.command == 'nop i3dt_tabbed_toggle':
            i3dt_tabbed_toggle(i3, e)
    elif e.binding.command == 'kill':
        i3dt_kill(i3, e)
    elif e.binding.command == 'layout toggle tabbed split':
        i3dt_layout(i3, e)


def remove_opacity(i3):
    for workspace in i3.get_tree().workspaces():
        for w in workspace:
            w.command("opacity 1")
    i3.main_quit()
    sys.exit(0)


i3 = i3ipc.Connection()

# Check if i3 or sway.
version = i3.get_version().ipc_data
if 'variant' in version:
    I3DT_VARIANT = version['variant']
else:
    I3DT_VARIANT = 'i3'

# Find the focused window and set opacity for all windows.
tree = i3.get_tree()
leaves = tree.leaves()
command = []
for c in leaves:
    if c.focused:
        I3DT_WINDOW_CURR = c.id
        if I3DT_VARIANT == 'sway':
            command.append('[con_id={}] opacity {}'\
                    .format(c.id, I3DT_OPACITY_ACTIVE))
    else:
        if I3DT_VARIANT == 'sway':
            command.append('[con_id={}] opacity {}'\
                    .format(c.id, I3DT_OPACITY_INACTIVE))
execute_commands(command, '')

for sig in [signal.SIGINT, signal.SIGTERM]:
    signal.signal(sig, lambda signal, frame: remove_opacity(i3))

try:
    i3.on(Event.BINDING, on_binding)
    i3.on(Event.WINDOW_CLOSE, on_window_close)
    i3.on(Event.WINDOW_FLOATING, on_window_floating)
    i3.on(Event.WINDOW_FOCUS, on_window_focus)
    i3.on(Event.WINDOW_MOVE, on_window_move)
    i3.on(Event.WINDOW_NEW, on_window_new)
    i3.on(Event.WORKSPACE_FOCUS, on_workspace_focus)
    i3.main()
finally:
    i3.main_quit()
