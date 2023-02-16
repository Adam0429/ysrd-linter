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
import importlib
import inspect


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

    def check(self, if_print=True, if_csv=False):
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

            error_type = re.findall('\(.*?\)', line)[-1].replace('(', '').replace(')', '')

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

    @property
    def project_type(self):
        """
        判断项目属于前端还是api-framework或者yard-base或前端
        :return:
        """
        all_files = []
        all_dirs = []
        for root, dirs, files in os.walk(self.module_path, topdown=False):
            all_files.extend(files)
            all_dirs.extend(dirs)
        if 'package.json' in all_files:
            return 'frontend'
        elif 'runserver.py' in all_files:
            if 'bin' in all_dirs:
                return 'yard-base'
            else:
                return 'api-framework'
        else:
            return 'other'

    def check_f_string(self, text):
        if 'f"' in text or "f'" in text:
            if '{' in text and '}' in text:
                return True
            if '}' in text and '{' in text:
                return True
        return False

    def check_comment(self, text):
        text = text.replace(' ', '')
        if len(text) == 0:
            return False
        if text[0] == '#':
            return True
        return False

    def recover_f_string(self, f_string, lines):
        var_reg = '(?<={).+?(?=\})'
        var_names = re.findall(var_reg, f_string)
        var_dict = {}
        for var_name in var_names:
            for line in lines:
                if f_string == line:
                    break
                line = line.replace(' ', '')
                reg = f'(?<={var_name}\=[\'\"]).+?(?=[\'\"])'
                var_value = re.findall(reg, line)
                if len(var_value) != 0:
                    var_dict[var_name] = var_value[0]
        for var_name in var_dict.keys():
            f_string = f_string.replace('{' + f'{var_name}' + '}', var_dict[var_name])
        return f_string.replace(' ', '')

    def extract_database_url(self):
        datas = []
        for root, dirs, files in os.walk(self.module_path, topdown=False):
            for file in files:
                if os.path.splitext(file)[1] == '.py':
                    filepath = os.path.join(root, file)
                    with open(filepath, 'r') as f:
                        lines = f.readlines()
                        for idx, line in enumerate(lines):
                            database_url = self.extract_database_url_from_line(line, lines)
                            if database_url == None:
                                continue
                            data = {'file': os.path.abspath(filepath).replace(self.module_path, ''),
                                 'database_url': database_url.replace(re.search('(?<=\/\/).+?(?=\@)', database_url).group(), '账号密码已打码'), # 这里加密一下密码字段
                                 'line': idx + 1, 'text': line}
                            datas.append(data)
        df = pd.DataFrame(datas)
        df.index = [i for i in range(len(df))]
        return df

    def extract_database_url_from_line(self, text, lines):
        # 需要解决这种情况：mysql+pymysql://{username}:{password}@{host}:{port}/{database}?charset=utf8
        # reg = '(?<=[\"\'`]).+\+.+:\/\/.+\:.+@.+\/.+(?=[\"\'`])'
        if self.check_comment(text) == True:
            return None

        reg = '(?<=[\"\'])[^\"\']+\+.+:\/\/.+\:.+@.+\/.+(?=[\"\'`])'
        result = re.search(reg, text)

        if result == None:
            return None
        else:
            database_url = result.group()
        if self.check_f_string(text) == True:
            try:
                database_url = self.recover_f_string(text, lines)
                return re.search(reg, database_url).group()
            except:
                pass
        return database_url

    def extract_api(self):
        if self.project_type == 'yard-base':
            df = self.extract_api_from_yard_base()
        elif self.project_type == 'api-framework':
            df = self.extract_api_from_api_framework()
        elif self.project_type == 'frontend':
            df = self.extract_api_from_frontend()
        else:
            df = pd.DataFrame()
        return df

    def extract_api_from_line(self, text):
        reg_with_port = '(?<=[\"\'`])[http|https].+/.+:[0-9]+.+(?=[\"\'`])'
        apis_with_port = re.findall(reg_with_port, text)

        # reg = '(?<=[\"\'])/.+/.+(?=[\"\'])'
        # reg = '/.+/.+(?=[\"\'`])'
        reg = '(?<=[\"\'`])/.*?(?=[\"\'`])'
        apis_without_port = re.findall(reg, text)

        apis = set(apis_with_port + apis_without_port)
        apis = [api for api in apis if ' ' not in api or '<' not in api or '(' not in api]
        apis = [api for api in apis if len(api) < 100 and len(api) > 4]
        return apis

    def extract_api_from_yard_base(self):
        def get_default_url_name(cls_name):
            p = re.compile(r'([a-z]|\d)([A-Z])')
            return re.sub(p, r'\1-\2', cls_name).lower().replace('.py', '')

        def get_class_name(file):
            if file.endswith('.py'):
                with open(file, 'r') as f:
                    try:
                        lines = f.readlines()
                        for line in lines:
                            if 'class' in line and 'AbstractApi' in line:
                                class_name = line.split('class')[1].split('(AbstractApi')[0].replace(' ', '')
                                return class_name
                    except UnicodeDecodeError:
                        return False
            return False

        # def check_AbstractApi(file_name, package_name):
        #     不管用什么方法，都会由于api文件内的导包依旧找不到路径而 报错 ModuleNotFoundError: No module named 'framework'
        #     def find_module(self, fullname, path=None):
        #         import imp
        #         import sys
        #         try:
        #             # 1. Try imp.find_module(), which searches sys.path, but does
        #             # not respect PEP 302 import hooks.
        #             result = imp.find_module(fullname, path)
        #             if result:
        #                 return result
        #         except ImportError:
        #             pass
        #         if path is None:
        #             path = sys.path
        #         for item in path:
        #             # 2. Scan path for import hooks. sys.path_importer_cache maps
        #             # path items to optional "importer" objects, that implement
        #             # find_module() etc.  Note that path must be a subset of
        #             # sys.path for this to work.
        #             importer = sys.path_importer_cache.get(item)
        #             if importer:
        #                 try:
        #                     result = importer.find_module(fullname, [item])
        #                     if result:
        #                         return result
        #                 except ImportError:
        #                     pass
        #         raise ImportError("%s not found" % fullname)
        #     if file_name.endswith('.py') and not file_name.startswith('__init__'):
        #         cmd = f"{package_name.replace('/', '.')}.{file_name[:-3]}"
        #         print(file_name, package_name)
        #         import imp
        #         import sys
        #         # print(file_name[:-3], [package_name.replace('.', '/')])
        #         # fp, path, descrip = find_module(file_name[:-3], ['/'+package_name.replace('.', '/')])

        #         import importlib.machinery
        #         modulename = importlib.machinery.SourceFileLoader('pollutant_emission_monitoring', '/Users/wangfeihong/Desktop/meishan-middle-layer/src/app/bluesky/pollution_emergency_control/middle/pollutant_emission_monitoring.py').load_module()
        #         spec = importlib.util.spec_from_file_location('middle.pollutant_emission_monitoring', '/Users/wangfeihong/Desktop/meishan-middle-layer/src/app/bluesky/pollution_emergency_control/middle/pollutant_emission_monitoring.py')
        #         module = importlib.import_module(f"{'package_name'.replace('/', '.')}.{file_name[:-3]}")
        #         cls_list = inspect.getmembers(module, inspect.isclass)
        #         for cls_name, cls in cls_list:
        #             if cls != AbstractApi and issubclass(cls, AbstractApi):
        #                 return True
        datas = []
        app_path = os.path.join(self.module_path, 'src', 'app')
        for dir_path, dir_names, files in os.walk(app_path):
            for file in files:
                if '__pycache__' in dir_path:
                    continue
                file_full_path = os.path.join(dir_path, file)
                class_name = get_class_name(file_full_path)
                if class_name:
                    file_path = os.path.join(dir_path.replace(app_path, ''), file)
                    path1, path2 = os.path.split(file_path)
                    if path1[0] != '/':
                        path1 = '/' + path1

                    url = os.path.join(path1, get_default_url_name(class_name))
                    # url = '/'.join([get_default_url_name(item) for item in file_path.split('/')])
                    datas.append({
                        'file': file_full_path.replace(self.module_path, ''),
                        'api': url,
                        'line': '-'})
        df = pd.DataFrame(datas)
        df.index = [i for i in range(len(df))]
        return df

    def extract_api_from_api_framework(self):
        datas = []
        for dir_path, dir_names, files in os.walk(self.module_path):
            for file in files:
                single_file_urls = []
                if file == '__init__.py':
                    with open(os.path.join(dir_path, file), 'r') as f:
                        try:
                            lines = f.readlines()
                            for line in lines:
                                if 'Blueprint(' in line:
                                    reg = '(?<=[\"\'`]).+(?=[\"\'`])'
                                    Blueprint_name = re.findall(reg, line)[0]
                                if 'add_resource(' in line:
                                    reg = '(?<=[\"\'`]).+(?=[\"\'`])'
                                    url = re.findall(reg, line)
                                    single_file_urls.extend(url)
                        except UnicodeDecodeError:
                            continue
                if len(single_file_urls) > 0:
                    single_file_urls = ['/' + Blueprint_name + url for url in single_file_urls]
                    data = [{'file': os.path.abspath(os.path.join(dir_path, file)).replace(self.module_path, ''),
                             'api': api,
                             'line': '-'} for api in single_file_urls]
                    datas.extend(data)
        df = pd.DataFrame(datas)
        df.index = [i for i in range(len(df))]
        return df

    def extract_api_from_frontend(self):
        datas = []
        for root, dirs, files in os.walk(self.module_path, topdown=False):
            if os.path.join(self.module_path, 'node_modules') in root:
                continue
            for file in files:
                if os.path.splitext(file)[1] in ['.js', '.ts', '.tsx']:
                    filepath = os.path.join(root, file)
                    with open(filepath, 'r') as f:
                        lines = f.readlines()
                        for idx, line in enumerate(lines):
                            if 'from' in line or 'import' in line:
                                continue
                            apis = self.extract_api_from_line(line)
                            data = [{'file': os.path.abspath(filepath).replace(self.module_path, ''), 'api': api,
                                     'line': idx + 1} for api in apis]
                            datas.extend(data)
        df = pd.DataFrame(datas)
        df.index = [i for i in range(len(df))]
        return df


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
                    self.write(
                        f'{self.filepath}:{item.fromlineno}:NC001:[{item.name}] Function or Class has no comments (no comments)')

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
