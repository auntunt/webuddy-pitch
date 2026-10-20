package com.acme.oa.controller;

import com.acme.oa.service.LeaveService;
import org.springframework.web.bind.annotation.*;
import java.util.List;
import java.util.Map;

/** 请假审批 */
@RestController
@RequestMapping("/leave")
public class LeaveController {
    private final LeaveService leaveService;

    public LeaveController(LeaveService leaveService) {
        this.leaveService = leaveService;
    }

    /** 查询请假单列表 */
    @GetMapping("/list")
    public List<Map<String, Object>> list(@RequestParam(defaultValue = "1") int page) {
        return leaveService.list(page);
    }

    /** 提交请假申请 */
    @PostMapping("/submit")
    public long submit(@RequestParam String applicant, @RequestParam long deptId, @RequestParam int days, @RequestParam String reason) {
        return leaveService.submit(applicant, deptId, days, reason);
    }

    @PostMapping("/approve")
    public void approve(@RequestParam long id, @RequestParam String approver) {
        leaveService.approve(id, approver);
    }

    /** 驳回 */
    @PostMapping("/reject")
    public void reject(@RequestParam long id, @RequestParam String approver, @RequestParam String comment) {
        leaveService.reject(id, approver, comment);
    }
}
