package com.jsh.erp.utils;

import com.jsh.erp.datasource.entities.DepotHead;
import com.jsh.erp.exception.BusinessRunTimeException;

/** Demo policy only: cash sales returns require a traceable reason. */
public final class RefundReason {
    private RefundReason() { }

    public static void validate(DepotHead head) {
        if (!"销售退货".equals(head.getSubType()) || head.getChangeAmount() == null
                || head.getChangeAmount().signum() == 0) return;
        String reason = head.getRemark() == null ? "" : head.getRemark().replaceAll("(?U)^\\s+|\\s+$", "");
        int length = reason.codePointCount(0, reason.length());
        if (length < 5 || length > 200) {
            throw new BusinessRunTimeException(8590001, "退款说明须为5至200个字符，不能只填空白");
        }
        head.setRemark(reason);
    }
}
