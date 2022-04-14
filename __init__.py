import os
import time
from queue import Queue
from threading import Thread, Event
from . import git_manager
from .git_manager import GitManager

from cudatext import *
from cudax_lib import get_translation
_ = get_translation(__file__)  # I18N

CELL_TAG_INFO = 20 # CudaText tag of last statusbar cell, we insert our cell before it
CELL_TAG = app_proc(PROC_GET_UNIQUE_TAG, '')
BAR_H = 'main'
DLG_W = 700
DLG_H = 400

fn_config = os.path.join(app_path(APP_DIR_SETTINGS), 'plugins.ini')

### Threaded
is_getting_badge = Event()

gitmanager = GitManager()

def is_dir_root(s):
	return s==os.sep or s.endswith(':') or s.endswith(':\\')

def git_relative_path(fn):
    dir = os.path.dirname(fn)
    while dir and not is_dir_root(dir) and not os.path.isdir(dir+os.sep+'.git'):
        dir = os.path.dirname(dir)
    return os.path.relpath(fn, dir) if dir and not is_dir_root(dir) else ''
    
def gitman_loop(q_fns, q_badges):
    while True:
        fn = q_fns.get()    # wait for request
        is_getting_badge.set()
        while not q_fns.empty():    # get last if have multiple requests
            fn = q_fns.get()

        #if fn is None:
            #return

        _badge = gitmanager.badge(fn)
        q_badges.put((fn, _badge))
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

        self.h_menu = None

    def init_bar_cell(self):

        # insert our cell before "info" cell
        index = statusbar_proc(BAR_H, STATUSBAR_FIND_CELL, value=CELL_TAG_INFO)
        if index is None:
            return False

        index_new = statusbar_proc(BAR_H, STATUSBAR_FIND_CELL, value=CELL_TAG)
        if index_new is None:
            statusbar_proc(BAR_H, STATUSBAR_ADD_CELL, index=index, tag=CELL_TAG)
            statusbar_proc(BAR_H, STATUSBAR_SET_CELL_ALIGN, tag=CELL_TAG, value='C')
            statusbar_proc(BAR_H, STATUSBAR_SET_CELL_AUTOSIZE, tag=CELL_TAG, value=True)
            statusbar_proc(BAR_H, STATUSBAR_SET_CELL_CALLBACK, tag=CELL_TAG, value='module=cuda_git_status;cmd=callback_statusbar_click;')

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
        self.decor_style = ini_read(fn_config, 'git_status', 'decor_style', 'LightBG3')
        
        global DLG_W
        global DLG_H
        DLG_W = int(ini_read(fn_config, 'git_status', 'dialog_w', str(DLG_W)))
        DLG_H = int(ini_read(fn_config, 'git_status', 'dialog_h', str(DLG_H)))

        d = app_proc(PROC_THEME_SYNTAX_DICT_GET, '')
        if self.decor_style in d:
            git_manager.MY_DECOR_COLOR = d[self.decor_style]['color_back']

    def save_ops(self):

        ini_write(fn_config, 'git_status', 'white_icon', '1' if self.white_icon else '0')
        ini_write(fn_config, 'git_status', 'git_program', gitmanager.git)
        ini_write(fn_config, 'git_status', 'decor_style', self.decor_style)

        global DLG_W
        global DLG_H
        ini_write(fn_config, 'git_status', 'dialog_w', str(DLG_W))
        ini_write(fn_config, 'git_status', 'dialog_h', str(DLG_H))

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

        timer_proc(TIMER_START, 'cuda_git_status.on_timer', 150)

    def on_timer(self, tag='', info=''):
        """ * check if thread returned new badge
            * stop timer if thread is done
        """

        if not self.badge_results.empty(): # have new badge
            _fn, _badge = self.badge_results.get()
            self.update(_fn, _badge)

        # stop
        if self.badge_requests.empty() \
                and self.badge_results.empty() \
                and not is_getting_badge.is_set():
            timer_proc(TIMER_STOP, 'cuda_git_status.on_timer', 0)

    def update(self, fn, badge):

        if not self.init_bar_cell():
            #print('[Git Status] Statusbar not ready, '+reason)
            return
        #print('[Git Status] Statusbar ready, '+reason)

        # received answer for different filename?
        if fn != ed.get_filename():
            return

        statusbar_proc(BAR_H, STATUSBAR_SET_CELL_TEXT, tag=CELL_TAG, value=badge)
        statusbar_proc(BAR_H, STATUSBAR_SET_CELL_AUTOSIZE, tag=CELL_TAG, value=bool(badge))

        #show icon?
        icon = self.icon_index if badge else -1
        statusbar_proc(BAR_H, STATUSBAR_SET_CELL_IMAGEINDEX, tag=CELL_TAG, value=icon)

        #show panel?
        if not badge:
            statusbar_proc(BAR_H, STATUSBAR_SET_CELL_SIZE, tag=CELL_TAG, value=0)

    def is_git(self):
        s = statusbar_proc(BAR_H, STATUSBAR_GET_CELL_TEXT, tag=CELL_TAG)
        return bool(s)        

    def callback_statusbar_click(self, id_dlg, id_ctl, data='', info=''):
        if not self.is_git():
            return

        if self.h_menu is None:
            self.h_menu = menu_proc(0, MENU_CREATE)

            self.h_menu_jump1 = menu_proc(self.h_menu, MENU_ADD, caption=_('Jump to next change'), command='cuda_git_status.next_change')
            self.h_menu_jump2 = menu_proc(self.h_menu, MENU_ADD, caption=_('Jump to previous change'), command='cuda_git_status.prev_change')
            menu_proc(self.h_menu, MENU_ADD, caption='-')

            menu_proc(self.h_menu, MENU_ADD, caption=_('Get log'), command='cuda_git_status.get_log_')
            menu_proc(self.h_menu, MENU_ADD, caption=_('Get log of file'), command='cuda_git_status.get_log_file_')
            menu_proc(self.h_menu, MENU_ADD, caption='-')

            self.h_menu_status    = menu_proc(self.h_menu, MENU_ADD, caption=_('Get status'), command='cuda_git_status.get_status_')
            self.h_menu_notstaged = menu_proc(self.h_menu, MENU_ADD, caption=_('Get not-staged files'), command='cuda_git_status.get_notstaged_files_')
            self.h_menu_untracked = menu_proc(self.h_menu, MENU_ADD, caption=_('Get untracked files'), command='cuda_git_status.get_untracked_files_')
            menu_proc(self.h_menu, MENU_ADD, caption='-')

            self.h_menu_add       = menu_proc(self.h_menu, MENU_ADD, caption=_('Add file...'), command='cuda_git_status.add_file_')
            self.h_menu_restore   = menu_proc(self.h_menu, MENU_ADD, caption=_('Restore file...'), command='cuda_git_status.restore_file_')
            menu_proc(self.h_menu, MENU_ADD, caption='-')

            self.h_menu_commit    = menu_proc(self.h_menu, MENU_ADD, caption=_('Commit...'), command='cuda_git_status.commit_')
            self.h_menu_push      = menu_proc(self.h_menu, MENU_ADD, caption=_('Push'), command='cuda_git_status.push_')

        fn = ed.get_filename()
        fn_rel = git_relative_path(fn)
        diffs = bool(gitmanager.diff(fn))
        dirty = gitmanager.is_dirty()        
        list_notstaged = self.run_git(["diff", "--name-only"])
        list_untracked = self.run_git(["ls-files", ".", "--exclude-standard", "--others"])

        # 'not-staged', 'untracked'
        menu_proc(self.h_menu_notstaged, MENU_SET_ENABLED, command=bool(list_notstaged))
        menu_proc(self.h_menu_untracked, MENU_SET_ENABLED, command=bool(list_untracked))

        # 'add'
        en = fn_rel in list_notstaged.splitlines() or fn_rel in list_untracked.splitlines()
        menu_proc(self.h_menu_add, MENU_SET_ENABLED, command=en)

        # 'restore'
        menu_proc(self.h_menu_jump1, MENU_SET_ENABLED, command=diffs)
        menu_proc(self.h_menu_jump2, MENU_SET_ENABLED, command=diffs)
        menu_proc(self.h_menu_restore, MENU_SET_ENABLED, command=diffs)

        # 'commit'
        menu_proc(self.h_menu_commit, MENU_SET_ENABLED, command=dirty)

        menu_proc(self.h_menu, MENU_SHOW)

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
        if lines_start_:
            for line_start_ in lines_start_:
                if caret_y < line_start_:
                    ed.set_caret(0, line_start_ - 1)
                    break
        else:
            msg_status(_('No Git changes'))

    def prev_change(self):
        caret_y = self.get_caret_y()
        lines_start_ = self.get_lines_start()
        if lines_start_:
            lines_start_.reverse()
            for line_start_ in lines_start_:
                if caret_y > line_start_:
                    ed.set_caret(0, line_start_ - 1)
                    break
        else:
            msg_status(_('No Git changes'))

    def run_git(self, params_):
        (exit_code, output) = gitmanager.run_git(params_)
        if exit_code != 0:
            return ''
        return output

    def get_memo_(self, git_output_, caption_):
        output_ = git_output_.replace("\n", "\r")
        c1 = chr(1)
        text_ = '\n'.join([]
            +[c1.join(['type=memo', 'val='+output_, 'pos=%d,%d,%d,%d'%(6, 6, DLG_W-6, DLG_H-6*2-25), 'ex0=1', 'ex1=1'])]
            +[c1.join(['type=button', 'pos=%d,%d,%d,0'%(DLG_W-100, DLG_H-6-25, DLG_W-6), 'ex0=1', 'cap='+_('&OK')])]
        )
        dlg_custom(caption_, DLG_W, DLG_H, text_, focused=1)

    def get_status_(self):
        git_output_ = self.run_git(["status"])
        if git_output_:
            self.get_memo_(git_output_, _('Git: Status'))

    def add_file_(self):
        filename_ = ed.get_filename()
        res = msg_box(_("Do you really want to add this file?"), MB_OKCANCEL+MB_ICONQUESTION)
        if res == ID_OK:
            self.run_git(["add", filename_])
            msg_status(_('Git: file added'))

    def restore_file_(self):
        filename_ = ed.get_filename()
        res = msg_box(_("Do you really want to restore this file?"), MB_OKCANCEL+MB_ICONQUESTION)
        if res == ID_OK:
            git_output_ = self.run_git(["restore", filename_])
            if git_output_:
                self.get_memo_(git_output_, _('Git: Log of restore file'))

    def get_log_(self):
        git_output_ = self.run_git([
            '--no-pager', 'log', '--decorate=short', '--pretty=oneline', '--max-count=100',
        ])

        if git_output_:
            self.get_memo_(git_output_, _('Git: Log'))
        else:
            msg_status(_('Git: no log'))

    def get_log_file_(self):
        filename_ = ed.get_filename()
        git_output_ = self.run_git([
            '--no-pager', 'log', '--decorate=short', '--pretty=oneline', '--max-count=100',
            filename_])

        if git_output_:
            self.get_memo_(git_output_, _('Git: Log of file'))
        else:
            msg_status(_('Git: no log of file'))

    def get_notstaged_files_(self):
        git_output_ = self.run_git(["diff", "--name-only"])
        if git_output_:
            self.get_memo_(git_output_, _('Git: Changes not staged for commit'))
        else:
            msg_status(_('Git: no not-staged files'))

    def get_untracked_files_(self):
        git_output_ = self.run_git(["ls-files", ".", "--exclude-standard", "--others"])
        if git_output_:
            self.get_memo_(git_output_, _('Git: Untracked files'))
        else:
            msg_status(_('Git: no untracked files'))

    def commit_(self):
        if not self.is_git():
            return msg_status(_('No Git repo'))

        txt_ = dlg_input('Git: Commit changes', '')
        if txt_:
            git_output_ = self.run_git(["commit", "-m", txt_])
            if git_output_:
                self.get_memo_(git_output_, _('Git: Result of commit'))
            self.request_update(ed, 'commited')

    def push_(self):
        if not self.is_git():
            return msg_status(_('No Git repo'))

        git_output_ = self.run_git(["push"])
        if git_output_:
            self.get_memo_(git_output_, _('Git: Result of push'))
        self.request_update(ed, 'pushed')
