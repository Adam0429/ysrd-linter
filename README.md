# Ysrd Linter

Ysrd Linter是融合了google代码规范及公司内部一些开发规范形成的代码检查工具

强制要求python版本在3.8及以上

引入YsrdLinter

	from ysrd_linter import YsrdLinter

该工具支持检查module和单个文件

    ysrd_linter = YsrdLinter(filepath='/Users/wangfeihong/Desktop/std-api-v2')
    ysrd_linter.check()

运行以上代码会在本地目录得到日志:-Users-wangfeihong-Desktop-std-api-v2-YardBaseChecker-Document.txt

如需自定义输出日志的路径，可修改output参数

    ysrd_linter = YsrdLinter(filepath='/Users/wangfeihong/Desktop/std-api-v2',output='document.txt')
    ysrd_linter.check()


检查单个py文件

    ysrd_linter = YsrdLinter(filepath='./test.py',output='document.txt')
    ysrd_linter.check()


不在控制台打印信息

    ysrd_linter.check(if_print=False)
