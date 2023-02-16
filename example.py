from ysrd_linter import YsrdLinter, SingleFilechecker

# 跑文件夹
# if __name__ == '__main__':
#     """
#     验证多进程可以解决pylint管理资源异常(不释放内存)问题，
#     创建专门的子进程运行完pylint，子进程被杀死后，不占用内存，主进程内存占用一直不变
#     """
#     import glob
#     import psutil
#     import os
#     from tqdm import tqdm
#     files = glob.glob('../test_files/*')
#     for file in tqdm(files):
#         linter = YsrdLinter(filepath=file,
#                             output=f'document-{file.replace("/","-")}.txt')
#         linter.check(if_print=False)
#         print('主进程:', os.getpid(), '当前进程的内存使用：%.4f M' % (psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024))
#
# # 跑单个文件
# if __name__ == '__main__':
#     linter = YsrdLinter(filepath='test_file.py',
#                         output='document.txt')
#     linter.check(if_print=False)


# singlefilechecker = SingleFilechecker(filepath='/Users/wangfeihong/Desktop/gitlabchecker_frontend/src/pages/project/service.js')
# apis = singlefilechecker.extract_api()
# print(apis)
linter = YsrdLinter(filepath='/Users/wangfeihong/Desktop/gitlab-checker/')
# linter = YsrdLinter(filepath='/Users/wangfeihong/Desktop/visualization-data-sync')
# linter = YsrdLinter(filepath='/Users/wangfeihong/Desktop/gitlabchecker_frontend')

# df = linter.extract_api()
df = linter.extract_database_url()

print(df)
# import pandas as pd
df.to_csv('database_url.csv', encoding='gb18030')