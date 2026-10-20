# T001 请假列表按审批状态筛选

- 类型：新需求
- 创建：2026-10-07 14:42 · 基线提交 `5c6d0e4b0a57`
- 状态：待人工验收

## 1. 需求原文
请假列表接口 /leave/list 需要支持按审批状态（STATUS 字段，如 APPROVED、PENDING）筛选，不传时保持原行为

## 2. 要改变的行为
- [ ] `GET /leave/list` 新增可选参数 `status`（如 `APPROVED`、`PENDING`）：传入非空值时，只返回 `OA_LEAVE.STATUS` 等于该值的请假单。
- [ ] 筛选后仍按 `CREATED DESC` 排序、每页 20 条分页（分页发生在筛选之后）。

## 3. 必须保持不变的行为
- [ ] 不传 `status`（或传空串/纯空白）：SQL 无 STATUS 条件，结果与改动前完全一致。
- [ ] `GET /leave/list?page=N` 的签名、返回结构（List<Map>：ID/APPLICANT/REASON/START_DATE/DEPT_NAME）、页大小 20 不变。
- [ ] `POST /leave/approve` 与 `LeaveMapper.approve`、`deptTree` 不动。
- [ ] 基线测试 `LeaveServiceTest` 不改。

## 4. 验收标准与检查方式
| # | 验收条款 | 检查方式（自动化测试 / 命令 / 人工） | 结果 |
|---|---|---|---|
| A1 | 不传 status 时 `service.list(page)` 仍调用 mapper 的分页区间 (page-1)*20 ~ page*20 | LeaveListFilterTest（旧代码先跑通） | 通过（mvn test，LeaveListFilterTest） |
| A2 | 不传/空 status 时生成的 SQL 不含 `l.STATUS` 条件 | LeaveListFilterTest（MyBatis 动态 SQL 渲染） | 通过（mvn test，LeaveListFilterTest） |
| A3 | 传 status 时 SQL 含 `l.STATUS = ?` 且为参数绑定（非拼接） | LeaveListFilterTest | 通过（mvn test，LeaveListFilterTest） |
| A4 | 传 status 时 service 把值（去首尾空格）传给 mapper，空白视为未传 | LeaveListFilterTest | 通过（mvn test，LeaveListFilterTest） |
| A5 | 新增 SQL 片段无 Oracle 专有写法（达梦兼容） | tmh verify 的兼容检查 | 新增代码无新兼容点；tmh verify 整体“未通过”仅因 target/classes/application.yml 的既有 Oracle/Windows 配置（构建产物副本，非本次改动，属数据库改造工作项） |
| A6 | 真实库上筛选结果正确 | 需达梦/Oracle 环境，本仓库无库 → 人工验收 | 未验证（无数据库环境，需人工） |

## 5. 影响范围（用 tmh where / tmh impact 得到，附 文件:行号）
- 入口：`LeaveController.list` — src/main/java/com/acme/oa/controller/LeaveController.java:20（GET /leave/list，新增可选参数）
- 业务逻辑：`LeaveService.list` — src/main/java/com/acme/oa/service/LeaveService.java:16
- 数据表 / SQL：`LeaveMapper.selectPage`（接口 LeaveMapper.java:11；SQL LeaveMapper.xml:5-16），表 OA_LEAVE.STATUS
- 配置 / 前端：未发现前端页面调用 /leave/list（仓库内仅有 print.jsp，未引用）；无配置变更
- 其他调用方：`selectPage` 仅 LeaveService.list 调用；ReportJob、sql/proc_leave.sql 只涉及请假汇总，不经过该查询，不受影响
- 无需新增表/字段/索引 DDL（STATUS 已存在，approve 已在写入）。

## 6. 风险、未知项与需要人决定的问题（按合理默认处理，无需阻塞）
- [事实] 现有 selectPage 使用 Oracle 专有写法（ROWNUM、NVL、TO_CHAR、`(+)`），属于数据库适配工作项范围，**本次不顺带改**，避免扩大范围；新增条件只用标准 SQL（`AND l.STATUS = #{status}`），达梦下可直接运行。
- [推断] STATUS 取值至少有 PENDING、APPROVED，是否有 REJECTED 等未知。默认：**不做取值白名单**，精确匹配（区分大小写），传不存在的值返回空列表；不报错。
- [推断] 默认对 status 做 trim；空串/空白等同于未传。不转大写（达梦默认大小写敏感，与库内存储值一致）。
- [待确认] 业务方是否需要支持多值（如 `status=APPROVED,PENDING`）或不区分大小写——本次不做。
- [待确认] STATUS 列是否有索引；数据量大时建议由 DBA评估，本次不建索引。
- [待确认] 真实库验收（A6）需人工执行。

## 7. 实施计划
1. 先补“保持不变”的特征测试（characterization test），确认在旧代码上通过
2. 再按最小改动实现
3. 运行 `tmh verify`，把结果填回第 4 节

## 8. 验证记录

- 2026-10-07 特征测试 LeaveListFilterTest 的两条“保持不变”用例先在旧代码上通过；实现后 4+ 条新用例全部通过（`mvn -q -B test` 退出码 0）。
- `tmh verify`：基线测试/配置未改动 ✅；构建与测试 ✅；信创兼容检查 ❌ 4 条，均在 target/classes/application.yml（src/main/resources/application.yml 的构建副本），非本次引入。
- 未验证：A6 真实库筛选。
