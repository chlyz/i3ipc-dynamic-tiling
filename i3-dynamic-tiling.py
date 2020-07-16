#!/usr/bin/env python3

import i3ipc
from i3ipc import Event
import time
import argparse
import logging
import copy
import os

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

parser.add_argument(
        '--hide-polybar-tabbed',
        default='false',
        help="""Hide the polybar when in tabbed mode [false, true].""")

parser.add_argument(
        '--tabbed-use-monocle',
        default=2,
        help="""Hide the polybar when in tabbed mode [false, true].""")

args = parser.parse_args()

# Check the logging level argument.
log_level_numeric = getattr(logging, args.log_level.upper(), None)
if not isinstance(log_level_numeric, int):
    raise ValueError('Invalid log level: {}'.format(args.log_level))

if args.hide_polybar_tabbed.upper() not in ['FALSE', 'TRUE']:
    raise ValueError('Invalid hide polybar tabbed argument: {}'\
            .format(args.hide_polybar_tabbed))

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

I3DT_LAYOUT         = dict()
I3DT_GLBL_MARK      = 'I3DT_GLBL_{}'
I3DT_MAIN_MARK      = 'I3DT_MAIN_{}'
I3DT_SCND_MARK      = 'I3DT_SCND_{}'
I3DT_SCND_TBBD_MARK = 'I3DT_SCND_{}_TBBD_'
I3DT_WINDOW_PREV = []
I3DT_WINDOW_CURR = []
I3DT_HIDE_BAR = True if args.hide_polybar_tabbed.upper() == 'TRUE' else False

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
        if isinstance(commands, list):
            if preamble: logging.debug(preamble)
            i3.command(', '.join(commands))
            for c in commands:
                if c: logging.debug('+ Command: {}'.format(c))
        else:
            if preamble: logging.debug(preamble)
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
            'main': { 'mark': main_mark, 'id': None, 'focus': None, 'layout': 'splitv', 'children': [] },
            'scnd': { 'mark': scnd_mark, 'id': None, 'focus': None, 'layout': 'splitv', 'children': [], 'position': 'right' },
            'tbbd': { 'mark': tbbd_mark, 'indices': [], 'children': [] },
            }

    # Collect workspace information.
    if not key in I3DT_WORKSPACE_IGNORE:
        info['mode'] = 'tiled'

    info['descendants'] = workspace.descendants()
    for c in workspace.leaves():
        info['children'].append(c.id)
        if c.floating.endswith('on'):
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
    command = ''
    if info[key]['id']:
        if info['name'] not in I3DT_LAYOUT:
            I3DT_LAYOUT[info['name']] = { 'main': 'splitv', 'scnd': 'splitv' }
        if not key in I3DT_LAYOUT[info['name']]:
            I3DT_LAYOUT[info['name']][key] = 'splitv'
        if info[key]['layout'] != I3DT_LAYOUT[info['name']][key]:
            command = '[con_id={}] layout {}'\
                    .format(info[key]['children'][0],
                        I3DT_LAYOUT[info['name']][key])
    return command

def save_container_layout(key, info):
    global I3DT_LAYOUT
    if info['name'] not in I3DT_LAYOUT:
        I3DT_LAYOUT[info['name']] = { 'main': 'splitv', 'scnd': 'splitv' }
    command = ''
    if info[key]['id']:
        I3DT_LAYOUT[info['name']][key] = info[key]['layout']
        command = '[con_id={}] layout tabbed'\
                .format(info[key]['children'][0])
    return command

def find_parent_id(con_id, info):
    parent = None
    containers = (c for c in info['descendants'] if not c.name)
    for c in containers:
        for d in c.descendants():
            if d.id == con_id:
                parent = c.id
                break
    return parent

def create_container(i3, target, con_id=None):

    # Get workspace information.
    info = get_workspace_info(i3)

    logging.debug('Create container: {}'.format(target))

    # Exit if container already exists.
    if info[target]['id']:
        raise ValueError('Container already exist!')

    # Get the window that should be contained and make sure it is focused.
    command = []
    focused = info['focused']
    if not con_id:
        con_id = focused
    else:
        command.append('[con_id={}] focus'.format(con_id))

    # Remove any marks that may exist.
    command.append('[con_id={}] unmark'.format(con_id))

    # Move the window outside any other container.
    other = 'main' if target == 'scnd' else 'scnd'
    if con_id in info[other]['children']:
        if info['glbl']['id']:
            command.append('move to mark {}, splitv'\
                    .format(info['glbl']['mark']))
        else:
            if info[other]['layout'] in ['splith', 'tabbed']:
                command.append('move down')
            if target == 'main':
                command.append('move left, splitv')
            else:
                command.append('move right, splitv')
    else:
        command.append('splitv')
    command = execute_commands(command, '')

    # Find and mark the newly created split container.
    info = get_workspace_info(i3)
    parent = find_parent_id(con_id, info)
    command.append('[con_id={}] mark {}'\
            .format(parent, info[target]['mark']))

    # Make sure that the newly created container is in the global split
    # container.
    if info['glbl']['id']:
        command.append('[con_id={}] move to mark {}'\
                .format(parent, info['glbl']['mark']))
        if target == 'main' and info['scnd']['id']:
            command.append('[con_id={}] swap container with con_id {}'\
                    .format(parent, info['scnd']['id']))

    # Revert the change of focus.
    if con_id != focused:
        command.append('[con_id={}] focus'.format(focused))

    command = execute_commands(command, '')

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

def find_container_index(info):
    ind = 0;
    for c in info['tiled']:
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
                    .format(info['tiled'][(index + 1) % len(info['tiled'])]))
        elif action == 'prev':
            command.append('[con_id={}] focus'\
                    .format(info['tiled'][(index - 1) % len(info['tiled'])]))
        if info['fullscreen']:
            command.append('fullscreen toggle')
    elif action == 'other':
        if info['scnd']['id']:
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
                create_container(i3, 'scnd')
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


def i3dt_tabbed_toggle(i3, e):

    global I3DT_LAYOUT
    logging.info('Workspace::Tabbed')
    info = get_workspace_info(i3)

    # Exit if workspace should not be handled.
    if info['mode'] == 'manual':
        return

    if info['mode'] == 'monocle':
        i3dt_monocle_toggle(i3, e)
        return

    if len(info['tiled']) <= args.tabbed_use_monocle:
        i3dt_monocle_toggle(i3, e)
        return

    # Toggle the tabbed layout.
    command = []
    if info['glbl']['layout'] == 'tabbed':
        if I3DT_HIDE_BAR: os.system("polybar-msg cmd show 1>/dev/null")

        # Toggle the split of the secondary container.
        if info['scnd']['id']:
            command.append('[con_id={}] layout toggle split'.\
                    format(info['scnd']['id']))

        # Recreate the layouts of the individual containers.
        for k in ['main', 'scnd']:
            command.append(restore_container_layout(k, info))

        # Execute command chain.
        execute_commands(command, 'Disable:')

    elif info['mode'] == 'tiled':

        if I3DT_HIDE_BAR: os.system("polybar-msg cmd hide 1>/dev/null")

        # Toggle the split of the secondary container.
        if info['scnd']['id']:
            command.append('[con_id={}] layout tabbed'.\
                    format(info['scnd']['id']))

        # Store the layouts of the individual containers.
        for k in ['main', 'scnd']:
            command.append(save_container_layout(k, info))

        # Execute command chain.
        execute_commands(command, 'Enable:')
        info = get_workspace_info(i3)

        # Find the newly created split container and mark it.
        if not info['glbl']['id']:
            glbl = info['descendants'][0].id
            execute_commands('[con_id={}] mark {}'\
                    .format(glbl, info['glbl']['mark']), '')



def i3dt_monocle_toggle(i3, e):

    global I3DT_LAYOUT

    logging.info('Workspace::Monocle')

    info = get_workspace_info(i3)
    if info['mode'] == 'manual' or not info['main']['id']:
        return

    # Toggle monocle mode.
    command = []
    if info['mode'] == 'tiled':
        if I3DT_HIDE_BAR: os.system("polybar-msg cmd hide 1>/dev/null")

        focused = info['focused']

        # Store the layout of the main container.
        if info['glbl']['layout'] != 'tabbed':
            if info['name'] not in I3DT_LAYOUT:
                I3DT_LAYOUT[info['name']] = { 'main': 'splitv', 'scnd': 'splitv' }
            I3DT_LAYOUT[info['name']]['main'] = info['main']['layout']

        # No secondary container: change the layout of the main
        # container.
        if not info['scnd']['id']:
            command.append('[con_id={}] layout tabbed'\
                    .format(info['main']['focus']))
        else:
            # Store the layout of the secondary container.
            if info['glbl']['layout'] != 'tabbed':
                I3DT_LAYOUT[info['name']]['scnd'] = info['scnd']['layout']

            # Mark all windows in the secondary container.
            for i, c in enumerate(info['scnd']['children']):
                command.append('[con_id={}] mark {}'\
                        .format(c, info['tbbd']['mark'] + str(i)))

            # Move as few windows as possible.
            source = 'scnd'
            target = 'main'
            if len(info['scnd']['children'])\
                    > len(info['main']['children']):
                source = 'main'
                target = 'scnd'

            # Move the source windows to the target container.
            children = info[source]['children']
            if target == 'scnd':
                command.append('[con_id={}] focus'\
                        .format(info['scnd']['children'][0]))
                command.append('[con_id={}] focus, move to mark {}'\
                            .format(children.pop(0), info['scnd']['mark']))
                command.append('move {}'\
                        .format(get_movement(info['scnd']['layout'], 'prev')))
            else:
                command.append('[con_id={}] focus'\
                        .format(info['main']['children'][-1]))
                children.reverse()
            for c in children:
                command.append('[con_id={}] move to mark {}'\
                        .format(c, info[target]['mark']))

            # Change the mark if necessary.
            if target == 'scnd':
                command.extend(rename_secondary_container(info))

            # Focus the correct window and make tabbed.
            command.append('[con_id={}] focus'.format(focused))
            if not info[target]['layout'] == 'tabbed':
                command.append('layout tabbed')

    elif info['mode'] == 'monocle':

        if I3DT_HIDE_BAR: os.system("polybar-msg cmd show 1>/dev/null")

        focused = info['focused']

        # Parse the children.
        info['scnd']['children'] = info['tbbd']['children']
        for c in info['scnd']['children']:
            info['main']['children'].remove(c)
            command.append('[con_id={}] unmark'.format(c))

        # Make sure that the main container is not empty.
        if not info['main']['children']:
            info['main']['children'].append(info['scnd']['children'].pop(0))

        # Create the secondary container and move all windows.
        if info['scnd']['children']:
            first = info['scnd']['children'].pop(0)
            create_container(i3, 'scnd', first)
            logging.debug('Move windows to container: {}'.format('scnd'))
            command.append('[con_id={}] layout tabbed'.format(first))
            for c in info['scnd']['children']:
                command.append('[con_id={}] move to mark {}'\
                    .format(c, info['scnd']['mark']))
            command = execute_commands(command, '')

        # Reapply the container layouts.
        info = get_workspace_info(i3)
        for k in ['main', 'scnd']:
            command.append(restore_container_layout(k, info))

    # Execute the command chain.
    execute_commands(command, '')


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


def on_window_close(i3, e):
    logging.info('Window::Close')
    if e.container.floating.endswith('on'): return
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
            elif len(info['tiled']) > 1:
                children = info['tiled']
                create_container(i3, 'main', children[0])
                create_container(i3, 'scnd', children[1])
                info = get_workspace_info(i3)
                for i in info['unmanaged']:
                    command.append('[con_id={}] move to mark {}'\
                            .format(i, info['scnd']['mark']))
    else:
        os.system("polybar-msg cmd show 1>/dev/null")

    execute_commands(command)


def on_window_new(i3, e):

    logging.info('Window::New')

    # Ignore polybar events.
    if not e.container.name or e.container.name.startswith('polybar'):
        return

    # Ignore floating windows
    if e.container.floating.endswith('on'):
        return

    info = get_workspace_info(i3)

    # Ignore manually tiled workspaces.
    if info['mode'] == 'manual':
        return

    # Exit if there are to few tiled windows.
    if len(info['tiled']) < 2:
        return

    # Create the main container.
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
            i3dt_monocle_toggle(i3, e)
        elif e.binding.command == 'nop i3dt_tabbed_toggle':
            i3dt_tabbed_toggle(i3, e)


i3 = i3ipc.Connection()
try:
    i3.on(Event.WINDOW_FLOATING, on_window_floating)
    i3.on(Event.WINDOW_FOCUS, on_window_focus)
    i3.on(Event.WINDOW_NEW, on_window_new)
    i3.on(Event.BINDING, on_binding)
    i3.on(Event.WORKSPACE_FOCUS, on_workspace_focus)
    i3.on(Event.WINDOW_CLOSE, on_window_close)
    # i3.on(Event.WINDOW_FOCUS, on_window_focus)
    # i3.on(Event.WINDOW_MOVE, on_window_move)
    i3.main()
finally:
    i3.main_quit()
