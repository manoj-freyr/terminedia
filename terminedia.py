import fcntl, os, sys, termios
import threading
import time

from contextlib import contextmanager
from enum import Enum
from functools import lru_cache
from math import ceil


__version__ = "0.2.0"
__author__ = "João S. O. Bueno"


# Keyboard reading code copied and evolved from
# https://stackoverflow.com/a/6599441/108205
# (@mheyman, Mar, 2011)

@contextmanager
def realtime_keyb():
    """Reconfigure stdin to non-blocking, realtime mode
    """
    fd = sys.stdin.fileno()
    # save old state
    flags_save = fcntl.fcntl(fd, fcntl.F_GETFL)
    attrs_save = termios.tcgetattr(fd)
    # make raw - the way to do this comes from the termios(3) man page.
    attrs = list(attrs_save)  # copy the stored version to update
    # iflag
    attrs[0] &= ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK
                  | termios.ISTRIP | termios.INLCR | termios. IGNCR
                  | termios.ICRNL | termios.IXON)
    # oflag
    attrs[1] &= ~termios.OPOST
    # cflag
    attrs[2] &= ~(termios.CSIZE | termios. PARENB)
    attrs[2] |= termios.CS8
    # lflag
    attrs[3] &= ~(termios.ECHONL | termios.ECHO | termios.ICANON
                  | termios.ISIG | termios.IEXTEN)
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags_save | os.O_NONBLOCK)
    try:
        yield
    finally:
        # restore old state
        termios.tcsetattr(fd, termios.TCSAFLUSH, attrs_save)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags_save)


def inkey(break_=True):
    keycode = ""
    while True:
        c = sys.stdin.read(1)  # returns a single character
        if not c:
            break
        if c == "\x03" and break_:
            raise KeyboardInterrupt
        keycode += c
    return keycode


def testkeys():
    with realtime_keyb():
        while True:
            try:
                key = inkey()
            except KeyboardInterrupt:
                break
            if key:
                print("", key.encode("utf-8"), end="", flush=True)
            print(".", end="", flush=True)
            time.sleep(0.3)


DEFAULT_BG = 0xfffe
DEFAULT_FG = 0xffff


class Directions(Enum):
    UP = (0, -1)
    RIGHT = (1, 0)
    DOWN = (0, 1)
    LEFT = (-1, 0)


def _mirror_dict(dct):
    return {value: key for key, value in dct.items()}


class KeyCodes:
    F1 = '\x1bOP'
    F2 = '\x1bOQ'
    F3 = '\x1bOR'
    F4 = '\x1bOS'
    F5 = '\x1b[15~'
    F6 = '\x1b[17~'
    F7 = '\x1b[18~'
    F8 = '\x1b[19~'
    F9 = '\x1b[20~'
    F10 = '\x1b[21~'
    F11 = '\x1b[23~'
    F12 = '\x1b[24~'
    ESC = '\x1b'
    BACK = '\x7f'
    DELETE = '\x1b[3~'
    ENTER = '\r'
    PGUP = '\x1b[5~'
    PGDOWN = '\x1b[6~'
    HOME = '\x1b[H'
    END = '\x1b[F'
    INSERT = '\x1b[2~'
    UP = '\x1b[A'
    RIGHT = '\x1b[C'
    DOWN = '\x1b[B'
    LEFT = '\x1b[D'


class BlockChars:
    EMPTY = " "
    QUADRANT_UPPER_LEFT = '\u2598'
    QUADRANT_UPPER_RIGHT = '\u259D'
    UPPER_HALF_BLOCK = '\u2580'
    QUADRANT_LOWER_LEFT = '\u2596'
    LEFT_HALF_BLOCK = '\u258C'
    QUADRANT_UPPER_RIGHT_AND_LOWER_LEFT = '\u259E'
    QUADRANT_UPPER_LEFT_AND_UPPER_RIGHT_AND_LOWER_LEFT = '\u259B'
    QUADRANT_LOWER_RIGHT = '\u2597'
    QUADRANT_UPPER_LEFT_AND_LOWER_RIGHT = '\u259A'
    RIGHT_HALF_BLOCK = '\u2590'
    QUADRANT_UPPER_LEFT_AND_UPPER_RIGHT_AND_LOWER_RIGHT = '\u259C'
    LOWER_HALF_BLOCK = '\u2584'
    QUADRANT_UPPER_LEFT_AND_LOWER_LEFT_AND_LOWER_RIGHT = '\u2599'
    QUADRANT_UPPER_RIGHT_AND_LOWER_LEFT_AND_LOWER_RIGHT = '\u259F'
    FULL_BLOCK = '\u2588'

    # This depends on Python 3.6+ ordered behavior for local namespaces and dicts:
    block_chars_by_name = {key: value for key, value in locals().items() if key.isupper()}
    block_chars_to_name = _mirror_dict(block_chars_by_name)
    blocks_in_order = {i: value for i, value in enumerate(block_chars_by_name.values())}
    block_to_order = _mirror_dict(blocks_in_order)

    def __contains__(self, char):
        return char in self.block_chars_to_name

    @classmethod
    def op(cls, pos, data, operation):
        number = cls.block_to_order[data]
        index = 2 ** (pos[0] + 2 * pos[1])
        return operation(number, index)

    @classmethod
    def set(cls, pos, data):
        op = lambda n, index: n | index
        return cls.blocks_in_order[cls.op(pos, data, op)]

    @classmethod
    def reset(cls, pos, data):
        op = lambda n, index: n & (0xf - index)
        return cls.blocks_in_order[cls.op(pos, data, op)]

    @classmethod
    def get_at(cls, pos, data):
        op = lambda n, index: bool(n & index)
        return cls.op(pos, data, op)


# Enables __contains__:
BlockChars = BlockChars()


class ScreenCommands:
    last_pos = None

    def print(self, *args, sep='', end='', flush=True, count=0):
        try:
            for arg in args:
                sys.stdout.write(arg)
                if sep:
                    sys.stdout.write(sep)
            if end:
                sys.stdout.write(end)
            if flush:
                sys.stdout.flush()
        except BlockingIOError:
            if count > 10:
                print("arrrrghhhh - stdout clogged out!!!", file=sys.stderr)
                raise
            time.sleep(0.002 * 2 ** count)
            self.print(*args, sep=sep, end=end, flush=flush, count=count + 1)

    def CSI(self, *args):
        command = args[-1]
        args = ';'.join(str(arg) for arg in args[:-1]) if args else ''
        self.print("\x1b[", args, command)

    def SGR(self, *args):
        self.CSI(*args, 'm')

    def clear(self):
        self.CSI(2, 'J')

    def cursor_hide(self):
        self.CSI('?25', 'l')

    def cursor_show(self):
        self.CSI('?25', 'h')

    def moveto(self, pos):
        if list(pos) == self.__class__.last_pos:
            return
        x, y = pos
        self.CSI(f'{y + 1};{x + 1}H')
        self.__class__.last_pos = list(pos)

    def print_at(self, pos, txt):
        self.moveto(pos)
        self.print(txt)
        self.__class__.last_pos[0] += len(txt)

    @lru_cache()
    def _normalize_color(self, color):
        if isinstance(color, int):
            return color
        if 0 <= color[0] < 1.0 or color[0] == 1.0 and all(c <= 1.0 for c in color[1:]):
            color = tuple(int(c * 255) for c in color)
        return color

    def reset_colors(self):
        self.SGR(0)

    def set_colors(self, foreground, background):
        self.set_fg_color(foreground)
        self.set_bg_color(background)

    def set_fg_color(self, color):
        if color == DEFAULT_FG:
            self.SGR(39)
        else:
            color = self._normalize_color(color)
            self.SGR(38, 2, *color)

    def set_bg_color(self, color):
        if color == DEFAULT_BG:
            self.SGR(49)
        else:
            color = self._normalize_color(color)
            self.SGR(48, 2, *color)



class JournalingScreenCommands(ScreenCommands):

    def __init__(self):
        self.in_block = 0
        self.current_color = DEFAULT_FG
        self.current_background = DEFAULT_BG
        self.current_pos = 0, 0

    def __enter__(self):
        if self.in_block == 0:
            self.journal = {}
        self.tick = 0
        self.in_block += 1


    def set(self, pos, char):
        if not self.in_block:
            raise RuntimeError("Journal not open")
        self.journal.setdefault(pos, []).append((self.tick, char, self.current_color, self.current_background))
        self.tick += 1


    def __exit__(self, exc_name, traceback, frame):
        if exc_name:
            return

        self.in_block -= 1
        if self.in_block == 0:
            self.replay()

    def replay(self):
        last_color = last_bg = None
        last_pos = None
        buffer = ""

        for pos in sorted(self.journal, key=lambda pos: (pos[1], pos[0])):
            tick, char, color, bg = self.journal[pos][-1]
            call = []
            if color != last_color:
                last_color = color
                call.append((self.set_fg_color, color))

            if bg != last_bg:
                last_bg = bg
                call.append((self.set_bg_color, bg))

            if pos != last_pos:
                last_pos = pos
                call.append((self.moveto, pos))

            if call:
                if buffer:
                    self.print(buffer)
                    buffer = ""
                for func, arg in call:
                    func(arg)
            buffer += char
            last_pos = pos[0] + 1, pos[1]

        if buffer:
            self.print(buffer)

    def print_at(self, pos, txt):
        if not self.in_block:
            return super().print_at(pos, txt)
        for x, char in enumerate(txt, pos[0]):
            self.set((x, pos[1]), char)

    def set_fg_color(self, color):
        if not self.in_block:
            super().set_fg_color(color)
        self.current_color = color

    def set_bg_color(self, color):
        if not self.in_block:
            super().set_bg_color(color)
        self.current_background = color


class Drawing:
    """Intended to be used as a namespace for drawing, including primitives"""

    def __init__(self, set_fn, reset_fn, size_fn, context):
        self.set = set_fn
        self.reset = reset_fn
        self.size = property(size_fn)
        self.context = context

    def line(self, pos1, pos2, erase=False):

        op = self.reset if erase else self.set
        x1, y1 = pos1
        x2, y2 = pos2
        op(pos1)

        max_manh = max(abs(x2 - x1), abs(y2 - y1))
        if max_manh == 0:
            return
        step_x = (x2 - x1) / max_manh
        step_y = (y2 - y1) / max_manh
        total_manh = 0
        while total_manh < max_manh:
            x1 += step_x
            y1 += step_y
            total_manh += max(abs(step_x), abs(step_y))
            op((round(x1), round(y1)))

    def rect(self, pos1, pos2=(), *, rel=(), fill=False, erase=False):
        if not pos2:
            if not rel:
                raise TypeError("Must have either two corners of 'rel' parameter")
            pos2 = pos1[0] + rel[0], pos1[1] + rel[1]
        x1, y1 = pos1
        x2, y2 = pos2
        self.line(pos1, (x2, y1), erase=erase)
        self.line((x1, y2), pos2, erase=erase)
        if (fill or erase) and y2 != y1:
            direction = int((y2 - y1) / abs(y2 - y1))
            for y in range(y1 + 1, y2, direction):
                self.line((x1, y), (x2, y), erase=erase)
        else:
            self.line(pos1, (x1, y2))
            self.line((x2, y1), pos2)

    def vsize(self, x, y):
        return (x ** 2 + y ** 2) ** 0.5

    def _link_prev(self, pos, i, limits, mask):
        if i < limits[0] - 1:
            for j in range(i, limits[0]):
                self.set((pos[0] + j, pos[1]))
                mask[j] = True
        elif i + 1 > limits[1]:
            for j in range(limits[1], i):
                self.set((pos[0] + j, pos[1]))
                mask[j] = True

    def ellipse(self, pos1, pos2, fill=False):
        from math import sin, cos, asin

        x1, y1 = pos1
        x2, y2 = pos2

        x1, x2 = (x1, x2) if x1 <= x2 else (x2, x1)
        y1, y2 = (y1, y2) if y1 <= y2 else (y2, y1)

        cx, cy = x1 + (x2 - x1) / 2, y1 + (y2 - y1) / 2
        r1, r2 = x2 - cx, y2 - cy

        lx = x2 - x1 + 1

        prev_mask = borders = []
        for y in range(y1, y2 + 1):
            sin_y = abs(y - cy) / r2
            az = asin(sin_y)
            r_y = self.vsize(r2 * sin_y, r1 * cos(az))
            mask = [False,] * lx
            inside = False
            for i, x in enumerate(range(x1, x2 + 1)):
                d = self.vsize(x - cx, y - cy)
                if not inside and d <= (r_y + 0.25):
                    inside = True
                    self.set((x, y))
                    mask[i] = True
                    if borders:
                        self._link_prev((x1, y), i, borders[0], mask)

                elif inside and (d > (r_y + 0.25) and i or i == lx - 1):
                    inside = False
                    self.set((x - 1, y))
                    mask[i - 1] = True

                    if borders:
                        self._link_prev((x1, y), i - 1, borders[-1], mask)


                elif inside and (y == y1 or y == y2) and d <= r_y + 0.25:
                    self.set((x, y))
                    mask[i] = True


                #if abs(r_y - d) <= 1.1:
                    #self.set((x, y))
                if fill and d < r_y:
                    self.set((x, y))

            if not fill:
                # adaptativeness:
                border_count = 0
                borders = []
                for i, p1 in enumerate(mask):
                    if (p1 and border_count % 2 == 0):
                        borders.append([i])
                        border_count += 1
                    elif (not p1 and border_count % 2 == 1) or (i == lx - 1 and len(borders[-1]) == 0):
                        borders[-1].append(i)
                        border_count += 1




            prev_mask = mask


    def blit(self, pos, shape, color_map=None, erase=False):
        """Blits a blocky image in the associated screen at POS

        Any character but space (\x20) or "." is considered a block.
        Shape can be a "\n" separated string or a list of strings.
        If a color_map is not given, any non-space character is
        set with the context color. Otherwise, color_map
        should be a mapping from characters to RGB colors
        for each block.

        If "erase" is given, spaces are erased, instead of being ignored.

        ("." is allowed as white-space to allow drawing shapes
        inside Python multi-line strings when editors
        and linters are set to remove trailing spaces)
        """
        if isinstance(shape, str):
            shape = shape.split("\n")
        last_color = self.context.color
        for y, line in enumerate(shape, start=pos[1]):
            for x, char in enumerate(line, start=pos[0]):
                if char not in " .":
                    if color_map:
                        color = color_map[char]
                        if color != last_color:
                            self.context.color = last_color = color
                    self.set((x, y))
                elif erase:
                    self.reset((x, y))


class HighRes:
    def __init__(self, parent):
        self.parent = parent
        self.draw = Drawing(self.set_at, self.reset_at, self.get_size, self.parent.context)
        self.context = parent.context

    def get_size(self):
        w, h = self.parent.get_size()
        return w * 2, h * 2

    def operate(self, pos, operation):
        p_x = pos[0] // 2
        p_y = pos[1] // 2
        i_x, i_y = pos[0] % 2, pos[1] % 2
        graphics = True
        original = self.parent[p_x, p_y]
        if original not in BlockChars:
            graphics = False
            original = " "
        new_block = operation((i_x, i_y), original)
        return graphics, (p_x, p_y), new_block

    def set_at(self, pos):
        _, gross_pos, new_block = self.operate(pos, BlockChars.set)
        self.parent[gross_pos] = new_block

    def reset_at(self, pos):
        _, gross_pos, new_block = self.operate(pos, BlockChars.reset)
        self.parent[gross_pos] = new_block

    def get_at(self, pos):
        graphics, _, is_set = self.operate(pos, BlockChars.get_at)
        return is_set if graphics else None


class Screen:
    lock = threading.Lock()

    last_background = None
    last_color = None

    def __init__(self, size=()):
        if not size:
            self.get_size = os.get_terminal_size
            size = os.get_terminal_size()
        else:
            self.get_size = lambda: size

        self.context = threading.local()

        self.draw = Drawing(self.set_at, self.reset_at, self.get_size, self.context)
        self.width, self.height = self.size = size

        self.high = HighRes(self)

        self.commands = JournalingScreenCommands()

    def __enter__(self):
        self.clear(True)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.commands.clear()
        self.commands.cursor_show()
        self.commands.reset_colors()

    def clear(self, wet_run=True):
        self.data = [" "] * self.width * self.height
        self.color_data = [(DEFAULT_FG, DEFAULT_BG)] * self.width * self.height
        self.context.color = DEFAULT_FG
        self.context.background = DEFAULT_BG
        self.context.direction = Directions.RIGHT
        # To use when we allow custom chars along with blocks:
        # self.char_data = " " * self.width * self.height
        if wet_run:
            with self.lock:
                self.commands.clear()
                self.commands.cursor_hide()

    def set_at(self, pos, color=None):
        if color:
            self.context.color = color
        self[pos] = BlockChars.FULL_BLOCK

    def reset_at(self, pos):
        self[pos] = " "

    def line_at(self, pos, length, sequence=BlockChars.FULL_BLOCK):
        x, y = pos
        if not sequence:
            return
        for i, char in zip(range(length), sequence * (ceil(length / len(sequence)))):
            self[x, y] = char
            x += self.context.direction.value[0]
            y += self.context.direction.value[1]

    def print_at(self, pos, text):
        self.line_at(pos, len(text), sequence=text)

    def __getitem__(self, pos):
        index = pos[0] + pos[1] * self.width
        if index < 0 or index >= len(self.data):
            return " "
        return self.data[index]

    def __setitem__(self, pos, value):
        index = pos[0] + pos[1] * self.width
        if index < 0 or index >= len(self.data):
            return
        self.data[index] = value

        cls = self.__class__
        with self.lock:
            update_colors =  cls.last_color != self.context.color or cls.last_background != self.context.background
            colors = self.context.color, self.context.background
            self.color_data[index] = colors
            if update_colors:
                self.commands.set_colors(*colors)
                cls.last_color = self.context.color
                cls.last_background = self.context.background
            self.commands.print_at(pos, value)


class Context:
    SENTINEL = object()
    def __init__(self, screen, **kwargs):
        """Context manager for screen context attributes
        (Pun not intended)

        Kwargs should contain desired temporary attributes:
        color: color special value or RGB sequence for foreground color - either int 0-255  or float 0-1 based.
        background: color special value or RGB sequence sequence for background color
        direction: terminedia.Directions Enum value with writting direction

        When entering this context, the original context is returned - changes made to it
        will be reverted when exiting.
        """
        self.screen = screen
        self.attrs = kwargs

    def __enter__(self):
        self.original_values = {key:getattr(self.screen.context, key) for key in dir(self.screen.context) if not key.startswith("_")}
        for key, value in self.attrs.items():
            setattr(self.screen.context, key, value)
        return self.screen.context

    def __exit__(self, exc_name, traceback, frame):
        for key, value in self.original_values.items():
            if value is self.SENTINEL:
                continue
            setattr(self.screen.context, key, value)
        for key in dir(self.screen.context):
            if not key.startswith("_") and not key in self.original_values:
                delattr(self.screen.context, key)







shape1 = """\
           .
     *     .
    * *    .
   ** **   .
  *** ***  .
 ********* .
           .
"""

shape2 = """\
                   .
    *    **    *   .
   **   ****   **  .
  **   **##**   ** .
  **   **##**   ** .
  **   **##**   ** .
  **************** .
  **************** .
    !!   !!   !!   .
    !!   !!   !!   .
   %  % %  % %  %  .
                   .
"""

c_map = {
    '*': DEFAULT_FG,
    '#': (.5, 0.8, 0.8),
    '!': (1, 0, 0),
    '%': (1, 0.7, 0),
}


def main():
    with realtime_keyb(), Screen() as scr:

        factor = 2
        x = (scr.high.get_size()[0] // 2 - 13)
        x = x - x % factor
        y = 0
        K = KeyCodes
        mode = 0
        while True:
            key = inkey()
            if key == '\x1b':
                break

            with scr.commands:
                scr.high.draw.rect((x, y), rel=(26, 14), erase=True)


                if mode == 0:
                    y += factor

                    if y >= scr.high.get_size()[1] - 17:
                        mode = 1

                if mode == 1:
                    x -= factor
                    if x <= 0:
                        break


                #x += factor * ((key == K.RIGHT) - (key == K.LEFT))
                #y += factor * ((key == K.DOWN) - (key == K.UP))

                scr.high.draw.blit((x, y), shape2, color_map=c_map)

            time.sleep(1/30)

if __name__ == "__main__":
    #testkeys()
    main()

