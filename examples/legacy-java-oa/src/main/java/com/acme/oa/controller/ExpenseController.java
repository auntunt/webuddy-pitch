package com.acme.oa.controller;

import com.acme.oa.service.ExpenseService;
import org.springframework.web.bind.annotation.*;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

/** 费用报销 */
@RestController
@RequestMapping("/expense")
public class ExpenseController {
    private final ExpenseService expenseService;

    public ExpenseController(ExpenseService expenseService) {
        this.expenseService = expenseService;
    }

    /** 我的报销单 */
    @GetMapping("/mine")
    public List<Map<String, Object>> mine(@RequestParam String userId) {
        return expenseService.listByUser(userId);
    }

    /** 提交报销单 */
    @PostMapping("/submit")
    public long submit(@RequestParam String userId, @RequestParam long deptId, @RequestParam BigDecimal amount, @RequestParam String category) {
        return expenseService.submit(userId, deptId, amount, category);
    }

    /** 财务审核 */
    @PostMapping("/audit")
    public void audit(@RequestParam long id, @RequestParam String auditor, @RequestParam boolean pass, @RequestParam(required = false) String comment) {
        expenseService.audit(id, auditor, pass, comment);
    }

    /** 出纳付款 */
    @PostMapping("/pay")
    public void pay(@RequestParam long id, @RequestParam String cashier) {
        expenseService.pay(id, cashier);
    }
}
