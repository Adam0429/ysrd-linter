from ysrd_linter import YsrdLinter

linter = YsrdLinter(filepath='./test_file.py', output='document.txt')
linter.check(if_print=True)
