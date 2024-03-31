#!/usr/bin/python

# to add:
#   bug: collapsed blocks still show some of their content
#   image blocks
#   tabs?


import gi
gi.require_version('Gtk', '4.0')
import threading, socket, traceback, string, random, subprocess, time, argparse, sys, os
from gi.repository import GLib as glib, Gtk as gtk, GObject as gobj, Pango as pango


# Prelim definitions

def random_string(n):
  return ''.join(random.choices(string.ascii_uppercase + string.digits, k=n))

log_file = None
def log_write(s):
  global log_file
  assert(log_file is not None)
  with open(log_file, 'a') as f:
    f.write(s)
    f.write('\n')

def write_error(msg=None, print_stack=True):
  global log_file
  sys.stderr.write('\x1b[41m***ERROR:***\x1b[0m')
  if msg is not None:
    sys.stderr.write(f'{msg}\n')
  if print_stack:
    sys.stderr.write(traceback.format_exc())
  if log_file is not None:
    with open(log_file, 'a') as f:
      f.write(f'***ERROR***:\n{msg}\n')

def get_nth_of(n, iter):
  for i, obj in enumerate(iter):
    if i == n:
      return obj

def copy_to_clipboard(obj):
  s = repr(obj)
  # use xclip
  subprocess.run(['xclip', '-selection', 'clipboard', '-i'], input=s, encoding='utf-8')


def remove_list_item(item):
  parent = item.get_parent()
  gparent = parent.get_parent()
  gparent.remove(parent)

def remove_box_item(item):
  parent = item.get_parent()
  parent.remove(item)

def remove_from_parent(child):
  parent = child.get_parent()
  parent.remove(child)

def each_child_of(widget):
  if widget is None:
    return
  elif hasattr(widget, 'get_first_child'):
    cur_child = widget.get_first_child()
    while cur_child is not None:
      yield cur_child
      cur_child = cur_child.get_next_sibling()
  elif hasattr(widget, 'get_children'):
    for child in widget.get_children():
      yield child

def each_descendant_of(widget):
  if widget is None:
    return
  for child in each_child_of(widget):
    yield from each_descendant_of(child)
    yield child

fonts = {}

block_last_uid = 0
uid_to_block = {}
name_to_block = {}

def new_block_uid():
  global block_last_uid
  block_last_uid += 1
  return block_last_uid

def register_block(block):
  global uid_to_block
  uid = new_block_uid()
  block.uid = uid
  uid_to_block[uid] = block

def to_block(obj):
  global uid_to_block, name_to_block
  if isinstance(obj, gtk.Widget):
    return obj
  if obj in uid_to_block:
    return uid_to_block[obj]
  if obj in name_to_block:
    return name_to_block[obj]
  
def to_uid(obj):
  global uid_to_block, name_to_block
  if isinstance(obj, gtk.Widget):
    if hasattr(obj, 'uid'):
      return obj.uid
  if obj in uid_to_block:
    return obj
  if obj in name_to_block:
    return name_to_block[obj].uid

def to_name(obj):
  global uid_to_block, name_to_block
  if isinstance(obj, gtk.Widget):
    if hasattr(obj, 'block_name'):
      return obj.block_name
  if obj in uid_to_block:
    return uid_to_block[obj].block_name
  if obj in name_to_block:
    return obj

def to_block_and_uid(ref):
  block = to_block(ref)
  if block is None:
    return None, None
  uid = block.uid
  return block, uid

def type_of_ref(ref):
  if isinstance(ref, gtk.Widget):
    return 'widget'
  if ref in uid_to_block:
    return 'uid'
  if ref in name_to_block:
    return 'name'
  return None

def clear_block_name(name):
  global name_to_block
  block = name_to_block.get(name, None)
  if block is not None:
    block.block_name = None
    if name in name_to_block:
      del name_to_block[name]

def set_block_name(block_or_uid, new_name):
  block, uid = to_block_and_uid(block_or_uid)
  if block is None:
    return None
  block.block_name = new_name
  clear_block_name(new_name)
  name_to_block[new_name] = block

def get_block_by_name(name):
  return name_to_block[name]

# def each_child_of(widget):
#   for child in widget.get_children():
    

block_container = None # will be a gtk.Box


def toggle_block_expansion(button, block, content):
  if block.has_css_class('contracted'):
    # make it expanded
    content.set_policy(gtk.PolicyType.AUTOMATIC, gtk.PolicyType.NEVER)
    content.set_propagate_natural_height(True)
    content.set_size_request(-1, -1)
    block.remove_css_class('contracted')
    button.remove_css_class('contracted')
    button.set_label('V')
  else:
    # make it contracted
    content.set_policy(gtk.PolicyType.AUTOMATIC, gtk.PolicyType.AUTOMATIC)
    content.set_propagate_natural_height(False)
    content.set_size_request(-1, 70)
    block.add_css_class('contracted')
    button.add_css_class('contracted')
    button.set_label('>')
  content.queue_resize()

def remove_block(block_or_uid, *, and_descendants=True):
  block, uid = to_block_and_uid(block_or_uid)
  if block is None:
    return False
  if and_descendants:
    descendant_blocks = [d for d in each_descendant_of(block) if getattr(d, 'is_block', False)]
    for desc in descendant_blocks:
      remove_block(desc, and_descendants=False)
  del uid_to_block[uid]
  if getattr(block, 'block_name', None) is not None:
    clear_block_name(block.block_name)
  remove_from_parent(block)
  return True

def replace_block_content(block, new_content=None):
  if block is None  or  getattr(block, 'content_widget', None) is None:
    return False
  content_widget = block.content_widget
  content_widget.remove(content_widget.get_first_child())
  if new_content is None:
    return True
  content_widget.append(new_content)
  return True

def remove_block_content(block):
  return replace_block_content(block, None)
  

def get_block(block_or_uid):
  block, uid = to_block_and_uid(block_or_uid)
  if block is None:
    return None
  return block

def get_nth_block(n):
  global block_container
  return get_nth_of(n, each_child_of(block_container))

def get_block_count():
  global block_container
  return len(list(each_child_of(block_container)))

def make_block(*, add_expander_button=False, label=None, name=None, expanded=True):
  block = gtk.Box(orientation=gtk.Orientation.HORIZONTAL)
  block.set_halign(gtk.Align.FILL)
  block.set_hexpand(True)
  block.add_css_class('block')
  
  sidebar = gtk.ListBox()
  sidebar.add_css_class('block-sidebar')
  block.append(sidebar)
  
  if label is not None:
    label_widget = gtk.Label(label=label)
    label_widget.add_css_class('block-label')
    label_widget.set_halign(gtk.Align.START)
    label_widget.set_valign(gtk.Align.START)
    block.append(label_widget)
  
  # content = gtk.Box(orientation=gtk.Orientation.HORIZONTAL)
  content = gtk.ScrolledWindow()
  content.set_policy(gtk.PolicyType.NEVER, gtk.PolicyType.NEVER)
  content.add_css_class('block-content')
  content.set_halign(gtk.Align.FILL)
  content.set_valign(gtk.Align.START)
  content.set_hexpand(True)
  block.append(content)
  
  # sidebar stuff
  remove_button = gtk.Button(label="X")
  remove_button.set_tooltip_text('Remove')
  remove_button.add_css_class('block-sidebar-remove-button')
  remove_button.connect('clicked', lambda button, block: remove_block(block), block)
  sidebar.append(remove_button)
  
  if add_expander_button:
    expander_button = gtk.Button(label="V")
    expander_button.set_tooltip_text('Expand/contract')
    expander_button.add_css_class('block-sidebar-expander-button')
    expander_button.connect('clicked', toggle_block_expansion, block, content)
    if not expanded:
      toggle_block_expansion(expander_button, block, content)
    sidebar.append(expander_button)
  
  # attributes
  block.is_block = True
  block.content_widget = content
  block.block_type = 'none'
  register_block(block)
  
  if name is not None:
    set_block_name(block, name)
  
  return block

def add_block(ref, after=None):
  global block_container
  block, uid = to_block_and_uid(ref)
  if block is None:
    return None
  if after is not None: # insert block widget after this after_block's widget
    after_block = to_block(after)
    if after_block is None:
      return None
    parent = after_block.get_parent()
    block.insert_after(parent, after_block) # instead block after after_block in parent
  else:
    block_container.append(block)
  return block.uid


def make_text_content(text_content, text_attributes=None):
  text = gtk.Label(label=text_content)
  text.add_css_class('block-text')
  text.add_css_class('monospace')
  text.set_halign(gtk.Align.START) # stay left and up
  text.set_valign(gtk.Align.START)
  text.set_hexpand(True) # take up as much horizontal space as possible
  text.set_xalign(0.0) # keep on the left
  text.set_yalign(0.0)
  text.set_selectable(True) # text is copiable
  text.set_wrap(True)
  return text

def make_text_block(text_content, text_attributes=None, **block_kwargs):
  block = make_block(**block_kwargs)
  text = make_text_content(text_content, text_attributes=text_attributes)
  block.content_widget.set_child(text)
  block.block_type = 'text'
  return block

def add_text_block(text_content, to=None, after=None, text_attributes=None, **block_kwargs):
  text_block = make_text_block(text_content, **block_kwargs)
  if to is not None:
    append_to_container_block(to, text_block)
    return text_block.uid
  else:
    return add_block(text_block, after=after)

def update_text_block(ref, new_text_content):
  block, uid = to_block_and_uid(ref)
  if block is None:
    return False
  assert(block.is_block)
  assert(block.block_type == 'text')
  block.content_widget.get_first_child().set_text(new_text_content)
  return True

def get_block_text(ref):
  block, uid = to_block_and_uid(ref)
  if block is None:
    return None
  assert(block.is_block)
  assert(block.block_type == 'text')
  return block.content_widget.get_first_child().get_text()

def replace_with_text_block(ref, new_text_content):
  block = to_block(ref)
  if block is None:
    return False
  block.block_type = 'text'
  return replace_block_content(block, make_text_content(new_text_content))

def add_or_replace_with_text_block(ref, new_text_content, to=None, after=None, **block_kwargs):
  block = to_block(ref)
  if block is not None:
    res = replace_with_text_block(block, new_text_content)
    if res:
      return block.uid
  else:
    log_write(f'block_kwargs {repr(block_kwargs)}')
    return add_text_block(new_text_content, to=to, after=after, **block_kwargs)


def make_container_content(*items):
  container = gtk.Box(orientation=gtk.Orientation.VERTICAL, spacing=2)
  container.add_css_class('block-container')
  for item in items:
    container.append(item)
  return container

def make_container_block(*items, **block_kwargs):
  block = make_block(add_expander_button=True, **block_kwargs)
  block.content_widget.set_child(make_container_content(*items))
  block.block_type = 'container'
  return block

def add_container_block(*items, to=None, after=None, **block_kwargs):
  container_block = make_container_block(*items, **block_kwargs)
  if to is not None:
    append_to_container_block(to, container_block)
    return container_block.uid
  else:
    return add_block(container_block, after=after)

def replace_with_container_block(ref, *items):
  block = to_block(ref)
  if block is None:
    return False
  block.block_type = 'container'
  return replace_block_content(block, make_container_content(*items))

def add_or_replace_with_container_block(ref, *items, to=None, after=None, **block_kwargs):
  block = to_block(ref)
  if block is not None:
    res = replace_with_container_block(block, *items)
    if res:
      return block.uid
  else:
    return add_container_block(*items, to=to, after=after, **block_kwargs)

def append_to_container_block(ref, *items):
  block = to_block(ref)
  if block is None:
    return None
  assert(block.is_block)
  assert(block.block_type == 'container')
  container = block.content_widget.get_child().get_first_child()
  last_uid = None
  for ref in items:
    block = to_block(ref)
    if block is None:
      continue
    container.append(block)
    last_uid = block.uid
  return last_uid

def each_container_child(ref):
  block, uid = to_block_and_uid(ref)
  if block is None:
    return []
  assert(block.is_block)
  assert(block.block_type == 'container')
  for i, child in enumerate(each_child_of(block.content_widget.get_first_child())):
    yield child

def get_nth_container_block(ref, n):
  block, uid = to_block_and_uid(ref)
  if block is None:
    return None
  assert(block.is_block)
  assert(block.block_type == 'container')
  return get_nth_of(n, each_child_of(block.content_widget))


def toggle_widget_css_class(widget, css_class):
  if css_class in widget.get_css_classes():
    widget.remove_css_class(css_class)
  else:
    widget.add_css_class(css_class)


def style_block_content(ref, **style_kwargs):
  block, uid = to_block_and_uid(ref)
  if block is None:
    return None
  content = block.content_widget.get_first_child()
  for k, v in style_kwargs.items():
    if k == 'monospace'  or  k == 'mono':
      if v: # true
        content.add_css_class('monospace')
      else: # false
        content.remove_css_class('monospace')
    elif k == 'css_class':
      if isinstance(v, str):
        toggle_widget_css_class(content, v)
      elif isinstance(v, list):
        for css_class in v:
          toggle_widget_css_class(content, css_class)
  return True


# The program:

is_ready = False # is the gui up and running (for thread sync)

# argument parsing

parser = argparse.ArgumentParser()

parser.description = '''
Notebook Canvas.

Use --port PORT or -p PORT to open a socket with that port and listen on it for messages
'''

# arguments are: port
parser.add_argument('--port', '-p', type=int, default=4444, help='port to listen on')
parser.add_argument('--scan', '-s', type=bool, default=True, help='whether to scan for an open port')
parser.add_argument('--log', '-l', type=str, default='', help='log incoming and outgoing messages to the given file')
parser.add_argument('--verbose', '-v', type=bool, default=False, help='whether to print or log more messages')
parser.add_argument('--immediate', '-m', type=bool, default=False, help='Allow execution in the interface thread; allows getting return messages but is unstable')

args = parser.parse_args()
log_file = args.log if args.log != '' else None
do_log = log_file is not None
do_log_verbose = do_log and args.verbose

immediate_mode = args.immediate

# Sockets and pipe interfaces

_r = None # the response object; set to None each msg and then sent to the client after execing msg

def in_main_thread(fn_or_str):
  if isinstance(fn_or_str, str):
    fn = lambda: exec(fn_or_str)
  else:
    fn = fn_or_str
  glib.idle_add(fn)

def exec_msg_and_respond(msg, client_socket):
  global do_log, immediate_mode
  if len(msg) > 0  and  msg[0] == '!':
    exec_here = True
    msg = msg[1:]
  else:
    exec_here = False
  msg = 'global _r\n' + msg
  
  global _r
  _r = None
  try:
    # escaped_msg = msg.replace('\n', '\\n')
    if immediate_mode  and  exec_here:
      exec(msg)
    else:
      in_main_thread(msg)
  except Exception:
    write_error(f'Exception when executing message {repr(msg)}')
  except AssertionError:
    write_error(f'Assertion error when executing message {repr(msg)}')
  response_rep = repr(_r)
  response_string = response_rep.encode('utf-8') + b'\x04'
  if do_log:
    log_write(f'Sending {repr(response_rep)}')
  client_socket.send(response_string)


interface_running = True

stdin_buffer = sys.stdin.detach()
os.set_blocking(stdin_buffer.fileno(), False)


global_port = args.port
scan_for_port = args.scan



# sockets thread function
# listen and report socket data in a new thread
def listener(port=global_port, scan_for_port=scan_for_port):
  global interface_running, is_ready, do_log, do_log_verbose
  
  while not is_ready:
    time.sleep(0.01)
  
  # open socket on open port
  server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  while True:
    try: # try opening a port that works
      server_socket.bind(('localhost', port))
      break
    except OSError:
      if scan_for_port:
        port += 1
        continue
      write_error("Couldn't open requested port")
      in_main_thread('quit_app(); sys.exit(1)')
    except Exception:
      write_error()
      in_main_thread('quit_app(); sys.exit(1)')
  if scan_for_port:
    print(port)
    sys.stdout.flush()
    if do_log:
      log_write(f'port: {port}')
  if do_log_verbose:
    log_write('Server started: ' + str(server_socket))
  server_socket.listen(5)
  server_socket.settimeout(0.1)
  
  add_container_block(name='port_container')
  add_text_block('port:', to='port_container')
  add_text_block(str(port), to='port_container')
  
  # listen for connections
  while True:
    try:
      if not interface_running:
        break
      try:
        client_socket, client_address = server_socket.accept()
        client_socket.settimeout(0.1)
      except socket.timeout:
        continue
      if do_log_verbose:
        log_write('Connection from ' + str(client_address))
      # collect data from the client
      buffer = b''
      while True:
        if not interface_running:
          break
        try:
          chunk = client_socket.recv(1024)
        except BlockingIOError:
          continue
        if chunk:
          buffer += chunk
          if b'\x04' in buffer:
            # split into multiple messages, keep proccessing last part of buffer
            buffer_parts = buffer.split(b'\x04')
            for msg in buffer_parts[:-1]:
              rec = msg.decode('ascii')
              if do_log:
                log_write(f'Received {repr(rec)}')
              exec_msg_and_respond(rec, client_socket)
            buffer = buffer_parts[-1]
        else:
          rec = buffer.replace(b'\x04', b'\n').decode('ascii')
          if len(rec) == 0:
            break
          if do_log:
            log_write(f'Received {repr(rec)}')
          exec_msg_and_respond(rec, client_socket)
          client_socket.close()
          break
    except Exception:
      write_error()
      continue

interface_thread = threading.Thread(target=listener)
# interface_thread.daemon = True
interface_thread.start()

# GUI

win = None

def activate(app):
  global win, block_container, fonts
  win = gtk.ApplicationWindow(application=app, title="Noca")
  win.connect('destroy', lambda w: app.quit())
  win.present()
  
  # settings = gtk.Settings.get_default()
  settings = win.get_settings()
  settings.set_property("gtk-double-click-time", 10)
  settings.set_property("gtk-font-name", "sans")
  
  scrollwindow = gtk.ScrolledWindow()
  
  ui_box = gtk.Box(orientation=gtk.Orientation.VERTICAL)
  
  block_container = gtk.Box(orientation=gtk.Orientation.VERTICAL, spacing=4)
  ui_box.append(block_container)
  
  scrollpast_box = gtk.Box(orientation=gtk.Orientation.VERTICAL)
  scrollpast_box.set_size_request(-1, 256)
  scrollpast_box.queue_resize()
  ui_box.append(scrollpast_box)

  scrollwindow.set_child(ui_box)
  win.set_child(scrollwindow)

  win.set_name('Window')

  global style_provider
  style_provider = gtk.CssProvider()
  style_provider.load_from_data(b"""
    #Window {
      background-color: white;
    }
    .block {
      background-color: white;
      border: 1px solid black;
      margin-top: 4px;
      margin: 1px;
    }
    .block.contracted {
      # background-color: #eee;
      border-bottom-width: 2px;
      border-bottom-style: dotted;
    }
    .block-sidebar {
      background-color: lightgray;
      border-right: 1px solid black;
    }
    .block-sidebar-remove-button {
      padding: 1px 1px 1px 1px;
      background-color: lighter(gray);
      border-radius: 0px;
    }
    .block-sidebar-expander-button {
      padding: 1px 1px 1px 1px;
      background-color: lighter(gray);
      border-radius: 0px;
    }
    .block-text {
      color: black;
    }
    .block-text {
      font-family: "Sans", "Open Sans";
    }
    .block-text.monospace {
      font-family: "Fira Code", "Monospace", "DejaVu Sans Mono";
      font-variant-ligatures: normal;
    }
    .block-content {
      margin-left: 4px;
    }
  """)
  gtk.StyleContext.add_provider_for_display(win.get_display(), style_provider, gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
  
  # make fonts
  win_pango_ctx = win.get_pango_context()
  fonts = sorted([f.get_name() for f in win_pango_ctx.list_families()])
  
  add_text_block('Ready')


app = gtk.Application()

def quit_app():
  global app, do_log_verbose
  if do_log_verbose:
    log_write('Quitting')
  app.quit()
def set_ready():
  global is_ready
  is_ready = True

if do_log:
  log_write('\n\nNoca started')

glib.idle_add(set_ready)
app.connect('activate', activate)

try:
  app.run()
except KeyboardInterrupt:
  pass
except Exception:
  write_error()
  sys.exit(1)

# wait for socket thread
interface_running = False
interface_thread.join()

if do_log:
  log_write('Server stopped')

stdin_buffer.close()

if do_log:
  log_write('Done')
exit(0)