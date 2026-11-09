package com.jsh.erp.verification;

import com.jsh.erp.datasource.entities.DepotHead;
import com.jsh.erp.exception.BusinessRunTimeException;
import com.jsh.erp.utils.RefundReason;
import java.math.BigDecimal;
import org.junit.Test;
import static org.junit.Assert.*;

public class RefundReasonTest {
    private DepotHead head(String reason) {
        DepotHead head = new DepotHead();
        head.setSubType("销售退货"); head.setChangeAmount(new BigDecimal("-12.50")); head.setRemark(reason);
        return head;
    }
    @Test public void invalidReasonsAreRejected() {
        for (String value : new String[]{null, "", "　 \t\n", "退货", new String(new char[201]).replace('\0','退')}) {
            try { RefundReason.validate(head(value)); fail("Accepted invalid refund reason"); }
            catch (BusinessRunTimeException error) { assertEquals(8590001, error.getCode()); }
        }
    }
    @Test public void boundariesAndUnicodeUseCharacters() {
        for (String value : new String[]{"货品损坏退款", new String(new char[200]).replace('\0','退'), "😀😀😀😀😀"}) {
            DepotHead h=head("　" + value + " \n"); RefundReason.validate(h); assertEquals(value, h.getRemark());
        }
    }
    @Test public void zeroRefundAndOtherDocumentsKeepTheirBehavior() {
        DepotHead zero=head(null); zero.setChangeAmount(BigDecimal.ZERO); RefundReason.validate(zero);
        DepotHead other=head(null); other.setSubType("采购退货"); RefundReason.validate(other);
    }
}
