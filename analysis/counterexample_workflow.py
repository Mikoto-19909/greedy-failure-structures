"""Experiment-oriented entry points over the existing miner and conjecture search."""
from __future__ import annotations

import argparse
from datetime import datetime
from fractions import Fraction
import json
import os
from pathlib import Path
import shlex
import sys

from conjecture_spec import parse_design
from mine_counterexamples import mine, size, write_outputs as write_mining
from refute_conjecture import search, write_outputs as write_search
from validate_counterexamples import validate_document as verify_mining
from validate_conjecture import validate_document as verify_search
from r3_counterexamples import TARGETS, load_source, search_pair, write_outputs as write_pair
from validate_r3_counterexamples import validate_document as verify_pair

ROOT = Path(__file__).resolve().parents[1]
STATUS = {"counterexample_found": "找到反例", "domain_exhausted": "指定有限域已检查完，未找到反例",
          "budget_exhausted": "预算耗尽，尚未完成", "deletion_minimal": "单步删减已完成"}


def ratio(text):
    try:
        value = Fraction(text)
        if not 0 <= value <= 1:
            raise ValueError()
    except (ValueError, ZeroDivisionError):
        raise argparse.ArgumentTypeError("比例应在 0 到 1 之间，例如 1、4/5 或 0.8") from None
    return [value.numerator, value.denominator]


def set_size(text):
    if text.lower() == "any":
        return None
    try:
        return int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("集合大小应为整数；不限大小请用 any") from None


def display_path(path):
    path = path.resolve()
    try:
        return path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path)


def quoted(path):
    if os.name == "nt":
        return "'" + display_path(path).replace("'", "''") + "'"
    return shlex.quote(display_path(path))


def launcher():
    if os.name == "nt":
        return ".\\counterexamples.ps1" if Path.cwd().resolve() == ROOT else f"& {quoted(ROOT / 'counterexamples.ps1')}"
    return shlex.join([sys.executable, str(ROOT / "counterexamples.py")])


def fresh_output(kind, explicit):
    path = explicit if explicit is not None else (
        ROOT / "results/counterexamples" / f"{kind}-{datetime.now():%Y%m%d-%H%M%S-%f}")
    if path.exists():
        raise ValueError(f"结果目录已存在，未覆盖：{path}；省略 --output 可自动创建新目录")
    return path.resolve()


def explain_evaluation(instance, evaluation):
    print(f"集合数={len(instance['sets'])}，全集大小={instance['universe_size']}，k={instance['k']}")
    for i, elements in enumerate(instance["sets"]):
        print(f"  S{i} = {{{', '.join(map(str, elements))}}}")
    print(f"Greedy 覆盖 G={evaluation['greedy']}；最优覆盖 O={evaluation['optimum']}")
    print(f"Greedy 顺序={evaluation['greedy_selected']}；最优选择={evaluation['optimum_selected']}")
    for step in evaluation["trace"]:
        print(f"  第 {step['step']} 步：选 S{step['selected']}，新增 {step['gain']}，"
              f"累计覆盖 {step['coverage']}；最大增益候选={step['ties']}")


def summarize(document, kind, *, rank=None):
    counts = document["counts"]
    if kind == "r3-pair":
        labels = {"pair_found": "找到保度配对见证", "component_exhausted": "所定义交换的可达空间已检查完",
                  "state_budget_exhausted": "状态预算耗尽，搜索未完成",
                  "switch_budget_exhausted": "合法交换预算耗尽，搜索未完成"}
        print(f"{labels[document['status']]}：精确评估 {counts['states']} 个状态，"
              f"检查 {counts['switches']} 个合法交换；目标={document['settings']['target']}。")
        for title, item in (("原始", document["original"]), ("配对", document["pair"])):
            if item is None:
                continue
            value = item["evaluation"]
            print(f"{title}：E0={value['e0']}，G={value['greedy']}，O={value['optimum']}，"
                  f"O1={value['forced_optimum']}；首步不可恢复={'是' if value['first_step_irrecoverable'] else '否'}，"
                  f"最终失败={'是' if value['final_failure'] else '否'}。")
            if rank is not None:
                print(f"集合大小={value['row_degrees']}；元素频数={value['element_frequencies']}；"
                      f"交集分布={value['intersection_profile']}。")
                explain_evaluation(item["instance"], value)
        if rank not in (None, 1):
            raise ValueError("R3 搜索只保存首个配对见证，--rank 只能为 1")
        if document["pair"] is not None:
            print(f"交换路径 [i,j,a,b]：{document['pair']['switches']}。")
        print("O1 是强制保留集合 0 的最优值。保度选例不是 F3 随机协议样本，不用于估计协议效应。")
    elif kind == "mine":
        print(f"输入 {counts['input']}；精确评估 {counts['exact']}；反例 {counts['failures']}；"
              f"入选缩小 {counts['selected']}。")
        if counts["exact"] < counts["input"]:
            print(f"另有 {counts['input'] - counts['exact']} 个实例超过精确组合上限，未判定是否为反例。")
        population = document["settings"].get("population")
        print(f"来源筛选：{population or '未按 population 筛选'}。")
        for i, item in enumerate(document["selected"], 1):
            original = document["inputs"][item["input_index"]]
            source, before, after = original["source"], original["evaluation"], item["evaluation"]
            print(f"[{i}] {source.get('population', 'input')}/{source.get('case_id', '')}，"
                  f"来源记录 {source['record']}：尺寸(m,n,成员数) {size(original['instance'])}"
                  f" -> {size(item['instance'])}；G/O {before['greedy']}/{before['optimum']}"
                  f" -> {after['greedy']}/{after['optimum']}；{STATUS[item['status']]}。")
        print("缩小仅保持 k 和 G<O，不保证原结构前提或全局最小；选例计数不是总体失效率。")
        if rank is not None and document["selected"]:
            if not 1 <= rank <= len(document["selected"]):
                raise ValueError(f"--rank 应在 1 到 {len(document['selected'])} 之间")
            item = document["selected"][rank - 1]
            explain_evaluation(item["instance"], item["evaluation"])
        elif rank not in (None, 1):
            raise ValueError("没有可选的反例")
    else:
        status, domain = document["status"], document["design"]["domain"]
        numerator, denominator = document["design"]["claim"]["min_ratio"]
        print(f"前提：n={domain['universe_size']}，m={domain['set_count']}，k={domain['k']}，"
              f"集合大小={domain['set_size'] if domain['set_size'] is not None else '不限'}，"
              f"不重复={'是' if domain['unique_sets'] else '否'}，"
              f"最大频数={domain['max_frequency'] if domain['max_frequency'] is not None else '不限'}。")
        print(f"结论要求：G × {denominator} ≥ O × {numerator}。")
        print(f"{STATUS[status]}：已检查 {counts['scanned']}/{counts['candidate_space']}，"
              f"满足前提 {counts['eligible']}，被频数条件排除 {counts['rejected']}。")
        if rank not in (None, 1):
            raise ValueError("猜想搜索只保存首个反例，--rank 只能为 1")
        if document["counterexample"] is not None:
            item = document["counterexample"]
            explain_evaluation(item["instance"], item["evaluation"])
        elif status == "domain_exhausted":
            print("结论只适用于本次指定有限域，不能推广到其他规模。")
            if counts["eligible"] == 0:
                print("没有满足全部前提的实例，不能把空域当作猜想的经验支持。")
        else:
            print("可增加 --budget 后重跑；从头枚举，不是续跑。未找到不能说明猜想成立。")


def show(path, rank):
    if path.is_dir():
        candidates = [path / name for name in ("counterexamples.json", "search.json", "pair.json")
                      if (path / name).is_file()]
        if len(candidates) != 1:
            raise ValueError("目录中应有且仅有一个 counterexamples.json、search.json 或 pair.json")
        path = candidates[0]
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(document, dict):
        raise ValueError("结果应为 JSON 对象")
    if document.get("purpose") == "r3_counterexample_exploration":
        verify_pair(document)
        kind = "r3-pair"
    elif "inputs" in document:
        verify_mining(document)
        kind = "mine"
    elif "design" in document:
        verify_search(document)
        kind = "refute"
    else:
        raise ValueError("不是反例挖掘或猜想搜索的结果文件")
    print("独立重算通过。")
    summarize(document, kind, rank=rank)


def build_parser():
    parser = argparse.ArgumentParser(description="反例实验：挖掘已有样本、创建猜想、搜索并查看结果。",
                                     epilog="Windows: .\\counterexamples.ps1 <命令>；其他平台: python counterexamples.py <命令>")
    commands = parser.add_subparsers(dest="command", title="实验操作")
    mining = commands.add_parser("mine", help="筛选和缩小已有实验反例；默认只读 R1 pilot 样本")
    mining.add_argument("--input", type=Path, help="已有实例 JSON/JSONL；省略时使用内置 R1 数据")
    mining.add_argument("--population", help="来源标签，例如 pilot、fixture；all 表示不过滤")
    mining.add_argument("--top", type=int, default=5, help="缩小前几个反例，默认 5")
    mining.add_argument("--max-combinations", type=int, default=200000)
    mining.add_argument("--max-evaluations", type=int, default=10000, help="每个反例的删减候选预算；0 仅挖掘")
    mining.add_argument("--output", type=Path, help="新结果目录；省略时自动命名")
    create = commands.add_parser("design", help="用参数生成猜想 JSON，不覆盖已有设计")
    create.add_argument("path", type=Path, help="要新建的 JSON 路径，例如 designs/my_guess.json")
    create.add_argument("--n", type=int, default=4, help="全集大小，默认 4")
    create.add_argument("--m", type=int, default=3, help="集合数，默认 3")
    create.add_argument("--k", type=int, default=2, help="选择预算，默认 2")
    create.add_argument("--size", type=set_size, default=2, help="每个集合大小，默认 2；any 表示不限")
    create.add_argument("--ratio", type=ratio, default=[1, 1], help="覆盖比例要求，例如 1、4/5、0.8")
    create.add_argument("--allow-duplicates", action="store_true", help="允许重复集合；默认不重复")
    create.add_argument("--max-frequency", type=int)
    create.add_argument("--budget", type=int, default=10000, help="候选实例检查预算")
    create.add_argument("--max-combinations", type=int, default=200000)
    refute = commands.add_parser("refute", help="搜索猜想反例；省略设计时运行等长集合示例")
    refute.add_argument("--design", type=Path, default=ROOT / "designs/conjecture_equal_size.json")
    refute.add_argument("--budget", type=int, help="仅覆盖本次候选预算，不改原设计文件")
    refute.add_argument("--ratio", type=ratio, help="仅覆盖本次结论阈值，不改原设计文件")
    refute.add_argument("--output", type=Path, help="新结果目录；省略时自动命名")
    pair = commands.add_parser("r3-pair", help="固定两侧度数，搜索 E0/首步结局的成对反例")
    pair.add_argument("--input", type=Path, default=ROOT / "designs/r3_pair_example.json",
                      help="实例 JSON、JSONL 或 R2 原图 JSON；默认手工小例")
    pair.add_argument("--record", type=int, default=1, help="JSONL 中的实际行号，默认 1")
    pair.add_argument("--k", type=int, help="指定 k；导入多预算 R2 原图时必须给出")
    pair.add_argument("--target", choices=TARGETS, default="same-e0-flip")
    pair.add_argument("--same-optimum", action="store_true", help="额外要求两个端点的 O 相同")
    pair.add_argument("--max-states", type=int, default=200, help="含原图在内的精确评估状态预算")
    pair.add_argument("--max-switches", type=int, default=10000, help="合法交换检查预算（计入重复状态）")
    pair.add_argument("--max-combinations", type=int, default=200000)
    pair.add_argument("--output", type=Path, help="新结果目录；省略时自动命名")
    inspect = commands.add_parser("show", help="独立重算结果，再显示集合、Greedy 轨迹和最优见证")
    inspect.add_argument("result", type=Path, help="结果目录或其中的结果 JSON")
    inspect.add_argument("--rank", type=int, default=1, help="挖掘结果中的编号，默认 1")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        print("\n先试：.\\counterexamples.ps1 mine\n再试：.\\counterexamples.ps1 refute")
        return 0
    try:
        if args.command == "show":
            if args.rank < 1:
                raise ValueError("--rank 必须至少为 1")
            show(args.result, args.rank)
            return 0
        if args.command == "design":
            if args.path.exists():
                raise ValueError(f"设计文件已存在，未覆盖：{args.path}；请换一个新文件名")
            design = parse_design({"schema_version": 1, "name": args.path.stem,
                "domain": {"universe_size": args.n, "set_count": args.m, "k": args.k,
                           "set_size": args.size, "unique_sets": not args.allow_duplicates,
                           "max_frequency": args.max_frequency},
                "claim": {"min_ratio": args.ratio},
                "search": {"max_instances": args.budget, "max_combinations": args.max_combinations}})
            args.path.parent.mkdir(parents=True, exist_ok=True)
            with args.path.open("x", encoding="utf-8") as handle:
                json.dump(design, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            print(f"已创建设计：{args.path.resolve()}")
            print(f"下一步：{launcher()} refute --design {quoted(args.path)}")
            return 0
        output = fresh_output(args.command, args.output)
        if args.command == "r3-pair":
            instance, source = load_source(args.input, record=args.record, k=args.k)
            print("正在搜索保度配对并独立核验；此操作只做选例……", flush=True)
            document = search_pair(instance, source, target=args.target, same_optimum=args.same_optimum,
                                   max_states=args.max_states, max_switches=args.max_switches,
                                   max_combinations=args.max_combinations)
            write_pair(document, output)
        elif args.command == "mine":
            source = args.input or ROOT / "experiments/r1_prefix_exchange_v1/paths.jsonl"
            population = args.population if args.population is not None else ("pilot" if args.input is None else None)
            population = None if population == "all" else population
            print(f"读取已有实例：{source.resolve()}\n来源筛选：{population or '全部'}；正在精确评估与缩小……", flush=True)
            document = mine(source, population=population, top=args.top,
                            max_combinations=args.max_combinations, max_evaluations=args.max_evaluations)
            write_mining(document, output)
        else:
            design = parse_design(json.loads(args.design.read_text(encoding="utf-8-sig")))
            if args.budget is not None:
                design["search"]["max_instances"] = args.budget
            if args.ratio is not None:
                design["claim"]["min_ratio"] = args.ratio
            print(f"读取猜想：{args.design.resolve()}\n正在搜索并独立核验……", flush=True)
            document = search(design)
            write_search(document, output)
            (output / "design.json").write_text(json.dumps(document["design"], ensure_ascii=False, indent=2)
                                               + "\n", encoding="utf-8")
        summarize(document, args.command)
        print(f"\n独立重算通过。结果目录：{output}")
        print(f"阅读：{output / 'README.md'}")
        print(f"查看细节：{launcher()} show {quoted(output)}")
        return 0
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError) as error:
        parser.exit(2, f"实验未完成：{error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
