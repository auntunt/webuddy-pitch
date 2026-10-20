"""Fill the platform's 闭环改进 from the JeecgBoot test, without starting the service.

The test tickets are real GitHub issues whose official fixes are in the repository history, so each one is
an eval case exactly like "从历史工单生成用例" makes: start at the parent of the fix commit, the right files are
what the fix changed (lock files, generated files and whitespace-only edits left out). Where the review of our
change against the official fix found it went the wrong way or changed far too much, that review becomes a
lesson ("对照官方复盘"), which later prompts on similar tickets carry.

    python3 closeloop.py <work> [--data <work>/data] [--project JB] [--apply]

<work> is the test folder (report-data.json from longreport.py, report-notes.json, JeecgBoot/). Without
--apply it only prints what it would add. Re-running replaces the cases and skips lessons already there.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from tmh.platform import learn  # noqa: E402
from tmh.platform.agents import git  # noqa: E402

# What each wrong-way or oversized change teaches, in words a later prompt can use.
LESSONS = {
    "JB-6": "缺接口类问题照着已有的同类接口补齐即可（官方约 30 行，复制新增用户的逻辑）。不要顺手加一串新校验、补几百行测试，和其他接口行为不一致，合并成本高。",
    "JB-9": "ERP 主表编辑误删子表：根因是提交时把列表页分页后的 subTableSource 合并进了主表数据，官方只删掉这段合并（9 行）。不要为此再查一遍完整子表重新提交、加整套并发状态。",
    "JB-10": "编辑器打不开时先看编辑器自己怎么解析内容：官方只在代码编辑器“首尾是花括号就当 JSON 解析”处加 try/catch。不要顺着“运行时出错”的现象去给所有执行 JS 增强的地方包异常。",
    "JB-12": "树表添加子记录变成主记录，根因在表单设计器 CgformModal：多个表格异步同步互相覆盖，父节点字段配置串了。不要在运行时表单 OnlineForm 里跳过父 ID 默认值来堵现象。",
    "JB-13": "选择组件取消后仍回显：官方只在弹窗打开时 cloneDeep 已选值，避免表格勾选改到外面的数组。不要重写共用的 useSelectBiz，部门、角色等选择组件都在用。",
    "JB-16": "Swagger 接口错位是 knife4j 4.6.0 与 springdoc 不兼容，官方回退到 4.5.0 并把 GlobalOpenApiCustomizer 换成 OperationCustomizer。全局文档问题先查依赖版本和全局配置，不要逐个控制器补 operationId。",
    "JB-19": "批量删除超过几百条失败，官方原因是请求参数个数超过 Undertow 上限，在 UndertowConfiguration 调大 MAX_PARAMETERS 和 MAX_HEADER_SIZE。用户在问题里“推测”的原因（大事务）要先核实，不要直接照着改服务层和代码生成模板。",
    "JB-23": "导出异常：官方在 useListPage.ts 修 indexOf('_dictText') 没和 -1 比较导致列名被错误替换。只有截图没有文字的工单，先按功能名（导出）找导出列的处理，不要猜到下载响应处理上。",
    "JB-25": "标签页关闭报错只是空数组取 [0]，官方加一个可选链 validTabList[0]?.path 就修好。报错有明确行号时先修那一行，不要把标签页定位方式整体从 path 改成 fullPath。",
    "JB-27": "JVxeTable 卡顿来自列变化时反复重建列，官方给 vxeColumns 的 watch 加了 50ms 防抖。性能问题先找反复触发的 watch/重建，不要去改单元格组件的请求缓存。",
    "JB-34": "Excel 导入图片目录：官方只是 saveUrl 不为空时用它做目录（6 行）。不要顺手改公共的 CommonUtils.uploadOnlineImage，所有上传图片都会受影响。",
    "JB-37": "表格铺满、分页沉底这类需求，官方在 useTableScroll 里按分页信息算表格高度（26 行）。BasicTable 是全局组件，不要加整套自适应高度方案（近 200 行）。",
    "JB-38": "JSelectPosition resetFields 不生效：官方只补了值为空时清空 selectValues。用户在问题里给了重写方案也不要整段照搬，先做最小修复。",
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("work", type=Path)
    ap.add_argument("--data", type=Path)
    ap.add_argument("--project", default="JB")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    work = a.work.expanduser().resolve()
    data = (a.data or work / "data").expanduser().resolve()
    root = work / "JeecgBoot"
    rows = json.loads((work / "report-data.json").read_text(encoding="utf-8"))
    notes = json.loads((work / "report-notes.json").read_text(encoding="utf-8")) if (work / "report-notes.json").exists() else {}
    have = {(l.get("ticket"), l.get("kind")) for l in learn.lessons(data, a.project, 10000)}
    cases, lessons = [], []
    for r in rows:
        sha = r.get("official")
        if not sha:
            continue
        parent = git(root, "rev-parse", sha + "^", check=False).strip()
        gold = learn._kept(root, sha, parent) if parent else []
        if not gold:
            print("%s：官方提交 %s 找不到或没有有效改动，跳过" % (r["key"], sha[:10]))
            continue
        cases.append({"ticket": r["key"], "title": r["title"], "body": r.get("body") or "", "base": parent, "gold": gold[:40],
                      "flows": [], "source": "history"})
        if r["key"] in LESSONS and (r["key"], "review") not in have:
            v = (notes.get(r["key"]) or {}).get("verdict", "")
            lessons.append({"project": a.project, "ticket": r["key"], "title": r["title"], "flows": [], "by": "对照官方修复",
                            "kind": "review", "note": "%s%s" % ("（评审：%s）" % v if v else "", LESSONS[r["key"]]), "files": gold[:10]})
    print("评测用例 %d 个，教训 %d 条%s" % (len(cases), len(lessons), "" if a.apply else "（预览，加 --apply 写入）"))
    for l in lessons:
        print(" ", l["ticket"], l["note"][:70])
    if a.apply:
        for c in cases:
            learn.add_case(data, a.project, c)
        for l in lessons:
            learn.add_lesson(data, l)
        print("已写入 %s" % data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
