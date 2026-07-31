from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .solver import QuipqiupError, Solution, solve


MAX_DISPLAYED_SOLUTIONS = 5


@register(
    "quipqiup_helper",
    "Loraen_Konpeki",
    "使用 quipqiup 求解英文单表替换密码",
    "1.0.0",
)
class QuipqiupHelperPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("quip", alias={"qq", "cryptogram"})
    async def quip(self, event: AstrMessageEvent):
        """求解英文单表替换密码。"""
        ciphertext, clues = _parse_arguments(event.message_str)
        if not ciphertext:
            yield event.plain_result(
                "请输入密文。用法：/quip 密文\n"
                "可选已知映射：/quip 密文 --clues A=E B=T"
            )
            return

        if sum(char.isalpha() for char in ciphertext) < 8:
            yield event.plain_result("密文至少需要 8 个英文字母才值得尝试求解。")
            return

        try:
            solutions = await solve(ciphertext, clues)
        except QuipqiupError as exc:
            yield event.plain_result(str(exc))
            return

        if not solutions:
            yield event.plain_result("没有找到可信的结果。可以补充 `--clues A=E B=T` 后重试。")
            return

        yield event.plain_result(_format_solutions(solutions))

    @filter.command("quiphelp", alias={"qqhelp", "cryptogramhelp"})
    async def quip_help(self, event: AstrMessageEvent):
        """显示 quipqiup 插件用法。"""
        yield event.plain_result(
            "quipqiup 单表替换求解\n\n"
            "/quip <密文>\n"
            "/quip <密文> --clues A=E B=T\n\n"
            "`--clues` 左边是密文字母，右边是对应的明文字母。"
        )


def _parse_arguments(message: str) -> tuple[str, str]:
    parts = message.strip().split(maxsplit=1)
    if len(parts) < 2:
        return "", ""

    payload = parts[1].strip()
    ciphertext, separator, clue_part = payload.partition("--clues")
    clues = clue_part.strip() if separator else ""
    return ciphertext.strip(), clues


def _format_solutions(solutions: list[Solution]) -> str:
    lines = ["quipqiup 候选结果："]
    for index, solution in enumerate(solutions[:MAX_DISPLAYED_SOLUTIONS], start=1):
        lines.append(f"\n{index}. {solution.plaintext}")
        if solution.key:
            lines.append("   密文：ABCDEFGHIJKLMNOPQRSTUVWXYZ")
            lines.append(f"   明文：{''.join(solution.key).upper()}")
    if len(solutions) > MAX_DISPLAYED_SOLUTIONS:
        lines.append(f"\n仅显示前 {MAX_DISPLAYED_SOLUTIONS} 条，共 {len(solutions)} 条。")
    return "\n".join(lines)
