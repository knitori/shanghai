
import sys
import time
from shanghai.plugin import Plugin


def foo():
    Plugin.load_plugin('example')
    Plugin.unload_plugin('example')

foo()
time.sleep(1)
