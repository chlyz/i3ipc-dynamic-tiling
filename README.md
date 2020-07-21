# i3-dynamic-tiling

A Python IPC implementation of dynamic tiling for the i3 window manager, trying
to mimic the tiling behavior of the excellent [dwm](http://dwm.suckless.org/)
and [xmonad](https://xmonad.org/), while utilizing the strengths of
[i3](https://i3wm.org/) and [sway](https://swaywm.org/).

## Status

If someone actually, against all odds, find this code, here is a gently
warning: This code is to be considered _alpha_ and have only been tested in
_Ubuntu 18.04_ with `i3 4.18.1`.

Unfortunately, the current version is not compliant with `sway` due to that it
is not possible to mark split containers in the same way as in `i3`. This will
hopefully change in the future or a refactorization of this code is possible.

## Features

The software creates a _main_ and a _secondary_ container dynamically similar
to the tiling mode of `dwm` and `xmonad`. The containers have independent
layouts and the _secondary_ container can be toggled to be on the side of the
_main_ container of underneath it.

There is also a _tabbed_ mode mimicking the monocle mode of `dwm` and `xmonad`
that temporarily moves all windows to the main container and enables the
_tabbed_ layout, all the while remembering the tiling of the containers so that
the workspace is recreated when the _tabbed_ mode is toggled.

### Focus

Beyond the normal `i3` focus commands, the following are implemented:

+ `i3dt_focus next/prev`: Focus the next window on the active workspace with
  wrapping at the boundaries. For example, if focus _next_ on the last window
  of the workspace then the first window will be focused.

+ `i3dt_focus other`: If the focused window is in the main container then the
  last focused window in the secondary container will get focus and vice versa.

+ `i3dt_focus toggle`: Toggle the focus between the last two focused windows.

All focus commands in the list above respects the _fullscreen_ state of the
focused window, that is, if the focused window is in _fullscreen_ then the
focused window after the command will also be in _fullscreen_ mode.

### Move

Beyond the normal `i3` move commands, the following are implemented:

+ `i3dt_move next/prev`: Move the window within the parent container, without
  leaving the parent container.

+ `i3dt_move other`: If the focused window is in the main container then move
  the window to the secondary container and vice versa. The focus is kept
  within the original container.

+ `i3dt_move swap`: Swap the focused window with the focused window in other
  container. The focus is kept within the original container.

### Monocle alternatives

There are several alternatives the _monocle_ layout of `dwm` and `xmonad`:

+ _fullscreen_: It is possible to use the `i3` fullscreen mode to emulate the
  _monocle_ mode if the focus commands described in [Focus](#focus) are used.
  This is probably the fastest alternative with the downside is that it is easy
  to get lost.

+ _tabbed_: This package implements two different tabbed layouts:

  + `i3dt_monocle_toggle`: This version moves all windows to a main container
    and then applies the tabbed layout. The operation is reversible and the
    main and secondary containers are reproduced when toggled. This might be
    the most intuitive alternative to the _monocle_ layout, but it can be slow
    when there is a large number of windows on the workspace.

  + `i3dt_tabbed_toggle`: This version keeps the main and secondary containers
    but creates a global split container and applies the tabbed layout on all
    containers. This means that there will be two tab bars instead of one and
    therefore taking more screen real estate. I do not find this as intuitive
    as the version described above, but it is more in line with `i3` workflow
    and may be faster.

## Configuration

The configuration of _i3-dynamic-tiling_ is done in two ways:

### Argument passing

When execution the `python3 i3-dynamic-tiling.py` there are some options the
can be set:

- `--workspaces-ignore`: Workspaces to ignore, that is, use `i3` defaults and
  do not apply dynamic tiling for these workspaces. Example:

  ```bash
  python3 i3-dynamic-tiling.py --workspace-ignore 1 2 3
  ```

- `--workspaces-only`: Only apply dynamic tiling to these workspaces and let
  `i3` defaults rule the others. This takes precedence over
  `--workspaces-ignore`. Example:

  ```bash
  python3 i3-dynamic-tiling.py --workspace-only 1 2 3
  ```
- `--tabbed-hide-polybar`: Hide the polybar when in global tabbed or monocle
  mode. This require `enable-ipc = true` in your polybar config.

  ```bash
  python3 i3-dynamic-tiling.py --tabbed-hide-polybar true
  ```

- `--tabbed-use-monocle`: Use the monocle mode instead of the tabbed mode when
  the number of children is less than or equal to this number (default: 2)

  ```bash
  python3 i3-dynamic-tiling.py --tabbed-use-monocle 5
  ```

For debugging purposes, one can also change the level of logging with

- `--log-level`: The level of logging.

  ```bash
  python3 i3-dynamic-tiling.py --log-level debug
  ```

### Configuration file

These are my special settings that I use for this framework. Notice the `nop`
on _i3-dynamic-tiling_ special commands.

```
# Start the dynamic tiling.
exec_always $HOME/src/i3-dynamic-tiling/i3-dynamic-tiling --hide-polybar-tabbed true

# Disable the window title bar.
default_border pixel 2

hide_edge_borders smart
focus_follows_mouse no
workspace_auto_back_and_forth yes
show_marks yes

# Focus next cycle.
bindsym $mod+j nop i3dt_focus next

# Move next cycle.
bindsym $mod+shift+j nop i3dt_move next

# Focus previous in the same container.
bindsym $mod+k nop i3dt_focus prev

# Move next cycle.
bindsym $mod+shift+k nop i3dt_move prev

# Focus toggle container.
bindsym $mod+i nop i3dt_focus toggle

# Focus the other container.
bindsym $mod+o nop i3dt_focus other

# Move to the other container.
bindsym $mod+shift+o nop i3dt_move other

# Swap window with the other container.
bindsym $mod+Return nop i3dt_move swap

# Toggle simple tabbed mode.
bindsym $mod+space nop i3dt_tabbed_toggle

# Toggle tabbed mode.
bindsym $mod+shift+space nop i3dt_monocle_toggle

# Toggle secondary to the side of or below of main.
bindsym $mod+backslash nop i3dt_reflect

# Toggle secondary to the right or left hand side of main.
bindsym $mod+shift+backslash nop i3dt_mirror

# Toggle workspace.
bindsym $mod+Tab workspace back_and_forth

# Toggle layout current container.
bindsym $mod+semicolon layout toggle tabbed split
```

## Inspiration

I am/was a heavy user of `dwm` and `xmonad` and I absolutely love these window
managers, but the user base is quite small compared to `i3` and `sway`. This
implies a lot of manual patch management or scripting in a not so simple
language. Also, there are some programs that I require in my work that does
not behave well with these window managers, like `Matlab` in `xmonad`.

On the other hand, `i3` and `sway` has a relatively big user base and is under
active development, which implies that most programs will either behave well or
otherwise will get fixed. Furthermore, with `wayland` on the rise and there is
no, at least to my knowledge, `dwm` or `xmonad` implementations on the way.

Unfortunately, the positioning of the spawned windows in `i3` and `sway` needs
to be done manually. This can be tedious and I rather like the
dynamic/automatic tiling in other window managers like `dwm`, `xmonad`, or
`qtile` (there are many more).

Fortunately, there is an excellent protocol to talk with _i3_ and _sway_ that
can be used to force the behavior of dynamic tiling.

This code is written in python using the i3 IPC framework and _stealing_ ideas
from [budlabs i3ass](https://github.com/budlabs/i3ass). I highly recommend the
videos of [budlabs](https://www.youtube.com/channel/UCi8XrDg1bK_MJ0goOnbpTMQ)
on my favourite youtube channel.

