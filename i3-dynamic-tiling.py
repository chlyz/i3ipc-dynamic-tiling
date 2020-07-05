#!/usr/bin/env python3

import asyncio
import i3ipc
from i3ipc import Event
import os
import time

# Global variables.

DWM_DEBUG     = True
DWM_IGNORE    = ["1"]

DWM_MAIN_MARK = 'DWM_MAIN_{}'
DWM_SCND_MARK = 'DWM_SCND_{}'

# DWM_TBBD_MARK = 'DWM_TBBD_{}'
DWM = dict()
DWM_MODE = dict()
DWM_MAIN = dict()
DWM_SCND = dict()

DWM_MAIN_ID = dict()
DWM_SCND_ID = dict()

DWM_MAIN_LAYOUT = dict()
DWM_SCND_LAYOUT = dict()

previous_window = []
current_window = []

def i3_dwm_execute(i3, e):

    global DWM

    if not key in DWM:
        DWM[key] = {
                'mode': 'i3',
                'glbl': {'id': [], 'orientation': 'horizontal'},
                'main': {'id': [], 'layout': 'splitv', 'children': []},
                'scnd': {'id': [], 'layout': 'splitv', 'children': []},
                }

    # Get focused window.
    tree = i3.get_tree()
    focused = tree.find_focused()
    workspace = focused.workspace()

    # Check if workspace should be handled.
    key = workspace.name
    if key in DWM_IGNORE:
        return

    # Initialize the DWM dictionary.
    DWM[key]['mode'] = 'dwm'

    # If focused is in the main container, then focus either the main container
    # of the last child in the secondary container.
    # main_mark = DWM_MAIN_MARK.format(key)
    # main = workspace.find_marked(main_mark)
    # scnd = tree.find_marked(scnd_mark)
    # scnd_mark = DWM_SCND_MARK.format(key)
    # if main:
    #     main = main[0]
    #     main_children = main.descendants()
    #     main_ids = []
    #     for c in

    # if focused.id in DWM[key]['main']['children']:
    #     if DWM[key]['scnd']['id']:
    #         i3.command('[con_id={}] focus'\
    #                 .format(DWM[key]['scnd']['children'][-1]))
    #     else:
    #         i3.command('[con_id={}] focus'\
    #                 .format(DWM[key]['main']['id']))

    # If focused is in the secondary container, then focus the last child in
    # the secondary container.
    # if focused.id in DWM[key]['scnd']['children']:
    #     i3.command('[con_id={}] focus'\
    #             .format(DWM[key]['scnd']['children'][-1]))

def i3_dwm_layout(i3, e):

    global DWM

    if DWM_DEBUG:
        print('\nLayout')
        print('======')

    tree = i3.get_tree()
    focused = tree.find_focused()
    workspace = focused.workspace()

    # Update container layout.
    key = workspace.name
    for c in ['main', 'scnd']:
        if focused.id in DWM[key][c]['children']:
            DWM[key][c]['layout'] = tree.find_by_id(DWM[key][c]['id']).layout

    if DWM_DEBUG:
        print('DWM {}: {}'.format(key, DWM[key]))

def i3_dwm_create_container(i3, window, workspace, mark):

    global DWM

    # Create a temporary container.
    i3.command('open, mark DWM_TEMP, split v, layout splitv')

    # Move the window to the temporary container.
    i3.command('[con_id={}] floating disable, move to mark DWM_TEMP'.format(window.id))

    # Create the parent container.
    i3.command('[con_mark=DWM_TEMP] focus, focus parent')
    i3.command('mark {}'.format(mark))

    # Kill the temporary container.
    i3.command('[con_mark=DWM_TEMP] kill')

def i3_dwm_check_window_in_container(window, container):
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

def i3_dwm_tabbed_toggle_simple(i3):
    global DWM

    # Commmand chain array.
    command = []

    # Tree information.
    tree = i3.get_tree()
    focused = tree.find_focused()
    workspace = focused.workspace()

    # Check if workspace should be handled.
    key = workspace.name
    if key in DWM_IGNORE:
        return

    main_mark = DWM_MAIN_MARK.format(key)
    scnd_mark = DWM_SCND_MARK.format(key)
    tbbd_mark = scnd_mark + "_TABBED_"

    main = tree.find_marked(main_mark)

    if DWM[key]['mode'] == 'dwm':

        # Exit if there is no main container.
        if not main:
            return

        # Set tabbed mode enabled.
        DWM[key]['mode'] = 'simple_tabbed'

        # Store main layout and make tabbed.
        main = main[0]
        main_children = main.descendants()
        print(main_children)
        DWM_MAIN_LAYOUT[key] = main.layout
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
        DWM_SCND_LAYOUT[key] = scnd.layout
        if not scnd.layout == 'tabbed':
            command.append('[con_id={}] layout tabbed'\
                    .format(scnd_children[0].id))

        # Make the secondary container tabbed.
        command.append('[con_id={}] focus, focus parent, layout tabbed'.\
                format(scnd.id))
        command.append('[con_id={}] focus'.\
                format(focused.id))

    elif DWM[key]['mode'] == 'simple_tabbed':

        # Set dwm mode enabled.
        DWM[key]['mode'] = 'dwm'

        scnd = i3.get_tree().find_marked(scnd_mark)
        if scnd:

            # Focus the secondary container and make split.
            scnd = scnd[0]
            command.append('[con_id={}] layout toggle split'.\
                    format(scnd.id))

            # Recreate the layout of the secondary container.
            scnd_children = scnd.descendants()
            if not scnd.layout == DWM_SCND_LAYOUT[key]:
                command.append('[con_id={}] layout {}'\
                        .format(scnd_children[0].id, DWM_SCND_LAYOUT[key]))

        if main:
            main = main[0]
            main_children = main.descendants()
            if not main.layout == DWM_MAIN_LAYOUT[key]:
                command.append('[con_id={}] layout {}'\
                        .format(main_children[0].id, DWM_MAIN_LAYOUT[key]))

    # Execute the command chain.
    if command:
        i3.command(', '.join(command))

    if DWM_DEBUG:
        print('DWM {}: {}'.format(key, DWM[key]))

# The goal of tabbing mode, but not practical.
def i3_dwm_tabbed_toggle(i3):

    global DWM
    global DWM_MAIN_LAYOUT
    global DWM_SCND_LAYOUT

    if DWM_DEBUG:
        print('\nWorkspace::Tabbed')
        print('=================')

    # Commmand chain array.
    command = []

    tree = i3.get_tree()
    focused = tree.find_focused()
    workspace = focused.workspace()

    # Check if workspace should be handled.
    key = workspace.name
    if key in DWM_IGNORE:
        return

    main_mark = DWM_MAIN_MARK.format(key)
    scnd_mark = DWM_SCND_MARK.format(key)
    tbbd_mark = scnd_mark + "_TABBED_"

    main = tree.find_marked(main_mark)

    if DWM[key]['mode'] == 'dwm':

        # Main container.
        if main:
            main = main[0]

            # Set tabbed mode enabled.
            DWM[key]['mode'] = 'tabbed'

            # Store main layout and make tabbed.
            main_children = main.descendants()
            DWM_MAIN_LAYOUT[key] = main.layout
            if not main.layout == 'tabbed':
                command.append('[con_id={}] layout tabbed'\
                        .format(main_children[0].id))
            print('main')

        # Secondary container.
        scnd = tree.find_marked(scnd_mark)
        if scnd:
            scnd = scnd[0]

            # Store the layout of the secondary container.
            DWM_SCND_LAYOUT[key] = scnd.layout

            # Find all windows in the secondary container, then mark and move them.
            scnd_children = scnd.descendants()
            for i, c in enumerate(scnd_children):
                command.append('[con_id={}] mark {}, move to mark {}'\
                        .format(c.id, tbbd_mark + str(i), main_mark))

    else:

        # Set tabbed mode disabled.
        DWM[key]['mode'] = 'dwm'

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
                        i3_dwm_create_container(i3, c, workspace, scnd_mark)
                        scnd = i3.get_tree().find_marked(scnd_mark)
                        command.append('[con_id={}] layout {}'\
                                 .format(c.id, DWM_SCND_LAYOUT[key]))

                    break

        # Restore the main layout.
        command.append('[con_id={}] layout {}'\
                .format(main_children[0].id, DWM_MAIN_LAYOUT[key]))

        command.append('[con_id={}] focus'.format(focused.id))

    # Execute the command chain.
    if command:
        print(command)
        i3.command(', '.join(command))
        command = []

    return command



def i3_dwm_promote_demote(i3):
    print('Promote or demote')


def i3_dwm_reflect(i3):

    global DWM

    tree = i3.get_tree()
    focused = tree.find_focused()
    workspace = focused.workspace()

    if DWM_DEBUG:
        print('\nWorkspace::Reflect')
        print('==================')

    # Only reflect the workspace if the secondary container exist and for the
    # dwm standard mode.
    key = workspace.name
    if DWM[key]['scnd'] and DWM[key]['mode'] == 'dwm':

        # Change the split container.
        i3.command('[con_id={}] layout toggle split'.format(DWM[key]['scnd']['id']))

        # Read the split container, that is, the first descendant of the
        # workspace container. NOTE: This could be simplified.
        tree = i3.get_tree()
        focused = tree.find_focused()
        workspace = focused.workspace()

        # Find the global split container.
        glbl = workspace.descendants()[0]
        DWM[key]['glbl']['id'] = glbl.id
        DWM[key]['glbl']['orientation'] = glbl.orientation

        # Update the layout of the secondary container.
        scnd = tree.find_by_id(DWM[key]['scnd']['id'])
        DWM[key]['scnd']['layout'] = scnd.layout

        if (scnd.layout == 'splitv' and glbl.orientation == 'vertical') or \
                (scnd.layout == 'splith' and glbl.orientation == 'horizontal'):
            i3.command('[con_id={}] layout toggle split'.format(DWM[key]['scnd']['children'][0]))
            DWM[key]['scnd']['layout'] = \
                    i3.get_tree().find_by_id(DWM[key]['scnd']['id']).layout

    if DWM_DEBUG:
        print('DWM {}: {}'.format(key, DWM[key]))


def i3_dwm_kill(i3):

    global DWM

    if DWM_DEBUG:
        print('\nWindow::Kill')
        print('============')

    tree = i3.get_tree()
    focused = tree.find_focused()
    workspace = focused.workspace()
    ws_name = workspace.name

    # Check if focused window is in the main container.
    key = workspace.name
    is_in_main = focused.id in DWM[key]['main']['children']

    if not is_in_main \
            or (is_in_main and len(DWM[key]['main']['children']) > 1):
        # Not in main container or there are several windows in the main
        # container. Thus, it is safe to kill the focused window.
        i3.command('[con_id={}] kill'.format(focused.id))
        if focused.id in DWM[key]['main']['children']:
            DWM[key]['main']['children'].remove(focused.id)
            if not DWM[key]['main']['children']:
                DWM[key]['main'] = {'id': [], 'layout': 'splitv', 'children':[]}
        if focused.id in DWM[key]['scnd']['children']:
            DWM[key]['scnd']['children'].remove(focused.id)
            if not DWM[key]['scnd']['children']:
                DWM[key]['scnd'] = {'id': [], 'layout': 'splitv', 'children':[]}
    else:
        # The focused window is the only window in the main container. If
        # there is a secondary container, swap the focused window with the
        # first window in the second container and then kill the, now
        # moved, focused window. Otherwise just kill the focused window.
        if DWM[key]['scnd']['children']:
            # Get and remove the first element in the secondary container. If
            # empty reset the container.
            scnd_id = DWM[key]['scnd']['children'].pop(0)
            if not DWM[key]['scnd']['children']:
                DWM[key]['scnd'] = {'id': [], 'layout': 'splitv', 'children':[]}

            # Swap the containers.
            i3.command('[con_id={}] swap container with con_id {}'\
                    .format(focused.id, scnd_id))
            i3.command('[con_id={}] focus'.format(scnd_id))

            # Append the window to the main container.
            DWM[key]['main']['children'].append(scnd_id)

        # Kill the window.
        i3.command('[con_id={}] kill'.format(focused.id))
        DWM[key]['main']['children'].remove(focused.id)
        if not DWM[key]['main']['children']:
            DWM[key]['main'] = {'id': [], 'layout': 'splitv', 'children':[]}
            DWM[key]['glbl'] = {'id': [], 'orientation': 'horizontal'}
            DWM[key]['mode'] = 'dwm'

    if DWM_DEBUG:
        print('DWM {}: {}'.format(key, DWM[key]))



def on_workspace_focus(i3, e):

    global DWM

    tree = i3.get_tree()
    # focused = tree.find_focused()
    # workspace = focused.workspace()
    # ws_name = workspace.name
    key = e.current.name

    if DWM_DEBUG:
        print('\nWorkspace::Focus')
        print('================')

    if not key in DWM:

        # Get descendants.
        containers = e.current.descendants()

        # Exit if no containers.
        if not containers:
            return

        # Initialize the DWM dictionary.
        DWM[key] = {
                'mode': 'i3',
                'glbl': {'id': [], 'orientation': 'horizontal'},
                'main': {'id': [], 'layout': 'splitv', 'children': []},
                'scnd': {'id': [], 'layout': 'splitv', 'children': []},
                }

        # Exit if workspace is in the ignore list.
        if key in DWM_IGNORE:
            if DWM_DEBUG:
                print('DWM {}: {}'.format(key, DWM[key]))
            return

        # Check the container marks for the main and secondary container.
        main_mark = DWM_MAIN_MARK.format(e.current.name)
        scnd_mark = DWM_SCND_MARK.format(e.current.name)
        tbbd_mark = scnd_mark +  "_TABBED_"
        for c in containers:
            for m in c.marks:
                if m == main_mark:
                    DWM[key]['mode'] = 'dwm'
                    DWM[key]['main']['id'] = c.id
                    break
                elif m == scnd_mark:
                    DWM[key]['mode'] = 'dwm'
                    DWM[key]['scnd']['id'] = c.id
                    break
                elif m.startswith(tbbd_mark):
                    DWM[key]['mode'] = 'tabbed'
                    break

        # Restore DWM session.
        if DWM[key]['mode'] in ['dwm', 'tabbed']:

            # Find the children of the main container.
            main = tree.find_marked(main_mark)[0]
            DWM[key]['main']['id'] = main.id
            DWM[key]['main']['layout'] = main.layout
            for c in main.descendants():
                if c.marks:
                    for m in c.marks:
                        if m.startswith(tbbd_mark):
                            DWM[key]['scnd']['children'].append(c.id)
                            break
                else:
                    DWM[key]['main']['children'].append(c.id)

            # Find the children of the secondary container.
            scnd = tree.find_marked(scnd_mark)
            if scnd:
                DWM[key]['scnd']['id'] = scnd[0].id
                DWM[key]['scnd']['layout'] = scnd[0].layout
                for c in scnd[0].descendants():
                    DWM[key]['scnd']['children'].append(c.id)

            # Check if there is a workspace global container for the main and
            # secondary container.
            if not containers[0].marks:
                is_global = True
                for n in containers[0].nodes:
                    for m in n.marks:
                        if not m in [main_mark, scnd_mark]:
                            is_global = False
                            break
                if is_global:
                    DWM[key]['glbl']['id'] = containers[0].id
                    DWM[key]['glbl']['orientation'] = containers[0].orientation

        # Create DWM session.
        if DWM[key]['mode'] == 'i3':

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
                    i3_dwm_create_container(i3, w, e.current, main_mark)
                    no_main = False
                elif no_scnd:
                    # Secondary container.
                    i3.command('[con_id={}] focus'.format(DWM[key]['main']['id']))
                    i3_dwm_create_container(i3, w, e.current, scnd_mark)
                    no_scnd = False
                else:
                    # Mark the window to the secondary container.
                    DWM[key]['scnd']['children'].append(w.id)

            # Focus the correct window.
            i3.command('[con_id={}] focus'.format(focused))

    if DWM_DEBUG:
        print('DWM {}: {}'.format(key, DWM[key]))


def on_window_new(i3, e):

    global DWM

    # Commmand chain array.
    command = []

    # Print debug info.
    if DWM_DEBUG:
        print('\nWindow::New')
        print('===========')

    # Get the basic i3 state information.
    tree = i3.get_tree()
    window = tree.find_focused()
    workspace = window.workspace()

    # Initialize the DWM default dictionary.
    key = workspace.name
    if not key in DWM:
        DWM[key] = {
                'mode': 'dwm',
                'glbl': {'id': [], 'orientation': 'horizontal'},
                'main': {'id': [], 'layout': 'splitv', 'children': []},
                'scnd': {'id': [], 'layout': 'splitv', 'children': []},
                }

    # If workspace should be ignored set the mode to i3 and return.
    if key in DWM_IGNORE:
        DWM[key]['mode'] = 'i3'
        return

    # Workspace is handled by DWM. Create the main and the secondary containers
    # dynamically as needed.
    main_mark = DWM_MAIN_MARK.format(workspace.name)
    main = workspace.find_marked(main_mark)
    if not main:
        i3_dwm_create_container(i3, window, workspace, main_mark)
    else:
        scnd_mark = DWM_SCND_MARK.format(workspace.name)
        scnd  = workspace.find_marked(scnd_mark)
        if not scnd:
            i3.command('[con_id={}] focus'.format(main[0].id))
            i3_dwm_create_container(i3, window, workspace, scnd_mark)
        else:
            command.append('[con_id={}] move to mark {}'\
                    .format(window.id, scnd_mark))

    # Focus the current window.
    command.append('[con_id={}] focus'.format(window.id))

    # Execute the command chain.
    if command:
        i3.command(', '.join(command))

    # Print debug info.
    if DWM_DEBUG:
        print('DWM {}: {}'.format(key, DWM[key]))


def on_binding(i3, e):
    if e.binding.command.startswith('nop'):
        if e.binding.command == 'nop i3_dwm_kill':
            i3_dwm_kill(i3)
        elif e.binding.command == 'nop i3_dwm_reflect':
            i3_dwm_reflect(i3)
        elif e.binding.command == 'nop i3_dwm_tabbed_toggle':
            i3_dwm_tabbed_toggle_simple(i3)
        elif e.binding.command == 'nop i3_dwm_tabbed_simple_toggle':
            i3_dwm_tabbed_simple_toggle(i3)
    else:
        if e.binding.command.startswith('exec'):
            i3_dwm_execute(i3, e)


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
