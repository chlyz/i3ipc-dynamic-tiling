#!/usr/bin/env python3

import asyncio
import i3ipc
from i3ipc import Event
import os
import time
import argparse
import logging
import copy

# Things to do
#
# + Tabbed new window

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

args = parser.parse_args()

# Check the logging level argument.
log_level_numeric = getattr(logging, args.log_level.upper(), None)
if not isinstance(log_level_numeric, int):
    raise ValueError('Invalid log level: {}'.format(args.log_level))

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

I3DT                = dict()
I3DT_LAYOUT         = dict()
I3DT_MAIN_LAYOUT    = dict()
I3DT_SCND_LAYOUT    = dict()
I3DT_GLBL_MARK      = 'I3DT_GLBL_{}'
I3DT_MAIN_MARK      = 'I3DT_MAIN_{}'
I3DT_SCND_MARK      = 'I3DT_SCND_{}'
I3DT_SCND_TBBD_MARK = 'I3DT_SCND_{}_TBBD_'
I3DT_WINDOW_PREV = []
I3DT_WINDOW_CURR = []

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
    # Execute all commands
    if commands:
        if isinstance(commands, list):
            if preamble:
                logging.debug(preamble)
            i3.command(', '.join(commands))
            for c in commands:
                logging.debug('+ Command: {}'.format(c))
        else:
            if preamble:
                logging.debug(preamble)
            i3.command(commands)
            logging.debug('+ Command: {}'.format(commands))
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
            'layout': workspace.layout,
            'children': [],
            'descendants': [],
            'workspace': workspace.id,
            'focused': None,
            'fullscreen': False,
            'unmanaged': [],
            'glbl': { 'mark': glbl_mark, 'id': None, 'orientation': 'horizontal', 'layout': 'splith' },
            'main': { 'mark': main_mark, 'id': None, 'focus': None, 'layout': 'splitv', 'children': [] },
            'scnd': { 'mark': scnd_mark, 'id': None, 'focus': None, 'layout': 'splitv', 'children': [], 'position': 'right' },
            'tbbd': { 'mark': tbbd_mark, 'indices': [], 'children': [] },
            }

    # Collect workspace information.
    if not key in I3DT_WORKSPACE_IGNORE:
        info['mode'] = 'tiled'

    info['descendants'] = workspace.descendants()
    info['children'] = list(c.id for c in workspace.leaves())

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
            info['main']['layout'] = c.layout
            info['main']['children'] = list(d.id for d in c.leaves())
            main_index = i
        elif scnd_mark in marks:
            info['scnd']['id'] = c.id
            if c.focus:
                info['scnd']['focus'] = c.focus[0]
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
    info['unmanaged'] = copy.deepcopy(info['children'])
    for i in info['main']['children']:
        info['unmanaged'].remove(i)
    for i in info['scnd']['children']:
        info['unmanaged'].remove(i)

    return info

def find_parent_id(con_id, info):
    parent = None
    containers = (c for c in info['descendants'] if not c.name)
    for c in containers:
        for d in c.descendants():
            if d.id == con_id:
                parent = c.id
                break
    return parent

def create_split_container(i3, con_id, mark):
    info = get_workspace_info(i3)
    parent = find_parent_id(con_id, info)
    if not parent:
        execute_commands('[con_id={}] focus, splitv'\
                .format(con_id))
    else:
        logging.warning('Not yet supported!')
    info = get_workspace_info(i3)
    parent = find_parent_id(con_id, info)
    if mark:
        execute_commands('[con_id={}] mark {}'\
                .format(parent, mark))

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
        children = info['children']
    return parent, layout, children

def find_container_index(info):
    ind = 0;
    for c in info['children']:
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
    logging.info('Window::Focus::{}'\
            .format(e.binding.command.replace('nop ', '', 1)))
    action = e.binding.command.split(" ")[-1]
    info = get_workspace_info(i3)
    command = []
    if action in ['next', 'prev']:
        index = find_container_index(info)
        if action == 'next':
            command.append('[con_id={}] focus'\
                    .format(info['children'][(index + 1) % len(info['children'])]))
        elif action == 'prev':
            command.append('[con_id={}] focus'\
                    .format(info['children'][(index - 1) % len(info['children'])]))
        if info['fullscreen']:
            command.append('fullscreen toggle')
    elif action == 'other':
        if info['mode'] != 'manual':
            if info['fullscreen']:
                command.append('fullscreen toggle')
            command.append('focus parent, focus next')
            if info['fullscreen']:
                command.append('fullscreen toggle')
        else:
            logging.warning('Window::Focus::Other::No other container')
    elif action == 'toggle':
        if I3DT_WINDOW_PREV:
            command.append('[con_id={}] focus'\
                    .format(I3DT_WINDOW_PREV))
            if info['fullscreen']:
                command.append('fullscreen toggle')
        else:
            logging.warning('Window::Focus::Toggle::No previous window')
    execute_commands(command)


def i3dt_move(i3, e):
    logging.info('Window::Move::{}'\
            .format(e.binding.command.replace('nop ', '', 1)))
    action = e.binding.command.split(" ")[-1]
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
                movement = get_movement(info['scnd']['layout'], 'prev')
                command.append('[con_id={}] focus'\
                        .format(info['scnd']['children'][0]))
                command.append('[con_id={}] focus, move to mark {}, move {}'\
                        .format(info['focused'], info['scnd']['mark'], movement))
                command.append('[con_id={}] focus, focus child'\
                        .format(info['main']['id']))
            else:
                if info['glbl']['id']:
                    command.append('move to mark {}, splitv'\
                            .format(info['glbl']['mark']))
                else:
                    if info['main']['layout'] in ['splith', 'tabbed']:
                        command.append('move down')
                    command.append('move right')
                command = execute_commands(command)
                info = get_workspace_info(i3)
                create_split_container(i3, info['focused'], info['scnd']['mark'])
                info = get_workspace_info(i3)
                if info['glbl']['id']:
                    execute_commands('[con_id={}] move to mark {}'\
                            .format(info['scnd']['id'], info['glbl']['mark']))
        else:
            command.append('[con_id={}] focus'\
                    .format(info['main']['children'][-1]))
            command.append('[con_id={}] focus, move to mark {}'\
                    .format(info['focused'], info['main']['mark']))
            command.append('[con_id={}] focus, focus child'\
                    .format(info['scnd']['id']))
    elif action == 'swap':
        if info['focused'] in info['main']['children'] and info['scnd']['id']:
            command.append('[con_id={}] focus'.format(info['scnd']['focus']))
        else:
            command.append('[con_id={}] focus'.format(info['main']['focus']))
        command.append('swap container with con_id {}'\
                .format(info['focused']))

    execute_commands(command)


def i3dt_execute(i3, e):
    logging.info('Binding::Execute')
    info = get_workspace_info(i3)
    command = []

    if info['mode'] == 'manual' or not info['main']['id']:
        return

    # If focused is in the main container, then focus either the main container
    # or the last child in the secondary container.
    if info['focused'] in info['main']['children']:
        if info['scnd']['id']:
            command.append('[con_id={}] focus'\
                    .format(info['scnd']['children'][-1]))
        else:
            command.append('[con_id={}] focus'\
                    .format(info['main']['id']))
    elif info['scnd']['id']:
        command.append('[con_id={}] focus'\
                .format(info['scnd']['children'][-1]))
    execute_commands(command)


def i3dt_tabbed_toggle(i3):

    logging.info('Workspace::Tabbed')

    # Get tree information.
    info = get_workspace_info(i3)
    if info['mode'] == 'manual':
        return

    # Toggle the tabbed layout.
    command = []
    if info['glbl']['layout'] == 'tabbed':

        # Toggle the split of the secondary container.
        if info['scnd']['id']:
            command.append('[con_id={}] layout toggle split'.\
                    format(info['scnd']['id']))

        # Recreate the layouts of the individual containers.
        for k in ['main', 'scnd']:
            if info[k]['id']:
                if not k in I3DT_LAYOUT:
                    I3DT_LAYOUT[k] = 'splitv'
                if info[k]['layout'] != I3DT_LAYOUT[k]:
                    command.append('[con_id={}] layout {}'\
                            .format(info[k]['children'][0], I3DT_LAYOUT[k]))

        # Execute command chain.
        execute_commands(command, 'Disable:')

    else:

        # Toggle the split of the secondary container.
        if info['scnd']['id']:
            command.append('[con_id={}] layout tabbed'.\
                    format(info['scnd']['id']))

        # Store the layouts of the individual containers.
        for k in ['main', 'scnd']:
            if info[k]['id']:
                I3DT_LAYOUT[k] = info[k]['layout']
                command.append('[con_id={}] layout tabbed'\
                        .format(info[k]['children'][0]))

        # Execute command chain.
        execute_commands(command, 'Enable:')
        info = get_workspace_info(i3)

        # Find the newly created split container and mark it.
        if not info['glbl']['id']:
            glbl = info['descendants'][0].id
            execute_commands('[con_id={}] mark {}'\
                    .format(glbl, info['glbl']['mark']), '')


def i3dt_monocle_toggle(i3, e):

    global I3DT_MAIN_LAYOUT
    global I3DT_SCND_LAYOUT

    logging.info('Workspace::Monocle')
    info = get_workspace_info(i3)
    command = []

    # Check if workspace should be handled.
    if info['mode'] == 'manual':
        return

    if info['mode'] == 'tiled':
        logging.debug('Tabbed enable:')
        if info['main']['id']:
            # Store main layout and focused window id.
            if info['glbl']['layout'] != 'tabbed':
                I3DT_MAIN_LAYOUT[key] = info['main']['layout']
            main_focused_id = info['main']['focus']

            # No secondary container: change the layout of the main
            # container.
            if not info['scnd']['id']:
                command.append('[con_id={}] layout tabbed'\
                        .format(main_focused_id))
            else:
                # Store the layout and the focused window of the secondary
                # container.
                if info['glbl']['layout'] != 'tabbed':
                    I3DT_SCND_LAYOUT[key] = info['scnd']['layout']
                scnd_focused = info['scnd']['focus']

                # Mark all windows in the secondary container.
                for i, c in enumerate(info['scnd']['children']):
                    command.append('[con_id={}] mark {}'\
                            .format(c.id, tbbd_mark + str(i)))

                # Move as few windows as possible.
                if len(info['scnd']['children'])\
                        > len(info['main']['children']):
                    # Move all main windows to the secondary container and
                    # rename the container. The first child of the main
                    # container is moved below the first child of the second
                    # container and then moved up in the list.
                    command.append('[con_id={}] focus'\
                            .format(info['scnd']['children'][0]))
                    main_first_child = info['main']['children'].pop(0)
                    command.append('[con_id={}] focus, move to mark {}'\
                                .format(main_first_child.id, scnd_mark))
                    if scnd.layout in ['splith', 'tabbed']:
                        command.append('move left')
                    else:
                        command.append('move up')

                    # Move the rest of the children.
                    for c in info['main']['children']:
                        command.append('[con_id={}] move to mark {}'\
                                .format(c.id, scnd_mark))
                    command.append('[con_id={}] focus'\
                            .format(main_focused_id))

                    # Remove and add mark to the secondary, now the main,
                    # container.
                    command.append('[con_id={}] unmark {}'\
                            .format(scnd.id, scnd_mark))
                    command.append('[con_id={}] mark {}'\
                            .format(scnd.id, info['main']['mark']))

                    # Focus the right window.
                    command.append('[con_id={}] focus'\
                            .format(focused.id))

                else:
                    # Focus the right window.
                    command.append('[con_id={}] focus'\
                            .format(info['main']['children'][-1].id))
                    # Move all secondary windows to the main container. This is
                    # done in reverse due to the fact that i3 always puts the
                    # windows after the focused container, and thus implicitly
                    # reversing the order.
                    move_commands = []
                    for i, c in enumerate(info['scnd']['children']):
                        move_commands.append('[con_id={}] move to mark {}'\
                                .format(c.id, info['main']['mark']))
                    move_commands.reverse()
                    command.extend(move_commands)

                    # Focus the right window.
                    command.append('[con_id={}] focus'\
                            .format(focused.id))

                if not scnd.layout == 'tabbed':
                    command.append('layout tabbed')

    elif info['mode'] == 'monocle':

        logging.debug('Tabbed disable:')

        # Exit if there is no main container.
        if not main:
            return

        # Find all windows that should be in the main and the secondary
        # container, respectively.
        main = main[0]

        # Find all windows that should be in the secondary container.
        if not info['scnd']['children']:
            if not key in I3DT_MAIN_LAYOUT:
                I3DT_MAIN_LAYOUT[key] = 'splitv'
            if not glbl_tabbed:
                command.append('[con_id={}] layout {}'\
                        .format(info['main']['children'][0].id, I3DT_MAIN_LAYOUT[key]))
            execute_commands(command, '')
            return
        else:
            for c in info['scnd']['children']:
                info['main']['children'].remove(c)



        # Move as few windows as possible.
        if len(info['scnd']['children']) > len(info['main']['children']):
            scnd = main

            # Create a temporary split container for the first window with the
            # purpose to be the new main container.
            # TODO: Generalize the left movement to handle moved windows.
            child = info['main']['children'].pop(0)
            command.append('[con_id={}] focus, move left, splitv'\
                    .format(child.id))

            # Reset the container layout only if not in global tabbed mode.
            if not glbl_tabbed:
                if not key in I3DT_MAIN_LAYOUT:
                    I3DT_MAIN_LAYOUT[key] = 'splitv'
                command.append('layout {}'\
                    .format(I3DT_MAIN_LAYOUT[key]))
            else:
                command.append('layout tabbed')

            # Find the temporary split container.
            command = execute_commands(command, '')
            main_container = []
            logging.debug('+ Search after the main container')
            for c in i3.get_tree().find_by_id(workspace.id).descendants():
                for d in c.descendants():
                    if d.id == child.id:
                        main_container = c

            # Mark the main container.
            command.append('[con_id={}] mark {}'\
                        .format(main_container.id, info['main']['mark']))

            # Move the new split container into the global container.
            if glbl:
                command.append('[con_id={}] move to mark {}'\
                        .format(main_container.id, info['glbl']['mark']))
                if glbl[0].orientation == 'vertical':
                    command.append('[con_id={}] swap container with con_id {}'\
                            .format(main_container.id, scnd.id))

            # Move the remaining children to the main container.
            for c in info['main']['children']:
                command.append('[con_id={}] move to mark {}'\
                        .format(c.id, info['main']['mark']))

            # Mark the secondary container.
            command.append('[con_id={}] mark {}'\
                        .format(scnd.id, scnd_mark))

            # Apply the stored layout to the secondary container.
            if not glbl_tabbed:
                if not key in I3DT_SCND_LAYOUT:
                    I3DT_SCND_LAYOUT[key] = 'splitv'
                command.append('[con_id={}] layout {}'\
                        .format(info['scnd']['children'][0].id, I3DT_SCND_LAYOUT[key]))
        else:
            # Create a temporary split container for the last window with the
            # purpose to be the new scnd container.
            # TODO: Generalize the right movement to handle moved windows.
            child = info['scnd']['children'].pop(-1)
            command.append('[con_id={}] focus, move right, splitv'\
                    .format(child.id))

            # Reset the container layout only if not in global tabbed mode.
            if not glbl_tabbed:
                if not key in I3DT_SCND_LAYOUT:
                    I3DT_SCND_LAYOUT[key] = 'splitv'
                command.append('layout {}'\
                    .format(I3DT_SCND_LAYOUT[key]))
            else:
                command.append('layout tabbed')

            # Find the temporary split container.
            command = execute_commands(command)
            logging.debug('+ Search after the secondary container')
            scnd = []
            for c in i3.get_tree().find_by_id(workspace.id).descendants():
                for d in c.descendants():
                    if d.id == child.id:
                        scnd = c

            # Move the new split container into the global container.
            if glbl:
                command.append('[con_id={}] move to mark {}'\
                        .format(scnd.id, info['glbl']['mark']))

            # Mark the scnd container.
            command.append('[con_id={}] mark {}'\
                        .format(scnd.id, scnd_mark))

            # Move the remaining children to the scnd container.
            for c in info['scnd']['children']:
                command.append('[con_id={}] move to mark {}'\
                        .format(c.id, scnd_mark))

            # Apply the stored layout to the main container.
            if not glbl_tabbed:
                if not key in I3DT_MAIN_LAYOUT:
                    I3DT_MAIN_LAYOUT[key] = 'splitv'
                command.append('[con_id={}] layout {}'\
                        .format(info['main']['children'][0].id, I3DT_MAIN_LAYOUT[key]))

        # Focus the right container.
        command.append('[con_id={}] focus'\
                .format(focused.id))

    # Execute the command chain.
    execute_commands(command, '')


def i3dt_promote_demote(i3):
    print('Promote or demote')


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
        if not info['glbl']['id']:
            command = execute_commands(command)
            info = get_workspace_info(i3)
            command.append('[con_id={}] mark {}'\
                    .format(info['descendants'][0].id, info['glbl']['mark']))
        # Update the layout of the containers.
        command = execute_commands(command)
        info = get_workspace_info(i3)
        orientation = info['glbl']['orientation']
        for k in ['main', 'scnd']:
            layout = info[k]['layout']
            if (layout == 'splitv' and orientation == 'vertical')\
                    or (layout == 'splith' and orientation == 'horizontal'):
                command.append('[con_id={}] layout toggle split'\
                        .format(info[k]['children'][0]))
        execute_commands(command, '')


def i3dt_kill(i3):
    logging.info('Window::Kill::i3dt_kill')
    info = get_workspace_info(i3)

    if info['mode'] == 'manual' or not info['main']['id']:
        execute_commands('kill')
        return

    command = []
    main_focused = info['focused'] in info['main']['children']
    main_nchildr = len(info['main']['children'])
    if not main_focused or (main_focused and main_nchildr > 1):
        # If the focused window is not in the main container or there are
        # several windows in the main container then it is safe to kill the
        # focused window.
        command.append('kill')
    else:
        # The focused window is the only window in the main container. If there
        # is a secondary container then swap the focused window with the first
        # window in the second container and then kill the, now moved, focused
        # window. Otherwise just kill the focused window.
        if info['scnd']['id']:
            command.append('[con_id={}] swap container with con_id {}'\
                    .format(info['focused'], info['scnd']['children'][0]))
            command.append('[con_id={}] focus'\
                    .format(info['scnd']['children'][0]))
        command.append('[con_id={}] kill'\
                .format(info['focused']))
    execute_commands(command)


def on_workspace_focus(i3, e):
    logging.info('Workspace::Focus::{}'\
            .format(e.current.name))
    info = get_workspace_info(i3, e.current)
    command = []
    if not info['mode'] == 'manual':

        if info['unmanaged']:
            mark = None
            if info['scnd']['id']:
                mark = info['scnd']['mark']
                command.append('[con_id={}] focus'\
                        .format(info['scnd']['children'][-1]))
            elif info['main']['id']:
                mark = info['main']['mark']
                command.append('[con_id={}] focus'\
                        .format(info['main']['children'][-1]))
            if mark:
                for i in info['unmanaged']:
                    command.append('[con_id={}] move to mark {}'\
                            .format(i, mark))
            elif len(info['children']) > 1:
                children = info['children']
                create_split_container(i3, children[0], info['main']['mark'])
                create_split_container(i3, children[1], info['scnd']['mark'])
                info = get_workspace_info(i3)


        # windows = info['children']

        # # Create the main container.
        # if not info['main']['id'] and len(info['children']) > 1:
        #     window = windows.pop(0)
        #     execute_commands('[con_id={}] focus, splitv'.format(window.id), 'Create main container:')
        #     workspace = i3.get_tree().find_focused().workspace()
        #     main_container = []
        #     for c in workspace.descendants():
        #         for d in c.descendants():
        #             if d.id == window.id:
        #                 main_container = c
        #                 break
        #         if main_container:
        #             break
        #     execute_commands('[con_id={}] mark {}'\
        #             .format(main_container.id, main_mark), '')

#         # Create the secondary container.
#         window = windows.pop(0)
#         execute_commands('[con_id={}] focus, splitv'.format(window.id), 'Create secondary container:')
#         workspace = i3.get_tree().find_focused().workspace()
#         scnd_container = []
#         for c in workspace.descendants():
#             for d in c.descendants():
#                 if d.id == window.id:
#                     scnd_container = c
#                     break
#             if scnd_container:
#                 break
#         command = []
#         command.append('[con_id={}] mark {}'\
#                 .format(scnd_container.id, scnd_mark))
#         for c in windows:
#             command.append('[con_id={}] move to mark {}'\
#                     .format(c.id, scnd_mark))
#         execute_commands(command, '')

#     else:
#         # Find unmanaged windows.
#         unmanaged_windows = workspace.leaves()
#         main = workspace.find_marked(main_mark)
#         if main:
#             for c in main[0].leaves():
#                 unmanaged_windows.remove(c)
#         scnd = workspace.find_marked(scnd_mark)
#         if scnd:
#             for c in scnd[0].leaves():
#                 unmanaged_windows.remove(c)

#         # Move all unmanaged windows to an existing container.
#         mark = scnd_mark
#         if not scnd:
#             mark = main_mark
#         command = []
#         for c in unmanaged_windows:
#             command.append('[con_id={}] move to mark {}'\
#                     .format(c.id, mark))
#         execute_commands(command)

def on_window_new(i3, e):
    logging.info('Window::New')
    info = get_workspace_info(i3)

    if info['mode'] == 'manual' or len(info['children']) < 2:
        return

    # Create the main container.
    command = []
    if not info['main']['id']:
        children = info['children']
        create_split_container(i3, children[0], info['main']['mark'])
        create_split_container(i3, children[1], info['scnd']['mark'])
    elif not info['scnd']['id']:
            # Move window out ot the split container.
            if info['focused'] in info['main']['children']:
                command = []
                if info['main']['layout'] in ['splith', 'tabbed']:
                    command.append('move down')
                command.append('move right')
                execute_commands(command, '')

            # Create the secondary container.
            create_split_container(i3, info['focused'], info['scnd']['mark'])

            # Make sure that the secondary container is on the same level as
            # the main container.
            info = get_workspace_info(i3)
            if info['glbl']['id']:
                execute_commands('[con_id={}] move to mark {}'\
                        .format(info['scnd']['id'], info['glbl']['mark']))
            else:
                logging.warning('NOT YET IMPLEMENTED')
                logging.debug('POTENTIAL GLOBAL')
            #     parent = find_parent_id(info['main']['id'], info)
            #     print(parent)
            #     print(info['main']['id'])
            #     print('asdf')
                # glbl = info['descendants'][0].id
                # if not glbl in [info['main']['id'], info['main']['id']]:
                #     execute_commands('[con_id={}] mark {}'\
                #             .format(glbl, info['glbl']['mark']))
                #     execute_commands('[con_id={}] move to mark {}'\
                #             .format(info['scnd']['id'], info['glbl']['mark']))
    else:
        # If window spawned in the main constainer move it to the secondary
        # container.
        if info['focused'] in info['main']['children']:
            execute_commands('[con_id={}] move to mark {}'\
                    .format(info['focused'], info['scnd']['mark']))

def on_window_focus(i3, e):

    global I3DT_WINDOW_PREV
    global I3DT_WINDOW_CURR

    # Debug information.
    logging.info('Window::Focus')

    # Store container id.
    I3DT_WINDOW_PREV = I3DT_WINDOW_CURR
    I3DT_WINDOW_CURR = e.container.id


def on_binding(i3, e):
    if e.binding.command.startswith('nop'):
        if e.binding.command == 'nop i3dt_kill':
            i3dt_kill(i3)
        elif e.binding.command.startswith('nop i3dt_focus'):
            i3dt_focus(i3, e)
        elif e.binding.command.startswith('nop i3dt_move'):
            i3dt_move(i3, e)
        elif e.binding.command == 'nop i3dt_reflect':
            i3dt_reflect(i3)
        elif e.binding.command == 'nop i3dt_mirror':
            i3dt_mirror(i3)
        elif e.binding.command == 'nop i3dt_monocle_toggle':
            i3dt_monocle_toggle(i3, e)
        elif e.binding.command == 'nop i3dt_tabbed_toggle':
            i3dt_tabbed_toggle(i3)
    else:
        if e.binding.command.startswith('exec'):
            i3dt_execute(i3, e)


i3 = i3ipc.Connection()
try:
    i3.on(Event.WINDOW_FOCUS, on_window_focus)
    i3.on(Event.WINDOW_NEW, on_window_new)
    i3.on(Event.BINDING, on_binding)
    i3.on(Event.WORKSPACE_FOCUS, on_workspace_focus)
    # i3.on(Event.WINDOW_CLOSE, on_window_close)
    # i3.on(Event.WINDOW_FOCUS, on_window_focus)
    # i3.on(Event.WINDOW_MOVE, on_window_move)
    i3.main()
finally:
    i3.main_quit()
