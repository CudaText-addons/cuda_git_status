from cudatext import *
from .git_manager import GitManager

CELL_TAG_INFO = 20 #CudaText built-in value for last statusbar cell
CELL_TAG = 100 #uniq value for all plugins adding cells via statusbar_proc()
CELL_WIDTH = 150 #width of cell in pixels

class Command:
    def __init__(self):
        index = statusbar_proc('main', STATUSBAR_FIND_CELL, value=CELL_TAG_INFO)
        if not index:
            index = -1
        statusbar_proc('main', STATUSBAR_ADD_CELL, index=index, tag=CELL_TAG)
        statusbar_proc('main', STATUSBAR_SET_CELL_SIZE, tag=CELL_TAG, value=CELL_WIDTH)

        self.manager = GitManager(ed)

    def update(self):
        text = self.manager.badge()
        statusbar_proc('main', STATUSBAR_SET_CELL_TEXT, tag=CELL_TAG, value=text)

    def on_focus(self, ed_self):
        self.update()

    def on_open(self, ed_self):
        self.update()

    def on_save(self, ed_self):
        self.update()
