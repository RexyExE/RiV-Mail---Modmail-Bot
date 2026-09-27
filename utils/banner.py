import sys

ASCII = (
    "██████╗  ██╗ ██╗   ██╗   ███╗   ███╗  █████╗  ██╗ ██╗     \n"
    "██╔══██╗ ██║ ██║   ██║   ████╗ ████║ ██╔══██╗ ██║ ██║     \n"
    "██████╔╝ ██║ ██║   ██║   ██╔████╔██║ ███████║ ██║ ██║     \n"
    "██╔══██╗ ██║ ╚██╗ ██╔╝   ██║╚██╔╝██║ ██╔══██║ ██║ ██║     \n"
    "██║  ██║ ██║  ╚████╔╝    ██║ ╚═╝ ██║ ██║  ██║ ██║ ███████╗\n"
    "╚═╝  ╚═╝ ╚═╝   ╚═══╝     ╚═╝     ╚═╝ ╚═╝  ╚═╝ ╚═╝ ╚══════╝"
)

STOPS = [(0x7F, 0x5A, 0xF0), (0x2C, 0xB1, 0xFF), (0x00, 0xF0, 0xFF)]


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _gradient(steps: int) -> list[tuple[int, int, int]]:
    if steps <= 1:
        return [STOPS[0]]
    n = len(STOPS) - 1
    colours = []
    for i in range(steps):
        t = i / (steps - 1)
        seg = min(int(t * n), n - 1)
        local_t = (t * n) - seg
        colours.append(_lerp(STOPS[seg], STOPS[seg + 1], local_t))
    return colours


def _colour_line(line: str) -> str:
    colours = _gradient(max(len(line), 1))
    parts = [f"\033[38;2;{r};{g};{b}m{ch}" for ch, (r, g, b) in zip(line, colours)]
    parts.append("\033[0m")
    return "".join(parts)


def print_banner(bot_name: str, prefix: str) -> None:
    coloured = sys.stdout.isatty()
    for line in ASCII.split("\n"):
        print(_colour_line(line) if coloured else line)

    rule = "─" * 55
    print(f"\033[90m    {rule}\033[0m" if coloured else f"    {rule}")
    print(f"    {bot_name} | prefix: {prefix}")
    print(f"\033[90m    {rule}\033[0m" if coloured else f"    {rule}")
