
import sys, traceback, os

cwd = os.getcwd()
sys.path.append(cwd)

from clientlib import *

while True:
  res = sys.stdin.read()
  # with blue background
  print('\x1b[34m~~~Results~~~\x1b[0m')
  try:
    response = send(res)
    print(f'Received {repr(response)}')
  except KeyboardInterrupt:
    print('\x1b[31m***INTERRUPTED:***\x1b[0m')
    print('ctrl-c again to exit')
    print(traceback.format_exc())
  except Exception:
    # print with red background:
    print('\x1b[41m***ERROR:***\x1b[0m')
    print(traceback.format_exc())
  print('\x1b[32m~~~~~~~~~~~~~~\x1b[0m')
  print()
