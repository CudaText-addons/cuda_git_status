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
TIMERCALL = 'cuda_git_status.on_timer'

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

        timer_proc(TIMER_START, TIMERCALL, 70)

    def on_timer(self, tag='', info=''):
        """ * check if thread returned new badge
            * stop timer if thread is done
        """

        _fn, _badge = self.badge_results.get()
        self.update(_fn, _badge)

        # stop
        if self.badge_requests.empty() \
                and self.badge_results.empty() \
                and not is_getting_badge.is_set():
            timer_proc(TIMER_STOP, TIMERCALL, 0)

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

            self.h_menu_pull = menu_proc(self.h_menu, MENU_ADD, caption=_('Pull...'), command='cuda_git_status.pull_')
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

            self.h_menu_commit       = menu_proc(self.h_menu, MENU_ADD, caption=_('Commit...'), command='cuda_git_status.commit_')
            self.h_menu_commit_amend = menu_proc(self.h_menu, MENU_ADD, caption=_('Commit/amend...'), command='cuda_git_status.commit_amend_')
            self.h_menu_push         = menu_proc(self.h_menu, MENU_ADD, caption=_('Push...'), command='cuda_git_status.push_')
            self.h_menu_diff         = menu_proc(self.h_menu, MENU_ADD, caption=_('View file changes'), command='cuda_git_status.diff_')
            self.h_menu_diff_all     = menu_proc(self.h_menu, MENU_ADD, caption=_('View all changes'), command='cuda_git_status.diff_all_')
            menu_proc(self.h_menu, MENU_ADD, caption='-')

            self.h_menu_checkout     = menu_proc(self.h_menu, MENU_ADD, caption=_('Checkout branch'))


        fn = ed.get_filename()
        fn_rel = git_relative_path(fn)
        branch = gitmanager.branch()
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
        list_staged = bool(self.run_git(["diff", "--name-only", "--staged"]))
        no_commits_yet = 'No commits yet' in self.run_git(["status"])
        menu_proc(self.h_menu_commit, MENU_SET_ENABLED, command=((dirty and list_staged) or no_commits_yet))

        # 'commit amend'
        a, b = gitmanager.unpushed_info(branch)
        menu_proc(self.h_menu_commit_amend, MENU_SET_ENABLED, command=bool(a) or bool(b))

        # 'push'
        en = 'use "git push" to publish your local commits' in self.run_git(["status"])
        menu_proc(self.h_menu_push, MENU_SET_ENABLED, command=en)

        # 'checkout branch'
        list_branches = self.run_git(["branch"])
        menu_proc(self.h_menu_checkout,MENU_CLEAR)
        for branch in list_branches.splitlines():
            b = branch.strip()
            callback = 'module=cuda_git_status;cmd=checkout_;info={};'
            if b.startswith('*'):
                b = b[1:].strip()
                m = menu_proc(self.h_menu_checkout, MENU_ADD, caption=b, command=callback.format(b))
                menu_proc(m, MENU_SET_ENABLED, command=False)
                menu_proc(m, MENU_SET_CHECKED, command=True)
                menu_proc(m, MENU_SET_RADIOITEM, command=True)
            else:
                m = menu_proc(self.h_menu_checkout, MENU_ADD, caption=b, command=callback.format(b))
        menu_proc(self.h_menu_checkout, MENU_ADD, caption='-')
        menu_proc(self.h_menu_checkout, MENU_ADD, caption='<new branch>', command='cuda_git_status.checkout_new_branch_')

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

        if gitmanager.lastError:
                msg_box(gitmanager.lastError, MB_OK+MB_ICONERROR)

        if exit_code != 0:
            return ''
        return output

    def show_memo(self, text, caption):
        output_ = text.replace("\n", "\r")
        c1 = chr(1)
        text_ = '\n'.join([]
            +[c1.join(['type=memo', 'val='+output_, 'pos=%d,%d,%d,%d'%(6, 6, DLG_W-6, DLG_H-6*2-25), 'ex0=1', 'ex1=1'])]
            +[c1.join(['type=button', 'pos=%d,%d,%d,0'%(DLG_W-100, DLG_H-6-25, DLG_W-6), 'ex0=1', 'cap='+_('&OK')])]
        )
        dlg_custom(caption, DLG_W, DLG_H, text_, focused=1)

    def get_status_(self):
        text = self.run_git(["status"])
        if text:
            self.show_memo(text, _('Git: Status'))

    def add_file_(self):
        if not self.is_git():
            return msg_status(_('No Git repo'))

        filename_ = ed.get_filename()
        res = msg_box(_("Do you really want to add this file?"), MB_OKCANCEL+MB_ICONQUESTION)
        if res == ID_OK:
            self.run_git(["add", filename_])
            msg_status(_('Git: file added'))

    def restore_file_(self):
        if not self.is_git():
            return msg_status(_('No Git repo'))

        filename_ = ed.get_filename()
        res = msg_box(_("Do you really want to restore this file?"), MB_OKCANCEL+MB_ICONQUESTION)
        if res == ID_OK:
            text = self.run_git(["restore", filename_])
            if text:
                self.show_memo(text, _('Git: Log of restore file'))

    def get_log_(self):
        count = 100
        text = self.run_git([
            '--no-pager', 'log', '--decorate=short', '--pretty=oneline', '--max-count=%d'%count,
        ])

        if text:
            self.show_memo(text, _('Git: Log (last %d)')%count)
        else:
            msg_status(_('Git: no log'))

    def get_log_file_(self):
        count = 100
        filename_ = ed.get_filename()
        text = self.run_git([
            '--no-pager', 'log', '--decorate=short', '--pretty=oneline', '--max-count=%d'%count,
            filename_])

        if text:
            self.show_memo(text, _('Git: Log of file (last %d)')%count)
        else:
            msg_status(_('Git: no log of file'))

    def get_notstaged_files_(self):
        text = self.run_git(["diff", "--name-only"])
        if text:
            self.show_memo(text, _('Git: Changes not staged for commit'))
        else:
            msg_status(_('Git: no not-staged files'))

    def get_untracked_files_(self):
        text = self.run_git(["ls-files", ".", "--exclude-standard", "--others"])
        if text:
            self.show_memo(text, _('Git: Untracked files'))
        else:
            msg_status(_('Git: no untracked files'))

    def commit_(self):
        if not self.is_git():
            return msg_status(_('No Git repo'))

        txt_ = dlg_input(_('Git: Commit changes'), '')
        if txt_:
            text = self.run_git(["commit", "-m", txt_])
            if text:
                self.show_memo(text, _('Git: Result of commit'))
            self.request_update(ed, 'commited')

    def commit_amend_(self):
        if not self.is_git():
            return msg_status(_('No Git repo'))

        txt_ = dlg_input(_('Git: Commit/amend changes'), '')
        if txt_:
            text = self.run_git(["commit", "--amend", "-m", txt_])
            if text:
                self.show_memo(text, _('Git: Result of commit (amend)'))
            self.request_update(ed, 'commited_amend')

    def push_(self):
        if not self.is_git():
            return msg_status(_('No Git repo'))

        res = dlg_input(_("Run 'git push' with parameters:"), 'origin ' + gitmanager.branch())
        if res is None:
            return

        push_params = ['push']
        s = res.split(' ')
        if len(s) == 2:
            push_params += s

        text = self.run_git(push_params)
        if text:
            self.show_memo(text, _('Git: Result of push'))
        self.request_update(ed, 'pushed')

    def pull_(self):
        if not self.is_git():
            return msg_status(_('No Git repo'))

        remotes = self.run_git(['remote','show']).splitlines()
        cap = _('Select a remote to pull from:')
        index = dlg_menu(DMENU_LIST, remotes, caption=cap)
        if index is None:
            return

        remote = remotes[index]
        branch = gitmanager.branch()
        res = msg_box(
            _("Do you really want to run 'git pull {} {}'?".format(remote,branch)),
            MB_OKCANCEL+MB_ICONQUESTION
        )
        if res == ID_OK:
            text = self.run_git(["pull",remote,branch])
            if text:
                self.show_memo(text, _('Git: pull {} {}'.format(remote,branch)))
            self.request_update(ed, 'pulled')

    def diff_(self):
        if not self.is_git():
            return msg_status(_('No Git repo'))

        fn = ed.get_filename()
        diffs = self.run_git(["diff", "HEAD", fn])
        DiffDialog().show_diff_dlg(diffs, _('Git: diff HEAD')+' "'+os.path.basename(fn)+'"')

    def diff_all_(self):
        if not self.is_git():
            return msg_status(_('No Git repo'))

        diffs = self.run_git(["diff","HEAD"])
        DiffDialog().show_diff_dlg(diffs, _('Git: diff HEAD'))

    def checkout_(self, info):
        if not self.is_git():
            return msg_status(_('No Git repo'))
        branch_to = info

        branch = gitmanager.branch()
        if branch == branch_to:
            msg_box('Already on a "{}" branch.'.format(branch), MB_OK+MB_ICONINFO)
            return

        self.run_git(["checkout",branch_to])
        self.request_update(ed, 'checked_out')

    def checkout_new_branch_(self):
        if not self.is_git():
            return msg_status(_('No Git repo'))

        txt_ = dlg_input(_('Name of new branch:'), '')
        if txt_:
            text = self.run_git(["checkout", "-b", txt_])
            self.request_update(ed, 'checked_out_new_branch')


class DiffDialog:
    def __init__(self):
        self.h_dlg = None

    def show_diff_dlg(self,diffs,caption):
        if self.h_dlg:
            return

        h=dlg_proc(0, DLG_CREATE)
        self.h_dlg = h

        dlg_proc(h, DLG_PROP_SET, prop={
            'cap': caption,
            'w': 900,
            'h': 500,
            'resize': True,
            'keypreview': True,
#            'on_close': lambda *args, **vargs: timer_proc(TIMER_START_ONE, self.close_diff_dlg, 200)
            })

        n=dlg_proc(h, DLG_CTL_ADD, 'editor')
        dlg_proc(h, DLG_CTL_PROP_SET, index=n, prop={
            'name': 'ed',
            'x': 6,
            'y': 6,
            'a_r': ('', ']'),
            'a_b': ('', ']'),
            'sp_l': 6,
            'sp_t': 6,
            'sp_r': 6,
            'sp_b': 38,
            })

        h_editor = dlg_proc(h, DLG_CTL_HANDLE, index=n)
        ed0 = Editor(h_editor)
        ed0.set_prop(PROP_MICROMAP, False)
        ed0.set_prop(PROP_MINIMAP, False)
        ed0.set_prop(PROP_RULER, False)
        ed0.set_prop(PROP_GUTTER_NUM, False)
        ed0.set_prop(PROP_GUTTER_BM, False)
        ed0.set_text_all(diffs)
        ed0.set_prop(PROP_RO, True)
        ed0.set_prop(PROP_LEXER_FILE, 'Diff')

        n=dlg_proc(h, DLG_CTL_ADD, 'button')
        dlg_proc(h, DLG_CTL_PROP_SET, index=n, prop={
            'name': 'btn_close',
            'cap': _('Close'),
            'w': 120,
            'a_l': None,
            'a_t': None,
            'a_b': ('', ']'),
            'a_r': ('', ']'),
            'sp_a': 6,
            'on_change': self.callback_btn_close,
            })


        #set line states
        for i in range(ed0.get_line_count()):
            state = LINESTATE_NORMAL
            s = ed0.get_text_line(i)
            if s.startswith('+') and not s.startswith('+++'):
                state = LINESTATE_ADDED
            elif s.startswith('-') and not s.startswith('---'):
                state = LINESTATE_CHANGED
            ed0.set_prop(PROP_LINE_STATE, (i, state))

#        dlg_proc(h, DLG_CTL_FOCUS, name='ed')
        dlg_proc(h, DLG_SHOW_MODAL)
        dlg_proc(h, DLG_FREE)
        self.h_dlg = None

    def callback_btn_close(self, id_dlg, id_ctl, data='', info=''):
        dlg_proc(self.h_dlg, DLG_HIDE)
