import os
import re
import subprocess


class GitManager:
    def __init__(self):
        self.git = 'git'
        self.prefix = ''

    def run_git(self, args):
        cmd = [self.git] + args
        cwd = self.getcwd()
        if os.name=='nt':
            # make sure console does not come up
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 cwd=cwd,startupinfo=startupinfo)
        else:
            my_env = os.environ.copy()
            my_env["PATH"] = "/usr/local/bin:/usr/bin:" + my_env["PATH"]
            my_env["LANG"] = "en_US"
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 cwd=cwd,env=my_env)
        p.wait()
        stdoutdata, _ = p.communicate()
        ''' #debug
        if stdoutdata:
            print('Git for:', repr(args), ', gets:', stdoutdata)
        else:
            print('Git fails:', repr(args))
        '''
        return (p.returncode, stdoutdata.decode('utf-8'))

    def getcwd(self):
        f = self.filename
        cwd = None
        if f:
            cwd = os.path.dirname(f)
        return cwd

    def branch(self):
        (exit_code, output) = self.run_git(["branch"])
        if exit_code != 0:
            return ''
        output = output.replace('*', '').strip()
        return output

    def is_dirty(self):
        (exit_code, output) = self.run_git(["diff-index", "--quiet", "HEAD"])

        return exit_code == 1

    def unpushed_info__old(self, branch):
        a, b = 0, 0
        if branch:
            exit_code, output = self.run_git(["branch", "-v"])
            if output:
                m = re.search(r"\* .*?\[behind ([0-9])+\]", output, flags=re.MULTILINE)
                if m:
                    a = int(m.group(1))
                m = re.search(r"\* .*?\[ahead ([0-9])+\]", output, flags=re.MULTILINE)
                if m:
                    b = int(m.group(1))
        return (a, b)

    def unpushed_info(self, branch):
        if branch:
            (exit_code, output) = self.run_git(['rev-list', '--left-right', '--count', 'origin/'+branch+'...'+branch])
            m = re.search(r"(\d+)\s+(\d+)", output)
            if m:
                return (int(m.group(1)), int(m.group(2)))
            else:
                return (0,0)
        return (0,0)

    def badge(self, filename):
        self.filename = filename
        if not self.filename:
            return ""

        branch = self.branch()
        if not branch:
            return ""
        ret = branch
        if self.is_dirty():
            ret = ret + "*"
        a, b = self.unpushed_info(branch)
        if a:
            ret = ret + "-%d" % a
        if b:
            ret = ret + "+%d" % b
        return self.prefix + ret
