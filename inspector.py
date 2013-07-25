import subprocess
import threading
import os
import shlex
import sublime, sublime_plugin

PANEL_NAME = 'hg_log_comber_panel'


class CommandRunner(threading.Thread):
    def __init__(self, command_str, callback=None, name=None):
        threading.Thread.__init__(self)
        self.callback = callback
        self.command = command_str
        self.start()
        if name is None:
            name = command_str
        self.name = name

    def run(self):
        p = subprocess.Popen(
            shlex.split(self.command),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        out, err = p.communicate()
        if err:
            print('HgLogInspect (CommandRunner) Error: {}'.format(
                err.decode('utf-8')))
            self.callback(None)
        else:
            self.callback(out.decode('utf-8'))


class HgChangeset(object):
    def __init__(self, revision, node, branch, author, date, age, description):
        self.revision = revision
        self.node = node
        self.branch = branch
        self.author = author
        self.date = date
        self.age = age
        self.description = description

    def __str__(self):
        desc = self.description
        if len(self.description) < 20:
            desc = desc[:20]
        return '{rev}:{node} [{author} {date}]\n - {desc}'.format(
            rev=self.revision,
            node=self.node,
            author=self.author,
            date=self.date,
            desc=desc)


class HgLogCombGrepFileCommand(sublime_plugin.TextCommand):

    def run(self, edit):

        region = self.view.sel()[0]
        if region.begin() == region.end():
            self.search_str = self.view.substr(self.view.word(region.begin()))
        else:
            self.search_str = self.view.substr(region)
        if not self.search_str:
            print('No search string.')
            return

        self.file_name = self.view.file_name()
        if not self.file_name:
            print('Not in a saved file. Goodbye.')
            return
        self.file_wd = os.path.split(self.file_name)[0]

        self.grep()

    def grep(self):
        cmd = "hg grep -u -d -n {pattern} {file}".format(
            pattern=self.search_str,
            file=self.file_name)
        output = self.run_command(cmd)

        output = '[HgGrep] Grepping for "{}" in {}\n---\n{}'.format(
            self.search_str, self.file_name, output)
        self.update_panel(output)

    def update_panel(self, text, append=False):
        self.view.run_command(
            'hg_log_inspect_panel',
            {
                'text': text,
                'append': append
            }
        )


class HgLogCombLogFileCommand(sublime_plugin.TextCommand):

    MAX_CHANGESETS = 30

    @property
    def current_changeset(self):
        return self.changesets[self.current_changeset_index]

    def run(self, edit):
        self.changesets = []
        self.current_changeset_index = None

        self.file_name = self.view.file_name()
        if not self.file_name:
            print('Not in a saved file. Goodbye.')
            return
        self.window = sublime.active_window()
        self.file_wd = os.path.split(self.file_name)[0]
        self.get_log()
        self.show_menu()

    def get_log(self):
        # cmd = 'hg log --limit {} --style compact {}'.format(
        #     self.MAX_CHANGESETS,
        #     self.file_name)
        log_template = '{rev}|{node|short}|{branch}|{author|person}|{date|isodate}|{date|age}|{desc}||'
        cmd = 'hg log --limit {limit} --template {template} {file}'.format(
            limit=self.MAX_CHANGESETS,
            template=log_template,
            file=self.file_name)
        output = self.run_command(cmd)
        changesets = [c for c in output.split('||') if c]
        self.parse_changesets(changesets)

    def parse_changesets(self, raw_changesets):
        self.changesets = []
        for c in raw_changesets:
            print('c: {v}'.format(v=c))
            tokens = c.split('|')
            self.changesets.append(HgChangeset(
                revision=tokens[0],
                node=tokens[1],
                branch=tokens[2],
                author=tokens[3],
                date=tokens[4],
                age=tokens[5],
                description=tokens[6]
            ))

    def show_menu(self):
        self.menu_items = []
        for c in self.changesets:
            menu_item_str = '{} {}: {}'.format(
                c.author, c.age, c.description)
            self.menu_items.append(menu_item_str)
        self.window.show_quick_panel(self.menu_items, self.menu_on_done)

    def menu_on_done(self, index):
        self.current_changeset_index = index
        self.search_current_changeset()

    def prompt_next_changeset(self):
        self.window.show_input_panel(
            'Search next changeset? ({})'.format(self.current_changeset),
            initial_text='[Enter] to search. [Escape] to cancel.',
            on_done=self.search_current_changeset,
            on_change=self.on_prompt_change,
            on_cancel=self.cancel)

    def search_current_changeset(self):
        changeset = self.current_changeset
        cmd = 'hg log -p -r {rev}:{node}'.format(
            rev=changeset.revision,
            node=changeset.node)

        patch = self.run_command(cmd)
        self.update_panel('{}\n{}'.format(changeset, patch))

        self.current_changeset_index += 1
        # self.prompt_next_changeset()

    def on_prompt_change(self, text):
        pass

    def cancel(self):
        pass

    def run_command(self, command):
        p = subprocess.Popen(
            shlex.split(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.file_wd)
        out, err = p.communicate()
        if err:
            print('HgLogInspect (CommandRunner) Error: {}'.format(
                err.decode('utf-8')))
            return None
        else:
            return out.decode('utf-8')

    def update_panel(self, text, append=False):
        self.view.run_command(
            'hg_log_inspect_panel',
            {
                'text': text,
                'append': append,
                'diff_syntax': True
            }
        )


    # def run_cmd(self, command):

class HgLogCombShowPanelCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        sublime.active_window().run_command(
            'show_panel',
            {'panel': 'output.{}'.format(PANEL_NAME)}
        )


class HgLogInspectPanelCommand(sublime_plugin.TextCommand):
    panel = None

    def run(self, edit, text, append=False, diff_syntax=False):
        window = sublime.active_window()
        panel = window.create_output_panel(PANEL_NAME)
        start_point = 0
        if append:
            start_point = panel.size()
        panel.insert(edit, start_point, text)
        if diff_syntax:
            panel.set_syntax_file("Packages/Diff/Diff.tmLanguage")
        window.run_command(
            'show_panel',
            {'panel': 'output.{}'.format(PANEL_NAME)}
        )

