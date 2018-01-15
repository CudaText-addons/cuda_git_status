import os
from cudatext import *
from .git_manager import GitManager

CELL_TAG_INFO = 20 #CudaText built-in value for last statusbar cell
CELL_TAG = 100 #uniq value for all plugins adding cells via statusbar_proc()

fn_config = os.path.join(app_path(APP_DIR_SETTINGS), 'cuda_git_status.ini')

gitmanager = GitManager()


class Command:
    def __init__(self):

        self.load_ops()

        #insert our cell before "info" cell
        index = statusbar_proc('main', STATUSBAR_FIND_CELL, value=CELL_TAG_INFO)
        if not index:
            index = -1
        statusbar_proc('main', STATUSBAR_ADD_CELL, index=index, tag=CELL_TAG)
        statusbar_proc('main', STATUSBAR_SET_CELL_SIZE, tag=CELL_TAG, value=self.cell_width)
        statusbar_proc('main', STATUSBAR_SET_CELL_ALIGN, tag=CELL_TAG, value='C')

        imglist = statusbar_proc('main', STATUSBAR_GET_IMAGELIST)
        if not imglist:
            imglist = imagelist_proc(0, IMAGELIST_CREATE)
            statusbar_proc('main', STATUSBAR_SET_IMAGELIST, value=imglist)

        fn_icon = os.path.join(
                    os.path.dirname(__file__),
                    'git-branch.png' if not self.white_icon else 'git-branch_white.png'
                    )

        index = imagelist_proc(imglist, IMAGELIST_ADD, value=fn_icon)
        statusbar_proc('main', STATUSBAR_SET_CELL_IMAGEINDEX, tag=CELL_TAG, value=index)


    def load_ops(self):

        self.cell_width = int(ini_read(fn_config, 'op', 'statusbar_cell_width', '150'))
        self.white_icon = ini_read(fn_config, 'op', 'white_icon', '0') == '1'
        gitmanager.git = ini_read(fn_config, 'op', 'git_program', 'git')

    def save_ops(self):

        ini_write(fn_config, 'op', 'statusbar_cell_width', str(self.cell_width))
        ini_write(fn_config, 'op', 'white_icon', '1' if self.white_icon else '0')
        ini_write(fn_config, 'op', 'git_program', gitmanager.git)

    def open_config(self):

        self.save_ops()
        if os.path.isfile(fn_config):
            file_open(fn_config)

    def update(self):

        text = gitmanager.badge(ed.get_filename())
        statusbar_proc('main', STATUSBAR_SET_CELL_TEXT, tag=CELL_TAG, value=text)


    def on_focus(self, ed_self):
        self.update()

    def on_open(self, ed_self):
        self.update()

    def on_save(self, ed_self):
        self.update()
