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
BAR_H = app_proc(PROC_GET_MAIN_STATUSBAR, '')
DLG_W = 700
DLG_H = 400
TIMERCALL = 'cuda_git_status.on_timer'

fn_config = os.path.join(app_path(APP_DIR_SETTINGS), 'plugins.ini')
SECTION = 'git_status'

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
        try:
            fn = q_fns.get()    # wait for request
            is_getting_badge.set()
            while not q_fns.empty():    # get last if have multiple requests
                fn = q_fns.get()
    
            _badge = gitmanager.badge(fn)
            q_badges.put((fn, _badge))
            is_getting_badge.clear()
        except Exception as e:
            print('ERROR: Git Status: {}'.format(e))
            q_badges.put((None, None)) # put None (to avoid blocking inside `on_timer`)
            raise # print traceback
#end Threaded

class Command:
    def __init__(self):

        self.is_loading_sesh = False # to ignore 'on_open()' while loading session
        self.badge_requests = Queue()
        self.badge_results = Queue()
        self.t_gitman = None

        self._last_request = None

        self.load_ops()
        self.load_icon()

        self.h_menu = None

    def init_bar_cell(self):

        # insert our cell before "info" cell
        index_info = statusbar_proc(BAR_H, STATUSBAR_FIND_CELL, value=CELL_TAG_INFO)
        if index_info is None:
            return False

        index_new = statusbar_proc(BAR_H, STATUSBAR_FIND_CELL, value=CELL_TAG)
        if index_new is None:
            old_color_back = statusbar_proc(BAR_H, STATUSBAR_GET_CELL_COLOR_BACK, tag=CELL_TAG_INFO)
            old_color_font = statusbar_proc(BAR_H, STATUSBAR_GET_CELL_COLOR_FONT, tag=CELL_TAG_INFO)
            statusbar_proc(BAR_H, STATUSBAR_ADD_CELL, index=index_info, tag=CELL_TAG)
            statusbar_proc(BAR_H, STATUSBAR_SET_CELL_COLOR_BACK, tag=CELL_TAG, value=old_color_back)
            statusbar_proc(BAR_H, STATUSBAR_SET_CELL_COLOR_FONT, tag=CELL_TAG, value=old_color_font)
            statusbar_proc(BAR_H, STATUSBAR_SET_CELL_ALIGN, tag=CELL_TAG, value='C')
            statusbar_proc(BAR_H, STATUSBAR_SET_CELL_AUTOSIZE, tag=CELL_TAG, value=True)
            statusbar_proc(BAR_H, STATUSBAR_SET_CELL_CALLBACK, tag=CELL_TAG, value='module=cuda_git_status;cmd=callback_statusbar_click;')
            index_new = statusbar_proc(BAR_H, STATUSBAR_FIND_CELL, value=CELL_TAG)

        # config was reloaded, and Git cell was moved to 0 or 1 (1 with VimMode plugin); then move it
        if app_api_version()>='1.0.430':
            if index_new<2:
                statusbar_proc(BAR_H, STATUSBAR_MOVE_CELL, index=index_new, value=index_info-1)

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

        self.white_icon = ini_read(fn_config, SECTION, 'white_icon', '0') == '1'
        gitmanager.git = ini_read(fn_config, SECTION, 'git_program', 'git')
        self.git_bash_exe = ini_read(fn_config, SECTION, 'git_bash_exe', 'git-bash.exe')
        self.decor_style = ini_read(fn_config, SECTION, 'decor_style', 'LightBG3')

        global DLG_W
        global DLG_H
        DLG_W = int(ini_read(fn_config, SECTION, 'dialog_w', str(DLG_W)))
        DLG_H = int(ini_read(fn_config, SECTION, 'dialog_h', str(DLG_H)))

        d = app_proc(PROC_THEME_SYNTAX_DICT_GET, '')
        if self.decor_style in d:
            git_manager.MY_DECOR_COLOR = d[self.decor_style]['color_back']

    def save_ops(self):

        ini_write(fn_config, SECTION, 'white_icon', '1' if self.white_icon else '0')
        ini_write(fn_config, SECTION, 'git_program', gitmanager.git)
        ini_write(fn_config, SECTION, 'git_bash_exe', self.git_bash_exe)
        ini_write(fn_config, SECTION, 'decor_style', self.decor_style)

        global DLG_W
        global DLG_H
        ini_write(fn_config, SECTION, 'dialog_w', str(DLG_W))
        ini_write(fn_config, SECTION, 'dialog_h', str(DLG_H))

    def open_config(self):

        self.save_ops()
        if not os.path.isfile(fn_config):
            return
        file_open(fn_config)

        lines = [ed.get_text_line(i) for i in range(ed.get_line_count())]
        try:
            index = lines.index('['+SECTION+']')
            ed.set_caret(0, index)
        except:
            pass

    def request_update(self, ed_self, _reason):
        """ * send request to badge-thread
            * start timer to check for result
        """

        if self.is_loading_sesh:
            return

        # start (or restart) thread if not already started
        if self.t_gitman is None or not self.t_gitman.is_alive():
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
        def stop(): timer_proc(TIMER_STOP, TIMERCALL, 0)
        
        # stop timer if thread is not alive (that means exception occurred)
        if not self.t_gitman.is_alive():
            stop()
            return
        
        ## --> "wait" version (slows down Main Thread, causes stuttering)
            #_fn, _badge = self.badge_results.get()
            #if (_fn, _badge) == (None, None): # means exception occurred
                #stop()
                #return
            #self.update(_fn, _badge)
        ## --<
        
        ## --> "NOwait" version (Main Thread is happy)
        try:
            _fn, _badge = self.badge_results.get_nowait()
            if (_fn, _badge) == (None, None): # means exception occurred
                stop()
                return
            self.update(_fn, _badge)
        except:
            time.sleep(0.01) # give cpu time to other thread, improves git status speed a little
            return
        ## --<

        # stop
        if self.badge_requests.empty() \
                and self.badge_results.empty() \
                and not is_getting_badge.is_set():
            stop()

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
            self.h_menu_notstaged = menu_proc(self.h_menu, MENU_ADD, caption=_('Get non-staged files'), command='cuda_git_status.get_notstaged_files_')
            self.h_menu_untracked = menu_proc(self.h_menu, MENU_ADD, caption=_('Get untracked files'), command='cuda_git_status.get_untracked_files_')
            menu_proc(self.h_menu, MENU_ADD, caption='-')

            self.h_menu_add       = menu_proc(self.h_menu, MENU_ADD, caption=_('Add file...'), command='cuda_git_status.add_file_')
            self.h_menu_restore   = menu_proc(self.h_menu, MENU_ADD, caption=_('Restore file...'), command='cuda_git_status.restore_file_')
            menu_proc(self.h_menu, MENU_ADD, caption='-')

            self.h_menu_commit       = menu_proc(self.h_menu, MENU_ADD, caption=_('Commit...'), command='cuda_git_status.commit_')
            self.h_menu_commit_amend_combine = menu_proc(self.h_menu, MENU_ADD, caption=_('Combine... with previous commit (amend)'), command='cuda_git_status.commit_amend_combine_')
            self.h_menu_commit_amend = menu_proc(self.h_menu, MENU_ADD, caption=_("Edit previous commit's message (amend)"), command='cuda_git_status.commit_amend_')
            self.h_menu_push         = menu_proc(self.h_menu, MENU_ADD, caption=_('Push...'), command='cuda_git_status.push_')
            self.h_menu_diff         = menu_proc(self.h_menu, MENU_ADD, caption=_('View file changes'), command='cuda_git_status.diff_')
            self.h_menu_diff_all     = menu_proc(self.h_menu, MENU_ADD, caption=_('View all changes'), command='cuda_git_status.diff_all_')
            menu_proc(self.h_menu, MENU_ADD, caption='-')

            self.h_menu_checkout     = menu_proc(self.h_menu, MENU_ADD, caption=_('Checkout branch'))


        fn = ed.get_filename()
        fn_rel = git_relative_path(fn).replace(os.path.sep, '/') # convert Windows-style path separators to Unix-style (used in git)
        branch = gitmanager.branch()
        diffs = bool(gitmanager.diff(fn))
        #dirty = gitmanager.is_dirty()
        #a, b = gitmanager.unpushed_info(branch)
        list_staged = bool(self.run_git(["diff", "--name-only", "--staged"]))
        no_commits_yet = 'No commits yet' in self.run_git(["status"])

        list_notstaged = self.run_git(["diff", "--name-only"])
            # list contains full paths (relative)
        list_untracked = self.run_git(["ls-files", ".", "--exclude-standard", "--others", "--full-name"])
            # --full-name is needed to have full paths
            # so we have 2 lists, with full paths, then we do "if fn_rel in xxxx"

        # 'non-staged', 'untracked'
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
        menu_proc(self.h_menu_commit, MENU_SET_ENABLED, command=list_staged)

        # 'commit amend'
        menu_proc(self.h_menu_commit_amend_combine, MENU_SET_VISIBLE, command=not no_commits_yet and list_staged)
        menu_proc(self.h_menu_commit_amend, MENU_SET_VISIBLE, command=not no_commits_yet and not list_staged)

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
        menu_proc(self.h_menu_checkout, MENU_ADD, caption=_('<new branch>'), command='cuda_git_status.checkout_new_branch_')

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

        elif state == APPSTATE_CONFIG_REREAD:
            self.init_bar_cell()

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

        if gitmanager.last_error:
                msg_box(gitmanager.last_error, MB_OK+MB_ICONERROR)

        if exit_code != 0:
            return ''
        return output

    def show_memo(self, text, caption):

        h = dlg_proc(0, DLG_CREATE)
        dlg_proc(h, DLG_PROP_SET, prop={
            'w': DLG_W,
            'h': DLG_H,
            'cap': caption,
            'border': DBORDER_DIALOG,
        })

        n = dlg_proc(h, DLG_CTL_ADD, prop='button')
        dlg_proc(h, DLG_CTL_PROP_SET, index=n, prop={
            'name': 'btn_ok',
            'x': DLG_W-100,
            'y': DLG_H-6-25,
            'w': 100-6,
            'cap': _('&OK'),
            'on_change': 'module=cuda_git_status;cmd=callback_button_ok;',
            'ex0': True,
        })

        n = dlg_proc(h, DLG_CTL_ADD, prop='memo')
        dlg_proc(h, DLG_CTL_PROP_SET, index=n, prop={
            'name': 'memo_log',
            'val': text.replace("\n", "\r"),
            'x': 6,
            'y': 6,
            'w': DLG_W-6*2,
            'h': DLG_H-6*3-25,
            'ex0': True,
            'ex1': True,
        })

        dlg_proc(h, DLG_CTL_FOCUS, name='btn_ok')
        dlg_proc(h, DLG_SCALE)
        dlg_proc(h, DLG_SHOW_MODAL)
        dlg_proc(h, DLG_FREE)

    def callback_button_ok(self, id_dlg, id_ctl, data='', info=''):

        dlg_proc(id_dlg, DLG_HIDE)

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
        res = msg_box(_("Do you REALLY want to restore this file?"), MB_OKCANCEL+MB_ICONWARNING)
        if res == ID_OK:
            text = self.run_git(["restore", filename_])
            if text:
                self.show_memo(text, _('Git: Log of restore file'))
            self.request_update(ed, 'restored')

    def get_log_(self):
        count = 100
        text = self.run_git([
            '--no-pager', 'log', '--pretty=format:%h  %s%d', '--max-count=%d'%count,
        ])

        if text:
            self.show_memo(text, _('Git: Log (last %d)')%count)
        else:
            msg_status(_('Git: no log'))

    def get_log_file_(self):
        count = 100
        filename_ = ed.get_filename()
        text = self.run_git([
            '--no-pager', 'log', '--pretty=format:%h  %s%d', '--max-count=%d'%count,
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
            msg_status(_('Git: no non-staged files'))

    def get_untracked_files_(self):
        text = self.run_git(["ls-files", ".", "--exclude-standard", "--others"])
        if text:
            self.show_memo(text, _('Git: Untracked files'))
        else:
            msg_status(_('Git: no untracked files'))

    def dlg_input_multiline(self, caption, label, text=''):
        id_memo = 1
        id_ok = 2
        
        c1 = chr(1)
        text = '\n'.join([]
            +[c1.join(['type=label', 'pos=6,5,200,0', 'cap='+label])]
            +[c1.join(['type=memo', 'pos=6,25,400,220', 'val='+'\t'.join(text.split('\n'))])]
            +[c1.join(['type=button', 'pos=200,230,300,0', 'cap=&OK', 'ex0=0'])]
            +[c1.join(['type=button', 'pos=306,230,402,0', 'cap=Cancel'])]
        )
        
        res = dlg_custom(caption, 408, 260, text)
        if res is None:
            return
        
        res, text = res
        if res != id_ok:
            return
        text = text.splitlines()
        return '\n'.join(text[id_memo].split('\t'))
    
    def commit_(self):
        if not self.is_git():
            return msg_status(_('No Git repo'))
            
        txt_ = self.dlg_input_multiline(_('Git: Commit changes'), _('&Message:'))
        if txt_:
            text = self.run_git(["commit", "-m", txt_])
            if text:
                self.show_memo(text, _('Git: Result of commit'))
            self.request_update(ed, 'commited')

    def commit_amend_common(self, label):
        if not self.is_git():
            return msg_status(_('No Git repo'))

        text = self.run_git(['log','-1', '--pretty=format:%s'])
        txt_ = self.dlg_input_multiline(label, _('&Message:'), text)
        if txt_:
            text = self.run_git(["commit", "--amend", "-m", txt_])
            if text:
                self.show_memo(text, _('Git: Result of commit/amend'))
            self.request_update(ed, 'commited_amended')
    
    def commit_amend_combine_(self):
        self.commit_amend_common(_('Git: Combine... with previous commit (amend)'))
    
    def commit_amend_(self):
        self.commit_amend_common(_("Git: Edit previous commit's message (amend)"))

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

    def push_set_upstream_(self):
        if not self.is_git():
            return msg_status(_('No Git repo'))

        remotes = self.run_git(['remote','show']).splitlines()
        index = dlg_menu(DMENU_LIST, remotes, caption=_('Select a remote to push to'))
        if index is None:
            return

        remote = remotes[index]
        branch = gitmanager.branch()

        res = msg_box(
            _("Do you really want to run 'git push --set-upstream {} {}'?").format(remote,branch),
            MB_OKCANCEL+MB_ICONQUESTION
        )
        if res == ID_OK:
            text = self.run_git(["push",'--set-upstream',remote,branch])
            if text:
                self.show_memo(text, _('Git: push --set-upstream {} {}').format(remote,branch))
            self.request_update(ed, 'pushed_set_upstream')

    def push_force_(self):
        if not self.is_git():
            return msg_status(_('No Git repo'))

        res = msg_box(
            _("Do you really want to run 'git push --force'?"),
            MB_OKCANCEL+MB_ICONQUESTION
        )
        if res == ID_OK:
            text = self.run_git(['push','--force'])
            if text:
                self.show_memo(text, _('Git: Result of push --force'))
            self.request_update(ed, 'pushed_force')


    def pull_(self):
        if not self.is_git():
            return msg_status(_('No Git repo'))

        remotes = self.run_git(['remote','show']).splitlines()
        index = dlg_menu(DMENU_LIST, remotes, caption=_('Select a remote to pull from'))
        if index is None:
            return

        remote = remotes[index]
        branch = gitmanager.branch()
        if branch.startswith(remote+'/'):
            branch = branch[len(remote+'/'):]
        
        res = dlg_input(_("Run 'git pull' with parameters:"), remote+' '+branch)
        if res is None:
            return

        pull_params = ['pull']
        s = res.split(' ')
        if len(s) == 2:
            pull_params += s

        text = self.run_git(pull_params)
        if text:
            self.show_memo(text, _('Git: {}').format(' '.join(pull_params)))
        self.request_update(ed, 'pulled')

    def diff_(self):
        self.diff_ex(ed.get_filename())

    def diff_all_(self):
        self.diff_ex('')

    def diff_ex(self, fn):
        if not self.is_git():
            return msg_status(_('No Git repo'))

        if gitmanager.commit_count() > 0:
            params = ["diff", "HEAD"]
        else:
            params = ["diff", '--staged']
        if fn:
            params.append(fn)

        diffs = self.run_git(params)
        if not diffs:
            msg_box(_('No Git changes'), MB_OK+MB_ICONINFO)
            return

        if fn:
            cap = _('Git: diff for "{}"').format(os.path.basename(fn))
        else:
            cap = _('Git: diff')

        DiffDialog().show_diff_dlg(diffs, cap)

    def checkout_(self, info):
        if not self.is_git():
            return msg_status(_('No Git repo'))
        branch_to = info

        branch = gitmanager.branch()
        if branch == branch_to:
            msg_box(_('Already on a "{}" branch.').format(branch), MB_OK+MB_ICONINFO)
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

    def checkout_dlg_menu_(self):
        if not self.is_git():
            return msg_status(_('No Git repo'))

        branches = self.run_git(['branch']).splitlines()
        index = dlg_menu(DMENU_LIST, branches, caption=_('Select a branch'))
        if index is None:
            return

        branch_to = branches[index].strip()
        if branch_to.startswith('*'):
            return

        self.run_git(["checkout",branch_to])
        self.request_update(ed, 'checked_out')

    def rebase_(self):
        if not self.is_git():
            return msg_status(_('No Git repo'))

        IS_WIN = os.name=='nt'
        if IS_WIN:
            tool = self.git_bash_exe
            # check for git-bash.exe in PATH
            import shutil
            if not shutil.which(tool): # not in PATH
                file_path = dlg_file(True, 'git-bash.exe', '', 'git-bash.exe|git-bash.exe',
                                    _('Please, provide path to git-bash.exe'))
                if file_path:
                    self.git_bash_exe = tool = file_path
                    self.save_ops()
                else:
                    return

            commit_hash = self.commit_hash()
            if not commit_hash:
                return

            import subprocess
            pause = 'read -p "\n'+_('press Enter to close...')+'"'
            p = subprocess.Popen([tool, '-c', 'git rebase -i '+commit_hash+' ; '+pause],
                                cwd=gitmanager.getcwd())
            p.wait()
        else:
            TOOLS = [
              ['gnome-terminal', '--window', '--'],
              ['xterm', '-hold', '-e']
              ]

            tool = None
            tool_list = []

            import shutil
            for t in TOOLS:
                tool_list.append(t[0])
                if shutil.which(t[0]):
                    tool = t
                    break

            if not tool:
                msg_box(_('Cannot find terminal programs:')+'\n\n'+'\n'.join(tool_list), MB_OK+MB_ICONERROR)
                return

            commit_hash = self.commit_hash()
            if not commit_hash:
                return

            import subprocess
            p = subprocess.Popen(tool + ['git', 'rebase', '-i', commit_hash],
                                cwd=gitmanager.getcwd()
                                )
            p.wait()

    def commit_hash(self):
        commits = self.run_git(['log','--no-merges',
                                '--pretty=format:%h%<(11,trunc) %ar %s']).splitlines()
        if len(commits) == 0:
            return

        index = dlg_menu(DMENU_LIST+DMENU_EDITORFONT, commits,
                        caption=_('Select a starting commit'), w=700, h=500)
        if index is None:
            return
        commit_hash = commits[index].split()[0]
        initial_commit_hash = commits[-1].split()[0]
        is_initial_commit = commit_hash == initial_commit_hash

        if not is_initial_commit:
            commit_hash += '~' # using parent's hash we include selected commit into the rebase list
        else:
            commit_hash = '--root' # using --root because initial commit has no parent
        return commit_hash


class DiffDialog:
    def __init__(self):
        self.h_dlg = None

    def show_diff_dlg(self,diffs,caption):
        if self.h_dlg:
            return

        h=dlg_proc(0, DLG_CREATE)
        self.h_dlg = h

        form_w = int(ini_read(fn_config, SECTION, 'dialog_diff_w', '800'))
        form_h = int(ini_read(fn_config, SECTION, 'dialog_diff_h', '500'))

        dlg_proc(h, DLG_PROP_SET, prop={
            'cap': caption,
            'w': form_w,
            'h': form_h,
            'border': DBORDER_SIZE,
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


        if 'Diff' in lexer_proc(LEXER_GET_LEXERS, False):
            ed0.set_prop(PROP_LEXER_FILE, 'Diff')
        else:
            n=dlg_proc(h, DLG_CTL_ADD, 'label')
            dlg_proc(h, DLG_CTL_PROP_SET, index=n, prop={
                'name': 'label_diff',
                'cap': _('Install Diff lexer if you want to see colors.'),
                'align': ALIGN_BOTTOM,
                'sp_a': 10
            })

        n=dlg_proc(h, DLG_CTL_ADD, 'button')
        dlg_proc(h, DLG_CTL_PROP_SET, index=n, prop={
            'name': 'btn_close',
            'cap': _('Close'),
            'w': 100,
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

        props = dlg_proc(h, DLG_PROP_GET)
        form_w = props['w']
        form_h = props['h']
        ini_write(fn_config, SECTION, 'dialog_diff_w', str(form_w))
        ini_write(fn_config, SECTION, 'dialog_diff_h', str(form_h))

        dlg_proc(h, DLG_FREE)
        self.h_dlg = None

    def callback_btn_close(self, id_dlg, id_ctl, data='', info=''):
        dlg_proc(self.h_dlg, DLG_HIDE)
