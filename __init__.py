import os
from cudatext import *
from .git_manager import GitManager

CELL_TAG_INFO = 20 #CudaText built-in value for last statusbar cell
CELL_TAG = 100 #uniq value for all plugins adding cells via statusbar_proc()
CELL_WIDTH = 150 #width of cell in pixels

icon_branch = os.path.join(os.path.dirname(__file__), 'git-branch.png')


class Command:
    def __init__(self):

        #insert our cell before "info" cell
        index = statusbar_proc('main', STATUSBAR_FIND_CELL, value=CELL_TAG_INFO)
        if not index:
            index = -1
        statusbar_proc('main', STATUSBAR_ADD_CELL, index=index, tag=CELL_TAG)
        statusbar_proc('main', STATUSBAR_SET_CELL_SIZE, tag=CELL_TAG, value=CELL_WIDTH)
        statusbar_proc('main', STATUSBAR_SET_CELL_ALIGN, tag=CELL_TAG, value='C')

        imglist = statusbar_proc('main', STATUSBAR_GET_IMAGELIST)
        if not imglist:
            imglist = imagelist_proc(0, IMAGELIST_CREATE)
            statusbar_proc('main', STATUSBAR_SET_IMAGELIST, value=imglist)

        index = imagelist_proc(imglist, IMAGELIST_ADD, value=icon_branch)
        statusbar_proc('main', STATUSBAR_SET_CELL_IMAGEINDEX, tag=CELL_TAG, value=index)

        self.gitmanager = GitManager(ed)


    def update(self):
        text = self.gitmanager.badge()
        statusbar_proc('main', STATUSBAR_SET_CELL_TEXT, tag=CELL_TAG, value=text)

    def on_focus(self, ed_self):
        self.update()

    def on_open(self, ed_self):
        self.update()

    def on_save(self, ed_self):
        self.update()
