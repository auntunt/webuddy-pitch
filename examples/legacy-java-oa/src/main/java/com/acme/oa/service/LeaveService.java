package com.acme.oa.service;

import com.acme.oa.mapper.ApprovalLogMapper;
import com.acme.oa.mapper.LeaveMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.List;
import java.util.Map;

@Service
public class LeaveService {
    private final LeaveMapper mapper;
    private final ApprovalLogMapper logMapper;

    public LeaveService(LeaveMapper mapper, ApprovalLogMapper logMapper) {
        this.mapper = mapper;
        this.logMapper = logMapper;
    }

    public List<Map<String, Object>> list(int page) {
        return mapper.selectPage((page - 1) * 20, page * 20);
    }

    /** 提交：超过 3 天需要部门经理审批，这里只校验天数范围 */
    @Transactional
    public long submit(String applicant, long deptId, int days, String reason) {
        if (days <= 0 || days > 30) {
            throw new IllegalArgumentException("请假天数必须在 1 到 30 天之间");
        }
        long id = mapper.nextId();
        mapper.insert(id, applicant, deptId, days, reason);
        logMapper.insert(id, applicant, "SUBMIT", reason);
        return id;
    }

    /** 审批通过：记录审批人与审批时间 */
    @Transactional
    public void approve(long id, String approver) {
        int n = mapper.approve(id, approver);
        if (n == 0) {
            throw new IllegalStateException("单据不是待审批状态");
        }
        logMapper.insert(id, approver, "APPROVE", null);
    }

    @Transactional
    public void reject(long id, String approver, String comment) {
        mapper.reject(id, approver);
        logMapper.insert(id, approver, "REJECT", comment);
    }

    /** 超过 30 天未审批的单据自动作废 */
    public int expireStale() {
        return mapper.expireStale();
    }
}
