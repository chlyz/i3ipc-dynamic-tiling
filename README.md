# i3-dynamic-tiling

A Python IPC implementation of dynamic tiling for the i3 window manager, trying
to mimic the tiling behavior of the excellent [dwm](http://dwm.suckless.org/)
and [xmonad](https://xmonad.org/), while utilizing the strengths of
[i3](https://i3wm.org/) and [sway](https://swaywm.org/).

## Features

The software creates a _main_ and a _secondary_ container dynamically similar
to the tiling mode of _dwm_ and _xmonad_. The containers have independent
layouts and the _secondary_ container can be toggled to be on the side of the
_main_ container of underneath it.

There is also a _tabbed_ mode mimicking the monocle mode of _dwm_ and _xmonad_
that temporarily moves all windows to the main container and enables the
_tabbed_ layout, all the while remembering the tiling of the containers so that
the workspace is recreated when the _tabbed_ mode is toggled.

## Status

If someone actually, against all odds, find this code, here is a gently
warning: This code is to be considered _alpha_ and have only been tested in
_Ubuntu 18.04_ with _i3 4.18.1_. Features on the radar:

- [x] `window::new`: New windows are created and managed in a _main_ and a
  _secondary_ container.
- [ ] `window::move` (_Ongoing_): Windows can be moved but not yet ensured to
  be handled dynamically.
- [ ] `window::focus` (_Ongoing_): Implement moving focus between windows as
  they where in a list, without having to consider the position and layout of
  the _main_ and _secondary_ containers.
- [x] `workspace::focus`: Tries to recreate the dynamic tiling after a restart.

Special effects:

- [x] `Tabbed toggle`: The _tabbed_ mode is mimicking the _monocle_ mode of
  _dwm_ and _xmonad_ by the use of the _tabbed_ layout.
- [x] `Reflect toggle`: The _secondary_ container can be put on the side of
  underneath the _main_ container.

## Configuration

The configuration of _i3-dynamic-tiling_ is done in two ways:

### Environmental variables

  - `I3DT_WORKSPACE_IGNORE`: Workspaces to ignore, that is, use `i3` defaults
  and do not apply dynamic tiling for these workspaces.

### Configuration file

TODO: Add a minimal configuration file.

## Inspiration

I am/was a heavy user of _dwm_ and _xmonad_ and I absolutely love those window
managers, but the user base is quite small compared to _i3_ and _sway_. This
implies a lot of patch management or scripting in a not so simple language.
Also, there are some programs that I require in my work that does not behave
well with these window managers, like _Matlab_ in _xmonad_.

On the other hand, _i3_ and _sway_ has a relatively big user base and is under
active development, which implies that most programs will either behave well or
otherwise get fixed. Furthermore, with _wayland_ on the rise and no _dwm_ or
_xmonad_ implementations known to me on the way.

Unfortunately, the positions of the spawned windows in _i3_ and _sway_ needs to
be done manually. This can be tedious and I rather like the dynamic tiling in
other window managers like _dwm_, _xmonad_, or _qtile_ (there are many more).

But there is an excellent protocol to talk with _i3_ and _sway_ that can be
used to force the behavior to mimic the dynamic tiling.

The code is written in python using the i3 IPC framework and _stealing_ ideas
from [budlabs i3ass](https://github.com/budlabs/i3ass). I highly recommend the
videos of [budlabs](https://www.youtube.com/channel/UCi8XrDg1bK_MJ0goOnbpTMQ)
on my favourite youtube channel.

