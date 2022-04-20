from setuptools import setup, find_packages 
  
setup( 
 name = "ysrd-linter", 
 version = "1.0", 
 keywords = ("ysrd", "linter"), 
 description = "linter by ysrd", 
 long_description = "linter include google std and ysrd std", 
 license = "YSRD Licence", 
  
 url = "http://10.10.8.64:9980/Keylistener0429/ysrd-linter", 
 author = "Wang Feihong", 
 author_email = "", 
  
 packages = find_packages(), 
 include_package_data = True, 
 install_package_data = True,
 package_data = {
        '': ['*.conf'],
 },
 platforms = "any", 
 install_requires = ['pylint==2.13.2','chardet==4.0.0'], 
  
 scripts = [], 
 entry_points = { 
  'console_scripts': [ 

  ] 
 } 
)