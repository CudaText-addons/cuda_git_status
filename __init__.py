import os
from cudatext import *
from .git_manager import GitManager

CELL_TAG_INFO = 20 #CudaText built-in value for last statusbar cell
CELL_TAG = 100 #uniq value for all plugins adding cells via statusbar_proc()
BAR_H = 'main'

fn_config = os.path.join(app_path(APP_DIR_SETTINGS), 'cuda_git_status.ini')

gitmanager = GitManager()


class Command:
    def __init__(self):

        self.load_ops()
        self.load_icon()

    def init_bar_cell(self):

        #insert our cell before "info" cell
        index = statusbar_proc(BAR_H, STATUSBAR_FIND_CELL, value=CELL_TAG_INFO)
        if index is None:
            return False

        statusbar_proc(BAR_H, STATUSBAR_ADD_CELL, index=index, tag=CELL_TAG)
        statusbar_proc(BAR_H, STATUSBAR_SET_CELL_ALIGN, tag=CELL_TAG, value='C')
        return True

    def load_icon(self):

        imglist = statusbar_proc(BAR_H, STATUSBAR_GET_IMAGELIST)
        if not imglist:
            imglist = imagelist_proc(0, IMAGELIST_CREATE)
            statusbar_proc(BAR_H, STATUSBAR_SET_IMAGELIST, value=imglist)

        fn_icon = os.path.join(
                    os.path.dirname(__file__),
                    'git-branch.png' if not self.white_icon else 'git-branch_white.png'
                    )

        self.icon_index = imagelist_proc(imglist, IMAGELIST_ADD, value=fn_icon)


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

    def update(self, reason):

        if not self.init_bar_cell():
            #print('[Git Status] Statusbar not ready, '+reason)
            return
        #print('[Git Status] Statusbar ready, '+reason)
        
        text = gitmanager.badge(ed.get_filename())
        statusbar_proc(BAR_H, STATUSBAR_SET_CELL_TEXT, tag=CELL_TAG, value=text)

        #show icon?
        icon = self.icon_index if text else -1
        statusbar_proc(BAR_H, STATUSBAR_SET_CELL_IMAGEINDEX, tag=CELL_TAG, value=icon)

        #show panel?
        size = self.cell_width if text else 0
        statusbar_proc(BAR_H, STATUSBAR_SET_CELL_SIZE, tag=CELL_TAG, value=size)


    def on_tab_change(self, ed_self):
        self.update('on_tab_change')

    def on_open(self, ed_self):
        self.update('on_open')

    def on_save(self, ed_self):
        self.update('on_save')

    def on_focus(self, ed_self):
        self.update('on_focus')
