import os
import tokenize
import chardet
from pylint.lint import Run as PylintRun
from pylint.lint.pylinter import PyLinter
from pylint.typing import FileItem
from astroid.nodes.node_classes import ImportFrom
from astroid.nodes.node_classes import Import
from astroid.nodes.scoped_nodes.scoped_nodes import FunctionDef
from astroid.nodes.scoped_nodes.scoped_nodes import ClassDef

class YsrdLinter():
    def __init__(self,filepath,output=None):
        if not os.path.exists(filepath):
            print(filepath,'路径不存在！')
            exit()

        filepath = os.path.abspath(filepath).replace(os.getcwd() + '/', '')

        if output == None:
            self.output = os.path.splitext(filepath)[0].replace('/', '-') + '-YsrdLinter-Document.txt'
        else:
            self.output = output

        if os.path.isdir(filepath):
            """
            module和单个文件的情况分开处理,如果某包含py文件的文件夹下没有__init__.py文件，
            pylint会报错 [Errno 2] No such file or directory: './__init__.py' (parse-error)
            因此给这样的文件夹新建__init__.py文件
            """
            self.module_path = filepath
            self.init_folder(self.module_path)
            self.filepaths = []
            for root, dirs, files in os.walk(self.module_path, topdown=False):
                for file in files:
                    if os.path.splitext(file)[1] == '.py':
                        self.filepaths.append(os.path.join(root, file))

        elif os.path.splitext(filepath)[1] == '.py':
            self.filepath = filepath

        else:
            print('文件不符合要求，要求文件夹或者py格式!')
            exit()

    def init_folder(self,path):
        """第一层 __init__.py必加"""
        init_file = os.path.join(path, '__init__.py')
        if not os.path.exists(init_file):
            with open(os.path.join(path, '__init__.py'), 'a') as f:
                f.write('')
        for root, dirs, files in os.walk(path, topdown=False):
            for file in files:
                if os.path.splitext(file)[1] == '.py':
                    init_file = os.path.join(root, '__init__.py')
                    if not os.path.exists(init_file):
                        with open(os.path.join(root, '__init__.py'), 'a') as f:
                            f.write('')
                        break

    def check(self,if_print=True):
        if hasattr(self, 'filepath'):
            with open(self.output, 'a') as f:
                f.write('************* ysrdlinter' + '\n')
            self.singfilechecker = SingleFilechecker(self.filepath,self.output)
            self.singfilechecker.check(if_print=if_print)

        elif hasattr(self, 'filepaths'):
            argv = ['--rcfile=google_standard.conf', f'--output={self.output}', self.module_path]
            PylintRun(argv, do_exit=False)
            with open(self.output, 'a') as f:
                f.write('************* ysrdlinter' + '\n')
            for file in self.filepaths:
                self.singfilechecker = SingleFilechecker(file,self.output)
                self.singfilechecker.check(if_pylink=False,if_print=if_print)


class SingleFilechecker():

    def __init__(self,filepath,output=None):
        if not os.path.exists(filepath):
            print(filepath,'路径不存在！')
            exit()

        self.filepath = os.path.abspath(filepath).replace(os.getcwd()+'/','')
        if output == None:
            self.output = os.path.splitext(self.filepath)[0].replace('/','-') + '-YsrdLinter-Document.txt'
        else:
            self.output = output

        self.pylinter = PyLinter()
        self.file = FileItem(name=filepath, filepath=filepath, modpath=filepath)
        self.ast_node = self.pylinter.get_ast(self.file.filepath, self.file.name)
        self.body = self.ast_node.body
        self.basic_items_lst = []
        self.basic_items
        self.get_comments()

    def write(self,text):
        with open(self.output,'a') as f:
            f.write(text+'\n')

    def get_encoding(self,file):
        with open(file, 'rb') as f:
            data = f.read()
            return chardet.detect(data)['encoding']

    @property
    def body_items(self):
        return [item for item in self.body]

    @property
    def funcs(self):
        """
        只返回最上一层的方法，不包括类方法和嵌套方法
        :return:
        """
        return [item for item in self.body if isinstance(item,FunctionDef)]

    @property
    def classes(self):
        """
        只返回最上一层的类，不包括嵌套类
        :return:
        """
        return [item for item in self.body if isinstance(item,ClassDef)]

    @property
    def imports(self):
        return [item for item in self.body if isinstance(item,Import)]

    @property
    def import_froms(self):
        return [item for item in self.body if isinstance(item,ImportFrom)]

    @property
    def basic_items(self):
        """
        由于self.body中只包含了第一层的所有节点，类似结构树，每个节点下可能还存在节点
        需要用全扫描的方法扫出来，这个方法目前只返回了有name属性的节点，已满足需求
        后续如需所有节点，可以用该节点的*name*属性拼接成name
        :return: 返回方法、类、和类中的方法
        """
        def walk(item):
            if hasattr(item, 'name'):
                if hasattr(item, 'parent'):
                    if item.parent.name != self.file.name:
                        item.name = item.parent.name + '.' + item.name
                if item != self:
                    self.basic_items_lst.append(item)
            if hasattr(item, 'body'):
                for i in item.body:
                    walk(i)
        # 这里只遍历一次，否则name会重复叠加
        if self.basic_items_lst == []:
            walk(self)
        return self.basic_items_lst

    @property
    def all_funcs(self):
        """
        是结构树中所有的方法，包括类中的方法和嵌套方法
        :return: 返回方法、类、和类中的方法
        """
        return [item for item in self.basic_items if isinstance(item,FunctionDef)]

    @property
    def all_classes(self):
        """
        是结构树中所有的类，包括嵌套类
        :return:
        """
        return [item for item in self.basic_items if isinstance(item,ClassDef)]

    def get_comments(self):
        """
        doc方法只能获取到3引号的注释，获取不到#类型的注释,所以在这个方法将#注释加到doc里
        :return:
        """
        for item in self.basic_items:
            if item.doc != None:
                continue
            fileObj = open(self.filepath, 'r', encoding=self.get_encoding(self.filepath))
            for toktype, tok, start, end, line in tokenize.generate_tokens(fileObj.readline):
                line_num = start[0]
                if item.fromlineno-1 < line_num < item.end_lineno:
                    if toktype == tokenize.COMMENT:
                        item.doc = tok
                        break

    def check_func_length(self, max_length=80):
        """
        通过扫描的方式找出所有的方法，比 check_func_length_old 可靠
        :param max_length:
        :return:
        """
        for func in self.all_funcs:
            length = func.end_lineno-func.fromlineno
            if length > max_length:
                self.write(f'{self.filepath}:{func.fromlineno}:{func.name} 函数长度过长{length}/{max_length}')

    def check_class_def_number(self, max_number=10):
        for _class in self.all_classes:
            class_funcs = [item for item in _class.body if isinstance(item,FunctionDef)]
            number = len(class_funcs)
            if number > max_number:
                self.write(f'{self.filepath}:{_class.fromlineno}:{_class.name} 类的方法数量过大{number}/{max_number}')

    def check_comments(self, min_length=10):
        for item in self.basic_items:
            if isinstance(item, (FunctionDef, ClassDef)):
                length = item.end_lineno - item.fromlineno
                if length > min_length and item.doc == None:
                    self.write(f'{self.filepath}:{item.fromlineno}:{item.name} 没有注释')

    def pylink_check(self):
        argv = ['--rcfile=google_standard.conf', f'--output={self.output}', self.filepath]
        PylintRun(argv, do_exit=False)

    def check(self, if_pylink=True, if_print=True):
        if if_pylink:
            self.pylink_check()
        self.check_func_length()
        self.check_class_def_number()
        self.check_comments()
        if if_print:
            self.print_output()

    def print_output(self):
        fileObj = open(self.output, 'r')
        for line in fileObj.readlines():
            print(line)
