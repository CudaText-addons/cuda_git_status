import sys
import os
import re
import subprocess


class GitManager:
    def __init__(self):
        self.git = 'git'
        self.prefix = ''

    def run_git(self, cmd, cwd=None):
        plat = sys.platform
        if not cwd:
            cwd = self.getcwd()
        if cwd:
            if type(cmd) == str:
                cmd = [cmd]
            cmd = [self.git] + cmd
            if plat == "win32":
                # make sure console does not come up
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     cwd=cwd, startupinfo=startupinfo)
            else:
                my_env = os.environ.copy()
                my_env["PATH"] = "/usr/local/bin:/usr/bin:" + my_env["PATH"]
                p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     cwd=cwd, env=my_env)
            p.wait()
            stdoutdata, _ = p.communicate()
            return stdoutdata.decode('utf-8')

    def getcwd(self):
        f = self.filename
        cwd = None
        if f:
            cwd = os.path.dirname(f)
        return cwd

    def branch(self):
        ret = self.run_git(["symbolic-ref", "HEAD", "--short"])
        if ret:
            ret = ret.strip()
        else:
            output = self.run_git("branch")
            if output:
                m = re.search(r"\* *\(detached from (.*?)\)", output, flags=re.MULTILINE)
                if m:
                    ret = m.group(1)
        return ret

    def is_dirty(self):
        output = self.run_git("status")
        if not output:
            return False
        ret = re.search(r"working (tree|directory) clean", output)
        if ret:
            return False
        else:
            return True

    def unpushed_info(self, branch):
        a, b = 0, 0
        if branch:
            output = self.run_git(["branch", "-v"])
            if output:
                m = re.search(r"\* .*?\[behind ([0-9])+\]", output, flags=re.MULTILINE)
                if m:
                    a = int(m.group(1))
                m = re.search(r"\* .*?\[ahead ([0-9])+\]", output, flags=re.MULTILINE)
                if m:
                    b = int(m.group(1))
        return (a, b)

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

