import os
import re
import tokenize
import traceback
import chardet
import pandas as pd
from pylint.lint import Run as PylintRun
from pylint.lint.pylinter import PyLinter
from pylint.typing import FileItem
from astroid.nodes.node_classes import ImportFrom
from astroid.nodes.node_classes import Import
from astroid.nodes.scoped_nodes.scoped_nodes import FunctionDef
from astroid.nodes.scoped_nodes.scoped_nodes import ClassDef
import psutil
import multiprocessing


class Process(multiprocessing.Process):
    # 包装多进程，使主进程可以捕获exception

    def __init__(self, *args, **kwargs):
        multiprocessing.Process.__init__(self, *args, **kwargs)
        self._pconn, self._cconn = multiprocessing.Pipe()
        self._exception = None

    def run(self):
        try:
            multiprocessing.Process.run(self)
            self._cconn.send(None)
        except Exception as e:
            tb = traceback.format_exc()
            self._cconn.send((e, tb))

    @property
    def exception(self):
        if self._pconn.poll():
            self._exception = self._pconn.recv()
        return self._exception


def pylint_check(input, output):
    """
    pylint管理资源异常(不释放内存)问题，占用内存会随着程序运行时间一直增大，网上没有解决方案。
    因此用多进程运行pylint程序，结束即杀死，可以解决这个问题。用多线程测试时无法解决，子线程结束后，主进程依然占用线程的内存资源
    https://github.com/PyCQA/astroid/issues/792
    https://rtpg.co/2020/10/12/pylint-usage.html
    """
    argv = [f'--rcfile={os.path.dirname(__file__)}/google_standard.conf', f'--output={output}', input]
    PylintRun(argv, do_exit=False)
    # print('pylint_check进程：', os.getpid(), '当前进程的内存使用：%.4f M' % (psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024))


class AstNodeException(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return (self.msg)

class FilePathException(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return (self.msg)

class YsrdLinter():
    def __init__(self, filepath, output=None):
        if not os.path.exists(filepath):
            raise FilePathException(f'{filepath} 路径不存在')

        filepath = os.path.abspath(filepath).replace(os.getcwd() + '/', '')

        if output == None:
            self.output = os.path.splitext(filepath)[0].replace('/', '-') + '-YsrdLinter-Document.txt'
        else:
            self.output = output

        self.csv_path = self.output.replace(os.path.splitext(self.output)[1], '.csv')

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
            raise FilePathException(f'f{filepath}不符合要求，要求文件夹或者py格式!')

    def init_folder(self, path):
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

    def check(self, if_print=True,if_csv=False):
        if hasattr(self, 'filepath'):
            with open(self.output, 'a') as f:
                f.write('************* ysrdlinter' + '\n')
            self.singfilechecker = SingleFilechecker(self.filepath, self.output)
            self.singfilechecker.check(if_print=if_print)

        elif hasattr(self, 'filepaths'):

            # os.path.dirname(__file__) 获取google_standard.conf在python库中的位置
            p1 = Process(target=pylint_check, kwargs={'input': self.module_path, 'output': self.output})
            p1.start()
            p1.join()
            if p1.exception:
                exception, traceback = p1.exception
                p1.terminate()
                raise exception


            with open(self.output, 'a') as f:
                f.write('************* ysrdlinter' + '\n')
            for file in self.filepaths:
                self.singfilechecker = SingleFilechecker(file, self.output)
                self.singfilechecker.check(if_pylint=False, if_print=if_print)

        if if_csv:
            self.output_csv()

    def output_csv(self):
        datas = []
        fileObj = open(self.output, 'r')
        for line in fileObj.readlines():
            if line.count(':') == 2:
                file, lineno, info = line.split(':')
            elif line.count(':') == 3:
                file, lineno, code, info = line.split(':')
            elif line.count(':') == 4:
                file, lineno, indent, code, info = line.split(':')
            else:
                continue
            if 'indent' in locals().keys():
                lineno += ':' + indent

            error_type = re.findall('\(.*?\)', line)[-1].replace('(','').replace(')','')

            datas.append({
                '文件名': file,
                '位置': " " + lineno,
                '报错信息': info,
                '错误代码': code,
                '错误类型': error_type
            })
            """
            防止csv自动将日期转换
            "=\"" + lineno + "\"",
            https://www.itranslater.com/qa/details/2102459010002715648
            """
        df = pd.DataFrame(datas)
        df_stat = pd.DataFrame()

        df_stat['错误类型'] = list(df['错误类型'].value_counts().index)
        df_stat['次数'] = list(df['错误类型'].value_counts().values)
        df_stat['代码'] = list(df['错误代码'].value_counts().index)

        df_stat.to_csv(self.csv_path, encoding='gb18030', index=None)


class SingleFilechecker():

    def __init__(self, filepath, output=None):
        if not os.path.exists(filepath):
            raise FilePathException(f'{filepath} 路径不存在')

        self.filepath = os.path.abspath(filepath).replace(os.getcwd() + '/', '')
        if output == None:
            self.output = os.path.splitext(self.filepath)[0].replace('/', '-') + '-YsrdLinter-Document.txt'
        else:
            self.output = output

        self.pylinter = PyLinter()
        self.file = FileItem(name=filepath, filepath=filepath, modpath=filepath)
        try:
            self.ast_node = self.pylinter.get_ast(self.file.filepath, self.file.name)
            self.body = self.ast_node.body
            self.basic_items_lst = []
            self.basic_items
        except:
            raise AstNodeException(f'{self.filepath} raise AstNodeException!')
        self.get_comments()

    def write(self, text):
        with open(self.output, 'a') as f:
            f.write(text + '\n')

    def get_encoding(self, file):
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
        return [item for item in self.body if isinstance(item, FunctionDef)]

    @property
    def classes(self):
        """
        只返回最上一层的类，不包括嵌套类
        :return:
        """
        return [item for item in self.body if isinstance(item, ClassDef)]

    @property
    def imports(self):
        return [item for item in self.body if isinstance(item, Import)]

    @property
    def import_froms(self):
        return [item for item in self.body if isinstance(item, ImportFrom)]

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
        return [item for item in self.basic_items if isinstance(item, FunctionDef)]

    @property
    def all_classes(self):
        """
        是结构树中所有的类，包括嵌套类
        :return:
        """
        return [item for item in self.basic_items if isinstance(item, ClassDef)]

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
                if item.fromlineno - 1 < line_num < item.end_lineno:
                    if toktype == tokenize.COMMENT:
                        item.doc = tok
                        break

    def check_func_line(self, max_length=80):
        """
        通过扫描的方式找出所有的方法，比 check_func_length_old 可靠
        :param max_length:
        :return:
        """
        for func in self.all_funcs:
            length = func.end_lineno - func.fromlineno
            if length > max_length:
                self.write(
                    f'{self.filepath}:{func.fromlineno}:FR001:[{func.name}] Function has too many rows ({length}/{max_length}) (function has too many rows)')

    def check_class_def_number(self, max_number=10):
        for _class in self.all_classes:
            class_funcs = [item for item in _class.body if isinstance(item, FunctionDef)]
            number = len(class_funcs)
            if number > max_number:
                self.write(
                    f'{self.filepath}:{_class.fromlineno}:CF001:[{_class.name}] Class has too many functions ({number}/{max_number}) (class has too many functions)')

    def check_comments(self, min_length=10):
        for item in self.basic_items:
            if isinstance(item, (FunctionDef, ClassDef)):
                length = item.end_lineno - item.fromlineno
                if length > min_length and item.doc == None:
                    self.write(f'{self.filepath}:{item.fromlineno}:NC001:[{item.name}] Function or Class has no comments (no comments)')

    def check(self, if_pylint=True, if_print=True):
        if if_pylint:
            p1 = Process(target=pylint_check, kwargs={'input': self.filepath, 'output': self.output})
            p1.start()
            p1.join()
            if p1.exception:
                exception, traceback = p1.exception
                p1.terminate()
                raise exception
        self.check_func_line()
        self.check_class_def_number()
        self.check_comments()
        if if_print:
            self.print_output()

    def print_output(self):
        fileObj = open(self.output, 'r')
        for line in fileObj.readlines():
            print(line)

"""
由于使用多进程的原因
程序需要在
if __name__ == '__main__':
下执行
"""