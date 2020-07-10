#!/usr/bin/env python3

import asyncio
import i3ipc
from i3ipc import Event
import os
import time
import argparse
import logging

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

# Check the workspace ignore argument.
for w in args.workspaces_ignore:
    if w not in map(str, range(1, 10)):
        raise ValueError('Invalid ignore workspace: {}'.format(args.workspaces_ignore))

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
I3DT_MAIN_LAYOUT    = dict()
I3DT_SCND_LAYOUT    = dict()
I3DT_GLBL_MARK      = 'I3DT_GLBL_{}'
I3DT_MAIN_MARK      = 'I3DT_MAIN_{}'
I3DT_SCND_MARK      = 'I3DT_SCND_{}'
I3DT_MAIN_TBBD_MARK = 'I3DT_MAIN_{}_TBBD_'
I3DT_SCND_TBBD_MARK = 'I3DT_SCND_{}_TBBD_'

# Workspaces to ignore.
I3DT_WORKSPACE_IGNORE = []
if args.workspaces_only:
    I3DT_WORKSPACE_IGNORE = list(map(str, range(1, 10)))
    for w in args.workspaces_only:
        I3DT_WORKSPACE_IGNORE.remove(w)
elif args.workspaces_ignore:
    I3DT_WORKSPACE_IGNORE = args.workspaces_ignore

previous_window = []
current_window = []


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


def i3dt_focus(i3, e):

    # Logging event.
    logging.info('Window::Focus::{}'\
            .format(e.binding.command.replace('nop ', '', 1)))

    # Get focused window.
    tree = i3.get_tree()
    focused = tree.find_focused()
    workspace = focused.workspace()

    key = workspace.name
    if not key in I3DT:
        I3DT[key] = { 'mode': 'i3' }

    # Get the action.
    action = e.binding.command.split(" ")[-1]
    is_fullscreen_mode = focused.fullscreen_mode

    command = []
    if action in ['next', 'prev']:

        index = 0;
        focused_index = []
        windows = []
        for c in workspace.leaves():
            windows.append(c.id)
            if c.id == focused.id:
                focused_index = index
            index += 1

        if not focused_index:
            if action == 'next':
                command.append('[con_id={}] focus'\
                        .format(windows[1 % len(windows)]))
            elif action == 'prev':
                command.append('[con_id={}] focus'\
                        .format(windows[(len(windows) - 1) % len(windows)]))
        else:
            if action == 'next':
                command.append('[con_id={}] focus'\
                        .format(windows[(focused_index + 1) % len(windows)]))
            elif action == 'prev':
                command.append('[con_id={}] focus'\
                        .format(windows[(focused_index - 1) % len(windows)]))
        if is_fullscreen_mode:
            command.append('fullscreen toggle')

    elif action == 'other':
        if I3DT[key]['mode'] in ['i3dt', 'simple_tabbed']:
            if is_fullscreen_mode:
                command.append('fullscreen toggle')
            command.append('focus parent, focus next')
            if is_fullscreen_mode:
                command.append('fullscreen toggle')

    # Execute all commands.
    execute_commands(command)


def i3dt_move(i3, e):

    logging.info('Window::Focus::{}'\
            .format(e.binding.command.replace('nop ', '', 1)))

    # Get focused window.
    tree = i3.get_tree()
    focused = tree.find_focused()
    workspace = focused.workspace()

    command = []

    key = workspace.name
    if not key in I3DT:
        I3DT[key] = { 'mode': 'i3' }

    # Get the action.
    action = e.binding.command.split(" ")[-1]

    if action == 'other':
        # Check if focused is in the main container.
        main_mark = I3DT_MAIN_MARK.format(key)
        main = workspace.find_marked(main_mark)
        scnd_mark = I3DT_SCND_MARK.format(key)
        scnd = tree.find_marked(scnd_mark)
        if not main:
            return
        main_children = main[0].descendants()
        main_is_focused = False
        for c in main_children:
            if c.id == focused.id:
                main_is_focused = True
                break
        if main_is_focused:
            if len(main_children) == 1:
                if not scnd:
                    return
                scnd_focused = scnd[0].focus[0]
                command.append('[con_id={}] swap container with con_id {}'\
                        .format(main_children[0].id, scnd_focused))
                command.append('[con_id={}] focus'\
                        .format( scnd_focused))
            else:
                if not scnd:
                    command.append('[con_id={}] focus'\
                            .format(main[0].id))
                    command = execute_commands(command)
                    i3dt_create_container(i3, focused, workspace, scnd_mark)
                    command.append('[con_id={}] focus'\
                            .format(focused.id))
                else:
                    scnd_focused = scnd[0].focus[0]
                    scnd_children = scnd[0].descendants()
                    command.append('[con_id={}] focus'\
                            .format(scnd_children[0].id))
                    command.append('[con_id={}] move to mark {}'\
                            .format(focused.id, scnd_mark))
                    command.append('[con_id={}] focus'\
                            .format(focused.id))
                    if scnd[0].layout in ['splitv', 'stacked']:
                        command.append('[con_id={}] move up'\
                                .format(focused.id))
                    else:
                        command.append('[con_id={}] move left'\
                                .format(focused.id))
        else:
            command.append('[con_id={}] focus'\
                    .format(main_children[-1].id))
            command.append('[con_id={}] move to mark {}'\
                    .format(focused.id, main_mark))
            command.append('[con_id={}] focus'\
                    .format(focused.id))

    # Execute all commands.
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
        I3DT[key] = {
                'mode': 'i3',
                'glbl': {'id': [], 'orientation': 'horizontal'},
                'main': {'id': [], 'layout': 'splitv', 'children': []},
                'scnd': {'id': [], 'layout': 'splitv', 'children': []},
                }

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
    main_children = main.descendants()
    main_is_focused = False
    for c in main_children:
        if focused.id == c.id:
            main_is_focused = True
            break

    if main_is_focused:
        if scnd:
            if scnd.focus:
                command.append('[con_id={}] focus'\
                        .format(scnd.focus[-1]))
            else:
                scnd_children = scnd.descendants()
                if scnd_children :
                    command.append('[con_id={}] focus'\
                            .format(scnd_children[0].id))

        else:
            command.append('[con_id={}] focus'\
                    .format(main.id))
    else:
        if scnd:
            scnd_children = scnd.descendants()
            command.append('[con_id={}] focus'\
                    .format(scnd_children[-1].id))

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

def i3dt_tabbed_simple_toggle(i3):
    global I3DT

    logging.info('Workspace::Simple Tabbed')

    # Commmand chain array.
    command = []

    # Tree information.
    tree = i3.get_tree()
    focused = tree.find_focused()
    workspace = focused.workspace()

    # Check if workspace should be handled.
    key = workspace.name
    if key in I3DT_WORKSPACE_IGNORE:
        return

    glbl_mark = I3DT_GLBL_MARK.format(key)
    main_mark = I3DT_MAIN_MARK.format(key)
    scnd_mark = I3DT_SCND_MARK.format(key)

    glbl = workspace.find_marked(glbl_mark)
    main = workspace.find_marked(main_mark)
    scnd = workspace.find_marked(scnd_mark)

    if I3DT[key]['mode'] == 'i3dt':

        # Exit if there is no main container.
        if not main:
            return

        # Set tabbed mode enabled.
        I3DT[key]['mode'] = 'simple_tabbed'
        logging.debug('Enable:')

        # Store main layout and make tabbed.
        main = main[0]
        main_child = main.descendants()[0]
        I3DT_MAIN_LAYOUT[key] = main.layout
        if not main.layout == 'tabbed':
            command.append('[con_id={}] layout tabbed'\
                    .format(main_child.id))

        if scnd:
            # Store the layout of the secondary container and make tabbed.
            scnd = scnd[0]
            scnd_child = scnd.descendants()[0]
            I3DT_SCND_LAYOUT[key] = scnd.layout
            if not scnd.layout == 'tabbed':
                command.append('[con_id={}] layout tabbed'\
                        .format(scnd_child.id))

            if glbl:
                command.append('[con_id={}] layout tabbed'.\
                        format(scnd.id))

            # Make the secondary container tabbed.
            if not glbl:
                command.append('[con_id={}] layout tabbed'.\
                        format(workspace.id))
                command = execute_commands(command, '')
                tree = i3.get_tree()
                focused = tree.find_focused()
                workspace = focused.workspace()
                command.append('[con_id={}] mark {}'.\
                        format(workspace.descendants()[0].id, glbl_mark))

        execute_commands(command, '')

    elif I3DT[key]['mode'] == 'simple_tabbed':

        # Set i3dt mode enabled.
        I3DT[key]['mode'] = 'i3dt'

        if scnd:

            # Focus the secondary container and make split.
            scnd = scnd[0]
            command.append('[con_id={}] layout toggle split'.\
                    format(scnd.id))

            # Recreate the layout of the secondary container.
            scnd_children = scnd.descendants()
            if not scnd.layout == I3DT_SCND_LAYOUT[key]:
                command.append('[con_id={}] layout {}'\
                        .format(scnd_children[0].id, I3DT_SCND_LAYOUT[key]))

        if main:

            main = main[0]
            main_children = main.descendants()
            if not main.layout == I3DT_MAIN_LAYOUT[key]:
                command.append('[con_id={}] layout {}'\
                        .format(main_children[0].id, I3DT_MAIN_LAYOUT[key]))


        # Execute command chain.
        execute_commands(command, 'Disable:')


# The goal of tabbing mode, but slow.
def i3dt_tabbed_toggle(i3):

    global I3DT
    global I3DT_MAIN_LAYOUT
    global I3DT_SCND_LAYOUT

    logging.info('Workspace::Tabbed')

    # Commmand chain array.
    command = []

    tree = i3.get_tree()
    focused = tree.find_focused()
    workspace = focused.workspace()

    # Check if workspace should be handled.
    key = workspace.name
    if key in I3DT_WORKSPACE_IGNORE:
        return

    glbl_mark = I3DT_GLBL_MARK.format(key)
    main_mark = I3DT_MAIN_MARK.format(key)
    scnd_mark = I3DT_SCND_MARK.format(key)
    tbbd_mark = I3DT_SCND_TBBD_MARK.format(key)

    glbl = workspace.find_marked(glbl_mark)
    main = workspace.find_marked(main_mark)

    if I3DT[key]['mode'] == 'i3dt':

        logging.debug('Tabbed enable:')

        if main:
            # Set tabbed mode enabled.
            I3DT[key]['mode'] = 'tabbed'

            # Store main layout and focused window id.
            main = main[0]
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

    elif I3DT[key]['mode'] == 'tabbed':

        logging.debug('Tabbed disable:')

        # Set tabbed mode disabled.
        I3DT[key]['mode'] = 'i3dt'

        # Exit if there is no main container.
        if not main:
            return

        # Find all windows that should be in the main and the secondary
        # container, respectively.
        main = main[0]
        main_children = []
        scnd_children = []
        for c in main.leaves():
            in_scnd = False
            for m in c.marks:
                if m.startswith(tbbd_mark):
                    in_scnd = True
                    command.append('[con_id={}] unmark {}'\
                            .format(c.id, m))
                    break
            if in_scnd:
                scnd_children.append(c)
            else:
                main_children.append(c)

        if not scnd_children:
            if not key in I3DT_MAIN_LAYOUT:
                I3DT_MAIN_LAYOUT[key] = 'splitv'
            command.append('[con_id={}] layout {}'\
                    .format(main_children[0].id, I3DT_MAIN_LAYOUT[key]))
            execute_commands(command, '')
            return


        # Move as few windows as possible.
        if len(scnd_children) > len(main_children):
            scnd = main

            # Create a temporary split container for the first window with the
            # purpose to be the new main container.
            # TODO: Generalize the left movement to handle moved windows.
            main_child = main_children.pop(0)
            if not key in I3DT_MAIN_LAYOUT:
                I3DT_MAIN_LAYOUT[key] = 'splitv'
            command.append('[con_id={}] focus, move left, splitv, layout {}'\
                    .format(main_child.id, I3DT_MAIN_LAYOUT[key]))

            # Find the temporary split container.
            main = []
            command = execute_commands(command, '')
            for c in i3.get_tree().find_by_id(workspace.id).descendants():
                for d in c.descendants():
                    if d.id == main_child.id:
                        main = c

            # Move the new split container into the global container.
            if glbl:
                logging.debug('\tGlobal exist')
                command.append('[con_id={}] move to mark {}'\
                        .format(main.id, glbl_mark))

            # Mark the main container.
            command.append('[con_id={}] mark {}'\
                        .format(main.id, main_mark))

            # Move the remaining children to the main container.
            for c in main_children:
                command.append('[con_id={}] move to mark {}'\
                        .format(c.id, main_mark))

            # Mark the secondary container.
            command.append('[con_id={}] mark {}'\
                        .format(scnd.id, scnd_mark))

            # Apply the stored layout to the secondary container.
            if not key in I3DT_SCND_LAYOUT:
                I3DT_SCND_LAYOUT[key] = 'splitv'
            command.append('[con_id={}] layout {}'\
                     .format(scnd_children[0].id, I3DT_SCND_LAYOUT[key]))

        else:
            # Create a temporary split container for the last window with the
            # purpose to be the new scnd container.
            # TODO: Generalize the right movement to handle moved windows.
            scnd_last_child = scnd_children.pop(-1)
            if not key in I3DT_SCND_LAYOUT:
                I3DT_SCND_LAYOUT[key] = 'splitv'
            command.append('[con_id={}] focus, move right, splitv, layout {}'\
                    .format(scnd_last_child.id, I3DT_SCND_LAYOUT[key]))

            # Find the temporary split container.
            command = execute_commands(command, '')
            scnd = []
            for c in i3.get_tree().find_by_id(workspace.id).descendants():
                for d in c.descendants():
                    if d.id == main_child.id:
                        scnd = c

            # Move the new split container into the global container.
            if glbl:
                command.append('[con_id={}] move to mark {}'\
                        .format(scnd.id, glbl_mark))

            # Mark the scnd container.
            command.append('[con_id={}] mark {}'\
                        .format(scnd.id, scnd_mark))

            # Move the remaining children to the scnd container.
            for c in scnd_children:
                command.append('[con_id={}] move to mark {}'\
                        .format(c.id, scnd_mark))

            # Apply the stored layout to the main container.
            if not key in I3DT_MAIN_LAYOUT:
                I3DT_MAIN_LAYOUT[key] = 'splitv'
            command.append('[con_id={}] layout {}'\
                     .format(main_children[0].id, I3DT_MAIN_LAYOUT[key]))

        # Focus the right container.
        command.append('[con_id={}] focus'\
                .format(focused.id))

        # Check if global still exist.
        if glbl:
            command = execute_commands(command, '')
            tree = i3.get_tree()
            focused = tree.find_focused()
            workspace = focused.workspace()
            main = workspace.find_marked(main_mark)
            main_marks = []
            for c in main[0].descendants():
                for m in c.marks:
                    main_marks.append(m)
            if main_marks:
                print('Main marks')
                for m in main_marks:
                    print(m)
            else:
                print('No main marks')

            scnd = tree.find_marked(scnd_mark)
            scnd_marks = []
            for c in scnd[0].descendants():
                for m in c.marks:
                    scnd_marks.append(m)
            if scnd_marks:
                print('scnd marks')
                for m in scnd_marks:
                    print(m)
            else:
                print('No scnd marks')

            # maybe_glbl = workspace.descendant()[0]

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

    # Logging event.
    logging.info('Workspace::Focus::{}'\
            .format(e.current.name))

    key = e.current.name
    glbl_mark = I3DT_GLBL_MARK.format(key)
    main_mark = I3DT_MAIN_MARK.format(key)
    scnd_mark = I3DT_SCND_MARK.format(key)
    tbbd_mark = I3DT_SCND_TBBD_MARK.format(key)
    tree = i3.get_tree()
    focused = tree.find_focused()
    workspace = focused.workspace()
    marks = i3.get_marks()

    if not key in I3DT:

        # Initialize the I3DT dictionary.
        I3DT[key] = { 'mode': 'i3' }

        # Exit if workspace is in the ignore list.
        if key in I3DT_WORKSPACE_IGNORE:
            return

        # Check the container marks for the main and secondary container.
        I3DT[key] = { 'mode': 'i3' }
        for m in marks:
            if m in [main_mark, scnd_mark]:
                I3DT[key]['mode'] = 'i3dt'
            elif m == glbl_mark:
                glbl = workspace.find_marked(glbl_mark)
                if glbl[0].layout == 'tabbed':
                    I3DT[key]['mode'] = 'simple_tabbed'
                    break
            elif m.startswith(tbbd_mark):
                I3DT[key]['mode'] = 'tabbed'
                break

    # Exit if workspace is in the ignore list.
    if key in I3DT_WORKSPACE_IGNORE:
        return

    # Create an I3DT session.
    if I3DT[key]['mode'] == 'i3':

        # Get descendants.
        I3DT[key]['mode'] = 'i3dt'
        windows = workspace.leaves()

        # Exit if there are less than two windows.
        if len(windows) < 2:
            return

        # Create the main container.
        windows = workspace.leaves()
        window = windows.pop(0)
        execute_commands('[con_id={}] focus, splitv'.format(window.id), 'Create main container:')
        workspace = i3.get_tree().find_focused().workspace()
        main_container = []
        for c in workspace.descendants():
            for d in c.descendants():
                if d.id == window.id:
                    main_container = c
                    break
            if main_container:
                break
        execute_commands('[con_id={}] mark {}'\
                .format(main_container.id, main_mark), '')

        # Create the secondary container.
        window = windows.pop(0)
        execute_commands('[con_id={}] focus, splitv'.format(window.id), 'Create secondary container:')
        workspace = i3.get_tree().find_focused().workspace()
        scnd_container = []
        for c in workspace.descendants():
            for d in c.descendants():
                if d.id == window.id:
                    scnd_container = c
                    break
            if scnd_container:
                break
        command = []
        command.append('[con_id={}] mark {}'\
                .format(scnd_container.id, scnd_mark))
        for c in windows:
            command.append('[con_id={}] move to mark {}'\
                    .format(c.id, scnd_mark))
        execute_commands(command, '')

    else:
        # Find unmanaged windows.
        unmanaged_windows = workspace.leaves()
        main = workspace.find_marked(main_mark)
        if main:
            for c in main[0].leaves():
                unmanaged_windows.remove(c)
        scnd = workspace.find_marked(scnd_mark)
        if scnd:
            for c in scnd[0].leaves():
                unmanaged_windows.remove(c)

        # Move all unmanaged windows to an existing container.
        mark = scnd_mark
        if not scnd:
            mark = main_mark
        command = []
        for c in unmanaged_windows:
            command.append('[con_id={}] move to mark {}'\
                    .format(c.id, mark))
        execute_commands(command)


        # # Exit if no windows.
        # if not containers:
        #     return


        # # Parse the workspace.
        # key = workspace.name


        # Create I3DT session.
        # if I3DT[key]['mode'] == 'i3':

    #         # Find all windows with a valid name.
    #         focused = []
    #         windows = []
    #         for c in containers:
    #             if not c.name == None:
    #                 windows.append(c)
    #                 if c.focused:
    #                     focused = c.id

    #         # Make sure that one window will be focused.
    #         if not focused:
    #             focused = window[0].id

    #         # Move all windows to the scratchpad.
    #         for w in windows:
    #             i3.command('[con_id={}] move scratchpad'.format(w.id))

    #         # Make sure to horizontally.
    #         i3.command('split h, layout splith')

    #         # Move all windows back and tile.
    #         no_main = True
    #         no_scnd = True
    #         for w in windows:

    #             # Get window from scratchpad, focus and tile.
    #             i3.command('[con_id={}] scratchpad show, floating toggle, focus'.format(w.id))

    #             # Create the main and secondary containers.
    #             if no_main:
    #                 # Main container.
    #                 i3dt_create_container(i3, w, e.current, main_mark)
    #                 no_main = False
    #             elif no_scnd:
    #                 # Secondary container.
    #                 i3.command('[con_id={}] focus'.format(I3DT[key]['main']['id']))
    #                 i3dt_create_container(i3, w, e.current, scnd_mark)
    #                 no_scnd = False
    #             else:
    #                 # Mark the window to the secondary container.
    #                 I3DT[key]['scnd']['children'].append(w.id)

    #         # Focus the correct window.
    #         i3.command('[con_id={}] focus'.format(focused))


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
        I3DT[key] = {
                'mode': 'i3dt',
                'glbl': {'id': [], 'orientation': 'horizontal'},
                'main': {'id': [], 'layout': 'splitv', 'children': []},
                'scnd': {'id': [], 'layout': 'splitv', 'children': []},
                }

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
        elif e.binding.command == 'nop i3dt_tabbed_toggle':
            i3dt_tabbed_toggle(i3)
        elif e.binding.command == 'nop i3dt_tabbed_simple_toggle':
            i3dt_tabbed_simple_toggle(i3)
    else:
        if e.binding.command.startswith('exec'):
            i3dt_execute(i3, e)


i3 = i3ipc.Connection()
try:
    i3.on(Event.WINDOW_NEW, on_window_new)
    i3.on(Event.BINDING, on_binding)
    # i3.on("window::focus", on_window_focus)
    i3.on(Event.WORKSPACE_FOCUS, on_workspace_focus)
    # i3.on(Event.WINDOW_CLOSE, on_window_close)
    # i3.on(Event.WINDOW_FOCUS, on_window_focus)
    # i3.on(Event.WINDOW_MOVE, on_window_move)
    i3.main()
finally:
    i3.main_quit()
