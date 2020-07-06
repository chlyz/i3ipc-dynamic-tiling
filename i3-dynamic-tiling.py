#!/usr/bin/env python3

import asyncio
import i3ipc
from i3ipc import Event
import os
import time

# Global variables.

I3DT_DEBUG            = False
I3DT_WORKSPACE_IGNORE = ["1", "4"]
I3DT_MAIN_MARK        = 'I3DT_MAIN_{}'
I3DT_SCND_MARK        = 'I3DT_SCND_{}'

I3DT = dict()
I3DT_MAIN_LAYOUT = dict()
I3DT_SCND_LAYOUT = dict()

previous_window = []
current_window = []

def i3dt_focus(i3, e):

    # Get focused window.
    tree = i3.get_tree()
    focused = tree.find_focused()
    workspace = focused.workspace()

    key = workspace.name
    if not key in I3DT:
        I3DT[key] = { 'mode': 'i3' }

    # Get the action.
    action = e.binding.command.split(" ")[-1]

    if action in ['next', 'prev']:
        index = 0;
        focused_index = []
        windows = []
        for c in workspace.descendants():
            if not c.name == None:
                windows.append(c.id)
                if c.id == focused.id:
                    focused_index = index
                index += 1

        if action == 'next':
            i3.command('[con_id={}] focus'\
                    .format(windows[(focused_index + 1) % len(windows)]))
        elif action == 'prev':
            i3.command('[con_id={}] focus'\
                    .format(windows[(focused_index - 1) % len(windows)]))

    elif action == 'other':
        if I3DT[key]['mode'] in ['i3dt', 'simple_tabbed']:
            i3.command('focus parent, focus next')

def i3dt_move(i3, e):

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
                    i3.command('[con_id={}] focus'\
                            .format(main[0].id))
                    i3dt_create_container(i3, focused, workspace, scnd_mark)
                    i3.command('[con_id={}] focus'\
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

    if command:
        i3.command(', '.join(command))


def i3dt_execute(i3, e):

    global I3DT

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
            i3.command('[con_id={}] focus'\
                    .format(scnd.focus[-1]))

        else:
            i3.command('[con_id={}] focus'\
                    .format(main.id))
    else:
        scnd_children = scnd.descendants()
        i3.command('[con_id={}] focus'\
                .format(scnd_children[-1]))

def i3dt_create_container(i3, window, workspace, mark):

    global I3DT

    # Create a temporary container.
    i3.command('open, mark I3DT_TEMP, split v, layout splitv')

    # Move the window to the temporary container.
    i3.command('[con_id={}] floating disable, move to mark I3DT_TEMP'.format(window.id))

    # Create the parent container.
    i3.command('[con_mark=I3DT_TEMP] focus, focus parent')
    i3.command('mark {}'.format(mark))

    # Kill the temporary container.
    i3.command('[con_mark=I3DT_TEMP] kill')

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

    main_mark = I3DT_MAIN_MARK.format(key)
    scnd_mark = I3DT_SCND_MARK.format(key)
    tbbd_mark = scnd_mark + "_TABBED_"

    main = tree.find_marked(main_mark)

    if I3DT[key]['mode'] == 'i3dt':

        # Exit if there is no main container.
        if not main:
            return

        # Set tabbed mode enabled.
        I3DT[key]['mode'] = 'simple_tabbed'

        # Store main layout and make tabbed.
        main = main[0]
        main_children = main.descendants()
        I3DT_MAIN_LAYOUT[key] = main.layout
        if not main.layout == 'tabbed':
            command.append('[con_id={}] layout tabbed'\
                    .format(main_children[0].id))

        # Exit if there is no secondary container.
        scnd = tree.find_marked(scnd_mark)
        if not scnd:
            return

        # Store the layout of the secondary container and make tabbed.
        scnd = scnd[0]
        scnd_children = scnd.descendants()
        I3DT_SCND_LAYOUT[key] = scnd.layout
        if not scnd.layout == 'tabbed':
            command.append('[con_id={}] layout tabbed'\
                    .format(scnd_children[0].id))

        # Make the secondary container tabbed.
        command.append('[con_id={}] focus, focus parent, layout tabbed'.\
                format(scnd.id))
        command.append('[con_id={}] focus'.\
                format(focused.id))

    elif I3DT[key]['mode'] == 'simple_tabbed':

        # Set i3dt mode enabled.
        I3DT[key]['mode'] = 'i3dt'

        scnd = i3.get_tree().find_marked(scnd_mark)
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

    # Execute the command chain.
    if command:
        i3.command(', '.join(command))

    if I3DT_DEBUG:
        print('I3DT {}: {}'.format(key, I3DT[key]))

# The goal of tabbing mode, but slow.
def i3dt_tabbed_toggle(i3):

    global I3DT
    global I3DT_MAIN_LAYOUT
    global I3DT_SCND_LAYOUT

    if I3DT_DEBUG:
        print('\nWorkspace::Tabbed')
        print('=================')

    # Commmand chain array.
    command = []

    tree = i3.get_tree()
    focused = tree.find_focused()
    workspace = focused.workspace()

    # Check if workspace should be handled.
    key = workspace.name
    if key in I3DT_WORKSPACE_IGNORE:
        return

    main_mark = I3DT_MAIN_MARK.format(key)
    scnd_mark = I3DT_SCND_MARK.format(key)
    tbbd_mark = scnd_mark + "_TABBED_"

    main = tree.find_marked(main_mark)

    if I3DT[key]['mode'] == 'i3dt':

        # Main container.
        if main:
            main = main[0]

            # Store main layout and make tabbed.
            main_children = main.descendants()
            I3DT_MAIN_LAYOUT[key] = main.layout
            if not main.layout == 'tabbed':
                command.append('[con_id={}] layout tabbed'\
                        .format(main_children[0].id))

            # Store the focused container id.
            main_focused_id = main.focus[0]

        # Secondary container.
        scnd = tree.find_marked(scnd_mark)
        if scnd:
            scnd = scnd[0]

            # Store the layout of the secondary container.

            I3DT_SCND_LAYOUT[key] = scnd.layout

            # Make the secondary container tabbed.
            scnd_children = scnd.descendants()
            if not scnd.layout == 'tabbed':
                command.append('[con_id={}] layout tabbed'\
                        .format(scnd_children[0].id))

            # Focus last main window.
            command.append('[con_id={}] focus'\
                    .format(main_children[-1].id))

            # Find all windows in the secondary container, then mark and move
            # them. This is done in reverse due to the fact that i3 always puts
            # the windows after the focused container, and thus implicitly
            # reversing the order.
            move_commands = []
            for i, c in enumerate(scnd_children):
                move_commands.append('[con_id={}] mark {}, move to mark {}'\
                        .format(c.id, tbbd_mark + str(i), main_mark))
            move_commands.reverse()
            command.extend(move_commands)

        # Focus the window in focus before this script.
        command.append('[con_id={}] focus'\
                .format(main_focused_id))
        command.append('[con_id={}] focus'\
                .format(focused.id))

        # Set tabbed mode enabled.
        I3DT[key]['mode'] = 'tabbed'

    elif I3DT[key]['mode'] == 'tabbed':

        # Set tabbed mode disabled.
        I3DT[key]['mode'] = 'i3dt'

        # Exit if there is no main container.
        if not main:
            return

        # Find all marked windows in the main container, then move and unmark
        # them.
        main = main[0]
        main_children = main.descendants()
        scnd = []
        for c in main_children:
            for m in c.marks:
                if m.startswith(tbbd_mark):
                    # Remove the mark.
                    command.append('[con_id={}] unmark {}'.format(c.id, m))

                    # Create the secondary container and move the window.
                    if scnd:
                        command.append('[con_id={}] move to mark {}'\
                                .format(c.id, scnd_mark))
                    else:
                        command.append('[con_id={}] focus'\
                                .format(main.id))
                        i3.command(', '.join(command))
                        command = []
                        i3dt_create_container(i3, c, workspace, scnd_mark)
                        scnd = i3.get_tree().find_marked(scnd_mark)
                        if not key in I3DT_SCND_LAYOUT:
                            I3DT_SCND_LAYOUT[key] = 'splitv'
                        command.append('[con_id={}] layout {}'\
                                 .format(c.id, I3DT_SCND_LAYOUT[key]))

                    break

        # Restore the main layout.
        if not key in I3DT_MAIN_LAYOUT:
            I3DT_MAIN_LAYOUT[key] = 'splitv'
        command.append('[con_id={}] layout {}'\
                .format(main_children[0].id, I3DT_MAIN_LAYOUT[key]))

        command.append('[con_id={}] focus'.format(focused.id))

    # Execute the command chain.
    if command:
        i3.command(', '.join(command))
        command = []

    return command



def i3dt_promote_demote(i3):
    print('Promote or demote')


def i3dt_mirror(i3):

    global I3DT

    tree = i3.get_tree()
    focused = tree.find_focused()
    workspace = focused.workspace()

    if I3DT_DEBUG:
        print('\nWorkspace::Mirror')
        print('=================')

    # Only reflect the workspace if the secondary container exist and for the
    # i3dt standard mode.
    key = workspace.name
    main_mark = I3DT_MAIN_MARK.format(key)
    main = tree.find_marked(main_mark)
    scnd_mark = I3DT_SCND_MARK.format(key)
    scnd = i3.get_tree().find_marked(scnd_mark)
    if scnd and I3DT[key]['mode'] == 'i3dt':

        # Swap the containers.
        i3.command('[con_id={}] swap container with con_id {}'\
                .format(main[0].id, scnd[0].id))

    if I3DT_DEBUG:
        print('I3DT {}: {}'.format(key, I3DT[key]))


def i3dt_reflect(i3):

    global I3DT

    tree = i3.get_tree()
    focused = tree.find_focused()
    workspace = focused.workspace()

    if I3DT_DEBUG:
        print('\nWorkspace::Reflect')
        print('==================')

    # Only reflect the workspace if the secondary container exist and for the
    # i3dt standard mode.
    key = workspace.name
    scnd_mark = I3DT_SCND_MARK.format(key)
    scnd = i3.get_tree().find_marked(scnd_mark)
    if scnd and I3DT[key]['mode'] == 'i3dt':

        # Change the split container.
        scnd = scnd[0]
        i3.command('[con_id={}] layout toggle split'.format(scnd.id))

        # Read the split container, that is, the first descendant of the
        # workspace container.
        tree = i3.get_tree()
        focused = tree.find_focused()
        workspace = focused.workspace()

        # Find the global split container.
        glbl = workspace.descendants()[0]

        # Update the layout of the secondary container.
        scnd = i3.get_tree().find_marked(scnd_mark)[0]

        if (scnd.layout == 'splitv' and glbl.orientation == 'vertical') or \
                (scnd.layout == 'splith' and glbl.orientation == 'horizontal'):
            scnd_children = scnd.descendants()
            i3.command('[con_id={}] layout toggle split'\
                    .format(scnd_children[0].id))

    if I3DT_DEBUG:
        print('I3DT {}: {}'.format(key, I3DT[key]))


def i3dt_kill(i3):

    global I3DT

    if I3DT_DEBUG:
        print('\nWindow::Kill')
        print('============')

    tree = i3.get_tree()
    focused = tree.find_focused()
    workspace = focused.workspace()
    ws_name = workspace.name

    # Check if focused window is in the main container.
    key = workspace.name
    is_in_main = focused.id in I3DT[key]['main']['children']

    if not is_in_main \
            or (is_in_main and len(I3DT[key]['main']['children']) > 1):
        # Not in main container or there are several windows in the main
        # container. Thus, it is safe to kill the focused window.
        i3.command('[con_id={}] kill'.format(focused.id))
        if focused.id in I3DT[key]['main']['children']:
            I3DT[key]['main']['children'].remove(focused.id)
            if not I3DT[key]['main']['children']:
                I3DT[key]['main'] = {'id': [], 'layout': 'splitv', 'children':[]}
        if focused.id in I3DT[key]['scnd']['children']:
            I3DT[key]['scnd']['children'].remove(focused.id)
            if not I3DT[key]['scnd']['children']:
                I3DT[key]['scnd'] = {'id': [], 'layout': 'splitv', 'children':[]}
    else:
        # The focused window is the only window in the main container. If
        # there is a secondary container, swap the focused window with the
        # first window in the second container and then kill the, now
        # moved, focused window. Otherwise just kill the focused window.
        if I3DT[key]['scnd']['children']:
            # Get and remove the first element in the secondary container. If
            # empty reset the container.
            scnd_id = I3DT[key]['scnd']['children'].pop(0)
            if not I3DT[key]['scnd']['children']:
                I3DT[key]['scnd'] = {'id': [], 'layout': 'splitv', 'children':[]}

            # Swap the containers.
            i3.command('[con_id={}] swap container with con_id {}'\
                    .format(focused.id, scnd_id))
            i3.command('[con_id={}] focus'.format(scnd_id))

            # Append the window to the main container.
            I3DT[key]['main']['children'].append(scnd_id)

        # Kill the window.
        i3.command('[con_id={}] kill'.format(focused.id))
        I3DT[key]['main']['children'].remove(focused.id)
        if not I3DT[key]['main']['children']:
            I3DT[key]['main'] = {'id': [], 'layout': 'splitv', 'children':[]}
            I3DT[key]['glbl'] = {'id': [], 'orientation': 'horizontal'}
            I3DT[key]['mode'] = 'i3dt'

    if I3DT_DEBUG:
        print('I3DT {}: {}'.format(key, I3DT[key]))


def on_workspace_focus(i3, e):

    global I3DT

    tree = i3.get_tree()
    # focused = tree.find_focused()
    # workspace = focused.workspace()
    # ws_name = workspace.name
    key = e.current.name

    if I3DT_DEBUG:
        print('\nWorkspace::Focus')
        print('================')

    if not key in I3DT:

        # Get descendants.
        containers = e.current.descendants()

        # Exit if no containers.
        if not containers:
            return

        # Initialize the I3DT dictionary.
        I3DT[key] = {
                'mode': 'i3',
                'glbl': {'id': [], 'orientation': 'horizontal'},
                'main': {'id': [], 'layout': 'splitv', 'children': []},
                'scnd': {'id': [], 'layout': 'splitv', 'children': []},
                }

        # Exit if workspace is in the ignore list.
        if key in I3DT_WORKSPACE_IGNORE:
            if I3DT_DEBUG:
                print('I3DT {}: {}'.format(key, I3DT[key]))
            return

        # Check the container marks for the main and secondary container.
        main_mark = I3DT_MAIN_MARK.format(e.current.name)
        scnd_mark = I3DT_SCND_MARK.format(e.current.name)
        tbbd_mark = scnd_mark +  "_TABBED_"
        for c in containers:
            for m in c.marks:
                if m == main_mark:
                    I3DT[key]['mode'] = 'i3dt'
                    break
                elif m == scnd_mark:
                    I3DT[key]['mode'] = 'i3dt'
                    break
                elif m.startswith(tbbd_mark):
                    I3DT[key]['mode'] = 'tabbed'
                    break

        # Create I3DT session.
        if I3DT[key]['mode'] == 'i3':

            # Find all windows with a valid name.
            focused = []
            windows = []
            for c in containers:
                if not c.name == None:
                    windows.append(c)
                    if c.focused:
                        focused = c.id

            # Make sure that one window will be focused.
            if not focused:
                focused = window[0].id

            # Move all windows to the scratchpad.
            for w in windows:
                i3.command('[con_id={}] move scratchpad'.format(w.id))

            # Make sure to horizontally.
            i3.command('split h, layout splith')

            # Move all windows back and tile.
            no_main = True
            no_scnd = True
            for w in windows:

                # Get window from scratchpad, focus and tile.
                i3.command('[con_id={}] scratchpad show, floating toggle, focus'.format(w.id))

                # Create the main and secondary containers.
                if no_main:
                    # Main container.
                    i3dt_create_container(i3, w, e.current, main_mark)
                    no_main = False
                elif no_scnd:
                    # Secondary container.
                    i3.command('[con_id={}] focus'.format(I3DT[key]['main']['id']))
                    i3dt_create_container(i3, w, e.current, scnd_mark)
                    no_scnd = False
                else:
                    # Mark the window to the secondary container.
                    I3DT[key]['scnd']['children'].append(w.id)

            # Focus the correct window.
            i3.command('[con_id={}] focus'.format(focused))

    if I3DT_DEBUG:
        print('I3DT {}: {}'.format(key, I3DT[key]))


def on_window_new(i3, e):

    global I3DT

    # Commmand chain array.
    command = []

    # Print debug info.
    if I3DT_DEBUG:
        print('\nWindow::New')
        print('===========')

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

    # Workspace is handled by I3DT. Create the main and the secondary containers
    # dynamically as needed.
    main_mark = I3DT_MAIN_MARK.format(workspace.name)
    main = workspace.find_marked(main_mark)
    if not main:
        i3dt_create_container(i3, window, workspace, main_mark)
    else:
        scnd_mark = I3DT_SCND_MARK.format(workspace.name)
        scnd  = workspace.find_marked(scnd_mark)
        if not scnd:
            i3.command('[con_id={}] focus'.format(main[0].id))
            i3dt_create_container(i3, window, workspace, scnd_mark)
        else:
            command.append('[con_id={}] move to mark {}'\
                    .format(window.id, scnd_mark))

    # Focus the current window.
    command.append('[con_id={}] focus'.format(window.id))

    # Execute the command chain.
    if command:
        i3.command(', '.join(command))

    # Print debug info.
    if I3DT_DEBUG:
        print('I3DT {}: {}'.format(key, I3DT[key]))


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
