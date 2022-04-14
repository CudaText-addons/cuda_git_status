plugin for CudaText.
for active file tab, it shows information about Git repository, in the additional
cell of the statusbar:

- branch name, e.g. "master".
- '*' symbol, if this branch is not clean.
- '+number': number of commits ahead.
- '-number': number of commits behind.

plugin was ported from GitStatusBar plugin for Sublime Text.
later, gutter highlighting for Git changed lines was added.
later, additional actions were added, with the popup menu, which is shown by click
on the statusbar cell. those actions are also available by menu items in
"Plugins / Git Status".

plugin has config-file with few options. to edit it, call menu item:
"Options / Settings-plugins / Git Status / Config".
edit the suggested file "plugins.ini" section [git_status],
and then restart CudaText.


authors:
- Alexey Torgashin (CudaText)
- David Emanuel Santiago (@demanuel at GitHub)
- Shovel (@halfbrained at GitHub)
- Ildar Khasanshin (@ildarkhasanshin at GitHub)

license: MIT
icon from GitHub, license: MIT
