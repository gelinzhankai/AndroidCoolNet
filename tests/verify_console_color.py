"""Run in a Windows console: inspect actual foreground attributes while warning prints."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import setup_tool as s

assert sys.stdout.isatty(), 'This acceptance check requires a Windows console'
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.GetStdHandle.argtypes = [wintypes.DWORD]
kernel.GetStdHandle.restype = wintypes.HANDLE
kernel.GetConsoleScreenBufferInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
handle = kernel.GetStdHandle(-11)


def attributes():
    # CONSOLE_SCREEN_BUFFER_INFO: two COORDs (8 bytes), then the WORD attributes.
    buffer = ctypes.create_string_buffer(22)
    assert kernel.GetConsoleScreenBufferInfo(handle, buffer), ctypes.get_last_error()
    return int.from_bytes(buffer.raw[8:10], 'little')


before = attributes()
original = s.say
seen = []


def inspect(message):
    seen.append(attributes())
    assert seen[-1] & 15 == 12, 'Expected bright red foreground'
    original(message)


try:
    s.say = inspect
    s.say_red('【显示测试】隐私风险提醒：红色字体测试，无设备操作。')
finally:
    s.say = original
assert seen and attributes() == before, 'Console color was not restored'
print('PASS: Windows bright red foreground verified and original attributes restored')
