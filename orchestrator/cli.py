"""VerityLens 编排层 CLI 入口。

仅依赖标准库，保证在未安装第三方依赖时也能打印帮助；
完整子命令在 Phase 0 按 design-blueprint.md 实现。
"""
import argparse
import sys


def cmd_init(args):
    print(f"[init] discipline={args.discipline} (Phase 0 待实现)")


def cmd_gate(args):
    print(f"[gate] phase={args.phase} (Phase 0 待实现)")


def cmd_loop(args):
    print("[loop] 失败回流检查 (Phase 1 待实现)")


def cmd_budget(args):
    print("[budget] 预算硬阻断检查 (Phase 0 待实现)")


def cmd_lock(args):
    print(f"[lock] {args.action} {args.artifact} (Phase 3 待实现)")


def cmd_bundle(args):
    print(f"[bundle] new {args.discipline} (Phase 2 待实现)")


def cmd_finalize(args):
    print("[finalize] 收尾 (Phase 1 待实现)")


def build_parser():
    p = argparse.ArgumentParser(prog="vl", description="VerityLens 编排层 CLI")
    sub = p.add_subparsers(dest="command")

    sp = sub.add_parser("init", help="生成 Workspace 脚手架")
    sp.add_argument("discipline")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("gate", help="阶段门禁校验")
    sp.add_argument("phase")
    sp.set_defaults(func=cmd_gate)

    sp = sub.add_parser("loop", help="失败回流检查")
    sp.set_defaults(func=cmd_loop)

    sp = sub.add_parser("budget", help="预算硬阻断检查")
    sp.add_argument("action", nargs="?", default="check")
    sp.set_defaults(func=cmd_budget)

    sp = sub.add_parser("lock", help="制品写锁")
    sp.add_argument("action")
    sp.add_argument("artifact")
    sp.set_defaults(func=cmd_lock)

    sp = sub.add_parser("bundle", help="生成学科 Bundle")
    sp.add_argument("action", nargs="?", default="new")
    sp.add_argument("discipline")
    sp.set_defaults(func=cmd_bundle)

    sp = sub.add_parser("finalize", help="收尾导出")
    sp.set_defaults(func=cmd_finalize)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
