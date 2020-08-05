#!/usr/bin/env python3
"""Dynamic tiling for the I3 and SWAY window managers.

A Python IPC implementation of dynamic tiling for the I3 and SWAY window
managers, trying to mimic the tiling behavior of the excellent DWM and XMONAD
window managers, while utilizing the strengths of I3 and SWAY.  """

import argparse
import copy
import logging
import os
import signal
import sys
import i3ipc
from i3ipc import Event


###############################################################################
# Logging                                                                     #
###############################################################################

# Create the logger.

# logging.basicConfig(
#         format='%(asctime)s %(levelname)s: %(message)s',
#         level=log_level_numeric)

logging.basicConfig(
        format='%(asctime)s %(levelname)s: %(message)s',
        level=0)

###############################################################################
# Global variables                                                            #
###############################################################################

DATA = {
    'initialized': False,
    'opacity': {
        'focused': 1.0,
        'inactive': 1.0
        },
    'variant': None,
    'hide_bar': False,
    'workspace_ignore': []
    }
I3DT_LAYOUT = dict()
FOCUS = {'previous': None, 'current': None}


###############################################################################
# Helper functions                                                            #
###############################################################################

def execute_commands(ipc, commands, preamble='Executing:'):
    """Execute a chain of commands."""
    if commands:
        if preamble:
            logging.debug(preamble)
        if isinstance(commands, list):
            parsed_commands = [x for x in commands if x]
            commands = parsed_commands
            reply = ipc.command('; '.join(commands))
            for ind, cmd in enumerate(commands):
                logging.debug('+ %s => %s', cmd, reply[ind].ipc_data)
                if not reply[ind].success:
                    logging.error(reply[ind].error)
        else:
            reply = ipc.command(commands)
            logging.debug('+ %s => %s', commands, reply[0].ipc_data)
            if not reply[0].success:
                logging.error(reply[0].error)
    return []


def get_workspace_info(ipc, workspace=None):
    """Collect the state of the window manager."""
    if not workspace:
        tree = ipc.get_tree()
        focused = tree.find_focused()
        workspace = focused.workspace()

    # Initialize the dictionary.
    info = {
        'mode': 'manual',
        'name': workspace.name,
        'layout': workspace.layout,
        'children': [],
        'tiled': [],
        'descendants': [],
        'id': workspace.id,
        'focused': None,
        'fullscreen': False,
        'unmanaged': [],
        'glbl': {
            'mark': 'I3DT_GLBL_{}'.format(workspace.name),
            'id': None,
            'orientation': 'horizontal',
            'layout': 'splith'
            },
        'main': {
            'mark': 'I3DT_MAIN_{}'.format(workspace.name),
            'fullscreen': 0,
            'id': None,
            'focus': None,
            'layout': 'splitv',
            'children': []
            },
        'scnd': {
            'mark': 'I3DT_SCND_{}'.format(workspace.name),
            'fullscreen': 0,
            'id': None,
            'focus': None,
            'layout': 'splitv',
            'children': [],
            },
        }

    # Collect workspace information.
    if workspace.name not in DATA['workspace_ignore']:
        info['mode'] = 'tiled'

    info['descendants'] = workspace.descendants()
    for con in workspace.leaves():
        info['children'].append(con.id)
        if not con.floating or not con.floating.endswith('on'):
            info['tiled'].append(con.id)

    for con in info['descendants']:
        marks = con.marks
        if con.focused:
            info['focused'] = con.id
            info['fullscreen'] = con.fullscreen_mode
        if info['glbl']['mark'] in marks:
            info['glbl']['id'] = con.id
            info['glbl']['orientation'] = con.orientation
            info['glbl']['layout'] = con.layout
        for name in ['main', 'scnd']:
            if info[name]['mark'] in marks:
                info[name]['id'] = con.id
                if con.focus:
                    info[name]['focus'] = con.focus[0]
                info[name]['fullscreen'] = con.fullscreen_mode
                info[name]['layout'] = con.layout
                info[name]['children'] = list(d.id for d in con.leaves())

    # Find unmanaged windows.
    info['unmanaged'] = copy.deepcopy(info['tiled'])
    for cid in info['main']['children']:
        info['unmanaged'].remove(cid)
    for cid in info['scnd']['children']:
        info['unmanaged'].remove(cid)

    return info


def rename_secondary_container(info):
    """Rename the secondary container to the main container."""
    command = []
    command.append('[con_id={}] unmark {}'
                   .format(info['scnd']['id'], info['scnd']['mark']))
    command.append('[con_id={}] mark {}'
                   .format(info['scnd']['id'], info['main']['mark']))
    return command


def restore_container_layout(key, info):
    """Restore the saved container layout."""
    if not info[key]['id']:
        return []

    if info['name'] not in I3DT_LAYOUT:
        I3DT_LAYOUT[info['name']] = {'main': 'splitv', 'scnd': 'splitv'}

    commands = []
    if info[key]['layout'] != I3DT_LAYOUT[info['name']][key]:
        if I3DT_LAYOUT[info['name']][key] == 'stacked':
            commands.append('[con_id={}] layout {}'
                            .format(info[key]['children'][0], 'stacking'))
        else:
            commands.append('[con_id={}] layout {}'
                            .format(info[key]['children'][0],
                                    I3DT_LAYOUT[info['name']][key]))
        if DATA['variant'] == 'sway':
            if I3DT_LAYOUT[info['name']][key] in ['splith', 'splitv']:
                for cid in info[key]['children']:
                    if cid == info['focused']:
                        commands.append('[con_id={}] opacity {}'
                                        .format(cid,
                                                DATA['opacity']['focused']))
                    else:
                        commands.append('[con_id={}] opacity {}'
                                        .format(cid,
                                                DATA['opacity']['inactive']))
            else:
                for cid in info[key]['children']:
                    commands.append('[con_id={}] opacity {}'
                                    .format(cid, DATA['opacity']['focused']))
    return commands


def save_container_layout(key, info):
    """Save the container layout."""
    if info['name'] not in I3DT_LAYOUT:
        I3DT_LAYOUT[info['name']] = {'main': 'splitv', 'scnd': 'splitv'}
    if info[key]['id']:
        I3DT_LAYOUT[info['name']][key] = info[key]['layout']


def find_parent_id(con_id, info):
    """Find the parent container id."""
    parent = None
    containers = (con for con in info['descendants'] if not con.name)
    for con in containers:
        for dsc in con.descendants():
            if dsc.id == con_id:
                parent = con.id
                break
    return parent


def create_container(ipc, name, con_id=None):
    """Create a split container for the specified container id.

    Parameters
    ----------
    ipc : i3ipc.Connection
        An i3ipc connection
    name : str
        The name of the target split container
    con_id : int, optional
        The container id that should be contained (default is the
        focused container id)

    """
    logging.debug('Create container: %s', name)

    # Get workspace information.
    info = get_workspace_info(ipc)

    # Exit if container already exists.
    if info[name]['id']:
        raise ValueError('Container already exist!')

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
            command.append('move to mark {}; splitv'
                           .format(info['glbl']['mark']))
        else:
            if other == 'main':
                move = 'right'
                if info['layout'] in ['splitv', 'stacked']:
                    move = 'down'

                # Move the to the edge of the container.
                index = 0
                for cid in info['main']['children']:
                    if info['focused'] == cid:
                        break
                    index += 1
                layout = info['main']['layout']
                if (layout in ['splith', 'tabbed'] and move == 'right') or \
                        (layout in ['splitv', 'stacked'] and move == 'down'):
                    command.extend(['move {}'.format(move)]
                                   * (len(info['main']['children']) - index))
            else:
                move = 'left'
                if info['layout'] in ['splitv', 'stacked']:
                    move = 'up'

                # Move the to the edge of the container.
                index = 0
                for cid in info['scnd']['children']:
                    if info['focused'] == cid:
                        break
                    index += 1
                layout = info['main']['layout']
                if (layout in ['splith', 'tabbed'] and move == 'left') \
                        or (layout in ['splitv', 'stacked'] and move == 'up'):
                    command.extend(['move {}'.format(move)] * (index + 1))

            # Move outside the split container.
            command.append('move {}'.format(move))
            if info['layout'] in ['splitv', 'stacked']:
                command.append('splith')
                command.append('resize set height 50 ppt')
            else:
                command.append('splitv')
                command.append('resize set width 50 ppt')
    else:
        command.append('[con_id={}] splitv'.format(con_id))
    command = execute_commands(ipc, command, '')

    # Find and mark the newly created split container.
    info = get_workspace_info(ipc)
    parent = find_parent_id(con_id, info)
    command.append('[con_id={}] mark {}'
                   .format(parent, info[name]['mark']))

    # Make sure that the newly created container is in the global split
    # container.
    if info['glbl']['id']:
        command.append('[con_id={}] move to mark {}'
                       .format(parent, info['glbl']['mark']))
        if name == 'main' and info['scnd']['id']:
            command.append('[con_id={}] swap container with con_id {}'
                           .format(parent, info['scnd']['id']))

    command = execute_commands(ipc, command, '')


def find_parent_container_key(info, con_id=None):
    """Find parent the container key.

    Parameters
    ----------
    info : dict
        The state of the window manager
    con_id : int, optional
        A container id (default focused)

    """
    key = None
    if not con_id:
        con_id = info['focused']
    if info['main']['id'] and con_id in info['main']['children']:
        key = 'main'
    elif info['scnd']['id'] and con_id in info['scnd']['children']:
        key = 'scnd'
    return key


def find_parent_container(info):
    """Find parent the container.

    Parameters
    ----------
    info : dict
        The state of the window manager

    """
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
    """Find the container index in a list.

    Parameters
    ----------
    info : dict
        The state of the window manager
    con_ids : list, optional
        A list of container id's

    """
    if not con_ids:
        con_ids = info['tiled']
    ind = 0
    for cid in con_ids:
        if cid == info['focused']:
            break
        ind += 1
    return ind


def get_movement(layout, direction):
    """Convert next/prev to an i3/sway movement.

    Parameters
    ----------
    layout : str
        The layout of the container
    direction : str
        The movement next/prev to convert

    """
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


def i3ipc_focus_next_prev(ipc, info, key, is_monocle, direction):
    """Focus the next or previous window with wrapping."""
    command = []
    children = info['tiled']
    if key and is_monocle:
        children = info[key]['children']
    index = find_container_index(info, children)
    length = len(children)
    if length > 1:
        if direction == 'next':
            command.append('[con_id={}] focus'
                           .format(children[(index + 1) % length]))
        elif direction == 'prev':
            command.append('[con_id={}] focus'
                           .format(children[(index - 1) % length]))
    elif is_monocle:
        command.extend(i3ipc_monocle_disable_commands(key, info))
    execute_commands(ipc, command, '')


def i3ipc_focus_other(ipc, info, key, is_monocle):
    """Focus the window in the other container."""
    command = []
    if info['scnd']['id']:
        if is_monocle:
            command.extend(i3ipc_monocle_disable_commands(key, info))
        other = 'main' if key == 'scnd' else 'scnd'
        command.append('[con_id={}] focus'.format(info[other]['focus']))
    else:
        logging.warning('Window::Focus::Other::No other container')
    execute_commands(ipc, command, '')


def i3ipc_focus_toggle(ipc, info, key, is_monocle):
    """Focus the previously focused window."""
    command = []
    if is_monocle and \
            (not key or FOCUS['previous'] not in info[key]['children']):
        command.extend(i3ipc_monocle_disable_commands(key, info))
    if FOCUS['previous']:
        command.append('[con_id={}] focus'.format(FOCUS['previous']))
    else:
        logging.warning('Window::Focus::Toggle::No previous window')
    execute_commands(ipc, command, '')


def i3ipc_focus(ipc, event):
    """Different window focus events.

    Parameters
    ----------
    ipc : i3ipc.Connection
        An i3ipc connection
    event : i3ipc.BindingEvent
        An i3ipc binding event

    """
    action = event.binding.command.split(" ")[-1]
    logging.info('Window::Focus::%s', action.title())
    info = get_workspace_info(ipc)
    key = find_parent_container_key(info)
    is_monocle = i3ipc_monocle_enabled(key, info)
    if action in ['next', 'prev']:
        i3ipc_focus_next_prev(ipc, info, key, is_monocle, action)
    elif action == 'other':
        i3ipc_focus_other(ipc, info, key, is_monocle)
    elif action == 'toggle':
        i3ipc_focus_toggle(ipc, info, key, is_monocle)


def i3ipc_move_next_prev(ipc, info, direction):
    """Move the focused window forward or backward."""
    # Find the position of the focused window in the list of all windows
    # and only perform the movement if it keeps the window within the
    # container.
    _, layout, children = find_parent_container(info)
    command = []
    if children:
        movement = get_movement(layout, direction)
        if direction == 'next':
            if info['focused'] != children[-1]:
                command.append('move {}'.format(movement))
        elif direction == 'prev':
            if info['focused'] != children[0]:
                command.append('move {}'.format(movement))
    execute_commands(ipc, command, '')


def i3ipc_move_other(ipc, info):
    """Move the focused window to the other container."""
    # Find the parent container of the window and then move the window to the
    # other container. Make sure that the main container does not become empty.
    command = []
    if info['focused'] in info['main']['children']:
        if len(info['main']['children']) == 1:
            if info['scnd']['id']:
                command.append('[con_id={}] focus'
                               .format(info['scnd']['children'][0]))
                command.append('swap container with con_id {}'
                               .format(info['focused']))
        elif info['scnd']['id']:
            command.append('[con_id={}] move to mark {}'
                           .format(info['focused'], info['scnd']['mark']))
            command.append('[con_id={}] focus; focus child'
                           .format(info['main']['id']))
        else:
            create_container(ipc, 'scnd')
    else:
        command.append('[con_id={}] move to mark {}'
                       .format(info['focused'], info['main']['mark']))
        command.append('[con_id={}] focus; focus child'
                       .format(info['scnd']['id']))
    execute_commands(ipc, command, '')


def i3ipc_move_swap(ipc, info):
    """Swap the focused window with other container."""
    command = []
    if info['scnd']['id']:
        if info['focused'] in info['scnd']['children']:
            command.append('[con_id={}] focus'
                           .format(info['main']['focus']))
        command.append('swap container with con_id {}'
                       .format(info['scnd']['focus']))
        command.append('[con_id={}] focus'
                       .format(info['scnd']['focus']))
    execute_commands(ipc, command, '')


def i3ipc_move(ipc, event):
    """Different window movements.

    Parameters
    ----------
    ipc : i3ipc.Connection
        An i3ipc connection
    event : i3ipc.BindingEvent
        An i3ipc binding event

    """
    action = event.binding.command.split(" ")[-1]
    logging.info('Window::Move::%s', action.title())
    info = get_workspace_info(ipc)
    if action in ['next', 'prev']:
        i3ipc_move_next_prev(ipc, info, action)
    elif action == 'other':
        i3ipc_move_other(ipc, info)
    elif action == 'swap':
        i3ipc_move_swap(ipc, info)


def i3ipc_tabbed_disable(ipc, info):
    """Disable tabbed mode."""
    if info['layout'] == 'tabbed' or info['glbl']['layout'] == 'tabbed':
        if DATA['hide_bar']:
            os.system("polybar-msg cmd show 1>/dev/null")
        command = []
        if info['scnd']['id']:
            command.append('[con_id={}] layout toggle split'
                           .format(info['scnd']['id']))
        for k in ['main', 'scnd']:
            command.extend(restore_container_layout(k, info))
        execute_commands(ipc, command, '')


def i3ipc_tabbed_enable(ipc, info):
    """Enable tabbed mode."""
    if info['mode'] == 'tiled':
        if DATA['hide_bar']:
            os.system("polybar-msg cmd hide 1>/dev/null")
        command = []
        for k in ['main', 'scnd']:
            if info[k]['id']:
                save_container_layout(k, info)
                command.append('[con_id={}] layout tabbed'
                               .format(info[k]['children'][0]))
        if info['scnd']['id']:
            command.append('[con_id={}] layout tabbed'
                           .format(info['scnd']['id']))
        execute_commands(ipc, command, '')

        # Find the newly created split container and mark it.
        if DATA['variant'] != 'sway':
            info = get_workspace_info(ipc)
            if not info['glbl']['id']:
                glbl = info['descendants'][0].id
                execute_commands(ipc, '[con_id={}] mark {}'
                                 .format(glbl, info['glbl']['mark']), '')


def i3ipc_tabbed_toggle(ipc):
    """Toggle the tabbed mode on or off.

    Parameters
    ----------
    ipc : i3ipc.Connection
        An i3ipc connection

    """
    logging.info('Workspace::Tabbed')
    info = get_workspace_info(ipc)
    if info['mode'] == 'manual':
        return
    if info['mode'] == 'monocle':
        i3ipc_monocle_toggle(ipc)
        return
    if info['layout'] == 'tabbed' or info['glbl']['layout'] == 'tabbed':
        i3ipc_tabbed_disable(ipc, info)
    elif info['mode'] == 'tiled':
        i3ipc_tabbed_enable(ipc, info)


def i3ipc_monocle_disable_commands(key, info):
    """Generate a list of ipc commands to disable the monocle mode.

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
        commands.append('[con_id={}] fullscreen toggle'
                        .format(info[key]['id']))
    return commands


def i3ipc_monocle_enable_commands(key, info):
    """Generate a list of ipc commands to enable the monocle mode.

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
        if info[key]['layout'] != 'tabbed' \
                and (len(info[key]['children']) > 1):
            commands.append('layout tabbed')
            if DATA['variant'] == 'sway':
                for cid in info[key]['children']:
                    commands.append('[con_id={}] opacity {}'
                                    .format(cid, DATA['opacity']['focused']))
        commands.append('[con_id={}] fullscreen toggle'
                        .format(info[key]['id']))
        if DATA['variant'] != 'sway':
            commands.append('focus child')
    return commands


def i3ipc_monocle_toggle_commands(key, info):
    """Generate a list of ipc commands to toggle the monocle mode.

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
    if i3ipc_monocle_enabled(key, info):
        commands = i3ipc_monocle_disable_commands(key, info)
    else:
        commands = i3ipc_monocle_enable_commands(key, info)
    return commands


def i3ipc_monocle_enabled(key, info):
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


def i3ipc_monocle_toggle(ipc):
    """Toggle the monocle mode on or off.

    Parameters
    ----------
    ipc : i3ipc.Connection
        An i3ipc connection

    """
    logging.info('Workspace::Monocle')
    info = get_workspace_info(ipc)
    key = find_parent_container_key(info)
    commands = i3ipc_monocle_toggle_commands(key, info)
    execute_commands(ipc, commands, '')


def i3ipc_mirror(ipc):
    """Mirror the secondary container.

    This function handles the moving the secondary container from one side the
    main container to the other.

    Parameters
    ----------
    ipc : i3ipc.Connection
        An i3ipc connection

    """
    logging.info('Workspace::Mirror')
    info = get_workspace_info(ipc)
    if info['scnd']['id'] and info['mode'] == 'tiled':
        execute_commands(ipc, '[con_id={}] swap container with con_id {}'
                         .format(info['main']['id'], info['scnd']['id']))


def i3ipc_reflect(ipc):
    """Reflect the secondary container.

    This function handles the moving the secondary container between a
    horizontal and vertical position relative to the main container.

    Parameters
    ----------
    ipc : i3ipc.Connection
        An i3ipc connection

    """
    logging.info('Workspace::Reflect')
    info = get_workspace_info(ipc)
    command = []
    if info['scnd']['id'] and info['mode'] == 'tiled':
        # Toggle split on the second container to create a workspace global
        # split container.
        command.append('[con_id={}] layout toggle split'
                       .format(info['scnd']['id']))
        # Sway does not create a global split container as i3 does.
        if DATA['variant'] != 'sway' and not info['glbl']['id']:
            command = execute_commands(ipc, command)
            info = get_workspace_info(ipc)
            command.append('[con_id={}] mark {}'
                           .format(info['descendants'][0].id,
                                   info['glbl']['mark']))
        # Update the layout of the containers.
        command = execute_commands(ipc, command)
        info = get_workspace_info(ipc)
        orientation = 'horizontal'
        if DATA['variant'] == 'sway' and info['layout'] == 'splitv':
            orientation = 'vertical'
        else:
            orientation = info['glbl']['orientation']
        for k in ['main', 'scnd']:
            layout = info[k]['layout']
            if (layout == 'splitv' and orientation == 'vertical') \
                    or (layout == 'splith' and orientation == 'horizontal'):
                command.append('[con_id={}] layout toggle split'
                               .format(info[k]['children'][0]))
        execute_commands(ipc, command, '')


def i3ipc_kill(ipc):
    """Close the focused window.

    This function handles the special case of closing a window when there is a
    single window in the main contianer when there still is a secondary
    container.

    Parameters
    ----------
    ipc : i3ipc.Connection
        An i3ipc connection

    """
    # pylint: disable=unused-argument
    logging.info('Window::Close')
    info = get_workspace_info(ipc)
    if info['mode'] == 'manual':
        return
    command = []
    if info['focused'] in info['main']['children'] \
            and (len(info['main']['children']) == 1) \
            and info['scnd']['id']:
        command.append('[con_id={}] swap container with con_id {}'
                       .format(info['focused'], info['scnd']['children'][0]))
    execute_commands(ipc, command)


def on_window_close(ipc, event):
    """React on window close event.

    Parameters
    ----------
    ipc : i3ipc.Connection
        An i3ipc connection
    event : i3ipc.WindowEvent
        An i3ipc window event

    """
    logging.info('Window::Close')
    floating = event.container.floating
    if floating and floating.endswith('on'):
        return
    info = get_workspace_info(ipc)
    if info['mode'] == 'manual':
        return
    command = []
    if not info['main']['id'] and info['scnd']['id']:
        if len(info['scnd']['children']) == 1:
            command.extend(rename_secondary_container(info))
        else:
            con_id = info['scnd']['children'][0]
            create_container(ipc, 'main', con_id)
            command.append('[con_id={}] focus'.format(con_id))
    execute_commands(ipc, command)


def on_workspace_focus(ipc, event):
    """React on workspace focus event.

    Parameters
    ----------
    ipc : i3ipc.Connection
        An i3ipc connection
    event : i3ipc.WorkspaceEvent
        An i3ipc workspace event

    """
    logging.info('Workspace::Focus::%s', event.current.name)
    info = get_workspace_info(ipc, event.current)
    command = []
    if info['mode'] != 'manual':
        if info['glbl']['layout'] == 'tabbed' or info['mode'] == 'monocle':
            if DATA['hide_bar']:
                os.system("polybar-msg cmd hide 1>/dev/null")
        else:
            if DATA['hide_bar']:
                os.system("polybar-msg cmd show 1>/dev/null")
        if info['name'] not in I3DT_LAYOUT:
            I3DT_LAYOUT[info['name']] = {'main': 'splitv', 'scnd': 'splitv'}
        if info['unmanaged']:
            if info['main']['id']:
                if not info['scnd']['id']:
                    create_container(ipc, 'scnd', info['unmanaged'][0])
            elif len(info['unmanaged']) > 1:
                unmanaged = info['unmanaged']
                create_container(ipc, 'main', unmanaged[0])
                create_container(ipc, 'scnd', unmanaged[1])
            info = get_workspace_info(ipc)
            if info['scnd']['id']:
                for i in info['unmanaged']:
                    command.append('[con_id={}] move to mark {}'
                                   .format(i, info['scnd']['mark']))
    else:
        if DATA['hide_bar']:
            os.system("polybar-msg cmd show 1>/dev/null")
    execute_commands(ipc, command)


def on_window_new(ipc, event):
    """React on window new event.

    Parameters
    ----------
    ipc : i3ipc.Connection
        An i3ipc connection
    event : i3ipc.WindowEvent
        An i3ipc window event

    """
    logging.info('Window::New')
    info = get_workspace_info(ipc)

    window = event.container
    is_bar = window.name and window.name.startswith('polybar')
    is_floating = window.floating and window.floating.endswith('on')
    if info['mode'] == 'manual' or is_bar \
            or is_floating or len(info['tiled']) < 2:
        return

    if not info['main']['id']:
        create_container(ipc, 'main', info['tiled'][0])
        create_container(ipc, 'scnd', info['tiled'][1])
    elif not info['scnd']['id']:
        create_container(ipc, 'scnd')
    else:
        if info['focused'] in info['main']['children']:
            commands = []
            commands.append('[con_id={}] move to mark {}'
                            .format(info['focused'], info['scnd']['mark']))
            commands.append('[con_id={}] focus'
                            .format(info['focused']))
            execute_commands(ipc, commands, '')


def on_window_focus(ipc, event):
    """React on window focus event.

    Parameters
    ----------
    ipc : i3ipc.Connection
        An i3ipc connection
    event : i3ipc.WindowEvent
        An i3ipc window event

    """
    logging.info('Window::Focus')
    FOCUS['previous'] = FOCUS['current']
    FOCUS['current'] = event.container.id
    command = []
    if DATA['variant'] == 'sway' and FOCUS['previous']:
        info = get_workspace_info(ipc)
        prev_key = find_parent_container_key(info, FOCUS['previous'])
        if prev_key:
            logging.info('Window::Opacity')
            curr_key = find_parent_container_key(info)
            if curr_key != prev_key \
                    or info[curr_key]['layout'] in ['splith', 'splitv']:
                command.append('[con_id={}] opacity {}'
                               .format(FOCUS['previous'],
                                       DATA['opacity']['inactive']))
        command.append('[con_id={}] opacity {}'
                       .format(FOCUS['current'], DATA['opacity']['focused']))
        execute_commands(ipc, command, '')


def on_window_floating(ipc, event):
    """React on window floating toggle event.

    Parameters
    ----------
    ipc : i3ipc.Connection
        An i3ipc connection
    event : i3ipc.WindowEvent
        An i3ipc window event

    """
    logging.info('Window::Floating')
    info = get_workspace_info(ipc)
    if info['mode'] == 'manual':
        return
    command = []
    if event.container.floating == 'user_off':
        if info['scnd']['id']:
            command.append('move to mark {}'
                           .format(info['scnd']['mark']))
        elif info['main']['id']:
            create_container(ipc, 'scnd')
        else:
            if len(info['unmanaged']) > 1:
                unmanaged = info['unmanaged']
                create_container(ipc, 'main', unmanaged[0])
                create_container(ipc, 'scnd', unmanaged[1])
                info = get_workspace_info(ipc)
                for cid in info['unmanaged']:
                    command.append('[con_id={}] move to mark {}'
                                   .format(cid, info['scnd']['id']))
    elif not info['main']['id'] and info['scnd']['id']:
        if len(info['scnd']['children']) == 1:
            command.extend(rename_secondary_container(info))
        else:
            create_container(ipc, 'main', info['scnd']['children'][0])
    execute_commands(ipc, command)


def on_window_move(ipc, event):
    """React on window move event.

    Parameters
    ----------
    ipc : i3ipc.Connection
        An i3ipc connection
    event : i3ipc.WindowEvent
        An i3ipc window event

    """
    # pylint: disable=unused-argument
    logging.info('Window:move')
    info = get_workspace_info(ipc)
    if info['mode'] == 'manual':
        return
    command = []
    if not info['main']['id'] and info['scnd']['id']:
        if len(info['scnd']['children']) == 1:
            command.extend(rename_secondary_container(info))
        else:
            create_container(ipc, 'main', info['scnd']['children'][0])
    execute_commands(ipc, command)


def i3ipc_layout(ipc, event):
    """React on layout binding event.

    Parameters
    ----------
    ipc : i3ipc.Connection
        An i3ipc connection
    event : i3ipc.BindingEvent
        An i3ipc binding event

    """
    # pylint: disable=unused-argument
    logging.info('Container::Layout')
    if DATA['variant'] != 'sway':
        return
    info = get_workspace_info(ipc)
    key = find_parent_container_key(info)
    if key:
        command = []
        opacity = DATA['opacity']['focused']
        if info[key]['layout'] in ['splith', 'splitv']:
            opacity = DATA['opacity']['inactive']
        for cid in info[key]['children']:
            if cid != info['focused']:
                command.append('[con_id={}] opacity {}'.format(cid, opacity))
        command.append('[con_id={}] opacity {}'
                       .format(info['focused'], DATA['opacity']['focused']))
        execute_commands(ipc, command, '')


def on_binding(ipc, event):
    """React on selected binding events.

    Parameters
    ----------
    ipc : i3ipc.Connection
        An i3ipc connection
    event : i3ipc.BindingEvent
        An i3ipc binding event

    """
    if event.binding.command.startswith('nop'):
        if event.binding.command.startswith('nop i3ipc_focus'):
            i3ipc_focus(ipc, event)
        elif event.binding.command.startswith('nop i3ipc_move'):
            i3ipc_move(ipc, event)
        elif event.binding.command == 'nop i3ipc_reflect':
            i3ipc_reflect(ipc)
        elif event.binding.command == 'nop i3ipc_mirror':
            i3ipc_mirror(ipc)
        elif event.binding.command == 'nop i3ipc_monocle_toggle':
            i3ipc_monocle_toggle(ipc)
        elif event.binding.command == 'nop i3ipc_tabbed_toggle':
            i3ipc_tabbed_toggle(ipc)
    elif event.binding.command == 'kill':
        i3ipc_kill(ipc)
    elif event.binding.command == 'layout toggle tabbed split':
        i3ipc_layout(ipc, event)


def remove_opacity(ipc):
    """Remove opacity from all windows.

    Parameters
    ----------
    ipc : i3ipc.Connection
        An i3ipc connection

    """
    for workspace in ipc.get_tree().workspaces():
        for wrk in workspace:
            wrk.command("opacity 1")
    ipc.main_quit()
    sys.exit(0)


def init(ipc):
    """Initialize the module."""
    # Check if i3 or sway.
    if not DATA['initialized']:
        args = parse_arguments()
        DATA['opacity']['focused'] = float(args.opacity_focused)
        DATA['opacity']['inactive'] = float(args.opacity_inactive)
        DATA['hide_bar'] = args.tabbed_hide_polybar.upper() == 'TRUE'

        # Workspaces to ignore.
        if args.workspaces_only:
            DATA['workspace_ignore'] = list(map(str, range(1, 10)))
            for wrk in args.workspaces_only:
                DATA['workspace_ignore'].remove(wrk)
        elif args.workspaces_ignore:
            DATA['workspace_ignore'] = args.workspaces_ignore
        DATA['initialized'] = True

        version = ipc.get_version().ipc_data
        if 'variant' in version:
            DATA['variant'] = version['variant']
        else:
            DATA['variant'] = 'i3'

        # Find the focused window and set opacity for all windows.
        command = []
        for con in ipc.get_tree().leaves():
            if con.focused:
                FOCUS['current'] = con.id
                if DATA['variant'] == 'sway':
                    command.append(
                        '[con_id={}] opacity {}'
                        .format(con.id, DATA['opacity']['focused']))
            else:
                if DATA['variant'] == 'sway':
                    command.append(
                        '[con_id={}] opacity {}'
                        .format(con.id, DATA['opacity']['inactive']))
        execute_commands(ipc, command, '')


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="""A Python IPC implementation of dynamic tiling for the i3
        window manager, trying to mimic the tiling behavior of the excellent
        DWM and XMONAD window managers, while utilizing the strengths of I3 and
        SWAY.""")

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
        raise ValueError('Invalid hide polybar tabbed argument: {}'
                         .format(args.tabbed_hide_polybar))

    # Check the workspace ignore argument.
    msg = 'Invalid ignore workspace: {}'.format(args.workspaces_ignore)
    for wrk in args.workspaces_ignore:
        if wrk not in map(str, range(1, 10)):
            raise ValueError(msg)

    # Check the workspace only argument.
    for wrk in args.workspaces_only:
        if wrk not in map(str, range(1, 10)):
            raise ValueError('Invalid only workspace: {}'
                             .format(args.workspaces_only))
    return args


if __name__ == "__main__":
    IPC = i3ipc.Connection()

    init(IPC)

    for sig in [signal.SIGINT, signal.SIGTERM]:
        signal.signal(sig, lambda signal, frame: remove_opacity(IPC))

    try:
        IPC.on(Event.BINDING, on_binding)
        IPC.on(Event.WINDOW_CLOSE, on_window_close)
        IPC.on(Event.WINDOW_FLOATING, on_window_floating)
        IPC.on(Event.WINDOW_FOCUS, on_window_focus)
        IPC.on(Event.WINDOW_MOVE, on_window_move)
        IPC.on(Event.WINDOW_NEW, on_window_new)
        IPC.on(Event.WORKSPACE_FOCUS, on_workspace_focus)
        IPC.main()
    finally:
        IPC.main_quit()
