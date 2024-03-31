
import socket, time, subprocess, random, string, sys
from types import SimpleNamespace

def random_string(n):
  return ''.join(random.choices(string.ascii_uppercase + string.digits, k=n))

def from_uid_str(uid_response: str):
  return eval(uid_response)

def normalize_bool_response(uid_response):
  if uid_response == 'True':
    return True
  elif uid_response == 'False':
    return False
  else:
    raise ValueError(f'Expected bool response, got {uid_response}')

global_port = 4444

def set_global_port(new_global_port):
  global global_port
  global_port = new_global_port

def connect(*, port=global_port, max_refuse_retries=5):
  sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  sock.settimeout(0.1)
  refuse_retries = 0
  while True:
    try:
      sock.connect(('', port))
      break
    except BlockingIOError:
      continue
    except ConnectionRefusedError as exc:
      if refuse_retries >= max_refuse_retries:
        raise exc
      refuse_retries += 1
      time.sleep(0.1)
      continue
  return sock

def send(msg, *, port=global_port, timeout=None):
  sock = connect(port=port)
  sock.settimeout(timeout)
  sock.send(msg.encode('utf-8') + b'\x04')
  buffer = sock.recv(1024)
  res = buffer.decode('ascii').replace('\x04', '')
  return res


def quit_app(port=global_port, **kwargs):
  send('quit_app()', **kwargs)

def is_ready(port=global_port, **kwargs):
  return normalize_bool_response(send('!_r=is_ready', **kwargs))

def remove_block(uid, *, port=global_port, **kwargs):
  return send(f'!_r=remove_block({repr(uid)})', **kwargs)

def add_text(text, *, to=None, after=None, name=None, replace=False, **kwargs):
  if name is not None  and  replace:
    print('using add_or_replace_with_text_block')
    return from_uid_str(send(f'!_r=add_or_replace_with_text_block({repr(name)}, {repr(str(text))}, name={repr(name)}, to={repr(to)}, after={repr(after)})', **kwargs))
  else:
    return from_uid_str(send(f'!_r=add_text_block({repr(str(text))}, to={repr(to)}, after={repr(after)}, name={repr(name)})', **kwargs))

def update_text(uid, text, **kwargs):
  return send(f'update_text_block({repr(uid)}, {repr(str(text))})', **kwargs)


def add_container(*, to=None, after=None, name=None, replace=False, **kwargs):
  if name is not None  and  replace:
    return from_uid_str(send(f'!_r=add_or_replace_with_container_block({repr(name)}, name={repr(name)}, to={repr(to)}, after={repr(after)})', **kwargs))
  else:
    return from_uid_str(send(f'!_r=add_container_block(to={repr(to)}, after={repr(after)}, name={repr(name)})', **kwargs))

def append_to_container(contref, objref, **kwargs):
  return from_uid_str(send(f'!_r=append_to_container_block({repr(contref)}, {repr(objref)})', **kwargs))

def append_text_to_container(uid, text, **kwargs):
  return from_uid_str(send(
    f'!_r=append_to_container_block({repr(uid)}, make_text_block({repr(text)}))',
    **kwargs
  ))

def get_nth_block(n, **kwargs):
  return from_uid_str(send(f'!_r=get_nth_block({n}).uid', **kwargs))

def get_nth_container_block(uid, n, **kwargs):
  return from_uid_str(send(f'!_r=get_nth_container_block({repr(uid)}, {n}).uid', **kwargs))

def get_block_count(**kwargs):
  return eval(send('!_r=get_block_count()', **kwargs))


def add_container_with(*stuff:str|list|dict, **kwargs) -> SimpleNamespace:
  disp = container_display(**kwargs)
  for item in stuff:
    if isinstance(item, str):
      disp.add_text(item)
    elif isinstance(item, list):
      add_container_with(*item, to=disp.name)
    elif isinstance(item, dict):
      # item can have keys: as, content, kwargs, append_kwargs
      assert('as' in item)
      assert('content' in item)
      itemas = item.get('as')
      if itemas == 'text':
        disp.add_text(item['content'], **item.get('kwargs', {}))
      elif itemas == 'container':
        add_container_with(**item, to=disp.name, **item.get('kwargs', {}))
  return disp
      


def text_display(initial_text:str='', name:str|None=None, **kwargs) -> SimpleNamespace:
  if name is None:
    name = random_string(10)
  add_text(initial_text, name=name, **kwargs)
  return SimpleNamespace(
    update = lambda text, **kwargs: update_text(name, text, **kwargs),
    name = name
  )

def container_display(name:str|None=None, **kwargs) -> SimpleNamespace:
  if name is None:
    name = random_string(10)
  add_container(name=name, **kwargs)
  return SimpleNamespace(
    add_text = lambda text, **kwargs: add_text(text, to=name, **kwargs),
    add_container = lambda **kwargs: add_container(to=name, **kwargs),
    container_display = lambda **kwargs: container_display(to=name, **kwargs),
    text_display = lambda initial_text='', **kwargs: text_display(initial_text, to=name, **kwargs),
    name = name,
    get_nth = lambda n, **kwargs: get_nth_container_block(name, n, **kwargs)
  )


def wait_for_ready(timeout:float|None=None, **kwargs):
  start_Time = time.time()
  while True:
    if timeout is not None  and  time.time() - start_Time > timeout:
      raise Exception('Timed out waiting for noca to open')
    if is_ready(**kwargs):
      break
    time.sleep(0.1)

def open_noca(path:str='./noca.py', log:str|None=None, log_verbose:bool=False):
  args = ['python', path, '--scan', 'true']
  if log is not None:
    if isinstance(log, str):
      args.extend(['--log', log])
    else:
      args.extend(['--log', 'noca_log.txt'])
  if log_verbose:
    args.extend(['--verbose', 'true'])
  proc = subprocess.Popen(
    args, 
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, 
    text=True, bufsize=0, universal_newlines=True
  )
  time.sleep(0.25)
  # get port from noca's stdout
  port_res = proc.stdout.readline()
  set_global_port(int(port_res))
  print('using port', int(port_res))
  return proc


if __name__ == '__main__':
  proc = open_noca()
  wait_for_ready()
  while proc.poll() is None:
    inp = sys.stdin.read()
    res = send(inp)
    print(res)
  