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
I3DT_MAIN_TBBD_MARK = 'I3DT_MAIN_{}_TBBD_'
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

    info['children'] = list(c.id for c in workspace.leaves())

    main_index = None
    scnd_index = None
    for i, c in enumerate(workspace.descendants()):
        marks = c.marks
        info['descendants'].append(c.id)
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

def get_container_descendants(container):
    if isinstance(container, list):
        descendants = container
    else:
        descendants = container.descendants()
    return descendants

def is_member_mark(mark, mark_list):
    index  = 0
    member = False
    for m in mark_list:
        if m == mark:
            member = True
            break
        index += 1
    return member, index

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

    global I3DT

    logging.info('Binding::Execute')
    command = []

    # Get focused window.
    tree = i3.get_tree()
    focused = tree.find_focused()
    workspace = focused.workspace()

    key = workspace.name
    if not key in I3DT:
        I3DT[key] = { 'mode': 'i3' }

    # Check if workspace should be handled.
    if key in I3DT_WORKSPACE_IGNORE:
        return

    # Initialize the I3DT dictionary.
    I3DT[key]['mode'] = 'i3dt'

    # Find the main container.
    main_mark = I3DT_MAIN_MARK.format(key)
    main = workspace.find_marked(main_mark)
    if main:
        main = main[0]
    else:
        return

    scnd_mark = I3DT_SCND_MARK.format(key)
    scnd = tree.find_marked(scnd_mark)
    if scnd:
        scnd = scnd[0]

    # If focused is in the main container, then focus either the main container
    # or the last child in the secondary container.
    if is_member_id(focused, main.leaves())[0]:
        if scnd:
            command.append('[con_id={}] focus'\
                    .format(scnd.leaves()[-1].id))
        else:
            command.append('[con_id={}] focus'\
                    .format(main.id))
    else:
        if scnd:
            command.append('[con_id={}] focus'\
                    .format(scnd.leaves()[-1].id))

    # Execute the command chain.
    execute_commands(command)

def i3dt_create_container(i3, window, workspace, mark):

    global I3DT

    logging.info('Container::New')

    # Create a temporary container.
    execute_commands('open, mark I3DT_TEMP, split v, layout splitv')

    # Move the window to the temporary container.
    execute_commands('[con_id={}] floating disable, move to mark I3DT_TEMP'.format(window.id))

    # Create the parent container.
    execute_commands('[con_mark=I3DT_TEMP] focus, focus parent')
    execute_commands('mark {}'.format(mark))

    # Kill the temporary container.
    execute_commands('[con_mark=I3DT_TEMP] kill')

def i3dt_check_window_in_container(window, container):
    is_in_container = False
    number_of_descendants = 0

    if container:
        descendants = container[0].descendants()
        number_of_descendants = len(descendants)
        for descendant in descendants:
            if window.id == descendant.id:
                is_in_container = True
                break

    return is_in_container, number_of_descendants


def i3dt_tabbed_toggle(i3):

    logging.info('Workspace::Tabbed')

    # Get tree information.
    info = get_workspace_info(i3)

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

        # Find the newly created split container and mark it.
        if not info['glbl']['id']:
            info = get_workspace_info(i3)
            execute_commands('[con_id={}] mark {}'\
                    .format(info['descendants'][0], info['glbl']['mark']), '')


def i3dt_monocle_toggle(i3, e):

    global I3DT
    global I3DT_MAIN_LAYOUT
    global I3DT_SCND_LAYOUT

    logging.info('Workspace::Monocle')

    # Commmand chain array.
    command = []

    # Get workspace info.
    tree = i3.get_tree()
    focused = tree.find_focused()
    workspace = focused.workspace()
    info = get_workspace_info(i3)

    # Check if workspace should be handled.
    key = workspace.name
    if info['mode'] == 'manual':
        return

    main_mark = I3DT_MAIN_MARK.format(key)
    scnd_mark = I3DT_SCND_MARK.format(key)
    tbbd_mark = I3DT_SCND_TBBD_MARK.format(key)

    # Check if the global container is tabbed.
    glbl = workspace.find_marked(info['glbl']['mark'])
    glbl_tabbed = False
    if glbl and glbl[0].layout == 'tabbed':
        glbl_tabbed = True

    main = workspace.find_marked(main_mark)


    # if I3DT[key]['mode'] == 'i3dt':
    if info['mode'] == 'tiled':

        logging.debug('Tabbed enable:')

        if main:
            # Set tabbed mode enabled.
            # I3DT[key]['mode'] = 'tabbed'

            # Store main layout and focused window id.
            main = main[0]
            if info['glbl']['layout'] != 'tabbed':
                I3DT_MAIN_LAYOUT[key] = main.layout
            main_focused_id = main.focus[0]

            # No secondary container: change the layout of the main
            # container.
            scnd = tree.find_marked(scnd_mark)
            if not scnd:
                command.append('[con_id={}] layout tabbed'\
                        .format(main_focused_id))
            else:
                # Get the children of the main container.
                main_children = main.descendants()

                # Store the layout and the focused window of the secondary
                # container.
                scnd = scnd[0]
                if info['glbl']['layout'] != 'tabbed':
                    I3DT_SCND_LAYOUT[key] = scnd.layout
                scnd_focused = scnd.focus[0]

                # Get the children of the secondary container.
                scnd_children = scnd.descendants()

                # Mark all windows in the secondary container.
                for i, c in enumerate(scnd_children):
                    command.append('[con_id={}] mark {}'\
                            .format(c.id, tbbd_mark + str(i)))

                # Move as few windows as possible.
                if len(scnd_children) > len(main_children):
                    # Move all main windows to the secondary container and
                    # rename the container. The first child of the main
                    # container is moved below the first child of the second
                    # container and then moved up in the list.
                    command.append('[con_id={}] focus'\
                            .format(scnd_children[0].id))
                    main_first_child = main_children.pop(0)
                    command.append('[con_id={}] focus, move to mark {}'\
                                .format(main_first_child.id, scnd_mark))
                    if scnd.layout in ['splith', 'tabbed']:
                        command.append('move left')
                    else:
                        command.append('move up')

                    # Move the rest of the children.
                    for c in main_children:
                        command.append('[con_id={}] move to mark {}'\
                                .format(c.id, scnd_mark))
                    command.append('[con_id={}] focus'\
                            .format(main_focused_id))

                    # Remove and add mark to the secondary, now the main,
                    # container.
                    command.append('[con_id={}] unmark {}'\
                            .format(scnd.id, scnd_mark))
                    command.append('[con_id={}] mark {}'\
                            .format(scnd.id, main_mark))

                    # Focus the right window.
                    command.append('[con_id={}] focus'\
                            .format(focused.id))

                else:
                    # Focus the right window.
                    command.append('[con_id={}] focus'\
                            .format(main_children[-1].id))
                    # Move all secondary windows to the main container. This is
                    # done in reverse due to the fact that i3 always puts the
                    # windows after the focused container, and thus implicitly
                    # reversing the order.
                    move_commands = []
                    for i, c in enumerate(scnd_children):
                        move_commands.append('[con_id={}] move to mark {}'\
                                .format(c.id, main_mark))
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
        main_children = main.leaves()
        scnd_children = []
        for c in main_children:
            for m in c.marks:
                if m.startswith(tbbd_mark):
                    scnd_children.append(c)
                    command.append('[con_id={}] unmark {}'\
                            .format(c.id, m))
                    break


        if not scnd_children:
            if not key in I3DT_MAIN_LAYOUT:
                I3DT_MAIN_LAYOUT[key] = 'splitv'
            if not glbl_tabbed:
                command.append('[con_id={}] layout {}'\
                        .format(main_children[0].id, I3DT_MAIN_LAYOUT[key]))
            execute_commands(command, '')
            return
        else:
            for c in scnd_children:
                main_children.remove(c)



        # Move as few windows as possible.
        if len(scnd_children) > len(main_children):
            scnd = main

            # Create a temporary split container for the first window with the
            # purpose to be the new main container.
            # TODO: Generalize the left movement to handle moved windows.
            child = main_children.pop(0)
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
                        .format(main_container.id, main_mark))

            # Move the new split container into the global container.
            if glbl:
                command.append('[con_id={}] move to mark {}'\
                        .format(main_container.id, info['glbl']['mark']))
                if glbl[0].orientation == 'vertical':
                    command.append('[con_id={}] swap container with con_id {}'\
                            .format(main_container.id, scnd.id))

            # Move the remaining children to the main container.
            for c in main_children:
                command.append('[con_id={}] move to mark {}'\
                        .format(c.id, main_mark))

            # Mark the secondary container.
            command.append('[con_id={}] mark {}'\
                        .format(scnd.id, scnd_mark))

            # Apply the stored layout to the secondary container.
            if not glbl_tabbed:
                if not key in I3DT_SCND_LAYOUT:
                    I3DT_SCND_LAYOUT[key] = 'splitv'
                command.append('[con_id={}] layout {}'\
                        .format(scnd_children[0].id, I3DT_SCND_LAYOUT[key]))
        else:
            # Create a temporary split container for the last window with the
            # purpose to be the new scnd container.
            # TODO: Generalize the right movement to handle moved windows.
            child = scnd_children.pop(-1)
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
            for c in scnd_children:
                command.append('[con_id={}] move to mark {}'\
                        .format(c.id, scnd_mark))

            # Apply the stored layout to the main container.
            if not glbl_tabbed:
                if not key in I3DT_MAIN_LAYOUT:
                    I3DT_MAIN_LAYOUT[key] = 'splitv'
                command.append('[con_id={}] layout {}'\
                        .format(main_children[0].id, I3DT_MAIN_LAYOUT[key]))

        # Focus the right container.
        command.append('[con_id={}] focus'\
                .format(focused.id))

    # Execute the command chain.
    execute_commands(command, '')


def i3dt_promote_demote(i3):
    print('Promote or demote')


def i3dt_mirror(i3):

    global I3DT

    logging.info('Workspace::Mirror')

    tree = i3.get_tree()
    focused = tree.find_focused()
    workspace = focused.workspace()

    # Only reflect the workspace if the secondary container exist and for the
    # i3dt standard mode.
    key = workspace.name
    main_mark = I3DT_MAIN_MARK.format(key)
    main = tree.find_marked(main_mark)
    scnd_mark = I3DT_SCND_MARK.format(key)
    scnd = i3.get_tree().find_marked(scnd_mark)
    if scnd and I3DT[key]['mode'] == 'i3dt':

        # Swap the containers.
        execute_commands('[con_id={}] swap container with con_id {}'\
                .format(main[0].id, scnd[0].id))


def i3dt_reflect(i3):

    global I3DT

    logging.info('Workspace::Reflect')

    tree = i3.get_tree()
    focused = tree.find_focused()
    workspace = focused.workspace()

    # Only reflect the workspace if the secondary container exist and for the
    # i3dt standard mode.
    key = workspace.name
    main_mark = I3DT_MAIN_MARK.format(key)
    scnd_mark = I3DT_SCND_MARK.format(key)
    scnd = workspace.find_marked(scnd_mark)
    glbl_mark = I3DT_GLBL_MARK.format(key)
    glbl = workspace.find_marked(glbl_mark)

    if scnd and I3DT[key]['mode'] == 'i3dt':

        # Change the split container.
        scnd = scnd[0]
        execute_commands('[con_id={}] layout toggle split'\
                .format(scnd.id))

        # Read the split container, that is, the first descendant of the
        # workspace container.
        workspace = i3.get_tree().find_focused().workspace()
        glbl_mark = I3DT_GLBL_MARK.format(key)
        glbl = workspace.find_marked(glbl_mark)
        if not glbl:
            glbl = workspace.descendants()[0]
            execute_commands('[con_id={}] mark {}'\
                    .format(glbl.id, glbl_mark), '')
        else:
            glbl = glbl[0]

        # Update the layout of the first container.
        main = workspace.find_marked(main_mark)[0]
        if (main.layout == 'splitv' and glbl.orientation == 'vertical') or \
                (main.layout == 'splith' and glbl.orientation == 'horizontal'):
            main_children = main.descendants()
            execute_commands('[con_id={}] layout toggle split'\
                    .format(main_children[0].id), '')

        # Update the layout of the secondary container.
        scnd = workspace.find_marked(scnd_mark)[0]
        if (scnd.layout == 'splitv' and glbl.orientation == 'vertical') or \
                (scnd.layout == 'splith' and glbl.orientation == 'horizontal'):
            scnd_children = scnd.descendants()
            execute_commands('[con_id={}] layout toggle split'\
                    .format(scnd_children[0].id), '')

def i3dt_kill(i3):

    global I3DT

    # Print debug info.
    logging.info('Window::Kill::i3dt_kill')

    # Get workspace information.
    focused = i3.get_tree().find_focused()
    workspace = focused.workspace()

    # If workspace is handled by i3 simply kill the window and exit.
    key = workspace.name
    if key in I3DT_WORKSPACE_IGNORE:
        execute_commands('kill')
        return

    # If there is no main container then simply send kill the window and exit.
    main_mark = I3DT_MAIN_MARK.format(key)
    main = workspace.find_marked(main_mark)
    if not main:
        execute_commands('kill')
        return
    else:
        main = main[0]

    # Check if focused window is in the main container.
    main_focused = False
    main_children = main.descendants()
    for c in main_children:
        if c.id == focused.id:
            main_focused = True
            break

    # If the focused window is not in the main container or there are several
    # windows in the main container then it is safe to kill the focused window.
    command = []
    if not main_focused or (main_focused and len(main_children) > 1):
        command.append('kill')
    else:
        # The focused window is the only window in the main container. If there
        # is a secondary container then swap the focused window with the first
        # window in the second container and then kill the, now moved, focused
        # window. Otherwise just kill the focused window.
        scnd_mark = I3DT_SCND_MARK.format(key)
        scnd = workspace.find_marked(scnd_mark)
        if scnd:
            # Get and remove the first element in the secondary container. If
            # empty reset the container.
            scnd_children = scnd[0].descendants()

            # Swap the containers.
            command.append('[con_id={}] swap container with con_id {}'\
                    .format(focused.id, scnd_children[0].id))
            command.append('[con_id={}] focus'\
                    .format(scnd_children[0].id))

        # Kill the focused window.
        command.append('[con_id={}] kill'\
                .format(focused.id))

    # Execute command.
    execute_commands(command)



def on_workspace_focus(i3, e):

    global I3DT

    # Debug info.
    logging.info('Workspace::Focus::{}'\
            .format(e.current.name))

    # Parse workspace.
    info = get_workspace_info(i3, e.current)

    key = e.current.name
    tree = i3.get_tree()
    focused = tree.find_focused()
    workspace = focused.workspace()
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
            else:
                logging.warning('Not handled so far, make it so!')


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

    global I3DT

    logging.info('Window::New')

    # Get the basic i3 state information.
    tree = i3.get_tree()
    window = tree.find_focused()
    workspace = window.workspace()

    # Initialize the I3DT default dictionary.
    key = workspace.name
    if not key in I3DT:
        I3DT[key] = { 'mode': 'i3dt' }

    # If workspace should be ignored set the mode to i3 and return.
    if key in I3DT_WORKSPACE_IGNORE:
        I3DT[key]['mode'] = 'i3'
        return

    # Find the application windows on the focused workspace.
    wrks_children = []
    for c in workspace.descendants():
        if not c.name == None:
            wrks_children.append(c.id)

    # Exit if the the number of application windows are too low.
    if len(wrks_children) < 2:
        return

    # Parse the main container.
    main_mark = I3DT_MAIN_MARK.format(workspace.name)
    main = workspace.find_marked(main_mark)

    # Parse the secondary container.
    scnd_mark = I3DT_SCND_MARK.format(workspace.name)
    scnd = workspace.find_marked(scnd_mark)

    # Create the main container.
    command = []
    if not main:
        execute_commands('[con_id={}] focus, splitv'\
                .format(wrks_children[0]))
        workspace = i3.get_tree().find_focused().workspace()
        main_container = []
        for c in workspace.descendants():
            for d in c.descendants():
                if d.id == wrks_children[0]:
                    main_container = c.id
                    break
            if main_container:
                break
        execute_commands('[con_id={}] mark {}'\
                .format(main_container, main_mark))

        # Create the secondary container.
        if not scnd:
            execute_commands('[con_id={}] focus, splitv'.format(wrks_children[1]))
            workspace = i3.get_tree().find_focused().workspace()
            scnd_container = []
            for c in workspace.descendants():
                for d in c.descendants():
                    if d.id == wrks_children[1]:
                        scnd_container = c.id
                        break
                if scnd_container:
                    break
            execute_commands('[con_id={}] mark {}'.format(scnd_container, scnd_mark))
    else:
        # Create the secondary container.
        if not scnd:
            execute_commands('[con_id={}] move right, splitv'.format(window.id))
            workspace = i3.get_tree().find_focused().workspace()
            scnd_container = []
            for c in workspace.descendants():
                for d in c.descendants():
                    if d.id == window.id:
                        scnd_container = c.id
                        break
                if scnd_container:
                    break
            execute_commands('[con_id={}] mark {}'.format(scnd_container, scnd_mark))

            # Make sure that the secondary container is on the same level as
            # the main container.
            workspace = i3.get_tree().find_focused().workspace()
            scnd = workspace.find_marked(scnd_mark)
            glbl_mark = I3DT_GLBL_MARK.format(workspace.name)
            glbl = workspace.find_marked(glbl_mark)
            scnd = workspace.find_marked(scnd_mark)
            if glbl:
                execute_commands('[con_id={}] move to mark {}'\
                        .format(scnd[0].id, glbl_mark))
            else:
                containers = workspace.descendants()
                if not containers[0].id == main[0].id and containers[1].id == scnd[0].id:
                    execute_commands('[con_id={}] mark {}'\
                            .format(containers[0].id, glbl_mark))
                    execute_commands('[con_id={}] move to mark {}'\
                            .format(scnd[0].id, glbl_mark))
        else:
            # If window spawned in the main constainer move it to the secondary
            # container.
            for c in main[0].descendants():
                if c.id == window.id:
                    execute_commands('[con_id={}] move to mark {}'\
                            .format(window.id, scnd_mark))
                    break

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
