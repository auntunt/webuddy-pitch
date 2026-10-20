package com.acme.oa.service;

import com.acme.oa.mapper.ApprovalLogMapper;
import com.acme.oa.mapper.BudgetMapper;
import com.acme.oa.mapper.ExpenseMapper;
import com.acme.oa.mapper.UserMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.client.RestTemplate;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

@Service
public class ExpenseService {
    private final ExpenseMapper expenseMapper;
    private final BudgetMapper budgetMapper;
    private final UserMapper userMapper;
    private final ApprovalLogMapper logMapper;
    private final RestTemplate restTemplate = new RestTemplate();

    public ExpenseService(ExpenseMapper expenseMapper, BudgetMapper budgetMapper, UserMapper userMapper, ApprovalLogMapper logMapper) {
        this.expenseMapper = expenseMapper;
        this.budgetMapper = budgetMapper;
        this.userMapper = userMapper;
        this.logMapper = logMapper;
    }

    public List<Map<String, Object>> listByUser(String userId) {
        return expenseMapper.selectByUser(userId);
    }

    /** 提交报销：单笔不超过 5 万，且部门当月预算要够 */
    @Transactional
    public long submit(String userId, long deptId, BigDecimal amount, String category) {
        Map<String, Object> user = userMapper.selectById(userId);
        if (user == null || "DISABLED".equals(user.get("STATUS"))) {
            throw new IllegalStateException("用户不存在或已停用");
        }
        if (amount.compareTo(new BigDecimal("50000")) > 0) {
            throw new IllegalArgumentException("单笔报销不能超过 5 万元");
        }
        BigDecimal left = budgetMapper.remaining(deptId);
        if (left == null || left.compareTo(amount) < 0) {
            throw new IllegalStateException("部门预算不足");
        }
        long id = expenseMapper.nextId();
        expenseMapper.insert(id, userId, deptId, amount, category);
        budgetMapper.freeze(deptId, amount);
        logMapper.insert(id, userId, "EXPENSE_SUBMIT", category);
        return id;
    }

    /** 财务审核：不通过时释放冻结的预算 */
    @Transactional
    public void audit(long id, String auditor, boolean pass, String comment) {
        Map<String, Object> e = expenseMapper.selectById(id);
        if (e == null) {
            throw new IllegalArgumentException("报销单不存在");
        }
        if (pass) {
            expenseMapper.auditPass(id, auditor);
        } else {
            expenseMapper.auditReject(id, auditor);
            budgetMapper.release((Long) e.get("DEPT_ID"), (BigDecimal) e.get("AMOUNT"));
        }
        logMapper.insert(id, auditor, pass ? "EXPENSE_PASS" : "EXPENSE_REJECT", comment);
    }

    /** 付款：调用财务系统接口，成功后扣减预算 */
    @Transactional
    public void pay(long id, String cashier) {
        Map<String, Object> e = expenseMapper.selectById(id);
        if (e == null || !"AUDITED".equals(e.get("STATUS"))) {
            throw new IllegalStateException("只有审核通过的报销单才能付款");
        }
        restTemplate.postForObject("http://fin.internal/api/pay", e, String.class);
        expenseMapper.markPaid(id, cashier);
        budgetMapper.consume((Long) e.get("DEPT_ID"), (BigDecimal) e.get("AMOUNT"));
    }
}
