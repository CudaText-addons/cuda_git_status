import os
from queue import Queue
from threading import Thread, Event
import time
from cudatext import *
from .git_manager import GitManager

CELL_TAG_INFO = 20 #CudaText built-in value for last statusbar cell
CELL_TAG = 100 #uniq value for all plugins adding cells via statusbar_proc()
BAR_H = 'main'

fn_config = os.path.join(app_path(APP_DIR_SETTINGS), 'plugins.ini')

### Threaded
is_getting_badge = Event()

gitmanager = GitManager()

def gitman_loop(q_fns, q_badges):
    while True:
        fn = q_fns.get()    # wait for request
        is_getting_badge.set()
        while not q_fns.empty():    # get last if have multiple requests
            fn = q_fns.get()

        #if fn is None:
            #return

        _badge = gitmanager.badge(fn)
        q_badges.put(_badge)
        is_getting_badge.clear()
#end Threaded

class Command:
    def __init__(self):

        self.is_loading_sesh = False # to ignore 'on_open()' while loading session
        self.badge_requests = None
        self.badge_results = None
        self.t_gitman = None

        self._last_request = None

        self.load_ops()
        self.load_icon()

    def init_bar_cell(self):

        #insert our cell before "info" cell
        index = statusbar_proc(BAR_H, STATUSBAR_FIND_CELL, value=CELL_TAG_INFO)
        if index is None:
            return False

        statusbar_proc(BAR_H, STATUSBAR_ADD_CELL, index=index, tag=CELL_TAG)
        statusbar_proc(BAR_H, STATUSBAR_SET_CELL_ALIGN, tag=CELL_TAG, value='C')

        statusbar_proc(BAR_H, STATUSBAR_SET_CELL_AUTOSIZE, tag=CELL_TAG, value=True)

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

        self.white_icon = ini_read(fn_config, 'git_status', 'white_icon', '0') == '1'
        gitmanager.git = ini_read(fn_config, 'git_status', 'git_program', 'git')

    def save_ops(self):

        ini_write(fn_config, 'git_status', 'white_icon', '1' if self.white_icon else '0')
        ini_write(fn_config, 'git_status', 'git_program', gitmanager.git)

    def open_config(self):

        self.save_ops()
        if os.path.isfile(fn_config):
            file_open(fn_config)


    def request_update(self, ed_self, _reason):
        """ * send request to badge-thread
            * start timer to check for result
        """

        if self.is_loading_sesh:
            return

        if self.t_gitman is None:
            self.badge_requests = Queue()
            self.badge_results = Queue()

            self.t_gitman = Thread(
                    target=gitman_loop,
                    args=(self.badge_requests, self.badge_results),
                    name='gitstatus_read',
                    daemon=True,
            )
            self.t_gitman.start()

        _filename = (ed_self or ed).get_filename()

        if (self._last_request
                and  self._last_request[0] == _filename
                and  self._last_request[1]+0.25 > time.time()): # skip if same request in last 250ms
            return

        self._last_request = (_filename, time.time())

        self.badge_requests.put(_filename)

        timer_proc(TIMER_START, self.on_timer, 50)

    def on_timer(self, tag='', info=''):
        """ * check if thread returned new badge
            * stop timer if thread is done
        """

        if not self.badge_results.empty(): # have new badge
            _badge = self.badge_results.get()
            self.update(_badge)

        # stop
        if self.badge_requests.empty() \
                and self.badge_results.empty() \
                and not is_getting_badge.is_set():
            timer_proc(TIMER_STOP, self.on_timer, 0)

    def update(self, badge):

        if not self.init_bar_cell():
            #print('[Git Status] Statusbar not ready, '+reason)
            return
        #print('[Git Status] Statusbar ready, '+reason)

        statusbar_proc(BAR_H, STATUSBAR_SET_CELL_TEXT, tag=CELL_TAG, value=badge)

        #show icon?
        icon = self.icon_index if badge else -1
        statusbar_proc(BAR_H, STATUSBAR_SET_CELL_IMAGEINDEX, tag=CELL_TAG, value=icon)

        #show panel?
        if not badge:
            statusbar_proc(BAR_H, STATUSBAR_SET_CELL_SIZE, tag=CELL_TAG, value=0)


    def on_tab_change(self, ed_self):
        self.request_update(ed_self, 'on_tab_change')

    def on_open(self, ed_self):
        self.request_update(ed_self, 'on_open')

    def on_save(self, ed_self):
        self.request_update(ed_self, 'on_save')

    def on_focus(self, ed_self):
        self.request_update(ed_self, 'on_focus')

    def on_change_slow(self, ed_self):
        self.request_update(ed_self, 'on_change_slow')

    def on_state(self, ed_self, state):
        # to skip on_open() when loading session
        if state == APPSTATE_SESSION_LOAD_BEGIN: # started
            self.is_loading_sesh = True

        elif state in [APPSTATE_SESSION_LOAD_FAIL, APPSTATE_SESSION_LOAD]: # ended
            self.is_loading_sesh = False
            self.request_update(ed, 'session loaded')

    def get_caret_y(self):
        return ed.get_carets()[0][1] + 1

    def get_lines_start(self):
        parts_ = gitmanager.diff(ed.get_filename())
        lines_start_ = []
        for part_ in parts_:
            if len(part_) == 2 and isinstance(part_, list):
                lines_start_.append(int(part_[0]))
            else:
                lines_start_.append(int(part_))
        return lines_start_

    def next_change(self):
        caret_y = self.get_caret_y()
        lines_start_ = self.get_lines_start()
        if len(lines_start_) > 0:
            for line_start_ in lines_start_:
                if caret_y < line_start_:
                    ed.set_caret(0, line_start_ - 1)
                    return

    def prev_change(self):
        caret_y = self.get_caret_y()
        lines_start_ = self.get_lines_start()
        if len(lines_start_) > 0:
            for line_start_ in lines_start_:
                if caret_y > line_start_:
                    ed.set_caret(0, line_start_ - 1)
